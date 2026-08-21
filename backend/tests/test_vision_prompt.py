"""The vision prompt is a safety surface, not just a formatting concern.

Everything asserted here is a property that, if it silently regressed, would
change what a blind user hears while deciding whether it is safe to step
forward. That is why these are pinned rather than left to prompt drift.
"""

import re

import pytest

from app.services.prompt import DEFAULT_VISION_QUESTION, build_vision_prompt


def flat(text: str) -> str:
    """Collapses the prompt's line wrapping.

    The assertions below are about what the prompt *instructs*, not about where
    its lines happen to break — without this, re-wrapping a paragraph would
    fail a safety test for no real reason.
    """
    return re.sub(r"\s+", " ", text)


def test_uses_the_question_that_was_asked():
    prompt = build_vision_prompt("Is there a chair nearby?", "en")
    assert "Is there a chair nearby?" in prompt


def test_falls_back_to_a_default_question_when_none_given():
    """Pressing the button without speaking is a normal gesture — it should
    still describe the scene rather than send an empty request."""
    for empty in (None, "", "   "):
        assert DEFAULT_VISION_QUESTION in build_vision_prompt(empty, "en")


def test_question_is_sanitised():
    prompt = build_vision_prompt("What\x00 is\x07 ahead?", "en")
    assert "\x00" not in prompt
    assert "\x07" not in prompt


@pytest.mark.parametrize(
    ("lang", "expected"),
    [
        ("en", "English"),
        ("hi", "Hindi"),
        ("kn", "Kannada"),
        ("ta", "Tamil"),
        ("ml", "Malayalam"),
        ("fr", "French"),
        ("de", "German"),
    ],
)
def test_responds_in_the_users_language(lang, expected):
    assert f"Respond in {expected}." in build_vision_prompt(None, lang)


def test_unknown_language_does_not_crash():
    # "fr" no longer proves this — it's a real supported language now with its
    # own name in LANG_NAMES. "es" (Spanish) is genuinely unlisted, so it's
    # what actually exercises the fallback this test is named for.
    prompt = build_vision_prompt(None, "es")
    assert "Respond in" in prompt


def test_hazards_are_ordered_first():
    """If the user only hears the opening words before moving, those words
    have to be the ones that matter."""
    prompt = flat(build_vision_prompt(None, "en"))
    assert "Say these first, before anything else" in prompt
    for hazard in ("steps", "kerbs", "vehicles"):
        assert hazard in prompt


def test_positions_are_relative_to_the_body_not_the_image():
    """"On the right of the photo" is meaningless to someone who cannot see
    the photo."""
    prompt = flat(build_vision_prompt(None, "en"))
    assert "relative to the user's own body" in prompt
    assert 'Never say "in the image"' in prompt


def test_uncertainty_must_be_admitted():
    """A head-mounted camera produces blurry frames constantly. A confident
    guess about a blurry frame is more dangerous than admitting the blur."""
    prompt = flat(build_vision_prompt(None, "en"))
    assert "cannot tell, say so plainly" in prompt
    assert "Never guess at something that matters for their safety" in prompt


def test_does_not_give_walking_directions():
    """Turn-by-turn instructions from one still image, from a model that can
    be wrong, is the failure mode most likely to physically hurt someone."""
    prompt = flat(build_vision_prompt(None, "en"))
    assert "Do not give step-by-step walking directions" in prompt


def test_reply_is_kept_short_because_it_is_spoken():
    prompt = flat(build_vision_prompt(None, "en"))
    assert "spoken aloud" in prompt


def test_profile_facts_are_included_when_present():
    """Facts change what is worth mentioning — a kerb matters far more to a
    wheelchair user than to someone walking."""
    prompt = build_vision_prompt(None, "en", facts=["Uses a wheelchair"])
    assert "Uses a wheelchair" in prompt


def test_no_facts_block_when_there_are_none():
    prompt = build_vision_prompt(None, "en", facts=[])
    assert "Known facts about this user" not in prompt
