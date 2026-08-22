"""Scene description from a camera frame — the assistive half of Phase 2.

Gemini only. Groq's chat model is text-only, so unlike `/chat/ask` there is
no separate *provider* to fall back to when this fails. That asymmetry is
deliberate rather than an oversight: a wrong description read aloud to someone
who is blind is worse than no description, so a failure here says so plainly
instead of degrading into a guess.

Uses the same `google-generativeai` package the text fallback already uses —
Gemini's Flash models are natively multimodal, so this needs no new
dependency and no new API key.

What this *does* fall back across is models, and that took getting bitten
three separate times to justify:

1. `gemini-2.5-flash`, pinned, started returning 404 — deprecated, but still
   listed by list_models(), so nothing looked wrong until a real call needed it.
2. `gemini-flash-latest`, an alias meant to dodge #1 by always tracking
   Google's current model, instead drifted onto whichever Flash release was
   newest — and the newest release consistently carries the *smallest*
   free-tier quota, so it 429'd at 20 requests/day.
3. `gemini-3.5-flash`, pinned specifically for its quota after verifying it
   empirically, ALSO hit a 20/day wall within the same day real testing and
   real usage both leaned on it — the same failure as #2, just without even
   the excuse of chasing "latest".

The pattern across all three: whichever *non-lite* Flash model this points
at eventually gets squeezed, on a timeline nothing here controls. Pinning a
single "best" model just picks which one runs out first. So this tries an
ordered list of models instead of one — cheap insurance, since quota is
tracked per model name (the 429 body literally names it as part of the
metric), meaning models with different names almost certainly draw from
separate buckets. `-lite` variants specifically, which have consistently had
more headroom than their non-lite counterparts every time this has been
checked.
"""

import logging

import google.api_core.exceptions as google_exceptions
import google.generativeai as genai
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.services.prompt import build_vision_prompt

logger = logging.getLogger(__name__)

# A frame from the glasses is ~15-30KB at QVGA. Anything far beyond that is a
# misconfigured camera or a bug, and sending it wastes the user's time and our
# quota on an upload that won't describe any better.
MAX_IMAGE_BYTES = 2 * 1024 * 1024

# Tried in order. `settings.gemini_model` leads because it's the one thing an
# operator can override without a code change; the rest are a fixed insurance
# list. All confirmed working against the real account at time of writing —
# re-verify with a real image before adding or trusting a new one, the same
# way the three failures above were each found by testing, not by reading
# Google's published numbers (which have disagreed with reality every time).
_FALLBACK_MODELS = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-flash-lite-latest")

# Errors worth trying the next model for: quota exhaustion (429) and a model
# that no longer exists (404) — the two failure modes actually seen in
# production. Anything else (a genuine network error, a malformed request) is
# not fixed by trying a different model name, so it propagates immediately
# rather than burning through the whole list for no reason.
_SKIPPABLE_ERRORS = (google_exceptions.ResourceExhausted, google_exceptions.NotFound)


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

    models_to_try = [settings.gemini_model, *(m for m in _FALLBACK_MODELS if m != settings.gemini_model)]

    # retry_if_not_exception_type deliberately excludes the two errors the
    # outer loop handles below (quota exhaustion, model not found): retrying
    # either on the *same* model wastes several real seconds of exponential
    # backoff on a call that cannot succeed no matter how many times it's
    # repeated, before ever reaching a model that actually has quota. Only
    # genuinely transient failures (a network blip, a 500) get retried here.
    @retry(
        reraise=True,
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_not_exception_type(_SKIPPABLE_ERRORS),
    )
    async def _call(model_name: str):
        model = genai.GenerativeModel(model_name)
        response = await model.generate_content_async(
            [prompt, {"mime_type": "image/jpeg", "data": image_bytes}]
        )
        return response.text

    text = None
    last_exc: Exception | None = None
    for model_name in models_to_try:
        try:
            text = await _call(model_name)
            if model_name != settings.gemini_model:
                logger.warning("Vision fell back to %s after %s failed", model_name, settings.gemini_model)
            break
        except _SKIPPABLE_ERRORS as exc:
            logger.warning("Vision model %s unavailable (%s), trying next", model_name, exc)
            last_exc = exc
            continue
        except Exception as exc:
            logger.warning("Gemini vision call failed after retries: %s", exc)
            raise VisionError(str(exc)) from exc

    if text is None:
        raise VisionError(str(last_exc) if last_exc else "No vision model available")

    # A safety filter or an empty candidate returns a response whose .text is
    # blank rather than raising. Passing that through would play silence to the
    # user, which reads as "nothing there" — exactly the wrong message.
    if not text.strip():
        raise VisionError("Model returned an empty description")

    return text.strip()
