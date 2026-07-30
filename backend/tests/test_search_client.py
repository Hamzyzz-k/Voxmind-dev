from app.services.search_client import is_time_sensitive


def test_english_time_sensitive_keyword_triggers():
    assert is_time_sensitive("What's the latest news on the election?", "en")
    assert is_time_sensitive("What's today's weather in Bangalore?", "en")


def test_english_non_time_sensitive_does_not_trigger():
    assert not is_time_sensitive("What is the capital of France?", "en")


def test_hindi_keyword_triggers():
    assert is_time_sensitive("आज का मौसम कैसा है?", "hi")


def test_kannada_keyword_triggers():
    assert is_time_sensitive("ಇಂದು ಹವಾಮಾನ ಹೇಗಿದೆ?", "kn")


def test_tamil_keyword_triggers():
    assert is_time_sensitive("இன்று வானிலை எப்படி இருக்கும்?", "ta")


def test_case_insensitive():
    assert is_time_sensitive("Give me the LATEST score", "en")


def test_unsupported_lang_falls_back_to_english_keywords():
    assert is_time_sensitive("today's price", "fr")
