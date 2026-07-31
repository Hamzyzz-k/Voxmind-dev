"""Firebase Admin SDK initialization, shared across the app.

Credential resolution, in priority order:

1. `FIREBASE_SERVICE_ACCOUNT_JSON` — the full service-account JSON as a single
   env var. This is what makes the backend deployable to hosts outside Google
   Cloud (Render, Hugging Face Spaces, Fly, a VPS...), which have no
   Application Default Credentials of their own.
2. Application Default Credentials — used on Google Cloud (the attached
   service account) and locally after `gcloud auth application-default login`.

Local dev note: even against the emulators the Admin SDK needs *a* resolvable
credential to construct — it isn't validated against emulator calls, but
`initialize_app` fails fast without one.
"""

import json
import logging
import os

import firebase_admin
from firebase_admin import credentials

from app.config import get_settings

logger = logging.getLogger(__name__)

_app: firebase_admin.App | None = None


def apply_emulator_env(settings) -> None:
    """Points the client libraries at the emulators, or makes sure they aren't.

    These are read for *presence*, not truthiness, so an empty value is not the
    same as unset: it reads as "an emulator is configured, at address ''", and
    the gRPC channel then fails with an opaque
    `Unknown: the target uri is not valid: dns:///` on the first Firestore call.
    Deployment dashboards make empty values very easy to introduce, so unset
    them rather than leaving them blank.
    """
    for var, value in (
        ("FIRESTORE_EMULATOR_HOST", settings.firestore_emulator_host),
        ("FIREBASE_AUTH_EMULATOR_HOST", settings.firebase_auth_emulator_host),
    ):
        if value.strip():
            os.environ[var] = value.strip()
        else:
            os.environ.pop(var, None)


def _resolve_credential(settings) -> credentials.Base:
    raw = settings.firebase_service_account_json.strip()
    if raw:
        try:
            info = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "FIREBASE_SERVICE_ACCOUNT_JSON is set but is not valid JSON. "
                "It must contain the entire service-account key file contents."
            ) from exc
        logger.info("Firebase credential source: FIREBASE_SERVICE_ACCOUNT_JSON")
        return credentials.Certificate(info)

    logger.info("Firebase credential source: Application Default Credentials")
    return credentials.ApplicationDefault()


def init_firebase_app() -> firebase_admin.App:
    global _app
    if _app is not None:
        return _app

    settings = get_settings()

    apply_emulator_env(settings)

    cred = _resolve_credential(settings)
    _app = firebase_admin.initialize_app(cred, {"projectId": settings.firebase_project_id})
    return _app
