"""Spoken-command detection.

VoxMind has to *follow* some instructions rather than answer them: "make it
louder", "speak in Hindi now". These arrive as ordinary transcripts, so
something has to separate "change how the app behaves" from "answer this
question" before the transcript reaches the LLM.

Deliberately not an NLU system. Two matching strategies, chosen per script for
a reason:

* **English — exact phrase match** after stripping a small set of politeness
  fillers. Precision is the hard requirement here: substring matching turns
  *"how do I turn up the volume on my phone?"* into a volume command instead of
  a question the user actually wanted answered. Whole-utterance matching cannot
  make that mistake.

* **Hindi / Kannada / Tamil / Malayalam — token containment, capped at a short
  utterance.** These languages are agglutinative or heavily inflected, so the
  same word appears as ಕನ್ನಡ, ಕನ್ನಡದಲ್ಲಿ, தமிழ், தமிழில் … and enumerating whole
  phrases is hopeless. Matching stems by containment handles the morphology;
  the word cap supplies the precision that exact matching would have given,
  since a real question is essentially never five words long *and* built only
  from command tokens. Malayalam is Dravidian, same family as Kannada and
  Tamil, so it gets this same treatment rather than French/German's.

* **French / German — exact phrase match**, same strategy as English and for
  the same reason: neither inflects anywhere near heavily enough to need
  containment matching, so exact phrases give the same precision English gets
  without needing a word-cap safety net.

Text is NFC-normalised first, which matters more than it looks: Devanagari
nukta letters (ज़ in आवाज़, ड़ in कन्नड़) are composition-exclusion characters, so
NFC leaves them *decomposed* as base + U+093C. Both spellings therefore
normalise to the same sequence and a single nukta-less stem matches both.

English patterns are always tried, whatever the active language, because users
code-switch constantly — "volume up" mid-Kannada-sentence is entirely normal.
French and German patterns are tried unconditionally too, for the same
reason — exact-phrase matching can't false-positive on an unrelated question
the way containment matching could, so there's no precision cost to always
checking them.
"""

import re
import unicodedata

from app.models.chat import SUPPORTED_LANGS, CommandAction

# Beyond this, an utterance is a sentence rather than an instruction. Only the
# containment matchers need it; exact matching is inherently bounded.
_MAX_COMMAND_WORDS = 6

_PUNCTUATION = ".,!?;:\"'()[]{}।॥–—…"
_PUNCT_TABLE = {ord(ch): " " for ch in _PUNCTUATION}

# Stripped from either end before matching, so "please turn it up" and
# "voxmind, turn it up" reach the same phrase as "turn it up".
_LEADING_FILLERS = (
    "voxmind", "hey", "hi", "ok", "okay", "please", "now", "can you", "could you",
    "would you", "will you", "i want you to", "i need you to", "let's", "lets",
)
_TRAILING_FILLERS = ("please", "now", "for me", "thanks", "thank you", "voxmind")


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.translate(_PUNCT_TABLE)
    return re.sub(r"\s+", " ", text).strip().lower()


def _strip_fillers(text: str) -> str:
    """Repeatedly peels filler words off both ends until nothing changes."""
    previous = None
    while text and text != previous:
        previous = text
        for filler in _LEADING_FILLERS:
            if text.startswith(f"{filler} "):
                text = text[len(filler) + 1 :]
                break
        for filler in _TRAILING_FILLERS:
            if text.endswith(f" {filler}"):
                text = text[: -(len(filler) + 1)]
                break
        text = text.strip()
    return text


# --- English: exact phrases ---

_EN_VOLUME_UP = frozenset(
    {
        "volume up", "turn up the volume", "turn the volume up", "turn up volume",
        "turn it up", "turn up", "louder", "make it louder", "speak louder",
        "speak up", "say it louder", "increase the volume", "increase volume",
        "raise the volume", "raise volume", "put the volume up", "sound up",
        "more volume", "make it loud", "be louder", "talk louder",
    }
)

_EN_VOLUME_DOWN = frozenset(
    {
        "volume down", "turn down the volume", "turn the volume down",
        "turn down volume", "turn it down", "turn down", "quieter", "softer",
        "make it quieter", "make it softer", "make it quiet", "speak quieter",
        "speak softly", "speak more quietly", "say it quieter", "lower the volume",
        "lower volume", "decrease the volume", "decrease volume",
        "reduce the volume", "reduce volume", "put the volume down", "sound down",
        "less volume", "be quieter", "talk quieter",
    }
)

_EN_LANGUAGE_NAMES = {
    "english": "en",
    "hindi": "hi",
    "kannada": "kn",
    "tamil": "ta",
    "malayalam": "ml",
    "french": "fr",
    "german": "de",
}

# Bare language names ("hindi") are excluded on purpose — a one-word utterance
# is far more likely to be an answer or a topic than a switch instruction.
_EN_LANGUAGE_FRAMES = (
    "speak in {}", "speak {}", "speak to me in {}", "talk in {}", "talk {}",
    "talk to me in {}", "switch to {}", "change to {}", "change language to {}",
    "change the language to {}", "reply in {}", "answer in {}", "respond in {}",
    "say it in {}", "use {}", "in {}", "speak in {} language",
)

_EN_LANGUAGE_PHRASES: dict[str, str] = {
    frame.format(name): code
    for name, code in _EN_LANGUAGE_NAMES.items()
    for frame in _EN_LANGUAGE_FRAMES
}


# --- French / German: exact phrases, same strategy as English ---
#
# Neither language gets folded into the Indic containment system below —
# see the module docstring for why. Vocabulary here is standard, common
# phrasing rather than an exhaustive set; like the English lists above, it
# covers the phrasings someone would actually say, not every possible one.

_FR_VOLUME_UP = frozenset(
    {
        "plus fort", "monte le volume", "monte le son", "augmente le volume",
        "augmente le son", "parle plus fort", "mets plus fort", "plus de volume",
        "plus de son", "volume plus fort",
    }
)

_FR_VOLUME_DOWN = frozenset(
    {
        "moins fort", "baisse le volume", "baisse le son", "diminue le volume",
        "diminue le son", "parle plus doucement", "plus doucement",
        "mets moins fort", "moins de volume", "moins de son",
    }
)

_DE_VOLUME_UP = frozenset(
    {
        "lauter", "lauter bitte", "mach es lauter", "erhöhe die lautstärke",
        "lautstärke erhöhen", "sprich lauter", "sag es lauter", "mehr lautstärke",
    }
)

_DE_VOLUME_DOWN = frozenset(
    {
        "leiser", "leiser bitte", "mach es leiser", "verringere die lautstärke",
        "lautstärke verringern", "sprich leiser", "sag es leiser", "weniger laut",
    }
)

_FR_LANGUAGE_NAMES = {
    "anglais": "en",
    "hindi": "hi",
    "kannada": "kn",
    "tamoul": "ta",
    "malayalam": "ml",
    "français": "fr",
    "allemand": "de",
}

_DE_LANGUAGE_NAMES = {
    "englisch": "en",
    "hindi": "hi",
    "kannada": "kn",
    "tamil": "ta",
    "malayalam": "ml",
    "französisch": "fr",
    "deutsch": "de",
}

# Bare names excluded here too, for the same reason as English's frames — a
# one-word utterance is more likely an answer than an instruction.
_FR_LANGUAGE_FRAMES = (
    "parle en {}", "parle {}", "réponds en {}", "réponds-moi en {}",
    "change la langue en {}", "passe au {}", "passe en {}",
)

_DE_LANGUAGE_FRAMES = (
    "sprich {}", "sprich auf {}", "antworte auf {}", "wechsle zu {}",
    "wechsle die sprache zu {}", "auf {}",
)

_FR_LANGUAGE_PHRASES: dict[str, str] = {
    frame.format(name): code
    for name, code in _FR_LANGUAGE_NAMES.items()
    for frame in _FR_LANGUAGE_FRAMES
}

_DE_LANGUAGE_PHRASES: dict[str, str] = {
    frame.format(name): code
    for name, code in _DE_LANGUAGE_NAMES.items()
    for frame in _DE_LANGUAGE_FRAMES
}


# --- Hindi / Kannada / Tamil: stems matched by containment ---
#
# Stems are written without a trailing virama or case suffix so they survive
# inflection: "தமிழ" is inside both தமிழ் and தமிழில், where "தமிழ்" is inside
# neither of the inflected forms.

_VOLUME_NOUNS = {
    "hi": ("आवाज", "वॉल्यूम", "वॉल्युम", "ध्वनि", "साउंड"),
    "kn": ("ಧ್ವನಿ", "ಸದ್ದ", "ವಾಲ್ಯೂ", "ಶಬ್ದ", "ಸೌಂಡ"),
    "ta": ("ஒலி", "சத்த", "வால்யூ", "சவுண்ட"),
    # ശബ്ദ (shabda-) is the same root Sanskrit loanword as Hindi's आवाज/ध्वनि
    # cousin शब्द — confirmed against real usage ("ശബ്ദം കൂട്ടുക" / "കുറയ്ക്കുക",
    # the ordinary phone-settings phrasing for volume up/down).
    "ml": ("ശബ്ദ", "വോള്യூ", "സൗണ്ട്"),
}

_VOLUME_UP_WORDS = {
    "hi": ("तेज", "बढ़", "बढा", "ज्यादा", "जोर", "ऊंच", "ऊँच", "अधिक"),
    "kn": ("ಜೋರ", "ಹೆಚ್ಚ", "ಜಾಸ್ತಿ", "ಏರಿಸ"),
    "ta": ("அதிக", "கூட்ட", "ஜாஸ்தி", "பெரிசா", "உயர்த்த"),
    "ml": ("കൂട്ട", "ഉച്ചത്തി", "കൂടുത"),
}

_VOLUME_DOWN_WORDS = {
    "hi": ("कम", "धीम", "घटा", "हल्क", "छोट"),
    "kn": ("ಕಡಿಮೆ", "ಕಮ್ಮಿ", "ಸಣ್ಣ", "ನಿಧಾನ", "ಇಳಿಸ"),
    "ta": ("குறை", "கம்மி", "மெதுவா", "சிறிய"),
    "ml": ("കുറ", "ചെറിയ", "പതുക്ക"),
}

# Language names as written in each script, mapped to the code they select.
# Every dict includes an entry for its own language too (matches the existing
# hi/kn/ta convention below), which matters for "malayalam" specifically:
# hi/kn/ta previously had no way to name it since it wasn't a target yet.
_NATIVE_LANGUAGE_NAMES: dict[str, dict[str, str]] = {
    "hi": {
        "अंग्रेज": "en", "इंग्लिश": "en", "इंग्ल": "en",
        "हिंद": "hi", "हिन्द": "hi",
        "कन्नड": "kn",
        "तमिल": "ta",
        "मलयालम": "ml",
    },
    "kn": {
        "ಇಂಗ್ಲಿ": "en", "ಆಂಗ್ಲ": "en",
        "ಹಿಂದಿ": "hi",
        "ಕನ್ನಡ": "kn",
        "ತಮಿಳ": "ta",
        "ಮಲಯಾಳ": "ml",
    },
    "ta": {
        "ஆங்கில": "en", "இங்கிலீ": "en",
        "இந்தி": "hi", "ஹிந்தி": "hi",
        "கன்னட": "kn",
        "தமிழ": "ta",
        "மலையாள": "ml",
    },
    # French/German are deliberately not named here: they get the same
    # exact-phrase treatment as English rather than the containment system, so
    # switching to/from them from an Indic language goes through the
    # always-tried English layer ("switch to German") rather than needing a
    # French/German name transliterated into four more scripts.
    "ml": {
        # Both stems end one character short of the citation form's final
        # consonant (ഇംഗ്ലീഷ്, തമിഴ്, മലയാളം), matching Kannada's ಇಂಗ್ಲಿ /
        # ತಮಿಳ below for the identical reason: an oblique/locative suffix
        # ("ിൽ" in ഇംഗ്ലീഷിൽ, "ത്തിൽ" in മലയാളത്തിൽ) changes that final
        # consonant's diacritic, so the citation form is not a substring of
        # its own inflected forms. Caught by a real failing test, not a guess.
        "ഇംഗ്ലീ": "en",
        "ഹിന്ദി": "hi",
        "കന്നഡ": "kn",
        "തമിഴ": "ta",
        "മലയാള": "ml",
    },
}

_SPEAK_VERBS = {
    "hi": ("बोल", "बात", "जवाब", "उत्तर", "कहो", "बदल", "भाषा"),
    "kn": ("ಮಾತ", "ಹೇಳ", "ಉತ್ತರ", "ಬದಲ", "ಭಾಷ"),
    "ta": ("பேச", "பேசு", "சொல", "பதில", "மாற்று", "மொழி"),
    # Verified individually: സംസാര/പറ ("speak"/"say"), മാറ്റ ("change"), and
    # ഭാഷ ("language") itself as a trigger word — matching how Hindi's list
    # includes "भाषा" for the same reason: "ഭാഷ മാറ്റൂ" ("change language")
    # names no verb of speaking at all.
    "ml": ("സംസാര", "പറ", "മാറ്റ", "ഭാഷ"),
}


def _contains_any(text: str, stems: tuple[str, ...]) -> bool:
    return any(stem in text for stem in stems)


def _match_native(text: str, lang: str) -> CommandAction | None:
    """Containment matching for the Indic scripts, guarded by a word cap.

    English, French and German are excluded up front rather than relying on
    them simply having no entries below: they use exact-phrase matching
    instead (see the module docstring for why), so containment matching
    should never run for them at all.
    """
    if lang in ("en", "fr", "de") or len(text.split()) > _MAX_COMMAND_WORDS:
        return None

    names = _NATIVE_LANGUAGE_NAMES.get(lang, {})
    verbs = _SPEAK_VERBS.get(lang, ())
    if _contains_any(text, verbs):
        for name, code in names.items():
            if name in text:
                return CommandAction(action="set_language", lang=code)

    nouns = _VOLUME_NOUNS.get(lang, ())
    has_noun = _contains_any(text, nouns)
    if _contains_any(text, _VOLUME_UP_WORDS.get(lang, ())) and has_noun:
        return CommandAction(action="volume_up")
    if _contains_any(text, _VOLUME_DOWN_WORDS.get(lang, ())) and has_noun:
        return CommandAction(action="volume_down")

    return None


def detect_command(transcript: str, lang: str) -> CommandAction | None:
    """Returns the app-behaviour command this transcript is issuing, or None if
    it's an ordinary question that should go to the LLM."""
    text = _strip_fillers(_normalize(transcript))
    if not text:
        return None

    if text in _EN_VOLUME_UP or text in _FR_VOLUME_UP or text in _DE_VOLUME_UP:
        return CommandAction(action="volume_up")
    if text in _EN_VOLUME_DOWN or text in _FR_VOLUME_DOWN or text in _DE_VOLUME_DOWN:
        return CommandAction(action="volume_down")

    code = _EN_LANGUAGE_PHRASES.get(text) or _FR_LANGUAGE_PHRASES.get(text) or _DE_LANGUAGE_PHRASES.get(text)
    if code:
        return CommandAction(action="set_language", lang=code)

    return _match_native(text, lang)


# --- Confirmations ---
#
# Written locally rather than asked of the LLM: the outcome is already known, a
# fixed string can't hallucinate, and skipping the round trip makes the reply
# effectively instant.

_CONFIRMATIONS: dict[str, dict[str, str]] = {
    "volume_up": {
        "en": "Volume up.",
        "hi": "आवाज़ बढ़ा दी।",
        "kn": "ಧ್ವನಿ ಹೆಚ್ಚಿಸಿದೆ.",
        "ta": "ஒலி அதிகரித்தேன்.",
        "ml": "ശബ്ദം കൂട്ടി.",
        "fr": "Volume augmenté.",
        "de": "Lautstärke erhöht.",
    },
    "volume_down": {
        "en": "Volume down.",
        "hi": "आवाज़ कम कर दी।",
        "kn": "ಧ್ವನಿ ಕಡಿಮೆ ಮಾಡಿದೆ.",
        "ta": "ஒலி குறைத்தேன்.",
        "ml": "ശബ്ദം കുറച്ചു.",
        "fr": "Volume baissé.",
        "de": "Lautstärke verringert.",
    },
    "set_language": {
        "en": "Okay, I'll speak in English now.",
        "hi": "ठीक है, अब मैं हिंदी में बोलूँगा।",
        "kn": "ಸರಿ, ಇನ್ನು ಮುಂದೆ ಕನ್ನಡದಲ್ಲಿ ಮಾತನಾಡುತ್ತೇನೆ.",
        "ta": "சரி, இனி தமிழில் பேசுவேன்.",
        "ml": "ശരി, ഇനി ഞാൻ മലയാളത്തിൽ സംസാരിക്കും.",
        "fr": "D'accord, je vais maintenant parler en français.",
        "de": "Okay, ich spreche jetzt auf Deutsch.",
    },
}


def command_reply_lang(command: CommandAction, current_lang: str) -> str:
    """A language switch confirms itself in the language being switched *to* —
    hearing the new voice is the confirmation."""
    if command.action == "set_language" and command.lang in SUPPORTED_LANGS:
        return command.lang
    return current_lang


def command_confirmation(command: CommandAction, reply_lang: str) -> str:
    by_lang = _CONFIRMATIONS[command.action]
    return by_lang.get(reply_lang, by_lang["en"])
