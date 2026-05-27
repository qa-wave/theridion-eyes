"""DNS resolution inspection."""

from __future__ import annotations

import socket
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class DnsInspectRequest(BaseModel):
    hostname: str = Field(..., min_length=1)


class AddressEntry(BaseModel):
    ip: str
    family: str


class DnsInspectResult(BaseModel):
    hostname: str
    addresses: list[AddressEntry]
    resolved_in_ms: float


@router.post("/dns-inspect", response_model=DnsInspectResult)
async def dns_inspect(req: DnsInspectRequest) -> DnsInspectResult:
    try:
        start = time.perf_counter()
        infos = socket.getaddrinfo(req.hostname, None)
        elapsed = (time.perf_counter() - start) * 1000

        seen: set[str] = set()
        addresses: list[AddressEntry] = []
        for family, _, _, _, sockaddr in infos:
            ip = sockaddr[0]
            if ip in seen:
                continue
            seen.add(ip)
            family_str = "IPv4" if family == socket.AF_INET else "IPv6"
            addresses.append(AddressEntry(ip=ip, family=family_str))

        return DnsInspectResult(
            hostname=req.hostname,
            addresses=addresses,
            resolved_in_ms=round(elapsed, 2),
        )
    except socket.gaierror as exc:
        raise HTTPException(status_code=502, detail=f"DNS resolution failed: {exc}") from exc
