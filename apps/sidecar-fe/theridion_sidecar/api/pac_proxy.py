"""PAC proxy: parse PAC files to resolve proxy for URLs."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/proxy", tags=["pac-proxy"])


class PacResolveInput(BaseModel):
    pac_content: str
    url: str


class PacResolveOutput(BaseModel):
    proxy_url: str | None = None


@router.post("/pac-resolve", response_model=PacResolveOutput)
async def pac_resolve(body: PacResolveInput) -> PacResolveOutput:
    # Basic PAC parsing: look for PROXY and DIRECT directives
    pac = body.pac_content
    parsed_url = urlparse(body.url)
    host = parsed_url.hostname or ""

    # Check for simple host-based rules
    lines = pac.replace(";", "\n").split("\n")
    for line in lines:
        line = line.strip()
        # Match "PROXY host:port"
        proxy_match = re.search(r'PROXY\s+([\w.\-]+:\d+)', line, re.IGNORECASE)
        if proxy_match:
            # Check if there's a condition excluding this host
            if "DIRECT" in line.upper() and host in line:
                continue
            return PacResolveOutput(proxy_url=f"http://{proxy_match.group(1)}")

    # Check for DIRECT
    if "DIRECT" in pac.upper():
        return PacResolveOutput(proxy_url=None)

    return PacResolveOutput(proxy_url=None)
