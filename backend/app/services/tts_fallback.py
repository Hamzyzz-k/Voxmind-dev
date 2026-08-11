"""Last-resort speech synthesis, so the glasses are never silent.

The website can fall back to the browser's own `speechSynthesis` when
ElevenLabs fails. A pair of glasses has no browser, so without this the device
simply says nothing — and for a blind user, silence is not a degraded
experience. They cannot tell "the service broke" apart from "there is nothing
in front of you", and those two mean very different things when deciding
whether to step forward.

espeak-ng is deliberately chosen for what it *cannot* do rather than what it
can. It has no API key to revoke, no quota to exhaust, no account to expire,
and no network call to fail. It runs entirely inside our own container. The
voice is obviously robotic, and that is an acceptable trade: a robot voice
that always works beats a natural voice that sometimes doesn't.

Order of preference is ElevenLabs first, this second, an honest error third.

**Requires the `espeak-ng` package**, installed in `backend/Dockerfile`. It is
typically absent on a developer machine, so this raises locally rather than
speaking. The tests below cover the guards and the failure mode; the actual
synthesis is only verifiable in the container.
"""

import asyncio
import io
import logging

from pydub import AudioSegment

from app.services.audio_convert import DEVICE_CHANNELS, DEVICE_SAMPLE_RATE, DEVICE_SAMPLE_WIDTH

logger = logging.getLogger(__name__)

# espeak-ng's own language codes happen to match ours for all four, but they
# are mapped explicitly rather than passed through — they are two separate
# namespaces that agree by coincidence, and a silent mismatch would produce
# confident speech in the wrong language.
ESPEAK_VOICES = {"en": "en", "hi": "hi", "kn": "kn", "ta": "ta"}

# Slightly slower than espeak's default 175. Synthetic speech is harder to
# follow than a real voice, more so in a second language and outdoors.
ESPEAK_WORDS_PER_MINUTE = 150

_TIMEOUT_SECONDS = 15


class FallbackTTSError(Exception):
    pass


async def synthesize_pcm_fallback(text: str, lang: str) -> bytes:
    """Speaks `text` and returns raw 16-bit mono PCM at the device's rate.

    Returns the same format as `audio_convert.mp3_to_device_pcm`, so the
    caller can use either interchangeably and the firmware never has to know
    which voice it is hearing.
    """
    if not text or not text.strip():
        raise FallbackTTSError("Nothing to speak")

    voice = ESPEAK_VOICES.get(lang, "en")

    try:
        # create_subprocess_exec, never a shell. `text` is model output and
        # could contain anything at all; passing it as an argv element means
        # quoting, semicolons and backticks are inert rather than interpreted.
        proc = await asyncio.create_subprocess_exec(
            "espeak-ng",
            "-v",
            voice,
            "-s",
            str(ESPEAK_WORDS_PER_MINUTE),
            "--stdout",
            text,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        wav_bytes, stderr = await asyncio.wait_for(proc.communicate(), timeout=_TIMEOUT_SECONDS)
    except FileNotFoundError as exc:
        raise FallbackTTSError("espeak-ng is not installed on this machine") from exc
    except asyncio.TimeoutError as exc:
        raise FallbackTTSError("espeak-ng timed out") from exc
    except Exception as exc:
        raise FallbackTTSError(f"espeak-ng failed to start: {exc}") from exc

    if proc.returncode != 0 or not wav_bytes:
        detail = stderr.decode(errors="replace")[:200] if stderr else "no output"
        raise FallbackTTSError(f"espeak-ng exited {proc.returncode}: {detail}")

    try:
        # WAV is decoded by pydub without ffmpeg, unlike the MP3 path in
        # audio_convert — so this fallback still works on a host where ffmpeg
        # is missing, which is exactly the situation a fallback exists for.
        segment = AudioSegment.from_file(io.BytesIO(wav_bytes), format="wav")
        segment = (
            segment.set_frame_rate(DEVICE_SAMPLE_RATE)
            .set_channels(DEVICE_CHANNELS)
            .set_sample_width(DEVICE_SAMPLE_WIDTH)
        )
        return segment.raw_data
    except Exception as exc:
        raise FallbackTTSError(f"Could not convert espeak-ng output: {exc}") from exc
