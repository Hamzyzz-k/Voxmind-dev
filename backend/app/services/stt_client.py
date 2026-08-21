"""Speech-to-text, used by two callers with very different stakes.

The browser has its own Web Speech API and only lands here when that is
unsupported or fails. The glasses have no such thing: this is the only way a
spoken question ever becomes text, so a failure here does not degrade the
device's answer, it changes the question. When transcription fails,
`/iot/ask` falls back to describing the scene generically — so a silently
failing transcriber does not look broken, it looks like the assistant ignored
what you asked. That is exactly how it presented in testing: every question,
whatever was said, came back as a plain description of the view.

Two providers, in this order:

1. Groq Whisper (`whisper-large-v3-turbo`). Reuses GROQ_API_KEY, needs no new
   account, and accepts browser-recorded webm/opus directly — so the audio
   goes up exactly as recorded, with no ffmpeg transcode in the request path.
2. SpeechRecognition's keyless `recognize_google`, kept as a backstop. This
   was the only provider originally, on zero-budget grounds. It is an
   undocumented endpoint with no availability guarantee and is unreliable from
   datacenter IP ranges — which is the likely reason device transcription was
   failing in production while working locally. It needs a WAV, so this path
   still transcodes via pydub/ffmpeg.
"""

import asyncio
import io
import logging

import speech_recognition as sr
from groq import AsyncGroq
from pydub import AudioSegment
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings

logger = logging.getLogger(__name__)

# recognize_google wants a full locale; Whisper wants a bare ISO-639-1 code.
STT_LANG_CODES = {"en": "en-IN", "hi": "hi-IN", "kn": "kn-IN", "ta": "ta-IN"}

STT_MODEL = "whisper-large-v3-turbo"


class STTError(Exception):
    pass


class _TransientSTTError(Exception):
    pass


async def _transcribe_groq(audio_bytes: bytes, lang: str, filename: str) -> str:
    settings = get_settings()
    if not settings.groq_api_key:
        raise _TransientSTTError("GROQ_API_KEY is not configured")

    client = AsyncGroq(api_key=settings.groq_api_key)
    # The filename is not cosmetic: the API infers the container format from
    # its extension, so stripping it makes a perfectly valid recording
    # undecodable.
    response = await client.audio.transcriptions.create(
        file=(filename, audio_bytes),
        model=STT_MODEL,
        language=lang if lang in STT_LANG_CODES else "en",
    )
    return (response.text or "").strip()


def _transcribe_google_sync(audio_bytes: bytes, lang_code: str) -> str:
    segment = AudioSegment.from_file(io.BytesIO(audio_bytes))
    wav_io = io.BytesIO()
    segment.export(wav_io, format="wav")
    wav_io.seek(0)

    recognizer = sr.Recognizer()
    with sr.AudioFile(wav_io) as source:
        audio_data = recognizer.record(source)
    return recognizer.recognize_google(audio_data, language=lang_code)


async def _transcribe_google(audio_bytes: bytes, lang: str) -> str:
    lang_code = STT_LANG_CODES.get(lang, "en-IN")

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),  # 1 initial attempt + 2 retries
        wait=wait_exponential(multiplier=1, min=1, max=6),
        retry=retry_if_exception_type(_TransientSTTError),
    )
    async def _attempt() -> str:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(_transcribe_google_sync, audio_bytes, lang_code), timeout=20
            )
        except sr.UnknownValueError as exc:
            # Genuinely unintelligible audio. Not retried — the same bytes will
            # not decode differently on a second attempt.
            raise STTError("Could not understand the audio. Please try again.") from exc
        except Exception as exc:
            raise _TransientSTTError(str(exc)) from exc

    return await _attempt()


async def transcribe_audio(audio_bytes: bytes, lang: str, filename: str = "audio.webm") -> str:
    """Transcribes recorded speech, or raises STTError.

    `filename` only needs to carry a truthful extension; the bytes are what
    matter. It defaults to webm because that is what MediaRecorder produces in
    every browser this app supports.
    """
    if not audio_bytes:
        raise STTError("No audio to transcribe.")

    try:
        text = await _transcribe_groq(audio_bytes, lang, filename)
        if text:
            return text
        # A successful call returning nothing means silence or noise, not a
        # provider problem. Falling through to the backstop would just spend
        # another few seconds to reach the same conclusion.
        raise STTError("Could not understand the audio. Please try again.")
    except STTError:
        raise
    except Exception as exc:
        logger.warning("Groq STT failed, falling back to recognize_google: %s", exc)

    try:
        return await _transcribe_google(audio_bytes, lang)
    except STTError:
        raise
    except _TransientSTTError as exc:
        logger.warning("STT fallback failed after retries: %s", exc)
        raise STTError("Speech recognition is unavailable right now. Please try again.") from exc
