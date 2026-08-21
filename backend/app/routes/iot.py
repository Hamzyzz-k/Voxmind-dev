"""Phase 2 — IoT device layer.

Camera streaming from a wearable device. Voice (mic + speaker) lands here too
once the hardware exists; the catch-all at the bottom keeps that namespace a
clean 501 until then, same as this whole router was before this phase.

Three credential types meet in this file and are never interchangeable — see
`services/device_auth.py` for why:

- Firebase ID token + MFA (`get_mfa_verified_user`)  — the browser managing devices
- Device token (`get_device`)                        — the physical device itself
- Stream ticket (`get_stream_ticket_uid`)             — the browser polling video

And two Firestore-avoidance mechanisms that only matter together — see
`services/device_runtime.py` for the numbers that make them necessary:
in-memory token-resolution caching, and liveness/frames held entirely in
memory rather than written on every request.
"""

import logging
from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status

from app.config import get_settings
from app.deps import CurrentUser, DeviceIdentity, get_device, get_mfa_verified_user, get_stream_ticket_uid
from app.middleware.rate_limit import device_key, limiter
from app.models.chat import SUPPORTED_LANGS
from app.models.device import (
    Device,
    DeviceListResponse,
    DeviceRegisterRequest,
    DeviceRegisterResponse,
    StreamTicketResponse,
)
from app.services import device_runtime, firestore_client
from app.services.audio_convert import AudioConversionError, mp3_to_device_pcm, pcm_duration_seconds
from app.services.device_auth import STREAM_TICKET_TTL_SECONDS, generate_device_token, hash_device_token, issue_stream_ticket
from app.services.elevenlabs_client import ElevenLabsError, synthesize_speech
from app.services.gemini_client import LLMProviderError as GeminiError
from app.services.gemini_client import ask_gemini
from app.services.groq_client import LLMProviderError as GroqError
from app.services.groq_client import ask_groq
from app.services.prompt import DEFAULT_VISION_QUESTION, build_messages
from app.services.stt_client import STTError, transcribe_audio
from app.services.tts_fallback import FallbackTTSError, synthesize_pcm_fallback
from app.services.vision_client import VisionError, describe_scene

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/iot", tags=["iot"])

# Generous for real hardware — nobody wears ten pairs of glasses — while still
# bounding what one account can cost. Deliberately not 1: the simulator issues
# a fresh device per session because a device token is shown only once at
# registration and cannot be recovered afterwards, so a few accumulate
# naturally during testing.
MAX_DEVICES_PER_USER = 10


def _to_device(doc: dict) -> Device:
    return Device(
        id=doc["id"],
        name=doc["name"],
        type=doc.get("type", "glasses"),
        online=device_runtime.is_online(doc["id"]),
        last_seen_at=doc.get("lastSeenAt"),
        created_at=doc.get("createdAt"),
    )


def _require_owned_device(uid: str, device_id: str) -> dict:
    """Loads a device or 404s. The uid is part of the Firestore path, so this
    can never resolve to another user's device — same pattern as
    chat.py:_require_thread."""
    doc = firestore_client.get_device_doc(uid, device_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return doc


# --- Browser: device management (Firebase ID token + MFA) ---


@router.post("/devices", response_model=DeviceRegisterResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(get_settings().rate_limit_chat)
async def register_device(
    request: Request, body: DeviceRegisterRequest, user: CurrentUser = Depends(get_mfa_verified_user)
):
    # Registration was previously unbounded: an authenticated session could
    # create devices in a loop, and every one costs two Firestore documents
    # (the device plus its token-hash mapping) that nothing ever cleans up.
    # That went from theoretical to easy the moment the simulator put device
    # registration behind a single button.
    #
    # Two limits, because they stop different things. The rate limit slows a
    # scripted loop; the cap bounds the total a single account can ever hold,
    # which a rate limit alone does not — 10/minute still reaches thousands of
    # devices if left running.
    existing = firestore_client.list_devices(user.uid)
    if len(existing) >= MAX_DEVICES_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"You already have {MAX_DEVICES_PER_USER} devices registered. "
                "Remove one before adding another."
            ),
        )

    token = generate_device_token()
    token_hash = hash_device_token(token)
    doc = firestore_client.create_device(user.uid, body.name, body.type, token_hash)
    return DeviceRegisterResponse(
        id=doc["id"],
        name=doc["name"],
        type=doc["type"],
        token=token,
        created_at=doc.get("createdAt"),
    )


@router.get("/devices", response_model=DeviceListResponse)
async def list_devices(user: CurrentUser = Depends(get_mfa_verified_user)):
    docs = firestore_client.list_devices(user.uid)
    return DeviceListResponse(devices=[_to_device(d) for d in docs])


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_device(device_id: str, user: CurrentUser = Depends(get_mfa_verified_user)):
    doc = _require_owned_device(user.uid, device_id)
    firestore_client.delete_device(user.uid, device_id)
    # Evict immediately rather than waiting out the cache TTL — see
    # device_runtime's module docstring for the single-instance caveat this
    # relies on.
    device_runtime.cache_evict_device(doc["tokenHash"])
    device_runtime.forget_device(device_id)


# --- Browser: camera viewing ---


@router.post("/camera/{device_id}/ticket", response_model=StreamTicketResponse)
async def issue_camera_ticket(device_id: str, user: CurrentUser = Depends(get_mfa_verified_user)):
    _require_owned_device(user.uid, device_id)
    settings = get_settings()
    if not settings.stream_ticket_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Streaming is not configured on this server.",
        )
    ticket = issue_stream_ticket(user.uid, device_id, settings.stream_ticket_secret)
    return StreamTicketResponse(ticket=ticket, expires_in=STREAM_TICKET_TTL_SECONDS)


@router.get("/camera/{device_id}/frame")
@limiter.limit(get_settings().rate_limit_stream_poll)
async def get_camera_frame(request: Request, device_id: str, uid: str = Depends(get_stream_ticket_uid)):
    frame = device_runtime.get_frame(device_id)
    if frame is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No recent frame from this device")
    return Response(content=frame, media_type="image/jpeg")


# --- Device: liveness and frames (device token) ---


@router.post("/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(get_settings().rate_limit_device, key_func=device_key)
async def device_heartbeat(request: Request, device: DeviceIdentity = Depends(get_device)):
    became_online = device_runtime.mark_seen(device.device_id)
    if became_online:
        firestore_client.touch_device_last_seen(device.uid, device.device_id)


@router.post("/camera/frame", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(get_settings().rate_limit_device, key_func=device_key)
async def upload_camera_frame(request: Request, device: DeviceIdentity = Depends(get_device)):
    # Reject an oversized body before reading it into memory when the device
    # is honest enough to send Content-Length; store_frame() below is the
    # real enforcement either way.
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > device_runtime.MAX_FRAME_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Frame exceeds {device_runtime.MAX_FRAME_BYTES} bytes",
        )

    data = await request.body()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty frame body")

    try:
        device_runtime.store_frame(device.device_id, data)
    except device_runtime.FrameTooLarge as exc:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)) from exc
    except device_runtime.TooManyDevices as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    # A frame is proof of life too, so this doubles as a heartbeat — the
    # device doesn't need to send both every cycle.
    became_online = device_runtime.mark_seen(device.device_id)
    if became_online:
        firestore_client.touch_device_last_seen(device.uid, device.device_id)


# --- Device: ask about what the camera sees ---


# A reply longer than this takes too long to listen to standing on a pavement,
# and the device has to buffer all of it before playback starts.
MAX_REPLY_SECONDS = 30


def _header_safe(text: str) -> str:
    """HTTP headers are latin-1 only, so a Hindi or Tamil reply placed in one
    raw would raise on encoding. Percent-encoded instead."""
    return quote(text, safe="")


async def _answer_without_image(uid: str, question: str, lang: str, facts: list[str]) -> str:
    """Plain text question from the glasses — no photo involved.

    This repeats a little of `routes/chat.py`'s provider logic rather than
    calling into it. Extracting a shared helper would mean refactoring the
    deployed, working chat endpoint days before a submission deadline, and
    Phase 2 is meant to be purely additive. The duplication is a handful of
    lines and is worth revisiting once the hardware work has landed.
    """
    user_doc = firestore_client.get_user_doc(uid) or {}
    messages = build_messages(
        tone=user_doc.get("tone", "friendly"),
        facts=facts,
        chat_history=[],
        transcript=question,
        lang=lang,
        today=date.today().isoformat(),
        search_context=None,
    )
    try:
        return await ask_groq(messages)
    except GroqError as exc:
        logger.warning("Groq failed for device uid=%s, falling back to Gemini: %s", uid, exc)
        try:
            return await ask_gemini(messages)
        except GeminiError as exc2:
            logger.error("Both providers failed for device uid=%s: %s / %s", uid, exc, exc2)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="The assistant is busy right now. Please try again.",
            ) from exc2


def _resolve_thread(uid: str) -> str:
    """Posts device turns into the user's most recently updated thread.

    Deliberate: ask a question through the glasses and it appears in the web
    app's transcript on the same conversation, rather than the hardware and
    the website keeping two disconnected histories.
    """
    threads = firestore_client.list_threads(uid, limit=1)
    if threads:
        return threads[0]["id"]
    return firestore_client.create_thread(uid)["id"]


@router.post("/ask")
@limiter.limit(get_settings().rate_limit_device, key_func=device_key)
async def device_ask(
    request: Request,
    lang: str = Form(default="en"),
    image: UploadFile | None = File(default=None),
    audio: UploadFile | None = File(default=None),
    device: DeviceIdentity = Depends(get_device),
):
    """The glasses' main endpoint: a photo, a spoken question, or both.

    Returns raw 16-bit mono PCM at 16kHz — not MP3, not JSON — so the device
    can stream the response bytes straight to its I2S amplifier without
    decoding anything. See services/audio_convert.py for why the conversion
    happens here rather than on the device.
    """
    if lang not in SUPPORTED_LANGS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported language: {lang}")
    if image is None and audio is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Send an image, audio, or both")

    settings = get_settings()

    # 1. What did they ask? Silence is a valid gesture — pressing the button
    #    without speaking means "describe what's ahead".
    question: str | None = None
    if audio is not None:
        audio_bytes = await audio.read()
        if len(audio_bytes) > settings.max_audio_upload_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Audio file too large"
            )
        if audio_bytes:
            try:
                question = await transcribe_audio(audio_bytes, lang)
            except STTError as exc:
                # Don't fail the whole request — with a photo in hand we can
                # still describe the scene, which is the more useful half.
                logger.info("Device STT failed for uid=%s, falling back to a plain description: %s", device.uid, exc)

    if image is None and not question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Could not understand the audio, and no image was sent"
        )

    # 2. Answer it.
    facts = [f["text"] for f in firestore_client.list_profile_facts(device.uid)]

    if image is not None:
        image_bytes = await image.read()
        try:
            reply_text = await describe_scene(image_bytes, question, lang, facts)
        except VisionError as exc:
            logger.warning("Vision failed for uid=%s: %s", device.uid, exc)
            # No second vision provider exists, and staying silent would be
            # heard as "nothing is in front of you" — a very different claim
            # from "I couldn't look". Say which one it is.
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="I couldn't see just then. Please try again.",
            ) from exc
    else:
        reply_text = await _answer_without_image(device.uid, question, lang, facts)

    # 3. Record it in the user's conversation, so the website shows it too.
    thread_id = _resolve_thread(device.uid)
    firestore_client.append_chat_message(
        device.uid, thread_id, "user", question or DEFAULT_VISION_QUESTION, lang
    )
    firestore_client.append_chat_message(device.uid, thread_id, "assistant", reply_text, lang)
    firestore_client.touch_thread(device.uid, thread_id)

    # 4. Speak it. ElevenLabs first, espeak-ng if that fails, and only then an
    #    error — the device has no browser voice to fall back to, and silence
    #    reads to a blind user as "nothing is in front of you" rather than
    #    "the service broke".
    pcm: bytes | None = None
    voice_used = "elevenlabs"
    try:
        mp3 = await synthesize_speech(reply_text, lang)
        pcm = mp3_to_device_pcm(mp3)
    except (ElevenLabsError, AudioConversionError) as exc:
        logger.warning("Primary TTS failed for uid=%s, trying espeak-ng: %s", device.uid, exc)
        try:
            pcm = await synthesize_pcm_fallback(reply_text, lang)
            voice_used = "espeak"
        except FallbackTTSError as exc2:
            logger.error("Both voices failed for uid=%s: %s / %s", device.uid, exc, exc2)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Speech is unavailable right now.",
            ) from exc2

    duration = pcm_duration_seconds(pcm)
    if duration > MAX_REPLY_SECONDS:
        logger.info("Truncating a %.1fs reply to %ss for uid=%s", duration, MAX_REPLY_SECONDS, device.uid)
        pcm = pcm[: int(MAX_REPLY_SECONDS * 16000 * 2)]

    device_runtime.mark_seen(device.device_id)

    return Response(
        content=pcm,
        media_type="application/octet-stream",
        headers={
            # Debug/inspection only — the device ignores these and reads the
            # body. Percent-encoded because headers cannot carry Devanagari.
            "X-Transcript": _header_safe(question or ""),
            "X-Reply-Text": _header_safe(reply_text),
            "X-Sample-Rate": "16000",
            # Lets you tell a robotic reply apart from a bug during testing.
            "X-Voice": voice_used,
        },
    )


# --- Everything else under /iot is not implemented yet ---


@router.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def iot_not_implemented(full_path: str):
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Not implemented yet.",
    )
