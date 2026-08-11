"""Conversion itself needs ffmpeg, which is in the Docker image but usually
not on a dev machine — so these cover the guards and the failure mode, and
the real decode is verified in the container. Asserting otherwise here would
make the suite pass or fail depending on whose laptop it ran on."""

import pytest

import wave
from io import BytesIO

from app.services.audio_convert import (
    DEVICE_CHANNELS,
    DEVICE_SAMPLE_RATE,
    DEVICE_SAMPLE_WIDTH,
    AudioConversionError,
    mp3_to_device_pcm,
    pcm_duration_seconds,
    pcm_to_wav_bytes,
)


def test_empty_input_rejected():
    with pytest.raises(AudioConversionError):
        mp3_to_device_pcm(b"")


def test_garbage_input_raises_conversion_error_not_a_raw_exception():
    """Callers catch AudioConversionError. A pydub/ffmpeg exception leaking
    through would bypass that and surface as a 500."""
    with pytest.raises(AudioConversionError):
        mp3_to_device_pcm(b"this is definitely not an mp3")


def test_failure_message_points_at_ffmpeg():
    """Missing ffmpeg is by far the most common cause, and pydub's own error
    doesn't say so — it sends people inspecting their audio bytes instead of
    their PATH."""
    with pytest.raises(AudioConversionError) as exc:
        mp3_to_device_pcm(b"not an mp3")
    assert "device" in str(exc.value).lower()


def test_device_format_matches_the_firmware_i2s_config():
    """These three constants and the firmware's I2S setup have to agree. If
    someone changes one, this test is the reminder to change the other."""
    assert DEVICE_SAMPLE_RATE == 16000
    assert DEVICE_CHANNELS == 1
    assert DEVICE_SAMPLE_WIDTH == 2


def test_duration_of_one_second_of_audio():
    one_second = b"\x00" * (DEVICE_SAMPLE_RATE * DEVICE_CHANNELS * DEVICE_SAMPLE_WIDTH)
    assert pcm_duration_seconds(one_second) == pytest.approx(1.0)


def test_duration_of_empty_audio_is_zero():
    assert pcm_duration_seconds(b"") == 0.0


def test_duration_scales_linearly():
    chunk = b"\x00" * 3200
    assert pcm_duration_seconds(chunk * 2) == pytest.approx(pcm_duration_seconds(chunk) * 2)


# --- pcm_to_wav_bytes ---
#
# Uses the stdlib `wave` module rather than pydub/ffmpeg, unlike the MP3 path
# above — so unlike that path, this one is fully verifiable without Docker.


def test_wav_output_is_readable_by_the_stdlib_wave_module():
    """The whole point is producing something a browser can actually play.
    If Python's own wave reader can't parse it, nothing else will either."""
    pcm = b"\x01\x02" * 100
    wav_bytes = pcm_to_wav_bytes(pcm)
    with wave.open(BytesIO(wav_bytes), "rb") as f:
        assert f.getnchannels() == DEVICE_CHANNELS
        assert f.getsampwidth() == DEVICE_SAMPLE_WIDTH
        assert f.getframerate() == DEVICE_SAMPLE_RATE
        assert f.readframes(f.getnframes()) == pcm


def test_wav_starts_with_the_riff_header():
    wav_bytes = pcm_to_wav_bytes(b"\x00\x00" * 10)
    assert wav_bytes[:4] == b"RIFF"
    assert wav_bytes[8:12] == b"WAVE"


def test_wav_is_larger_than_the_raw_pcm_by_exactly_the_header():
    """A 44-byte difference is the signal that a header was added and nothing
    else changed — no resampling, no re-encoding, no dropped samples."""
    pcm = b"\x00\x01" * 500
    wav_bytes = pcm_to_wav_bytes(pcm)
    assert len(wav_bytes) - len(pcm) == 44


def test_wav_respects_custom_format_args():
    pcm = b"\x00" * 8000
    wav_bytes = pcm_to_wav_bytes(pcm, sample_rate=8000, channels=2, sample_width=1)
    with wave.open(BytesIO(wav_bytes), "rb") as f:
        assert f.getframerate() == 8000
        assert f.getnchannels() == 2
        assert f.getsampwidth() == 1


def test_empty_pcm_still_produces_a_valid_wav():
    """A zero-length reply shouldn't crash the wrapper — it should produce a
    silent, valid file rather than raising."""
    wav_bytes = pcm_to_wav_bytes(b"")
    with wave.open(BytesIO(wav_bytes), "rb") as f:
        assert f.getnframes() == 0
