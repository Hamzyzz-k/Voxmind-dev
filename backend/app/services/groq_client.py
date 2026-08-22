"""Groq API client: retry + exponential backoff, and a concurrency limiter so
a burst of simultaneous requests doesn't overwhelm the API. The semaphore
holds only a counter (no user data), so it doesn't violate the "no global
mutable user state" rule — it's the concurrency limiter the spec asks for."""

import asyncio
import logging

from groq import AsyncGroq
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings

logger = logging.getLogger(__name__)


class LLMProviderError(Exception):
    pass


_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(get_settings().groq_max_concurrency)
    return _semaphore


async def ask_groq(messages: list[dict]) -> str:
    settings = get_settings()
    if not settings.groq_api_key:
        raise LLMProviderError("GROQ_API_KEY is not configured")

    client = AsyncGroq(api_key=settings.groq_api_key)

    @retry(
        reraise=True,
        stop=stop_after_attempt(settings.groq_max_retries),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def _call():
        response = await client.chat.completions.create(
            model=settings.groq_model,
            messages=messages,
            temperature=0.7,
            max_tokens=1024,
            # gpt-oss models reason before answering by default ("medium"),
            # spending tokens (and latency) on a hidden chain-of-thought even
            # for a plain "hi". "low" is Groq's own setting for fast
            # general-dialogue replies, which is what a voice assistant needs.
            #
            # Passed via extra_body, not as a direct kwarg. groq==0.13.1's
            # typed client signature predates this parameter, so
            # `reasoning_effort="low"` raised `AsyncCompletions.create() got
            # an unexpected keyword argument 'reasoning_effort'` on every
            # single call — a TypeError, not an API error, so it was never
            # something a retry could fix. This broke every Groq call in
            # production silently: replies kept working because Gemini
            # covered for it on every request, until Gemini also ran out of
            # quota and both failing at once surfaced "the assistant is busy"
            # for what looked like a new problem but had been live since the
            # commit that added this parameter. extra_body forwards the field
            # straight into the JSON body, which is what the raw HTTP API
            # actually accepts regardless of what the SDK's client method has
            # a typed parameter for.
            extra_body={"reasoning_effort": "low"},
        )
        return response.choices[0].message.content

    async with _get_semaphore():
        try:
            return await _call()
        except Exception as exc:
            logger.warning("Groq call failed after retries: %s", exc)
            raise LLMProviderError(str(exc)) from exc
