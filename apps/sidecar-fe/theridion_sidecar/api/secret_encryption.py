"""Secret encryption: Fernet encrypt/decrypt individual values."""

from __future__ import annotations

import base64
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/security", tags=["secret-encryption"])


class SecretEncryptInput(BaseModel):
    value: str
    passphrase: str


class SecretEncryptOutput(BaseModel):
    encrypted: str = ""
    decrypted: str = ""


def _derive_fernet_key(passphrase: str, salt: bytes) -> bytes:
    """Derive a Fernet-compatible key via PBKDF2-HMAC-SHA256."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=390_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


@router.post("/encrypt-secret", response_model=SecretEncryptOutput)
async def encrypt_secret(body: SecretEncryptInput) -> SecretEncryptOutput:
    salt = os.urandom(16)
    key = _derive_fernet_key(body.passphrase, salt)
    f = Fernet(key)
    encrypted = f.encrypt(body.value.encode("utf-8"))
    # Prepend salt so decrypt can re-derive the same key.
    encoded = base64.b64encode(salt + encrypted).decode()
    return SecretEncryptOutput(encrypted=encoded)


@router.post("/decrypt-secret", response_model=SecretEncryptOutput)
async def decrypt_secret(body: SecretEncryptInput) -> SecretEncryptOutput:
    try:
        payload = base64.b64decode(body.value)
        salt = payload[:16]
        encrypted = payload[16:]
        key = _derive_fernet_key(body.passphrase, salt)
        f = Fernet(key)
        decrypted = f.decrypt(encrypted).decode("utf-8")
        return SecretEncryptOutput(decrypted=decrypted)
    except (InvalidToken, Exception) as exc:
        return SecretEncryptOutput(decrypted=f"Error: {exc}")
