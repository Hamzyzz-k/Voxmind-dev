"""Per-client rate limiting via slowapi (in-memory).

This is an infra control, not user/request *data* — the limiter's internal
counters hold no user content and are keyed transiently, so they don't violate
the "no global mutable state holding user/request state" rule; the spec
explicitly calls for rate limiting here.

Note on scope: counters live in process memory, so with more than one server
instance each instance enforces its own limit. That's acceptable here (the
limits exist to stop runaway loops and abuse, not to meter billing), but it's
why the limits aren't a security boundary on their own.
"""

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings
from app.services.device_auth import hash_device_token, parse_device_authorization

settings = get_settings()


def client_key(request: Request) -> str:
    """Identifies the caller for rate-limiting purposes.

    Every managed host (Cloud Run, Render, Fly, ...) puts a reverse proxy in
    front of the app, so `request.client.host` is the *proxy's* IP — identical
    for every user. Using it directly would lump all users into a single
    bucket, letting one caller exhaust everyone's quota. The real client IP is
    the first entry in X-Forwarded-For.

    Only trusted when `behind_proxy` is set, since the header is trivially
    spoofable when requests can reach the app directly.
    """
    if settings.behind_proxy:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return get_remote_address(request)


def device_key(request: Request) -> str:
    """Identifies a device by its own token, not by IP.

    A device and its owner's browser routinely share a public IP (same home
    WiFi), so IP-based limiting would let the device's request volume eat into
    the user's own chat quota, or vice versa. Keying on the token hash gives
    every device — and every human — an independent bucket.

    Falls back to `client_key` when the header is missing or malformed, so a
    bad request still gets *a* bucket rather than crashing the limiter; the
    request fails auth separately in the route's own dependency regardless.
    """
    token = parse_device_authorization(request.headers.get("authorization"))
    if token:
        return f"device:{hash_device_token(token)}"
    return client_key(request)


limiter = Limiter(key_func=client_key, default_limits=[settings.rate_limit_default])
