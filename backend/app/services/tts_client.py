"""Google Cloud Text-to-Speech, with retry/backoff. Raises on failure after
retries — the caller decides how to degrade (text-only response)."""

import asyncio
import logging

from google.cloud import texttospeech
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# BCP-47 locale + a WaveNet voice per supported language.
_VOICE_BY_LANG = {
    "en": ("en-IN", "en-IN-Wavenet-D"),
    "hi": ("hi-IN", "hi-IN-Wavenet-D"),
    "kn": ("kn-IN", "kn-IN-Wavenet-A"),
    "ta": ("ta-IN", "ta-IN-Wavenet-A"),
}


class TTSError(Exception):
    pass


def _synthesize_sync(text: str, lang: str) -> bytes:
    locale, voice_name = _VOICE_BY_LANG.get(lang, _VOICE_BY_LANG["en"])
    client = texttospeech.TextToSpeechClient()
    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(language_code=locale, name=voice_name)
    audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
    response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
    return response.audio_content


@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
async def synthesize_speech(text: str, lang: str) -> bytes:
    try:
        return await asyncio.wait_for(asyncio.to_thread(_synthesize_sync, text, lang), timeout=15)
    except Exception as exc:
        logger.warning("Cloud TTS synthesis failed: %s", exc)
        raise TTSError(str(exc)) from exc
