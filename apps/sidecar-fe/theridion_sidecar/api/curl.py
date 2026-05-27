"""cURL import / export — parse a cURL command into request parts and
generate a cURL command from request config.
"""

from __future__ import annotations

import shlex
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..models import AuthConfig, HttpMethod

router = APIRouter(prefix="/api/curl", tags=["curl"])


# ---- models ---------------------------------------------------------------


class ParsedCurl(BaseModel):
    method: HttpMethod = "GET"
    url: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    auth: AuthConfig | None = None


class ParseInput(BaseModel):
    curl: str = Field(..., min_length=1)


class GenerateInput(BaseModel):
    method: HttpMethod = "GET"
    url: str = Field(..., min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    auth: AuthConfig | None = None


class GenerateOutput(BaseModel):
    curl: str


# ---- parser ---------------------------------------------------------------


def parse_curl(raw: str) -> ParsedCurl:
    """Parse a cURL command string into structured request components."""
    # Normalize: strip leading $, handle line continuations.
    text = raw.strip()
    if text.startswith("$ "):
        text = text[2:]
    text = text.replace("\\\n", " ").replace("\\\r\n", " ")

    try:
        tokens = shlex.split(text)
    except ValueError:
        return ParsedCurl()

    if not tokens or tokens[0] != "curl":
        return ParsedCurl()

    method: str | None = None
    url: str = ""
    headers: dict[str, str] = {}
    body: str | None = None
    user: str | None = None  # -u / --user
    has_data = False

    i = 1
    while i < len(tokens):
        tok = tokens[i]

        if tok in ("-X", "--request") and i + 1 < len(tokens):
            method = tokens[i + 1].upper()
            i += 2
        elif tok in ("-H", "--header") and i + 1 < len(tokens):
            hdr = tokens[i + 1]
            colon = hdr.find(":")
            if colon != -1:
                name = hdr[:colon].strip()
                value = hdr[colon + 1:].strip()
                headers[name] = value
            i += 2
        elif tok in ("-d", "--data", "--data-raw", "--data-binary") and i + 1 < len(tokens):
            body = tokens[i + 1]
            has_data = True
            i += 2
        elif tok == "--data-urlencode" and i + 1 < len(tokens):
            body = tokens[i + 1]
            has_data = True
            i += 2
        elif tok in ("-u", "--user") and i + 1 < len(tokens):
            user = tokens[i + 1]
            i += 2
        elif tok in ("-k", "--insecure", "--compressed", "-s", "--silent",
                      "-S", "--show-error", "-v", "--verbose", "-L",
                      "--location", "-i", "--include", "-o", "--output",
                      "--globoff", "-g"):
            # Flags we recognize but skip.
            if tok in ("-o", "--output") and i + 1 < len(tokens):
                i += 2
            else:
                i += 1
        elif not tok.startswith("-") and not url:
            url = tok
            i += 1
        else:
            i += 1

    # Infer method from data presence.
    if method is None:
        method = "POST" if has_data else "GET"

    # Build auth config.
    auth: AuthConfig | None = None
    auth_header = headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        auth = AuthConfig(type="bearer", token=auth_header[7:])
        del headers["Authorization"]
    elif user:
        parts = user.split(":", 1)
        auth = AuthConfig(
            type="basic",
            username=parts[0],
            password=parts[1] if len(parts) > 1 else "",
        )

    # Validate method.
    valid_methods = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
    if method not in valid_methods:
        method = "GET"

    return ParsedCurl(
        method=method,  # type: ignore[arg-type]
        url=url,
        headers=headers,
        body=body,
        auth=auth,
    )


# ---- generator -----------------------------------------------------------


def generate_curl(req: GenerateInput) -> str:
    """Generate a cURL command string from request config."""
    parts = ["curl"]

    if req.method != "GET":
        parts.append(f"-X {req.method}")

    # Auth.
    if req.auth and req.auth.type != "none":
        if req.auth.type == "bearer":
            parts.append(f"-H 'Authorization: Bearer {req.auth.token or ""}'")
        elif req.auth.type == "basic":
            user = req.auth.username or ""
            pwd = req.auth.password or ""
            parts.append(f"-u '{user}:{pwd}'")
        elif req.auth.type == "apikey" and req.auth.key:
            if req.auth.add_to == "query":
                # Will be added as query param to URL.
                sep = "&" if "?" in req.url else "?"
                req.url = f"{req.url}{sep}{req.auth.key}={req.auth.value or ''}"
            else:
                parts.append(f"-H '{req.auth.key}: {req.auth.value or ""}'")

    for name, value in req.headers.items():
        parts.append(f"-H '{name}: {value}'")

    if req.body:
        escaped = req.body.replace("'", "'\\''")
        parts.append(f"--data-raw '{escaped}'")

    parts.append(f"'{req.url}'")

    return " \\\n  ".join(parts)


# ---- endpoints ------------------------------------------------------------


@router.post("/parse", response_model=ParsedCurl)
def parse_endpoint(body: ParseInput) -> ParsedCurl:
    return parse_curl(body.curl)


@router.post("/generate", response_model=GenerateOutput)
def generate_endpoint(body: GenerateInput) -> GenerateOutput:
    return GenerateOutput(curl=generate_curl(body))
