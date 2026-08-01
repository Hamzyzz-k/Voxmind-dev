from app.services.email_client import _build_body


def test_build_body_returns_subject_text_and_html():
    subject, text, html = _build_body("123456", 10)
    assert subject == "Your VoxMind verification code"
    assert "123456" in text
    assert "123456" in html


def test_plaintext_part_is_kept_and_contains_no_markup():
    """HTML-only mail scores worse with spam filters and breaks plaintext
    clients, so the text part must survive the redesign."""
    _, text, _ = _build_body("654321", 5)
    assert "<" not in text
    assert "5 minutes" in text


def test_html_uses_inline_styles_only():
    """Most email clients strip <style> blocks, so a stylesheet would silently
    drop the entire design."""
    _, _, html = _build_body("111222", 10)
    assert "<style" not in html
    assert "style=" in html


def test_html_carries_the_project_palette_and_expiry():
    _, _, html = _build_body("999000", 7)
    assert "#03B3C3" in html  # cyan accent on the code itself
    assert "#D856BF" in html  # magenta accent in the wordmark
    assert "#080808" in html  # near-black card background
    assert "7 minutes" in html


def test_html_embeds_no_remote_images():
    """Remote images are blocked by default in most clients — an image-based
    header would render as a broken box for the majority of recipients."""
    _, _, html = _build_body("123123", 10)
    assert "<img" not in html
