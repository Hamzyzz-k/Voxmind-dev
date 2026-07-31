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


limiter = Limiter(key_func=client_key, default_limits=[settings.rate_limit_default])
