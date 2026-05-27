"""JWT token inspection — decode header and payload without verification."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/security", tags=["security"])


class JwtInspectRequest(BaseModel):
    token: str = Field(..., min_length=1)


class JwtInspectResult(BaseModel):
    header: dict
    payload: dict
    expired: bool
    expires_at: str | None = None
    issued_at: str | None = None


def _b64_decode(segment: str) -> dict:
    # Add padding if necessary
    padding = 4 - len(segment) % 4
    if padding != 4:
        segment += "=" * padding
    decoded = base64.urlsafe_b64decode(segment)
    return json.loads(decoded)


@router.post("/jwt-inspect", response_model=JwtInspectResult)
async def jwt_inspect(req: JwtInspectRequest) -> JwtInspectResult:
    parts = req.token.strip().split(".")
    if len(parts) < 2:
        raise HTTPException(status_code=400, detail="Invalid JWT: expected at least 2 dot-separated segments")

    try:
        header = _b64_decode(parts[0])
        payload = _b64_decode(parts[1])
    except (json.JSONDecodeError, Exception) as exc:
        raise HTTPException(status_code=400, detail=f"Failed to decode JWT: {exc}") from exc

    expired = False
    expires_at: str | None = None
    issued_at: str | None = None

    exp = payload.get("exp")
    if isinstance(exp, (int, float)):
        exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)
        expires_at = exp_dt.isoformat()
        expired = exp_dt < datetime.now(timezone.utc)

    iat = payload.get("iat")
    if isinstance(iat, (int, float)):
        issued_at = datetime.fromtimestamp(iat, tz=timezone.utc).isoformat()

    return JwtInspectResult(
        header=header,
        payload=payload,
        expired=expired,
        expires_at=expires_at,
        issued_at=issued_at,
    )
