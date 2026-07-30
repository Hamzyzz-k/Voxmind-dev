from app.services.prompt import build_messages, messages_to_flat_prompt, sanitize_transcript


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
