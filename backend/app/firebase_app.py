"""Firebase Admin SDK initialization, shared across the app.

Local dev note: even against the emulators, the Admin SDK needs *a* resolvable
credential object to construct (it doesn't validate it against emulator calls,
but `initialize_app` fails fast without one). Run `gcloud auth application-default
login` once locally (free, no billing needed) so `credentials.ApplicationDefault()`
resolves. In production (Cloud Run), the attached service account is used
automatically and no extra setup is needed.
"""

import os

import firebase_admin
from firebase_admin import credentials

from app.config import get_settings

_app: firebase_admin.App | None = None


def init_firebase_app() -> firebase_admin.App:
    global _app
    if _app is not None:
        return _app

    settings = get_settings()

    if settings.firestore_emulator_host:
        os.environ["FIRESTORE_EMULATOR_HOST"] = settings.firestore_emulator_host
    if settings.firebase_auth_emulator_host:
        os.environ["FIREBASE_AUTH_EMULATOR_HOST"] = settings.firebase_auth_emulator_host

    cred = credentials.ApplicationDefault()
    _app = firebase_admin.initialize_app(cred, {"projectId": settings.firebase_project_id})
    return _app
