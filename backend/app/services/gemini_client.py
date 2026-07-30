"""Gemini fallback — used only when Groq errors or rate-limits after retries."""

import logging

import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.services.prompt import messages_to_flat_prompt

logger = logging.getLogger(__name__)


class LLMProviderError(Exception):
    pass


async def ask_gemini(messages: list[dict]) -> str:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise LLMProviderError("GEMINI_API_KEY is not configured")

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(settings.gemini_model)
    prompt = messages_to_flat_prompt(messages)

    @retry(reraise=True, stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=8))
    async def _call():
        response = await model.generate_content_async(prompt)
        return response.text

    try:
        return await _call()
    except Exception as exc:
        logger.warning("Gemini fallback call failed after retries: %s", exc)
        raise LLMProviderError(str(exc)) from exc
