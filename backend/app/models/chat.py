from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

SUPPORTED_LANGS = {"en", "hi", "kn", "ta"}


class Role(str, Enum):
    user = "user"
    assistant = "assistant"


class ChatMessage(BaseModel):
    role: Role
    text: str
    lang: str
    created_at: datetime | None = None


class AskRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=2000)
    lang: str = Field(default="en")
    thread_id: str
    # False when the user has muted TTS — skips the ElevenLabs call entirely
    # rather than generating audio the client would throw away.
    speak: bool = True


class AskResponse(BaseModel):
    reply_text: str
    lang: str
    used_search: bool
    thread_id: str
    thread_title: str | None = None
    audio_base64: str | None = None
    audio_content_type: str = "audio/mpeg"
    audio_error: str | None = None
    llm_provider: str


class ChatHistoryResponse(BaseModel):
    messages: list[ChatMessage]


class Thread(BaseModel):
    id: str
    title: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ThreadListResponse(BaseModel):
    threads: list[Thread]


class ThreadDetailResponse(BaseModel):
    thread: Thread
    messages: list[ChatMessage]


class TranscribeResponse(BaseModel):
    transcript: str
    lang: str
