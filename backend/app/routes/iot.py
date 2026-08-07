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

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.config import get_settings
from app.deps import CurrentUser, DeviceIdentity, get_device, get_mfa_verified_user, get_stream_ticket_uid
from app.middleware.rate_limit import device_key, limiter
from app.models.device import (
    Device,
    DeviceListResponse,
    DeviceRegisterRequest,
    DeviceRegisterResponse,
    StreamTicketResponse,
)
from app.services import device_runtime, firestore_client
from app.services.device_auth import STREAM_TICKET_TTL_SECONDS, generate_device_token, hash_device_token, issue_stream_ticket

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/iot", tags=["iot"])


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
async def register_device(body: DeviceRegisterRequest, user: CurrentUser = Depends(get_mfa_verified_user)):
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


# --- Everything else under /iot is not implemented yet (voice, Phase 2b) ---


@router.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def iot_not_implemented(full_path: str):
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Not implemented yet.",
    )
