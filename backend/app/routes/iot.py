"""Placeholder for Phase 2 (ESP-based hardware/IoT layer) — not implemented.

Kept as a clearly separated namespace so Phase 1 doesn't need to touch routing
again when hardware support is added later.
"""

from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/iot", tags=["iot"])


@router.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def iot_not_implemented(full_path: str):
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="IoT/hardware layer is Phase 2 and not implemented yet.",
    )
