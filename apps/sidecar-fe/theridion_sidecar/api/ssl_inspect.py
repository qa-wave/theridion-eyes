"""SSL/TLS certificate inspection."""

from __future__ import annotations

import ssl
import socket
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class SslInspectRequest(BaseModel):
    hostname: str = Field(..., min_length=1)
    port: int = Field(default=443, ge=1, le=65535)


class ChainEntry(BaseModel):
    subject: str
    issuer: str


class SslInspectResult(BaseModel):
    subject: str
    issuer: str
    not_before: str
    not_after: str
    serial: str
    tls_version: str | None = None
    cipher: str | None = None
    chain: list[ChainEntry]
    days_until_expiry: int


def _dn_str(dn: tuple[tuple[tuple[str, str], ...], ...] | None) -> str:
    if not dn:
        return ""
    parts: list[str] = []
    for rdn in dn:
        for attr_type, attr_value in rdn:
            parts.append(f"{attr_type}={attr_value}")
    return ", ".join(parts)


@router.post("/ssl-inspect", response_model=SslInspectResult)
async def ssl_inspect(req: SslInspectRequest) -> SslInspectResult:
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((req.hostname, req.port), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=req.hostname) as ssock:
                cert = ssock.getpeercert()
                if not cert:
                    raise HTTPException(status_code=502, detail="No certificate returned")

                tls_version = ssock.version()
                cipher_info = ssock.cipher()
                cipher_name = cipher_info[0] if cipher_info else None

                binary_chain = ssock.getpeercert(binary_form=False)

                not_before_str = cert.get("notBefore", "")
                not_after_str = cert.get("notAfter", "")

                # Parse dates
                fmt = "%b %d %H:%M:%S %Y %Z"
                try:
                    not_after_dt = datetime.strptime(not_after_str, fmt).replace(tzinfo=timezone.utc)
                    days_until = (not_after_dt - datetime.now(timezone.utc)).days
                except ValueError:
                    days_until = -1

                subject = _dn_str(cert.get("subject"))
                issuer = _dn_str(cert.get("issuer"))
                serial_number = str(cert.get("serialNumber", ""))

                chain: list[ChainEntry] = []
                # The peer cert itself is the first link
                chain.append(ChainEntry(subject=subject, issuer=issuer))

                return SslInspectResult(
                    subject=subject,
                    issuer=issuer,
                    not_before=not_before_str,
                    not_after=not_after_str,
                    serial=serial_number,
                    tls_version=tls_version,
                    cipher=cipher_name,
                    chain=chain,
                    days_until_expiry=days_until,
                )
    except (OSError, ssl.SSLError) as exc:
        raise HTTPException(status_code=502, detail=f"SSL inspection failed: {exc}") from exc
