"""Token auto-refresh — send request, if 401 refresh and retry."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/auth", tags=["auth"])


class TokenRefreshRequest(BaseModel):
    url: str = Field(..., min_length=1)
    method: str = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    refresh_url: str = Field(..., min_length=1)
    refresh_body: dict | None = None
    token_field: str = "access_token"
    auth_header: str = "Authorization"


class TokenRefreshResult(BaseModel):
    original_status: int
    refreshed: bool
    final_status: int
    final_body: str
    new_token: str | None = None


@router.post("/auto-refresh", response_model=TokenRefreshResult)
async def auto_refresh(req: TokenRefreshRequest) -> TokenRefreshResult:
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            # First request
            content = req.body.encode() if req.body else None
            r1 = await client.request(
                method=req.method, url=req.url,
                headers=req.headers, content=content,
            )
            original_status = r1.status_code

            if r1.status_code != 401:
                return TokenRefreshResult(
                    original_status=original_status,
                    refreshed=False,
                    final_status=r1.status_code,
                    final_body=r1.text,
                )

            # Refresh token
            import json
            refresh_content = json.dumps(req.refresh_body).encode() if req.refresh_body else None
            refresh_headers = {"content-type": "application/json"} if refresh_content else {}
            r_refresh = await client.post(
                req.refresh_url,
                headers=refresh_headers,
                content=refresh_content,
            )

            if r_refresh.status_code >= 400:
                return TokenRefreshResult(
                    original_status=original_status,
                    refreshed=False,
                    final_status=r_refresh.status_code,
                    final_body=r_refresh.text,
                )

            # Extract new token
            try:
                refresh_data = r_refresh.json()
                new_token = refresh_data.get(req.token_field)
            except Exception:
                new_token = None

            if not new_token:
                return TokenRefreshResult(
                    original_status=original_status,
                    refreshed=False,
                    final_status=r_refresh.status_code,
                    final_body=r_refresh.text,
                )

            # Retry with new token
            retry_headers = {**req.headers, req.auth_header: f"Bearer {new_token}"}
            r2 = await client.request(
                method=req.method, url=req.url,
                headers=retry_headers, content=content,
            )

            return TokenRefreshResult(
                original_status=original_status,
                refreshed=True,
                final_status=r2.status_code,
                final_body=r2.text,
                new_token=new_token,
            )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
