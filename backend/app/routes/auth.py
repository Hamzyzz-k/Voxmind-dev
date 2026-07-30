import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.config import get_settings
from app.deps import CurrentUser, get_current_user
from app.middleware.rate_limit import limiter
from app.models.auth import OtpRequestResponse, OtpVerifyRequest, OtpVerifyResponse
from app.services import firestore_client
from app.services.email_client import send_otp_email
from app.services.otp import generate_otp, hash_otp, verify_otp

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/otp/request", response_model=OtpRequestResponse)
@limiter.limit(get_settings().rate_limit_otp)
async def request_otp(request: Request, user: CurrentUser = Depends(get_current_user)):
    settings = get_settings()

    if not settings.smtp_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email delivery is not configured yet. See ACCOUNT_SETUP.md to add SMTP credentials.",
        )
    if not user.email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account has no email on file")

    existing = firestore_client.get_otp_challenge(user.uid)
    if existing and existing.get("requestedAt"):
        requested_at = existing["requestedAt"]
        if requested_at.tzinfo is None:
            requested_at = requested_at.replace(tzinfo=timezone.utc)
        cooldown_until = requested_at + timedelta(seconds=settings.otp_resend_cooldown_seconds)
        if datetime.now(timezone.utc) < cooldown_until:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Please wait before requesting another code.",
            )

    code = generate_otp()
    code_hash = hash_otp(code)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.otp_expiry_seconds)
    firestore_client.set_otp_challenge(user.uid, code_hash, expires_at)

    try:
        await send_otp_email(user.email, code, settings.otp_expiry_seconds // 60)
    except Exception as exc:
        logger.error("OTP email delivery failed for uid=%s: %s", user.uid, exc)
        firestore_client.clear_otp_challenge(user.uid)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not send verification email. Please try again shortly.",
        ) from exc

    return OtpRequestResponse(message="Verification code sent.", expires_in_seconds=settings.otp_expiry_seconds)


@router.post("/otp/verify", response_model=OtpVerifyResponse)
@limiter.limit(get_settings().rate_limit_otp)
async def verify_otp_code(request: Request, body: OtpVerifyRequest, user: CurrentUser = Depends(get_current_user)):
    settings = get_settings()
    challenge = firestore_client.get_otp_challenge(user.uid)

    if not challenge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No pending verification. Request a new code."
        )

    if challenge.get("attempts", 0) >= settings.otp_max_attempts:
        firestore_client.clear_otp_challenge(user.uid)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many incorrect attempts. Request a new code.",
        )

    expires_at = challenge["expiresAt"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        firestore_client.clear_otp_challenge(user.uid)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Code expired. Request a new one.")

    if not verify_otp(body.code, challenge["codeHash"]):
        firestore_client.increment_otp_attempts(user.uid)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect code.")

    firestore_client.clear_otp_challenge(user.uid)
    verified_at = firestore_client.set_mfa_verified(user.uid)

    return OtpVerifyResponse(message="Verification successful.", mfa_verified_at=verified_at)
