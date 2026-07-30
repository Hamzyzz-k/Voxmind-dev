"""Per-IP rate limiting via slowapi (in-memory).

This is an infra control, not user/request *data* — the limiter's internal
counters hold no user content and are keyed transiently, so they don't violate
the "no global mutable state holding user/request state" rule; the spec
explicitly calls for rate limiting here.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings

settings = get_settings()
limiter = Limiter(key_func=get_remote_address, default_limits=[settings.rate_limit_default])
