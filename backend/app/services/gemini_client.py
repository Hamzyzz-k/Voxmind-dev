"""Gemini fallback — used only when Groq errors or rate-limits after retries."""

import logging

import google.api_core.exceptions as google_exceptions
import google.generativeai as genai
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.services.prompt import messages_to_flat_prompt

logger = logging.getLogger(__name__)

# Same list, same reasoning, as vision_client.py's _FALLBACK_MODELS — see that
# module's docstring for the three separate times pinning one Gemini model
# here got squeezed by a quota change nothing in this codebase controls.
# Duplicated rather than shared: two three-string tuples is cheap, and it
# keeps this module independent of vision_client's, matching how this
# codebase already accepts some duplication between chat.py and iot.py
# rather than force a shared helper across unrelated request paths.
_FALLBACK_MODELS = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-flash-lite-latest")

_SKIPPABLE_ERRORS = (google_exceptions.ResourceExhausted, google_exceptions.NotFound)


class LLMProviderError(Exception):
    pass


async def ask_gemini(messages: list[dict]) -> str:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise LLMProviderError("GEMINI_API_KEY is not configured")

    genai.configure(api_key=settings.gemini_api_key)
    prompt = messages_to_flat_prompt(messages)

    models_to_try = [settings.gemini_model, *(m for m in _FALLBACK_MODELS if m != settings.gemini_model)]

    # retry_if_not_exception_type: retrying a quota-exhausted or nonexistent
    # model on itself just spends real backoff seconds on a call that cannot
    # succeed. Only a genuinely transient failure gets retried in place;
    # quota/not-found errors advance to the next model immediately instead.
    @retry(
        reraise=True,
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_not_exception_type(_SKIPPABLE_ERRORS),
    )
    async def _call(model_name: str):
        model = genai.GenerativeModel(model_name)
        response = await model.generate_content_async(prompt)
        return response.text

    last_exc: Exception | None = None
    for model_name in models_to_try:
        try:
            text = await _call(model_name)
            if model_name != settings.gemini_model:
                logger.warning("Gemini fallback used %s after %s failed", model_name, settings.gemini_model)
            return text
        except _SKIPPABLE_ERRORS as exc:
            logger.warning("Gemini fallback model %s unavailable (%s), trying next", model_name, exc)
            last_exc = exc
            continue
        except Exception as exc:
            logger.warning("Gemini fallback call failed after retries: %s", exc)
            raise LLMProviderError(str(exc)) from exc

    raise LLMProviderError(str(last_exc) if last_exc else "No Gemini model available")
