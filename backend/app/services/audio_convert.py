"""Audio format conversion for the hardware device.

The glasses cannot decode MP3. Doing so costs CPU and RAM that are already
committed to the camera and WiFi, and ElevenLabs' raw-PCM output formats
appear to be a paid-tier feature — depending on them would build the device's
whole audio path on an assumption we cannot test while the key is revoked.

So the server converts instead: ElevenLabs returns MP3, ffmpeg decodes it to
raw 16-bit mono PCM, and the device streams those bytes straight to its I2S
amplifier with no decoding at all.

**Requires ffmpeg.** It is installed in `backend/Dockerfile` (already there for
`stt_client`'s pydub usage), so this works in production and on Render. It is
typically *not* installed on a developer's Windows machine, which means this
function raises locally rather than converting. That is why the tests below
cover the guard conditions and the failure mode rather than a real decode —
the conversion itself is only verifiable in the container.
"""

import io
import logging
import wave

from pydub import AudioSegment

logger = logging.getLogger(__name__)

# Matches the device's I2S configuration. 16kHz mono is plenty for speech and
# keeps the response small enough to buffer whole in PSRAM: a 10-second reply
# is 320KB, which the XIAO ESP32S3 Sense's 8MB holds without any streaming
# machinery.
DEVICE_SAMPLE_RATE = 16000
DEVICE_CHANNELS = 1
DEVICE_SAMPLE_WIDTH = 2  # bytes, i.e. 16-bit signed


class AudioConversionError(Exception):
    pass


def mp3_to_device_pcm(
    mp3_bytes: bytes,
    sample_rate: int = DEVICE_SAMPLE_RATE,
) -> bytes:
    """Decodes MP3 to headerless 16-bit mono PCM the device can play directly.

    Returns raw samples with no WAV header — the device already knows the
    format, and 44 bytes of header it would have to skip is 44 bytes of
    firmware complexity for nothing.
    """
    if not mp3_bytes:
        raise AudioConversionError("Empty audio")

    try:
        segment = AudioSegment.from_file(io.BytesIO(mp3_bytes), format="mp3")
        segment = (
            segment.set_frame_rate(sample_rate)
            .set_channels(DEVICE_CHANNELS)
            .set_sample_width(DEVICE_SAMPLE_WIDTH)
        )
        return segment.raw_data
    except Exception as exc:
        # Most likely cause by far is ffmpeg missing from PATH, which pydub
        # reports as a generic decode failure. Say so, because the raw message
        # sends people looking at their audio bytes instead of their PATH.
        logger.warning("MP3 to PCM conversion failed (is ffmpeg installed?): %s", exc)
        raise AudioConversionError(f"Could not convert audio for the device: {exc}") from exc


def pcm_to_wav_bytes(
    pcm_bytes: bytes,
    sample_rate: int = DEVICE_SAMPLE_RATE,
    channels: int = DEVICE_CHANNELS,
    sample_width: int = DEVICE_SAMPLE_WIDTH,
) -> bytes:
    """Wraps headerless PCM in a WAV container a browser can actually play.

    The device streams headerless PCM straight to its own I2S amplifier and
    doesn't need this. A browser `<audio>`/`Audio()` element does — it has no
    way to guess the sample rate, channel count or bit depth of raw bytes, so
    without a header the browser either refuses to play it or plays noise.

    Uses the standard library's `wave` module rather than pydub, so this has
    no ffmpeg dependency and works identically on a developer's machine and in
    the container — unlike the MP3 conversion above, which needs ffmpeg either
    way.
    """
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return buffer.getvalue()


def pcm_duration_seconds(pcm_bytes: bytes, sample_rate: int = DEVICE_SAMPLE_RATE) -> float:
    """How long the converted audio will take to play.

    Used to keep a reply from running longer than the device is willing to
    buffer, and to log something meaningful about what was sent.
    """
    bytes_per_second = sample_rate * DEVICE_CHANNELS * DEVICE_SAMPLE_WIDTH
    if bytes_per_second <= 0:
        return 0.0
    return len(pcm_bytes) / bytes_per_second
