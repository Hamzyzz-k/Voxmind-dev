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
        ("ശബ്ദം കൂട്ടുക", "ml", "volume_up"),
        ("ശബ്ദം കുറയ്ക്കുക", "ml", "volume_down"),
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
        ("मलयालम में बोलो", "hi", "ml"),
        ("ಕನ್ನಡದಲ್ಲಿ ಮಾತನಾಡು", "kn", "kn"),
        ("ಇಂಗ್ಲಿಷ್‌ನಲ್ಲಿ ಮಾತನಾಡು", "kn", "en"),
        ("ಮಲಯಾಳಂನಲ್ಲಿ ಮಾತನಾಡು", "kn", "ml"),
        ("தமிழில் பேசு", "ta", "ta"),
        ("ஆங்கிலத்தில் பேசு", "ta", "en"),
        ("மலையாளத்தில் பேசு", "ta", "ml"),
        ("മലയാളത്തിൽ സംസാരിക്കൂ", "ml", "ml"),
        ("ഇംഗ്ലീഷിൽ പറയൂ", "ml", "en"),
        ("ഹിന്ദിയിൽ മാറ്റൂ", "ml", "hi"),
    ],
)
def test_detects_language_switch_in_native_scripts(transcript, lang, expected):
    command = detect_command(transcript, lang)
    assert command is not None
    assert command.action == "set_language"
    assert command.lang == expected


# --- French / German: exact phrase, same shape as English ---


@pytest.mark.parametrize(
    ("transcript", "lang", "expected"),
    [
        ("plus fort", "fr", "volume_up"),
        ("monte le volume", "fr", "volume_up"),
        ("moins fort", "fr", "volume_down"),
        ("baisse le volume", "fr", "volume_down"),
        ("lauter", "de", "volume_up"),
        ("mach es lauter", "de", "volume_up"),
        ("leiser", "de", "volume_down"),
        ("mach es leiser", "de", "volume_down"),
    ],
)
def test_detects_volume_french_german(transcript, lang, expected):
    command = detect_command(transcript, lang)
    assert command is not None
    assert command.action == expected


@pytest.mark.parametrize(
    ("transcript", "lang", "expected"),
    [
        ("parle en anglais", "fr", "en"),
        ("parle allemand", "fr", "de"),
        ("réponds en hindi", "fr", "hi"),
        ("passe au malayalam", "fr", "ml"),
        ("sprich englisch", "de", "en"),
        ("sprich französisch", "de", "fr"),
        ("wechsle zu hindi", "de", "hi"),
        ("antworte auf malayalam", "de", "ml"),
    ],
)
def test_detects_language_switch_french_german(transcript, lang, expected):
    command = detect_command(transcript, lang)
    assert command is not None
    assert command.action == "set_language"
    assert command.lang == expected


@pytest.mark.parametrize(
    "transcript",
    [
        # A real question containing the trigger word/frame shape shouldn't be
        # swallowed — same failure mode the English suite guards against.
        "combien coûte le volume trois de cette encyclopédie",
        "wie laut darf ein konzert eigentlich sein",
    ],
)
def test_questions_are_not_commands_french_german(transcript):
    lang = "fr" if "combien" in transcript else "de"
    assert detect_command(transcript, lang) is None


def test_native_matching_respects_the_word_cap():
    """Containment matching is only safe on short utterances — a full sentence
    that happens to mention volume is a question, not an instruction."""
    long_hindi_question = "मुझे बताओ कि मेरे फोन में आवाज कैसे तेज करते हैं भाई"
    assert detect_command(long_hindi_question, "hi") is None


def test_malayalam_matching_respects_the_word_cap():
    long_malayalam_question = "എന്റെ ഫോണിൽ ശബ്ദം എങ്ങനെ കൂട്ടാം എന്ന് ഒന്ന് പറഞ്ഞുതരാമോ സുഹൃത്തേ"
    assert detect_command(long_malayalam_question, "ml") is None


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
    # "fr" no longer proves this — it's a real supported language now with its
    # own confirmation string. "es" (Spanish) is genuinely unsupported, so it's
    # what actually exercises the fallback this test is named for.
    command = detect_command("volume up", "en")
    assert command_confirmation(command, "es") == "Volume up."


def test_language_switch_confirms_in_malayalam():
    # A Hindi utterance asking to switch to Malayalam, mirroring
    # test_language_switch_confirms_in_the_new_language's English-asking-for-
    # Tamil shape — not a Malayalam-script transcript under lang="hi", which
    # would test nothing real since _match_native keys off the *active*
    # language, not the script of what was said.
    command = detect_command("मलयालम में बोलो", "hi")
    assert command_reply_lang(command, "hi") == "ml"
    assert command_confirmation(command, "ml") == "ശരി, ഇനി ഞാൻ മലയാളത്തിൽ സംസാരിക്കും."


def test_language_switch_confirms_in_french():
    command = detect_command("parle en français", "en")
    assert command_reply_lang(command, "en") == "fr"
    assert command_confirmation(command, "fr") == "D'accord, je vais maintenant parler en français."


def test_language_switch_confirms_in_german():
    command = detect_command("sprich deutsch", "en")
    assert command_reply_lang(command, "en") == "de"
    assert command_confirmation(command, "de") == "Okay, ich spreche jetzt auf Deutsch."


def test_volume_confirms_in_french_and_german():
    fr_command = detect_command("plus fort", "fr")
    assert command_confirmation(fr_command, "fr") == "Volume augmenté."

    de_command = detect_command("leiser", "de")
    assert command_confirmation(de_command, "de") == "Lautstärke verringert."
