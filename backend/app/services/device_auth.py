"""Device credentials and stream tickets — pure logic, no I/O, easy to unit test.

Two different credentials live here, for two different callers:

**Device tokens** authenticate the glasses. Long-lived, issued once, hashed at rest.

**Stream tickets** authenticate a browser polling video frames. Short-lived, signed,
and verified entirely in-process.

---

Why device tokens are hashed *without* a salt, unlike `services/otp.py`:

`otp.hash_otp()` generates a fresh random salt per call, so hashing the same code twice
gives different output. That is correct for OTP, where the stored hash is fetched *by
uid* and then compared. Device auth needs the opposite direction — given a token, find
which user owns it — which requires the hash to be deterministic so it can be a document
key.

Dropping the salt is safe *specifically because* a device token is 32 bytes of CSPRNG
output. Salting protects low-entropy secrets (passwords, six-digit codes) against
precomputed rainbow tables. A 256-bit random token has no rainbow table and cannot be
brute-forced, so the salt buys nothing while costing the ability to look the token up.

The discipline is unchanged from the OTP flow: the plaintext is never stored, and
comparisons use `hmac.compare_digest`.

---

Why stream tickets exist at all:

`get_mfa_verified_user` performs two Firestore reads per request. A browser polling video
frames at 3fps through that path would cost ~518,000 reads/day against a 50,000/day free
tier — exhausting the quota in under two minutes and taking the *entire* app down with
it, chat included.

So the browser authenticates once to obtain a short-lived signed ticket, then polls
frames using it. Ticket verification is an HMAC comparison with no database access at
all.

An `<img>` tag cannot send an Authorization header, and putting a credential in a query
string leaks it into browser history, server logs and Referer headers. So the ticket is
sent as a header by `fetch()`, and the frame is rendered from a blob.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time

# 32 bytes of entropy, URL-safe so it survives being typed into a captive portal.
_TOKEN_BYTES = 32

# Long enough that a browser refreshing every ~45s always holds a valid one, short
# enough that a leaked ticket is worthless almost immediately.
STREAM_TICKET_TTL_SECONDS = 60


class InvalidTicket(Exception):
    """Ticket was malformed, tampered with, or expired."""


# --- Device tokens ---


def generate_device_token() -> str:
    """A fresh device credential. Returned to the user exactly once, at
    registration, and never recoverable afterwards."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_device_token(token: str) -> str:
    """Deterministic, so it can be used as a Firestore document key. See the
    module docstring for why this is unsalted and why that is safe here."""
    return hashlib.sha256(token.encode()).hexdigest()


def tokens_match(token: str, stored_hash: str) -> bool:
    """Constant-time comparison, so a timing side channel can't be used to
    recover a token byte by byte."""
    return hmac.compare_digest(hash_device_token(token), stored_hash)


def parse_device_authorization(authorization: str | None) -> str | None:
    """Extracts the token from `Authorization: Device <token>`.

    Returns None rather than raising — the caller turns that into a 401, and
    keeping this function total makes it trivial to test.
    """
    if not authorization:
        return None
    prefix = "Device "
    if not authorization.startswith(prefix):
        return None
    token = authorization[len(prefix) :].strip()
    return token or None


# --- Stream tickets ---


def _sign(payload_b64: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64decode(value: str) -> bytes:
    # urlsafe_b64decode is strict about padding; restore whatever was stripped.
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def issue_stream_ticket(uid: str, device_id: str, secret: str, now: float | None = None) -> str:
    """Signs a short-lived grant to read one device's frames.

    `now` is injectable purely so expiry can be tested without sleeping.
    """
    issued_at = time.time() if now is None else now
    payload = {"uid": uid, "did": device_id, "exp": issued_at + STREAM_TICKET_TTL_SECONDS}
    payload_b64 = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    return f"{payload_b64}.{_sign(payload_b64, secret)}"


def verify_stream_ticket(ticket: str, secret: str, now: float | None = None) -> tuple[str, str]:
    """Returns (uid, device_id), or raises InvalidTicket.

    The signature is checked *before* the payload is trusted for anything, so a
    forged payload never reaches the JSON parser with any authority.
    """
    checked_at = time.time() if now is None else now

    try:
        payload_b64, signature = ticket.split(".", 1)
    except (ValueError, AttributeError) as exc:
        raise InvalidTicket("Malformed ticket") from exc

    if not hmac.compare_digest(_sign(payload_b64, secret), signature):
        raise InvalidTicket("Bad signature")

    try:
        payload = json.loads(_b64decode(payload_b64))
        uid = payload["uid"]
        device_id = payload["did"]
        expires_at = float(payload["exp"])
    except Exception as exc:
        # Signature was valid, so this means we wrote a payload we can't read —
        # a bug on our side, not an attack. Still refuse it.
        raise InvalidTicket("Unreadable payload") from exc

    if checked_at >= expires_at:
        raise InvalidTicket("Ticket expired")

    return uid, device_id


def parse_ticket_authorization(authorization: str | None) -> str | None:
    """Extracts the ticket from `Authorization: Ticket <ticket>`."""
    if not authorization:
        return None
    prefix = "Ticket "
    if not authorization.startswith(prefix):
        return None
    ticket = authorization[len(prefix) :].strip()
    return ticket or None
