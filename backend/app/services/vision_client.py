"""Scene description from a camera frame — the assistive half of Phase 2.

Gemini only. Groq's Llama 3.3 70B is text-only, so unlike `/chat/ask` there is
no second provider to fall back to when this fails. That asymmetry is
deliberate rather than an oversight: a wrong description read aloud to someone
who is blind is worse than no description, so a failure here says so plainly
instead of degrading into a guess.

Uses the same model and the same `google-generativeai` package the text
fallback already uses (see `settings.gemini_model`) — it is natively
multimodal, so this needs no new dependency and no new API key.

Because there is no fallback, this path is entirely at the mercy of that one
model's free-tier quota, and that has bitten once already: the configured
model was an alias tracking Google's newest Flash release, which carried a
20-requests-per-day cap, and scene description started failing mid-demo with
429 RESOURCE_EXHAUSTED. Quota is counted per model, so the fix was to pin one
with real headroom. Worth remembering that a 429 here is indistinguishable to
the user from the camera being broken.
"""

import logging

import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.services.prompt import build_vision_prompt

logger = logging.getLogger(__name__)

# A frame from the glasses is ~15-30KB at QVGA. Anything far beyond that is a
# misconfigured camera or a bug, and sending it wastes the user's time and our
# quota on an upload that won't describe any better.
MAX_IMAGE_BYTES = 2 * 1024 * 1024


class VisionError(Exception):
    pass


async def describe_scene(
    image_bytes: bytes,
    question: str | None,
    lang: str,
    facts: list[str] | None = None,
) -> str:
    """Describes a camera frame aloud-ready, answering the user's question.

    Raises VisionError on any failure. The caller turns that into an honest
    spoken message rather than silence — a blind user who hears nothing has no
    way to tell "it failed" from "there is nothing in front of me", and those
    two mean very different things when deciding whether to step forward.
    """
    settings = get_settings()
    if not settings.gemini_api_key:
        raise VisionError("GEMINI_API_KEY is not configured")

    if not image_bytes:
        raise VisionError("Empty image")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise VisionError(f"Image is {len(image_bytes)} bytes, over the {MAX_IMAGE_BYTES}-byte limit")

    prompt = build_vision_prompt(question, lang, facts)

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(settings.gemini_model)

    @retry(reraise=True, stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=8))
    async def _call():
        response = await model.generate_content_async(
            [prompt, {"mime_type": "image/jpeg", "data": image_bytes}]
        )
        return response.text

    try:
        text = await _call()
    except Exception as exc:
        logger.warning("Gemini vision call failed after retries: %s", exc)
        raise VisionError(str(exc)) from exc

    # A safety filter or an empty candidate returns a response whose .text is
    # blank rather than raising. Passing that through would play silence to the
    # user, which reads as "nothing there" — exactly the wrong message.
    if not text or not text.strip():
        raise VisionError("Model returned an empty description")

    return text.strip()
