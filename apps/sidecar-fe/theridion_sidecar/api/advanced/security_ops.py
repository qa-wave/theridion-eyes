"""Secrets vault and TLS certificate inspection endpoints."""

from __future__ import annotations

import base64
import json
import os
import re
import socket
import ssl
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from urllib.parse import urlsplit

from ... import storage

router = APIRouter()


# ---- Secrets vault --------------------------------------------------------


class VaultEntrySummary(BaseModel):
    name: str
    updated_at: str


class VaultListOutput(BaseModel):
    entries: list[VaultEntrySummary]


class VaultWriteInput(BaseModel):
    passphrase: str = Field(..., min_length=8)
    value: str


class VaultRevealInput(BaseModel):
    passphrase: str = Field(..., min_length=8)


class VaultRevealOutput(BaseModel):
    name: str
    value: str


def _vault_path() -> Path:
    path = storage.home_dir() / "vault.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_vault() -> dict[str, Any]:
    path = _vault_path()
    if not path.exists():
        return {"version": 1, "entries": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "entries": {}}
    return data if isinstance(data, dict) else {"version": 1, "entries": {}}


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{uuid.uuid4()}.tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _vault_key(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=390_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def _safe_secret_name(name: str) -> str:
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_.-]{0,127}$", name):
        raise HTTPException(status_code=400, detail="invalid secret name")
    return name


@router.get("/secrets", response_model=VaultListOutput)
def list_secrets() -> VaultListOutput:
    vault = _load_vault()
    entries = vault.get("entries") if isinstance(vault.get("entries"), dict) else {}
    return VaultListOutput(
        entries=[
            VaultEntrySummary(name=name, updated_at=str(data.get("updated_at", "")))
            for name, data in sorted(entries.items())
            if isinstance(data, dict)
        ]
    )


@router.put("/secrets/{name}", response_model=VaultEntrySummary)
def write_secret(name: str, body: VaultWriteInput) -> VaultEntrySummary:
    safe_name = _safe_secret_name(name)
    salt = os.urandom(16)
    token = Fernet(_vault_key(body.passphrase, salt)).encrypt(body.value.encode("utf-8"))
    vault = _load_vault()
    entries = vault.setdefault("entries", {})
    if not isinstance(entries, dict):
        entries = {}
        vault["entries"] = entries
    updated_at = datetime.now(tz=UTC).isoformat()
    entries[safe_name] = {
        "salt": base64.b64encode(salt).decode("ascii"),
        "token": token.decode("ascii"),
        "updated_at": updated_at,
    }
    _write_json_atomic(_vault_path(), vault)
    return VaultEntrySummary(name=safe_name, updated_at=updated_at)


@router.post("/secrets/{name}/reveal", response_model=VaultRevealOutput)
def reveal_secret(name: str, body: VaultRevealInput) -> VaultRevealOutput:
    safe_name = _safe_secret_name(name)
    vault = _load_vault()
    entries = vault.get("entries") if isinstance(vault.get("entries"), dict) else {}
    entry = entries.get(safe_name) if isinstance(entries, dict) else None
    if not isinstance(entry, dict):
        raise HTTPException(status_code=404, detail="secret not found")
    try:
        salt = base64.b64decode(str(entry["salt"]))
        token = str(entry["token"]).encode("ascii")
        value = Fernet(_vault_key(body.passphrase, salt)).decrypt(token).decode("utf-8")
    except (KeyError, InvalidToken, ValueError) as exc:
        raise HTTPException(status_code=403, detail="could not decrypt secret") from exc
    return VaultRevealOutput(name=safe_name, value=value)


@router.delete("/secrets/{name}", status_code=204)
def delete_secret(name: str) -> None:
    safe_name = _safe_secret_name(name)
    vault = _load_vault()
    entries = vault.get("entries") if isinstance(vault.get("entries"), dict) else {}
    if not isinstance(entries, dict) or safe_name not in entries:
        raise HTTPException(status_code=404, detail="secret not found")
    del entries[safe_name]
    _write_json_atomic(_vault_path(), vault)


# ---- TLS certificate inspector -------------------------------------------


class TlsInspectInput(BaseModel):
    url: str
    timeout_seconds: float = Field(default=5, gt=0, le=30)


class TlsInspectOutput(BaseModel):
    host: str
    port: int
    subject: dict[str, str]
    issuer: dict[str, str]
    not_before: str | None = None
    not_after: str | None = None
    san: list[str] = Field(default_factory=list)
    tls_version: str | None = None
    cipher: str | None = None


def _cert_name(parts: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    if isinstance(parts, tuple):
        for group in parts:
            if isinstance(group, tuple):
                for key, value in group:
                    out[str(key)] = str(value)
    return out


@router.post("/tls/inspect", response_model=TlsInspectOutput)
def inspect_tls(body: TlsInspectInput) -> TlsInspectOutput:
    parsed = urlsplit(body.url if "://" in body.url else f"https://{body.url}")
    host = parsed.hostname
    if not host:
        raise HTTPException(status_code=400, detail="URL must include a host")
    port = parsed.port or 443
    context = ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=body.timeout_seconds) as sock:
            with context.wrap_socket(sock, server_hostname=host) as tls:
                cert = tls.getpeercert()
                cipher = tls.cipher()
                version = tls.version()
    except OSError as exc:
        raise HTTPException(status_code=502, detail=f"TLS connection failed: {exc}") from exc
    san = [
        str(value)
        for key, value in cert.get("subjectAltName", [])
        if str(key).lower() == "dns"
    ]
    return TlsInspectOutput(
        host=host,
        port=port,
        subject=_cert_name(cert.get("subject")),
        issuer=_cert_name(cert.get("issuer")),
        not_before=cert.get("notBefore"),
        not_after=cert.get("notAfter"),
        san=san,
        tls_version=version,
        cipher=cipher[0] if cipher else None,
    )
