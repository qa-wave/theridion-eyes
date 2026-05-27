"""Health endpoint — used by the Tauri shell to confirm the sidecar is up."""

from __future__ import annotations

import time

from fastapi import APIRouter
from pydantic import BaseModel

from theridion_sidecar import __version__

router = APIRouter(prefix="/api", tags=["health"])

_STARTED_AT = time.monotonic()


class HealthResponse(BaseModel):
    status: str
    version: str
    uptime_seconds: float


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=__version__,
        uptime_seconds=round(time.monotonic() - _STARTED_AT, 3),
    )
