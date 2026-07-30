"""Backend STT fallback for when the browser's Web Speech API is unsupported
or fails. Uses SpeechRecognition's keyless `recognize_google` (free, no API
key — matches the "zero budget" constraint), converting the uploaded blob to
WAV via pydub/ffmpeg first since browsers typically record webm/ogg.

Retries twice with backoff on transient failures before giving up, per spec.
Audio that's simply unintelligible (no speech detected) is not retried —
retrying the same bytes won't change the outcome.
"""

import asyncio
import io
import logging

import speech_recognition as sr
from pydub import AudioSegment
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

STT_LANG_CODES = {"en": "en-IN", "hi": "hi-IN", "kn": "kn-IN", "ta": "ta-IN"}


class STTError(Exception):
    pass


class _TransientSTTError(Exception):
    pass


def _transcribe_sync(audio_bytes: bytes, lang_code: str) -> str:
    segment = AudioSegment.from_file(io.BytesIO(audio_bytes))
    wav_io = io.BytesIO()
    segment.export(wav_io, format="wav")
    wav_io.seek(0)

    recognizer = sr.Recognizer()
    with sr.AudioFile(wav_io) as source:
        audio_data = recognizer.record(source)
    return recognizer.recognize_google(audio_data, language=lang_code)


async def transcribe_audio(audio_bytes: bytes, lang: str) -> str:
    lang_code = STT_LANG_CODES.get(lang, "en-IN")

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),  # 1 initial attempt + 2 retries
        wait=wait_exponential(multiplier=1, min=1, max=6),
        retry=retry_if_exception_type(_TransientSTTError),
    )
    async def _attempt() -> str:
        try:
            return await asyncio.wait_for(asyncio.to_thread(_transcribe_sync, audio_bytes, lang_code), timeout=20)
        except sr.UnknownValueError as exc:
            raise STTError("Could not understand the audio. Please try again.") from exc
        except Exception as exc:
            raise _TransientSTTError(str(exc)) from exc

    try:
        return await _attempt()
    except _TransientSTTError as exc:
        logger.warning("STT fallback failed after retries: %s", exc)
        raise STTError("Speech recognition is unavailable right now. Please try again.") from exc
