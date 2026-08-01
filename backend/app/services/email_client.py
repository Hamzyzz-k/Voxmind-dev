"""OTP email delivery.

Two transports, tried in order:

1. **Brevo HTTP API** (preferred). Render's free web services block outbound
   traffic to SMTP ports 25, 465 and 587, so SMTP simply cannot leave the
   container there — the connection times out no matter how correct the
   credentials are. The HTTP API runs over ordinary HTTPS and is unaffected.
2. **SMTP** (fallback). Still useful for local development and for any host
   that permits SMTP egress.

No dummy fallback: if neither transport is configured, the caller
(routes/auth.py) returns an honest 503 rather than pretending an email went
out.
"""

import asyncio
import logging
import smtplib
from email.message import EmailMessage

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings

logger = logging.getLogger(__name__)

BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"


class EmailDeliveryError(Exception):
    pass


class _TransientEmailError(Exception):
    pass


def _build_html(code: str, expiry_minutes: int) -> str:
    """HTML-email conventions, not web conventions: table layout, every style
    inline (a <style> block is stripped by most clients), `bgcolor` attributes
    alongside the inline colours for Outlook, web-safe fonts only, no
    JavaScript, no animation.

    Deliberately no image logo. There's no asset in the repo, and remote images
    are blocked by default in most clients — an image-based header would render
    as a broken box for the majority of recipients, which is worse than text.
    """
    return f"""\
<!DOCTYPE html>
<html lang="en">
<body style="margin:0;padding:0;background-color:#000000;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#000000" \
style="background-color:#000000;padding:32px 12px;">
  <tr>
    <td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" \
style="max-width:480px;background-color:#080808;border:1px solid #1f1f1f;border-radius:16px;">
        <tr>
          <td align="center" style="padding:32px 32px 8px 32px;">
            <span style="font-family:Segoe UI,Helvetica,Arial,sans-serif;font-size:28px;font-weight:700;\
letter-spacing:1px;color:#D856BF;">Vox</span><span style="font-family:Segoe UI,Helvetica,Arial,sans-serif;\
font-size:28px;font-weight:700;letter-spacing:1px;color:#03B3C3;">Mind</span>
          </td>
        </tr>
        <tr>
          <td align="center" style="padding:0 32px 24px 32px;font-family:Segoe UI,Helvetica,Arial,sans-serif;\
font-size:13px;line-height:20px;color:#8a8a8a;">
            Multilingual voice assistant
          </td>
        </tr>
        <tr>
          <td align="center" style="padding:0 32px 20px 32px;font-family:Segoe UI,Helvetica,Arial,sans-serif;\
font-size:16px;line-height:24px;color:#ffffff;">
            Use this code to verify your account.
          </td>
        </tr>
        <tr>
          <td align="center" style="padding:0 32px 24px 32px;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td align="center" bgcolor="#000000" style="background-color:#000000;border:1px solid #03B3C3;\
border-radius:12px;padding:18px 32px;font-family:Consolas,Courier New,monospace;font-size:36px;\
font-weight:700;letter-spacing:10px;color:#03B3C3;">
                  {code}
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td align="center" style="padding:0 32px 8px 32px;font-family:Segoe UI,Helvetica,Arial,sans-serif;\
font-size:14px;line-height:22px;color:#c4c4c4;">
            This code expires in {expiry_minutes} minutes.
          </td>
        </tr>
        <tr>
          <td align="center" style="padding:0 32px 32px 32px;font-family:Segoe UI,Helvetica,Arial,sans-serif;\
font-size:12px;line-height:20px;color:#6f6f6f;">
            Didn't request this? You can safely ignore this email.
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
</body>
</html>"""


def _build_body(code: str, expiry_minutes: int) -> tuple[str, str, str]:
    """Returns (subject, plaintext, html).

    The plaintext part is kept rather than replaced: Brevo sends both parts
    together, HTML-only mail scores worse with spam filters, and plaintext
    clients would otherwise receive markup.
    """
    subject = "Your VoxMind verification code"
    text = (
        f"Your VoxMind verification code is: {code}\n\n"
        f"This code expires in {expiry_minutes} minutes. If you didn't request this, "
        f"you can ignore this email."
    )
    return subject, text, _build_html(code, expiry_minutes)


# --- Transport 1: Brevo HTTP API ---


async def _send_via_api(to_email: str, subject: str, text: str, html: str) -> None:
    settings = get_settings()
    payload = {
        "sender": {"email": settings.smtp_from, "name": "VoxMind"},
        "to": [{"email": to_email}],
        "subject": subject,
        "textContent": text,
        "htmlContent": html,
    }
    headers = {
        "api-key": settings.brevo_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(BREVO_ENDPOINT, headers=headers, json=payload)

    if response.status_code in (200, 201, 202):
        return

    detail = response.text[:300]
    # 5xx is worth another attempt; a rejected key or unverified sender is not.
    if response.status_code >= 500:
        raise _TransientEmailError(f"Brevo API {response.status_code}: {detail}")
    raise EmailDeliveryError(f"Brevo API {response.status_code}: {detail}")


# --- Transport 2: SMTP ---


def _send_sync(to_email: str, subject: str, text: str, html: str) -> None:
    settings = get_settings()
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to_email
    # set_content then add_alternative produces multipart/alternative, with the
    # HTML last so clients that render it prefer it.
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
        server.starttls()
        server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type((_TransientEmailError, smtplib.SMTPException, OSError)),
)
async def _deliver(to_email: str, subject: str, text: str, html: str) -> str:
    settings = get_settings()

    if settings.brevo_api_configured:
        await _send_via_api(to_email, subject, text, html)
        return "brevo_api"

    if settings.smtp_configured:
        await asyncio.to_thread(_send_sync, to_email, subject, text, html)
        return "smtp"

    raise EmailDeliveryError("No email transport is configured")


async def send_otp_email(to_email: str, code: str, expiry_minutes: int) -> str:
    """Sends the code and returns which transport delivered it."""
    settings = get_settings()
    if not settings.email_configured:
        raise EmailDeliveryError("No email transport is configured")

    subject, text, html = _build_body(code, expiry_minutes)
    try:
        transport = await _deliver(to_email, subject, text, html)
    except _TransientEmailError as exc:
        raise EmailDeliveryError(str(exc)) from exc

    logger.info("OTP email sent via %s", transport)
    return transport
