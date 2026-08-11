"""espeak-ng lives in the Docker image, not usually on a dev machine, so these
cover the guards and the failure mode. Real synthesis is verified in the
container — asserting on it here would make the suite pass or fail depending
on whose laptop ran it."""

import pytest

from app.services.audio_convert import DEVICE_CHANNELS, DEVICE_SAMPLE_RATE, DEVICE_SAMPLE_WIDTH
from app.services.tts_fallback import ESPEAK_VOICES, FallbackTTSError, synthesize_pcm_fallback


@pytest.mark.asyncio
@pytest.mark.parametrize("empty", ["", "   ", None])
async def test_empty_text_rejected(empty):
    with pytest.raises(FallbackTTSError):
        await synthesize_pcm_fallback(empty, "en")


@pytest.mark.asyncio
async def test_missing_binary_raises_fallback_error_not_filenotfound():
    """The caller catches FallbackTTSError. A raw FileNotFoundError leaking
    through would bypass that and surface as a 500 instead of a clean 502."""
    try:
        await synthesize_pcm_fallback("hello", "en")
    except FallbackTTSError:
        pass  # expected where espeak-ng isn't installed
    except FileNotFoundError:
        pytest.fail("FileNotFoundError leaked instead of FallbackTTSError")


def test_all_four_supported_languages_have_a_voice():
    """A missing entry would silently fall back to English and speak Kannada
    text with an English voice — confidently, and wrongly."""
    assert set(ESPEAK_VOICES) == {"en", "hi", "kn", "ta"}


def test_output_format_matches_the_primary_tts_path():
    """The device cannot tell which voice produced the bytes, so both paths
    must produce the identical format."""
    assert DEVICE_SAMPLE_RATE == 16000
    assert DEVICE_CHANNELS == 1
    assert DEVICE_SAMPLE_WIDTH == 2
