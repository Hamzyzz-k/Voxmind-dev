import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import get_settings
from app.firebase_app import init_firebase_app
from app.middleware.rate_limit import limiter
from app.routes import auth, chat, iot, profile

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
    return {"status": "ok"}
