import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import get_settings
from app.firebase_app import init_firebase_app  # noqa: F401  (also used by /readyz)
from app.middleware.rate_limit import limiter
from app.routes import auth, chat, iot, profile
from app.services import firestore_client

logging.basicConfig(level=logging.INFO)

settings = get_settings()

init_firebase_app()

app = FastAPI(title="VoxMind API")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
# Applies `default_limits` (see middleware/rate_limit.py) to every route;
# routes decorated with @limiter.limit(...) get their own stricter limit.
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(chat.router)
app.include_router(iot.router)


@app.get("/healthz")
async def healthz():
    """Liveness only — deliberately touches nothing external, so the platform's
    health check can't be knocked over by a transient Firestore blip."""
    return {"status": "ok"}


@app.get("/readyz")
async def readyz():
    """Readiness — actually exercises the credential chain and Firestore.

    Exists because a missing/invalid service-account credential otherwise shows
    up only as a 500 on a real user request, which is indistinguishable from a
    dozen other faults. Reports *which* dependency is broken and how the
    credential was resolved, without echoing any secret value.
    """
    checks: dict[str, str] = {
        "credential_source": (
            "service_account_json" if settings.firebase_service_account_json.strip() else "application_default"
        ),
        "project_id": settings.firebase_project_id or "(unset)",
    }
    ready = True

    # Step 1: can the credential actually sign? A service-account JSON pasted
    # into a dashboard often survives JSON parsing while its private_key
    # newlines get mangled, which only fails later at signing time — so check
    # it separately from reaching Firestore.
    try:
        import google.auth.transport.requests

        cred = init_firebase_app().credential.get_credential()
        cred.refresh(google.auth.transport.requests.Request())
        checks["credential_signing"] = "ok"
    except Exception as exc:
        logging.getLogger(__name__).exception("Credential refresh failed")
        checks["credential_signing"] = f"failed: {type(exc).__name__}: {str(exc)[:200]}"
        ready = False

    # Step 2: can we actually reach Firestore with it?
    try:
        firestore_client.probe()
        checks["firestore"] = "ok"
    except Exception as exc:
        logging.getLogger(__name__).exception("Firestore probe failed")
        checks["firestore"] = f"failed: {type(exc).__name__}: {str(exc)[:300]}"
        ready = False

    return JSONResponse(
        status_code=200 if ready else 503,
        content={"ready": ready, "checks": checks},
    )
