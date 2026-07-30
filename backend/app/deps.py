"""Auth dependencies. Every protected route runs these on every request —
there is no session/cache of "who's logged in" anywhere; each call re-verifies
the Firebase ID token via the Admin SDK.
"""

from dataclasses import dataclass

from fastapi import Header, HTTPException, status
from firebase_admin import auth as firebase_auth

from app.config import get_settings
from app.services import firestore_client


@dataclass
class CurrentUser:
    uid: str
    email: str | None


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
    firestore_client.ensure_user_doc(uid, display_name=email)
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
