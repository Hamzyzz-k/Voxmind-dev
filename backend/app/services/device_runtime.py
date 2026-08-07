"""In-memory runtime state for Phase 2 devices — token-resolution cache,
liveness, and the latest video frame per device.

Deliberately separate from `firestore_client.py`, whose own docstring commits
to "no module-level caches of user data here". Nothing cached in this module
is user *content* — it's infrastructure state (an auth cache, a liveness
timer, a rolling frame buffer), the same category already accepted for
`middleware/rate_limit.py`'s counters. It must never be extended to hold
anything that belongs in a chat thread or profile.

Why this exists at all: `get_mfa_verified_user` costs two Firestore reads per
call. A browser polling video at 3fps through that path would cost roughly
518,000 reads/day against a 50,000/day free-tier quota — exhausting it in
under two minutes and taking the *entire* app down with it, chat included.
Every function here exists to keep a high-frequency device/browser loop off
Firestore's hot path.

Uses `time.monotonic()` throughout, not `time.time()`. These are elapsed-time
comparisons within a single process, and monotonic time can't jump backwards
if the system clock is adjusted — unlike the stream tickets in
`device_auth.py`, which embed an absolute wall-clock expiry inside a payload
and therefore need real epoch time.

Caveat, stated once here rather than scattered in comments: this is
per-process state. Render's free tier runs exactly one instance, so a cache
eviction on revoke takes effect immediately. If this service is ever scaled to
multiple instances, a revoked token would keep working on other instances for
up to `TOKEN_CACHE_TTL_SECONDS`. Re-read this docstring before doing that.
"""

import time

TOKEN_CACHE_TTL_SECONDS = 60
LIVENESS_TIMEOUT_SECONDS = 15
FRAME_STALE_SECONDS = 10
MAX_FRAME_BYTES = 200 * 1024
MAX_TRACKED_DEVICES = 50


class FrameTooLarge(Exception):
    pass


class TooManyDevices(Exception):
    pass


# --- Device-token resolution cache ---
#
# token_hash -> (uid, device_id, expires_at)
_token_cache: dict[str, tuple[str, str, float]] = {}


def cache_get_device(token_hash: str, now: float | None = None) -> tuple[str, str] | None:
    now = time.monotonic() if now is None else now
    entry = _token_cache.get(token_hash)
    if entry is None:
        return None
    uid, device_id, expires_at = entry
    if now >= expires_at:
        del _token_cache[token_hash]
        return None
    return uid, device_id


def cache_put_device(token_hash: str, uid: str, device_id: str, now: float | None = None) -> None:
    now = time.monotonic() if now is None else now
    _token_cache[token_hash] = (uid, device_id, now + TOKEN_CACHE_TTL_SECONDS)


def cache_evict_device(token_hash: str) -> None:
    """Called on revoke, so deleting a device takes effect immediately rather
    than waiting out the TTL — see the single-instance caveat above."""
    _token_cache.pop(token_hash, None)


# --- Liveness ---
#
# device_id -> last-seen monotonic timestamp. Online/offline is derived from
# this on every read, never stored — Firestore is only touched on a genuine
# offline->online transition (see mark_seen), turning what would be ~43,000
# writes/day at one heartbeat every 2s into a handful per session.
_last_seen: dict[str, float] = {}


def is_online(device_id: str, now: float | None = None) -> bool:
    now = time.monotonic() if now is None else now
    ts = _last_seen.get(device_id)
    if ts is None:
        return False
    return (now - ts) < LIVENESS_TIMEOUT_SECONDS


def mark_seen(device_id: str, now: float | None = None) -> bool:
    """Records a heartbeat/frame as proof of life. Returns True exactly when
    this is an offline->online transition, so the caller knows to persist
    `lastSeenAt` — a write on every call would be the 43,200/day mistake this
    module exists to avoid."""
    now = time.monotonic() if now is None else now
    was_online = is_online(device_id, now)
    _last_seen[device_id] = now
    return not was_online


# --- Latest frame per device ---
#
# device_id -> (jpeg bytes, monotonic timestamp). Frames are never written to
# Firestore or logged — a camera bound to a user account is the most sensitive
# thing this project handles, and there is no reason for a frame to outlive
# the moment it's served.
_frames: dict[str, tuple[bytes, float]] = {}


def store_frame(device_id: str, data: bytes, now: float | None = None) -> None:
    """Raises FrameTooLarge or TooManyDevices rather than silently truncating
    or evicting — both are caller mistakes (a runaway resolution setting, a
    firmware bug looping frame posts) worth surfacing as an honest error
    rather than papering over."""
    if len(data) > MAX_FRAME_BYTES:
        raise FrameTooLarge(f"Frame is {len(data)} bytes, over the {MAX_FRAME_BYTES}-byte limit")
    if device_id not in _frames and len(_frames) >= MAX_TRACKED_DEVICES:
        raise TooManyDevices(f"Already tracking {MAX_TRACKED_DEVICES} devices")
    now = time.monotonic() if now is None else now
    _frames[device_id] = (data, now)


def get_frame(device_id: str, now: float | None = None) -> bytes | None:
    """None if there's no frame, or the frame is stale. A frozen last image
    served as if it were live is worse than an honest "offline" — it misleads
    whoever's watching."""
    entry = _frames.get(device_id)
    if entry is None:
        return None
    data, ts = entry
    now = time.monotonic() if now is None else now
    if now - ts > FRAME_STALE_SECONDS:
        return None
    return data


def forget_device(device_id: str) -> None:
    """Called when a device is deleted, so a revoked device's stale frame and
    liveness state don't linger for a viewer until they'd have expired
    naturally anyway."""
    _last_seen.pop(device_id, None)
    _frames.pop(device_id, None)


def _reset_for_tests() -> None:
    """Test-only. Module-level dicts persist across the whole process, so
    tests must clear them explicitly rather than relying on isolation that
    doesn't exist."""
    _token_cache.clear()
    _last_seen.clear()
    _frames.clear()
