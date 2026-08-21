from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: str = "development"

    # Firebase / GCP
    firebase_project_id: str = ""
    firestore_emulator_host: str = ""  # set to "localhost:8080" for local dev
    firebase_auth_emulator_host: str = ""  # set to "localhost:9099" for local dev
    google_application_credentials: str = ""  # path to service account json (prod only)
    # Full service-account key JSON as a single env var. Required on hosts
    # outside Google Cloud, which have no Application Default Credentials.
    firebase_service_account_json: str = ""

    # CORS
    allowed_origins: str = "http://localhost:5173"

    # LLM
    groq_api_key: str = ""
    # llama-3.3-70b-versatile was here and Groq deprecated it 2026-06-17
    # (free/developer tier) — see the GROQ_MODEL comment in render.yaml.
    groq_model: str = "openai/gpt-oss-120b"
    groq_max_concurrency: int = 5
    groq_max_retries: int = 3
    gemini_api_key: str = ""
    # Pinned on purpose — see the GEMINI_MODEL comment in render.yaml for the
    # full history. Short version: `gemini-flash-latest` tracks the newest
    # Flash model, and the newest model carries the smallest free-tier quota
    # (20 requests/day, versus 1,500/day here). Also used for vision
    # (services/vision_client.py), since the same model is natively multimodal.
    gemini_model: str = "gemini-3.5-flash"

    # TTS (ElevenLabs — no GCP billing account needed, unlike Cloud TTS)
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "pNInz6obpgDQGcFmaJgB"  # "Adam" — confirmed free-tier API usable
    elevenlabs_model_id: str = "eleven_v3"  # only ElevenLabs model that covers Kannada

    # Chat / memory
    chat_history_limit: int = 20

    # OTP / MFA
    otp_expiry_seconds: int = 300
    otp_max_attempts: int = 5
    otp_resend_cooldown_seconds: int = 60
    mfa_session_ttl_seconds: int = 43200  # 12h

    # OTP email delivery.
    # Brevo's HTTP API is preferred: Render's free web services block outbound
    # SMTP ports (25/465/587), so SMTP can't leave the container there at all.
    brevo_api_key: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""  # verified sender; used by both transports

    # Audio upload limits (backend STT fallback)
    max_audio_upload_bytes: int = 10 * 1024 * 1024  # 10MB
    allowed_audio_content_types: str = "audio/wav,audio/webm,audio/ogg,audio/mpeg"

    # IoT (Phase 2) — signs short-lived tickets that let a browser poll video
    # frames without a Firestore read per request (see
    # services/device_runtime.py for why that matters). 32+ random bytes, set
    # in the Render dashboard, never committed. If unset, the ticket endpoint
    # returns 503 rather than silently skipping the signature.
    stream_ticket_secret: str = ""

    # Rate limiting
    # Set true when running behind a reverse proxy (any managed host), so the
    # real client IP is read from X-Forwarded-For instead of the proxy's IP.
    behind_proxy: bool = False
    rate_limit_default: str = "30/minute"
    rate_limit_chat: str = "10/minute"
    rate_limit_otp: str = "5/minute"
    # Device endpoints are keyed by device token, not IP (see
    # middleware/rate_limit.py:device_key) — a device and its owner's browser
    # can share a public IP, so IP-keyed limiting would let the device exhaust
    # the user's own chat quota. ~3fps target plus headroom for a firmware bug
    # that loops faster than intended.
    rate_limit_device: str = "600/minute"
    rate_limit_stream_poll: str = "600/minute"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def allowed_audio_content_types_list(self) -> list[str]:
        return [t.strip() for t in self.allowed_audio_content_types.split(",") if t.strip()]

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_password and self.smtp_from)

    @property
    def brevo_api_configured(self) -> bool:
        return bool(self.brevo_api_key and self.smtp_from)

    @property
    def email_configured(self) -> bool:
        return self.brevo_api_configured or self.smtp_configured

    @property
    def email_transport(self) -> str:
        if self.brevo_api_configured:
            return "brevo_api"
        if self.smtp_configured:
            return "smtp"
        return "none"

    @property
    def stream_ticket_configured(self) -> bool:
        return bool(self.stream_ticket_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()
