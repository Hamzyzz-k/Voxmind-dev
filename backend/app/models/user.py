from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Tone(str, Enum):
    friendly = "friendly"
    official = "official"


class UserProfile(BaseModel):
    uid: str
    display_name: str | None = None
    tone: Tone = Tone.friendly
    created_at: datetime | None = None


class ProfileUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=100)
    tone: Tone | None = None


class ProfileFact(BaseModel):
    id: str
    text: str
    created_at: datetime | None = None


class ProfileFactCreateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class ProfileResponse(BaseModel):
    profile: UserProfile
    facts: list[ProfileFact]
