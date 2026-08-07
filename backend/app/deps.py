"""Auth dependencies. Every protected route runs these on every request —
there is no session/cache of "who's logged in" anywhere; each call re-verifies
the Firebase ID token via the Admin SDK.
"""

import logging
from dataclasses import dataclass

from fastapi import Header, HTTPException, status
from firebase_admin import auth as firebase_auth

from app.config import get_settings
from app.services import device_runtime, firestore_client
from app.services.device_auth import (
    InvalidTicket,
    hash_device_token,
    parse_device_authorization,
    parse_ticket_authorization,
    verify_stream_ticket,
)

logger = logging.getLogger(__name__)


@dataclass
class CurrentUser:
    uid: str
    email: str | None


@dataclass
class DeviceIdentity:
    uid: str
    device_id: str


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or malformed Authorization header"
        )
    return authorization.removeprefix("Bearer ").strip()


async def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    """Verifies the Firebase ID token only. Used by the OTP endpoints, where
    the user is authenticated but hasn't completed MFA yet."""
    token = _extract_bearer_token(authorization)
    try:
        decoded = firebase_auth.verify_id_token(token)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from exc

    uid = decoded["uid"]
    email = decoded.get("email")
    try:
        firestore_client.ensure_user_doc(uid, display_name=email)
    except Exception as exc:
        # Token was valid, so this is a backend/database problem, not the
        # caller's. Surfacing it as a bare 500 makes deployments very hard to
        # debug (a missing credential looks identical to a network blip), so
        # log the cause and return something honest.
        logger.exception("Firestore unavailable while loading user %s", uid)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable right now. Please try again shortly.",
        ) from exc
    return CurrentUser(uid=uid, email=email)


async def get_mfa_verified_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    """Verifies the Firebase ID token AND that MFA was completed recently.
    Used by every route that touches profile/chat data — MFA is enforced
    here, server-side, not just gated by a frontend screen."""
    user = await get_current_user(authorization)
    settings = get_settings()
    if not firestore_client.is_mfa_recent(user.uid, settings.mfa_session_ttl_seconds):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="MFA verification required or expired. Complete email OTP verification first.",
        )
    return user


async def get_device(authorization: str | None = Header(default=None)) -> DeviceIdentity:
    """Authenticates a physical device via its own long-lived token — never a
    Firebase ID token, never a stream ticket. See services/device_auth.py for
    why these three credential types are kept deliberately non-interchangeable,
    and services/device_runtime.py for why the resolution is cached rather
    than hitting Firestore on every request.
    """
    token = parse_device_authorization(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed device Authorization header",
        )

    token_hash = hash_device_token(token)

    cached = device_runtime.cache_get_device(token_hash)
    if cached:
        return DeviceIdentity(uid=cached[0], device_id=cached[1])

    mapping = firestore_client.resolve_device_token(token_hash)
    if not mapping:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked device token")

    device_runtime.cache_put_device(token_hash, mapping["uid"], mapping["deviceId"])
    return DeviceIdentity(uid=mapping["uid"], device_id=mapping["deviceId"])


async def get_stream_ticket_uid(device_id: str, authorization: str | None = Header(default=None)) -> str:
    """Authenticates a browser polling one device's video frames, via a
    short-lived signed ticket rather than the Firebase ID token — verified
    entirely in-process, with zero Firestore reads. `device_id` is taken from
    the route's own path parameter, which FastAPI supplies here the same way
    it would to the endpoint function itself.
    """
    ticket = parse_ticket_authorization(authorization)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or malformed stream ticket")

    settings = get_settings()
    if not settings.stream_ticket_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Streaming is not configured on this server.",
        )

    try:
        uid, ticket_device_id = verify_stream_ticket(ticket, settings.stream_ticket_secret)
    except InvalidTicket as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired stream ticket"
        ) from exc

    if ticket_device_id != device_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Ticket does not grant access to this device"
        )

    return uid
