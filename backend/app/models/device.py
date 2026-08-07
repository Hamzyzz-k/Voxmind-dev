from datetime import datetime

from pydantic import BaseModel, Field

DEVICE_NAME_MAX_LEN = 60
DEVICE_TYPE_MAX_LEN = 30


class DeviceRegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=DEVICE_NAME_MAX_LEN)
    type: str = Field(default="glasses", max_length=DEVICE_TYPE_MAX_LEN)


class DeviceRegisterResponse(BaseModel):
    id: str
    name: str
    type: str
    # Plaintext device token — returned exactly once, here, and never again.
    # Only its hash is ever stored.
    token: str
    created_at: datetime | None = None


class Device(BaseModel):
    id: str
    name: str
    type: str
    online: bool
    last_seen_at: datetime | None = None
    created_at: datetime | None = None


class DeviceListResponse(BaseModel):
    devices: list[Device]


class StreamTicketResponse(BaseModel):
    ticket: str
    expires_in: int
