"""ElevenLabs Text-to-Speech — chosen over Google Cloud TTS specifically to
avoid needing a GCP billing account attached (Cloud TTS requires one even
under its free quota). No credit card is required for ElevenLabs' free tier.

Uses eleven_v3, the only ElevenLabs model with Kannada support (Multilingual
v2 and Flash v2.5 top out at 29-32 languages and don't include it) — v3 also
covers Hindi, Tamil, and English.

Raises on any failure (bad/exhausted-credit key, network error, timeout)
after a bounded retry on transient errors only — auth/quota errors are
never retried, since retrying won't fix them. The caller (routes/chat.py)
treats this as "no audio available" and the frontend automatically falls
back to the browser's own speechSynthesis voice — there is no server-side
TTS fallback by design, per the chosen approach."""

import logging

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings

logger = logging.getLogger(__name__)

_API_BASE = "https://api.elevenlabs.io/v1"


class ElevenLabsError(Exception):
    pass


class _TransientElevenLabsError(Exception):
    pass


async def _request_speech(text: str, lang: str) -> bytes:
    settings = get_settings()
    url = f"{_API_BASE}/text-to-speech/{settings.elevenlabs_voice_id}"
    headers = {"xi-api-key": settings.elevenlabs_api_key, "Content-Type": "application/json"}
    payload = {
        "text": text,
        "model_id": settings.elevenlabs_model_id,
        "language_code": lang,
    }

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(url, headers=headers, json=payload)

    if response.status_code == 200:
        return response.content

    # 401 (bad key / exhausted credits) and 4xx (bad request, e.g.
    # unsupported language) won't be fixed by retrying.
    if response.status_code >= 500:
        raise _TransientElevenLabsError(f"ElevenLabs {response.status_code}: {response.text[:200]}")
    raise ElevenLabsError(f"ElevenLabs {response.status_code}: {response.text[:200]}")


async def synthesize_speech(text: str, lang: str) -> bytes:
    settings = get_settings()
    if not settings.elevenlabs_api_key:
        raise ElevenLabsError("ELEVENLABS_API_KEY is not configured")

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(_TransientElevenLabsError),
    )
    async def _attempt() -> bytes:
        try:
            return await _request_speech(text, lang)
        except httpx.HTTPError as exc:
            raise _TransientElevenLabsError(str(exc)) from exc

    try:
        return await _attempt()
    except _TransientElevenLabsError as exc:
        logger.warning("ElevenLabs TTS failed after retries: %s", exc)
        raise ElevenLabsError(str(exc)) from exc
    except ElevenLabsError as exc:
        logger.warning("ElevenLabs TTS failed: %s", exc)
        raise
