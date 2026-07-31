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

    # CORS
    allowed_origins: str = "http://localhost:5173"

    # LLM
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_max_concurrency: int = 5
    groq_max_retries: int = 3
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # TTS (ElevenLabs — no GCP billing account needed, unlike Cloud TTS)
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"  # "Rachel", a default premade voice
    elevenlabs_model_id: str = "eleven_v3"  # only ElevenLabs model that covers Kannada

    # Chat / memory
    chat_history_limit: int = 20

    # OTP / MFA
    otp_expiry_seconds: int = 300
    otp_max_attempts: int = 5
    otp_resend_cooldown_seconds: int = 60
    mfa_session_ttl_seconds: int = 43200  # 12h

    # SMTP (OTP email delivery)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    # Audio upload limits (backend STT fallback)
    max_audio_upload_bytes: int = 10 * 1024 * 1024  # 10MB
    allowed_audio_content_types: str = "audio/wav,audio/webm,audio/ogg,audio/mpeg"

    # Rate limiting
    rate_limit_default: str = "30/minute"
    rate_limit_chat: str = "10/minute"
    rate_limit_otp: str = "5/minute"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def allowed_audio_content_types_list(self) -> list[str]:
        return [t.strip() for t in self.allowed_audio_content_types.split(",") if t.strip()]

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_password and self.smtp_from)


@lru_cache
def get_settings() -> Settings:
    return Settings()
