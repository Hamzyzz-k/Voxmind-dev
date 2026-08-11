"""Conversion itself needs ffmpeg, which is in the Docker image but usually
not on a dev machine — so these cover the guards and the failure mode, and
the real decode is verified in the container. Asserting otherwise here would
make the suite pass or fail depending on whose laptop it ran on."""

import pytest

from app.services.audio_convert import (
    DEVICE_CHANNELS,
    DEVICE_SAMPLE_RATE,
    DEVICE_SAMPLE_WIDTH,
    AudioConversionError,
    mp3_to_device_pcm,
    pcm_duration_seconds,
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
