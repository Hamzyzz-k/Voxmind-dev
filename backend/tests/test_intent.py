import pytest

from app.services.intent import command_confirmation, command_reply_lang, detect_command


# --- English volume ---


@pytest.mark.parametrize(
    "transcript",
    [
        "turn up the volume",
        "Turn the volume up",
        "volume up",
        "louder",
        "Make it louder!",
        "speak louder",
        "increase the volume",
        "turn it up",
        "please turn it up",
        "hey voxmind, turn up the volume please",
        "Can you make it louder?",
    ],
)
def test_detects_volume_up_english(transcript):
    command = detect_command(transcript, "en")
    assert command is not None
    assert command.action == "volume_up"


@pytest.mark.parametrize(
    "transcript",
    [
        "turn down the volume",
        "volume down",
        "quieter",
        "make it quieter",
        "lower the volume",
        "decrease the volume",
        "turn it down",
        "speak softly",
        "could you turn it down for me",
    ],
)
def test_detects_volume_down_english(transcript):
    command = detect_command(transcript, "en")
    assert command is not None
    assert command.action == "volume_down"


# --- English language switching ---


@pytest.mark.parametrize(
    ("transcript", "expected"),
    [
        ("speak in Hindi now", "hi"),
        ("speak in hindi", "hi"),
        ("switch to Kannada", "kn"),
        ("change to Tamil", "ta"),
        ("reply in English", "en"),
        ("talk to me in Kannada", "kn"),
        ("answer in tamil please", "ta"),
        ("in hindi", "hi"),
        ("use english", "en"),
    ],
)
def test_detects_language_switch_english(transcript, expected):
    command = detect_command(transcript, "en")
    assert command is not None
    assert command.action == "set_language"
    assert command.lang == expected


# --- Questions must NOT be swallowed as commands ---
#
# This is the failure mode that matters: a naive substring match turns a real
# question into a silent app-setting change, and the user never gets an answer.


@pytest.mark.parametrize(
    "transcript",
    [
        "how do I turn up the volume on my phone",
        "why is the volume so low on this laptop",
        "what is the volume of a sphere with radius five",
        "can you tell me how to increase the volume in Windows",
        "how many people speak Hindi in India",
        "translate good morning into Tamil for me",
        "what is the population of Karnataka",
        "is Kannada harder to learn than Tamil",
        "tell me a joke",
        "what's the weather today",
        "who invented the telephone",
        "explain photosynthesis in simple terms",
        "how do I switch to a different language on my keyboard",
    ],
)
def test_questions_are_not_commands(transcript):
    assert detect_command(transcript, "en") is None


def test_empty_and_punctuation_only_are_not_commands():
    assert detect_command("", "en") is None
    assert detect_command("   ", "en") is None
    assert detect_command("???", "en") is None


# --- Native scripts ---


@pytest.mark.parametrize(
    ("transcript", "lang", "expected"),
    [
        ("आवाज़ तेज़ करो", "hi", "volume_up"),
        ("आवाज कम करो", "hi", "volume_down"),
        ("ಧ್ವನಿ ಜೋರು ಮಾಡು", "kn", "volume_up"),
        ("ಧ್ವನಿ ಕಡಿಮೆ ಮಾಡು", "kn", "volume_down"),
        ("ஒலியை அதிகரி", "ta", "volume_up"),
        ("ஒலியை குறை", "ta", "volume_down"),
    ],
)
def test_detects_volume_in_native_scripts(transcript, lang, expected):
    command = detect_command(transcript, lang)
    assert command is not None
    assert command.action == expected


@pytest.mark.parametrize(
    ("transcript", "lang", "expected"),
    [
        ("हिंदी में बोलो", "hi", "hi"),
        ("अंग्रेजी में बोलो", "hi", "en"),
        ("कन्नड़ में बात करो", "hi", "kn"),
        ("ಕನ್ನಡದಲ್ಲಿ ಮಾತನಾಡು", "kn", "kn"),
        ("ಇಂಗ್ಲಿಷ್‌ನಲ್ಲಿ ಮಾತನಾಡು", "kn", "en"),
        ("தமிழில் பேசு", "ta", "ta"),
        ("ஆங்கிலத்தில் பேசு", "ta", "en"),
    ],
)
def test_detects_language_switch_in_native_scripts(transcript, lang, expected):
    command = detect_command(transcript, lang)
    assert command is not None
    assert command.action == "set_language"
    assert command.lang == expected


def test_native_matching_respects_the_word_cap():
    """Containment matching is only safe on short utterances — a full sentence
    that happens to mention volume is a question, not an instruction."""
    long_hindi_question = "मुझे बताओ कि मेरे फोन में आवाज कैसे तेज करते हैं भाई"
    assert detect_command(long_hindi_question, "hi") is None


def test_english_commands_work_while_another_language_is_active():
    """Users code-switch — "volume up" mid-Kannada-session is normal."""
    command = detect_command("volume up", "kn")
    assert command is not None
    assert command.action == "volume_up"


# --- Confirmations ---


def test_language_switch_confirms_in_the_new_language():
    command = detect_command("speak in Tamil", "en")
    assert command_reply_lang(command, "en") == "ta"
    assert command_confirmation(command, "ta") == "சரி, இனி தமிழில் பேசுவேன்."


def test_volume_confirms_in_the_current_language():
    command = detect_command("louder", "hi")
    assert command_reply_lang(command, "hi") == "hi"
    assert command_confirmation(command, "hi") == "आवाज़ बढ़ा दी।"


def test_confirmation_falls_back_to_english_for_unknown_lang():
    command = detect_command("volume up", "en")
    assert command_confirmation(command, "fr") == "Volume up."
