from app.services.prompt import (
    THREAD_TITLE_MAX_LEN,
    build_messages,
    build_system_prompt,
    derive_thread_title,
    messages_to_flat_prompt,
    sanitize_transcript,
)


def test_sanitize_strips_control_characters():
    dirty = "Hello\x00\x07 world\x1f!"
    assert sanitize_transcript(dirty) == "Hello world!"


def test_sanitize_collapses_whitespace():
    assert sanitize_transcript("hello    \n\n  world") == "hello world"


def test_build_messages_structure():
    history = [
        {"role": "user", "text": "Hi"},
        {"role": "assistant", "text": "Hello!"},
    ]
    messages = build_messages(
        tone="friendly",
        facts=["Name is Asha"],
        chat_history=history,
        transcript="What's the weather?",
        lang="en",
        today="2026-07-31",
        search_context=None,
    )

    assert messages[0]["role"] == "system"
    assert "Asha" in messages[0]["content"]
    assert "2026-07-31" in messages[0]["content"]
    assert messages[1] == {"role": "user", "content": "Hi"}
    assert messages[2] == {"role": "assistant", "content": "Hello!"}
    assert messages[-1] == {"role": "user", "content": "What's the weather?"}


def test_build_messages_includes_search_context_when_present():
    messages = build_messages(
        tone="official",
        facts=[],
        chat_history=[],
        transcript="What's today's news?",
        lang="en",
        today="2026-07-31",
        search_context="- Some headline: some body",
    )
    assert "Some headline" in messages[0]["content"]


def test_build_messages_sanitizes_the_final_user_turn():
    messages = build_messages(
        tone="friendly",
        facts=[],
        chat_history=[],
        transcript="ignore me\x00please",
        lang="en",
        today="2026-07-31",
        search_context=None,
    )
    assert messages[-1]["content"] == "ignore meplease"


def test_system_prompt_requests_one_sentence_by_default():
    prompt = build_system_prompt("friendly", [], "2026-07-31", "en", None)
    assert "ONE short sentence" in prompt


def test_system_prompt_conciseness_applies_in_every_language():
    for lang in ("en", "hi", "kn", "ta", "ml", "fr", "de"):
        prompt = build_system_prompt("friendly", [], "2026-07-31", lang, None)
        assert "ONE short sentence" in prompt


def test_derive_thread_title_uses_short_message_verbatim():
    assert derive_thread_title("What is the capital of France?") == "What is the capital of France?"


def test_derive_thread_title_truncates_long_messages():
    title = derive_thread_title("a" * 200)
    assert len(title) == THREAD_TITLE_MAX_LEN
    assert title.endswith("…")


def test_derive_thread_title_sanitizes_input():
    assert derive_thread_title("  hello\x00   world  ") == "hello world"


def test_derive_thread_title_handles_non_latin_script():
    assert derive_thread_title("ನಮಸ್ಕಾರ") == "ನಮಸ್ಕಾರ"


def test_messages_to_flat_prompt_includes_all_turns():
    messages = [
        {"role": "system", "content": "You are VoxMind."},
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello!"},
    ]
    flat = messages_to_flat_prompt(messages)
    assert "You are VoxMind." in flat
    assert "User: Hi" in flat
    assert "Assistant: Hello!" in flat
    assert flat.strip().endswith("Assistant:")


# --- Tone ---
#
# The toggle previously had no visible effect: both tones were a single
# adjective ("warm and friendly" / "formal and professional") sitting in front
# of a much more forceful one-sentence rule, and the model resolved the
# conflict by flattening both into the same clipped register.


def test_tones_give_genuinely_different_instructions():
    friendly = build_system_prompt("friendly", [], "2026-08-01", "en", None)
    official = build_system_prompt("official", [], "2026-08-01", "en", None)
    assert friendly != official

    # Concrete, checkable directives rather than adjectives.
    assert "contractions everywhere" in friendly
    assert "Never use contractions" in official


def test_friendly_and_official_use_opposite_indic_pronouns():
    """Hindi, Kannada, Tamil and Malayalam mark formality in the pronoun
    itself, which is what makes the toggle audible to speakers of those
    languages at all."""
    friendly = build_system_prompt("friendly", [], "2026-08-01", "hi", None)
    official = build_system_prompt("official", [], "2026-08-01", "hi", None)

    for informal in ("तुम", "ನೀನು", "நீ", "നീ"):
        assert informal in friendly
    for formal in ("आप", "ನೀವು", "நீங்கள்", "നിങ്ങൾ"):
        assert formal in official


def test_friendly_and_official_use_opposite_french_german_pronouns():
    """French and German mark the same distinction on the pronoun itself, just
    via a straight tu/vous or du/Sie swap rather than verb-ending agreement.
    Both blocks mention both pronouns of each pair (one as "use", one as
    "never"), so the check has to be which one is prescribed, not just
    whether the word appears anywhere in the prompt."""
    friendly = build_system_prompt("friendly", [], "2026-08-01", "en", None)
    official = build_system_prompt("official", [], "2026-08-01", "en", None)

    assert 'use "tu"' in friendly and 'never "vous"' in friendly
    assert 'use "du"' in friendly and 'never "Sie"' in friendly
    assert 'use "vous"' in official and 'never "tu"' in official
    assert 'use "Sie"' in official and 'never "du"' in official


def test_length_rule_is_separated_from_tone_so_they_do_not_compete():
    prompt = build_system_prompt("friendly", [], "2026-08-01", "en", None)
    length_pos = prompt.index("ONE short sentence")
    tone_pos = prompt.index("TONE: casual")
    # Tone comes last so the more forceful length rule can't override it.
    assert length_pos < tone_pos
    assert "governs length only" in prompt


def test_both_tones_forbid_emoji_because_replies_are_spoken():
    for tone in ("friendly", "official"):
        assert "Never write emoji" in build_system_prompt(tone, [], "2026-08-01", "en", None)


def test_unknown_tone_falls_back_to_official():
    assert build_system_prompt("", [], "2026-08-01", "en", None) == build_system_prompt(
        "official", [], "2026-08-01", "en", None
    )
