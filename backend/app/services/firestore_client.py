"""All Firestore access, always explicitly scoped by a caller-supplied uid.

No module-level caches of user data here — every function takes `uid` as an
argument and reads/writes only `users/{uid}/...`. This is the single place
that touches Firestore so the per-user isolation guarantee has one home.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from firebase_admin import firestore
from google.auth.credentials import AnonymousCredentials
from google.cloud.firestore_v1 import Client

from app.config import get_settings

_db: Client | None = None


def get_db() -> Client:
    """Local dev against the Firestore emulator uses anonymous credentials
    directly (google-cloud-firestore routes to the emulator regardless of
    the credential passed in), so running the app locally doesn't require a
    `gcloud auth application-default login`. Production (no emulator host
    configured) goes through firebase_admin's normal credential chain,
    which resolves automatically via the Cloud Run service account."""
    global _db
    if _db is None:
        settings = get_settings()
        if settings.firestore_emulator_host:
            _db = Client(project=settings.firebase_project_id, credentials=AnonymousCredentials())
        else:
            _db = firestore.client()
    return _db


def probe() -> None:
    """Cheapest possible round-trip that proves credentials resolve and
    Firestore is reachable. Raises on failure; used by /readyz.

    Reads a document that isn't expected to exist — a miss still requires a
    successful authenticated call, so it validates the whole chain without
    writing anything or touching user data.
    """
    get_db().collection("_healthcheck").document("probe").get()


def _user_ref(uid: str):
    return get_db().collection("users").document(uid)


# --- User profile ---


def ensure_user_doc(uid: str, display_name: str | None = None) -> dict[str, Any]:
    ref = _user_ref(uid)
    snap = ref.get()
    if snap.exists:
        return snap.to_dict()
    data = {
        "displayName": display_name,
        "tone": "friendly",
        "mfaVerifiedAt": None,
        "createdAt": firestore.SERVER_TIMESTAMP,
    }
    ref.set(data)
    return ref.get().to_dict()


def get_user_doc(uid: str) -> dict[str, Any] | None:
    snap = _user_ref(uid).get()
    return snap.to_dict() if snap.exists else None


def update_user_profile(uid: str, display_name: str | None = None, tone: str | None = None) -> None:
    updates: dict[str, Any] = {}
    if display_name is not None:
        updates["displayName"] = display_name
    if tone is not None:
        updates["tone"] = tone
    if updates:
        _user_ref(uid).update(updates)


def set_mfa_verified(uid: str) -> datetime:
    now = datetime.now(timezone.utc)
    _user_ref(uid).update({"mfaVerifiedAt": now})
    return now


def is_mfa_recent(uid: str, ttl_seconds: int) -> bool:
    doc = get_user_doc(uid)
    if not doc or not doc.get("mfaVerifiedAt"):
        return False
    verified_at = doc["mfaVerifiedAt"]
    if verified_at.tzinfo is None:
        verified_at = verified_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - verified_at < timedelta(seconds=ttl_seconds)


# --- Profile facts (durable, always loaded into context) ---


def list_profile_facts(uid: str) -> list[dict[str, Any]]:
    docs = _user_ref(uid).collection("profile_facts").order_by("createdAt").stream()
    return [{"id": d.id, **d.to_dict()} for d in docs]


def add_profile_fact(uid: str, text: str) -> dict[str, Any]:
    ref = _user_ref(uid).collection("profile_facts").document()
    data = {"text": text, "createdAt": firestore.SERVER_TIMESTAMP}
    ref.set(data)
    return {"id": ref.id, **ref.get().to_dict()}


def delete_profile_fact(uid: str, fact_id: str) -> None:
    _user_ref(uid).collection("profile_facts").document(fact_id).delete()


# --- Chat threads ---
#
# Every thread lives at users/{uid}/threads/{threadId}, with its messages in a
# nested `messages` subcollection. Nothing is queryable across users, and
# history pulled into an LLM prompt comes from exactly one thread — threads
# never mix. Durable profile facts stay global (see profile_facts above) and
# are loaded into every thread.

THREAD_TITLE_MAX_LEN = 60


def _threads_ref(uid: str):
    return _user_ref(uid).collection("threads")


def _thread_ref(uid: str, thread_id: str):
    return _threads_ref(uid).document(thread_id)


def _messages_ref(uid: str, thread_id: str):
    return _thread_ref(uid, thread_id).collection("messages")


def create_thread(uid: str, title: str | None = None) -> dict[str, Any]:
    ref = _threads_ref(uid).document()
    ref.set(
        {
            "title": title,
            "createdAt": firestore.SERVER_TIMESTAMP,
            "updatedAt": firestore.SERVER_TIMESTAMP,
        }
    )
    return {"id": ref.id, **ref.get().to_dict()}


def list_threads(uid: str, limit: int = 50) -> list[dict[str, Any]]:
    docs = (
        _threads_ref(uid)
        .order_by("updatedAt", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .stream()
    )
    return [{"id": d.id, **d.to_dict()} for d in docs]


def get_thread(uid: str, thread_id: str) -> dict[str, Any] | None:
    """Returns None if the thread doesn't exist *or* belongs to another user —
    the uid is part of the document path, so a mismatched uid simply can't
    resolve to another user's thread."""
    snap = _thread_ref(uid, thread_id).get()
    return {"id": snap.id, **snap.to_dict()} if snap.exists else None


def delete_thread(uid: str, thread_id: str) -> None:
    for msg in _messages_ref(uid, thread_id).stream():
        msg.reference.delete()
    _thread_ref(uid, thread_id).delete()


def set_thread_title(uid: str, thread_id: str, title: str) -> None:
    _thread_ref(uid, thread_id).update({"title": title[:THREAD_TITLE_MAX_LEN]})


def touch_thread(uid: str, thread_id: str) -> None:
    _thread_ref(uid, thread_id).update({"updatedAt": firestore.SERVER_TIMESTAMP})


# --- Chat messages within a thread ---


def append_chat_message(uid: str, thread_id: str, role: str, text: str, lang: str) -> None:
    _messages_ref(uid, thread_id).document().set(
        {"role": role, "text": text, "lang": lang, "createdAt": firestore.SERVER_TIMESTAMP}
    )


def get_recent_chat_history(uid: str, thread_id: str, limit: int) -> list[dict[str, Any]]:
    """Most recent `limit` messages from this thread only, chronological."""
    docs = (
        _messages_ref(uid, thread_id)
        .order_by("createdAt", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .stream()
    )
    messages = [d.to_dict() for d in docs]
    messages.reverse()  # chronological order for prompt assembly
    return messages


def get_full_chat_history(uid: str, thread_id: str) -> list[dict[str, Any]]:
    """Whole thread, chronological — used to populate the UI when a thread is
    opened (as opposed to the trimmed slice that goes into the LLM prompt)."""
    docs = _messages_ref(uid, thread_id).order_by("createdAt").stream()
    return [d.to_dict() for d in docs]


def count_thread_messages(uid: str, thread_id: str, cap: int = 2) -> int:
    """Cheap 'is this thread empty?' check — only reads up to `cap` docs, since
    callers just need to know whether this is the first message."""
    return len(list(_messages_ref(uid, thread_id).limit(cap).stream()))


# --- OTP challenge ---


def _otp_ref(uid: str):
    return _user_ref(uid).collection("otp_challenge").document("current")


def set_otp_challenge(uid: str, code_hash: str, expires_at: datetime) -> None:
    _otp_ref(uid).set(
        {
            "codeHash": code_hash,
            "expiresAt": expires_at,
            "attempts": 0,
            "requestedAt": firestore.SERVER_TIMESTAMP,
        }
    )


def get_otp_challenge(uid: str) -> dict[str, Any] | None:
    snap = _otp_ref(uid).get()
    return snap.to_dict() if snap.exists else None


def increment_otp_attempts(uid: str) -> int:
    ref = _otp_ref(uid)

    @firestore.transactional
    def _txn(transaction):
        snap = ref.get(transaction=transaction)
        current = snap.to_dict().get("attempts", 0) if snap.exists else 0
        new_count = current + 1
        transaction.update(ref, {"attempts": new_count})
        return new_count

    return _txn(get_db().transaction())


def clear_otp_challenge(uid: str) -> None:
    _otp_ref(uid).delete()


# --- IoT devices (Phase 2) ---
#
# A device's own data lives under users/{uid}/devices/{id}, consistent with
# every other collection in this file. But *authenticating* a device means
# going the other way — given a bare token, find its owner — and that lookup
# cannot live under users/{uid} without already knowing the uid. So
# device_tokens/{tokenHash} is a top-level collection: the first one in this
# project, and the only thing that departs from the "everything nested under
# users/{uid}" isolation pattern. It holds nothing but the mapping itself —
# no user content ever goes in this collection, and nothing outside this file
# should read or write it directly.


def _devices_ref(uid: str):
    return _user_ref(uid).collection("devices")


def _device_ref(uid: str, device_id: str):
    return _devices_ref(uid).document(device_id)


def _device_token_ref(token_hash: str):
    return get_db().collection("device_tokens").document(token_hash)


def create_device(uid: str, name: str, device_type: str, token_hash: str) -> dict[str, Any]:
    ref = _devices_ref(uid).document()
    ref.set(
        {
            "name": name,
            "type": device_type,
            "tokenHash": token_hash,
            "lastSeenAt": None,
            "createdAt": firestore.SERVER_TIMESTAMP,
        }
    )
    # The device doc is the source of truth; the mapping only exists to route a
    # bare token back to it. Written second, not transactionally — if this
    # write failed, the device simply couldn't authenticate yet, which is a
    # safe failure rather than a security hole.
    _device_token_ref(token_hash).set({"uid": uid, "deviceId": ref.id})
    return {"id": ref.id, **ref.get().to_dict()}


def list_devices(uid: str) -> list[dict[str, Any]]:
    docs = _devices_ref(uid).order_by("createdAt").stream()
    return [{"id": d.id, **d.to_dict()} for d in docs]


def get_device_doc(uid: str, device_id: str) -> dict[str, Any] | None:
    """None if the device doesn't exist *or* belongs to another user — the uid
    is part of the document path, same structural guarantee as get_thread."""
    snap = _device_ref(uid, device_id).get()
    return {"id": snap.id, **snap.to_dict()} if snap.exists else None


def delete_device(uid: str, device_id: str) -> None:
    """Deletes the device doc and its token mapping together. There's no soft
    "revoked" flag — once the mapping is gone, resolve_device_token returns
    None and the device simply can't authenticate, which is the entire point,
    with one fewer piece of state to keep consistent."""
    doc = get_device_doc(uid, device_id)
    if doc and doc.get("tokenHash"):
        _device_token_ref(doc["tokenHash"]).delete()
    _device_ref(uid, device_id).delete()


def touch_device_last_seen(uid: str, device_id: str) -> None:
    """Called only on an offline->online transition, not on every heartbeat —
    see services/device_runtime.py. Liveness itself lives in memory; this just
    remembers the last time it happened, so the UI can show it after a
    restart wipes that in-memory state."""
    _device_ref(uid, device_id).update({"lastSeenAt": firestore.SERVER_TIMESTAMP})


def resolve_device_token(token_hash: str) -> dict[str, Any] | None:
    snap = _device_token_ref(token_hash).get()
    return snap.to_dict() if snap.exists else None
