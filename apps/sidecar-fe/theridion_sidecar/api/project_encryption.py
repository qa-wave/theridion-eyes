"""Project encryption: Fernet-encrypt all collection/environment files."""

from __future__ import annotations

import base64
import os

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from fastapi import APIRouter
from pydantic import BaseModel

from theridion_sidecar import storage

router = APIRouter(prefix="/api/security", tags=["project-encryption"])


class EncryptProjectInput(BaseModel):
    passphrase: str


class EncryptProjectOutput(BaseModel):
    status: str = "ok"
    files_encrypted: int = 0


def _derive_fernet_key(passphrase: str, salt: bytes) -> bytes:
    """Derive a Fernet-compatible key via PBKDF2-HMAC-SHA256."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=390_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


@router.post("/encrypt-project", response_model=EncryptProjectOutput)
async def encrypt_project(body: EncryptProjectInput) -> EncryptProjectOutput:
    home = storage.home_dir()
    salt = os.urandom(16)
    key = _derive_fernet_key(body.passphrase, salt)
    f = Fernet(key)
    count = 0
    for p in home.glob("**/*.json"):
        if p.name.startswith("."):
            continue
        data = p.read_bytes()
        encrypted = f.encrypt(data)
        # Prefix with salt so we can re-derive the key on decrypt.
        encoded = base64.b64encode(salt + encrypted)
        p.write_bytes(b"THERIDION_ENC:" + encoded)
        count += 1
    return EncryptProjectOutput(files_encrypted=count)


@router.post("/decrypt-project", response_model=EncryptProjectOutput)
async def decrypt_project(body: EncryptProjectInput) -> EncryptProjectOutput:
    home = storage.home_dir()
    count = 0
    for p in home.glob("**/*.json"):
        raw = p.read_bytes()
        if not raw.startswith(b"THERIDION_ENC:"):
            continue
        payload = base64.b64decode(raw[len(b"THERIDION_ENC:"):])
        salt = payload[:16]
        encrypted = payload[16:]
        key = _derive_fernet_key(body.passphrase, salt)
        f = Fernet(key)
        decrypted = f.decrypt(encrypted)
        p.write_bytes(decrypted)
        count += 1
    return EncryptProjectOutput(status="decrypted", files_encrypted=count)
