from datetime import datetime

from pydantic import BaseModel, Field


class OtpRequestResponse(BaseModel):
    message: str
    expires_in_seconds: int


class OtpVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class OtpVerifyResponse(BaseModel):
    message: str
    mfa_verified_at: datetime
