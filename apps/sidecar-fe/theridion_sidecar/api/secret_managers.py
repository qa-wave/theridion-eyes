"""Secret managers: fetch secrets from various providers."""

from __future__ import annotations

import os

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/secrets", tags=["secret-managers"])


class SecretFetchInput(BaseModel):
    provider: str  # "vault" | "aws" | "env"
    config: dict = {}


class SecretFetchOutput(BaseModel):
    name: str = ""
    value: str = ""
    error: str | None = None


@router.post("/fetch", response_model=SecretFetchOutput)
async def fetch_secret(body: SecretFetchInput) -> SecretFetchOutput:
    if body.provider == "env":
        key = body.config.get("key", "")
        value = os.environ.get(key, "")
        return SecretFetchOutput(name=key, value=value)
    elif body.provider == "vault":
        return SecretFetchOutput(
            name=body.config.get("path", ""),
            error="HashiCorp Vault integration requires vault client library",
        )
    elif body.provider == "aws":
        return SecretFetchOutput(
            name=body.config.get("key", ""),
            error="AWS Secrets Manager integration requires boto3",
        )
    else:
        return SecretFetchOutput(error=f"Unknown provider: {body.provider}")
