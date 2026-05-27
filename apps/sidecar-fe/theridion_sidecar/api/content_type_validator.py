"""Content-Type validator — compare declared vs detected content type."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class ContentTypeRequest(BaseModel):
    content_type: str = Field(default="")
    body: str = Field(default="")


class ContentTypeResult(BaseModel):
    declared: str
    detected: str
    match: bool
    details: str


def _detect_type(body: str) -> str:
    stripped = body.lstrip()
    if not stripped:
        return "empty"
    if stripped.startswith("{") or stripped.startswith("["):
        return "application/json"
    if stripped.startswith("<"):
        lower = stripped[:200].lower()
        if "<!doctype html" in lower or "<html" in lower:
            return "text/html"
        return "application/xml"
    return "text/plain"


@router.post("/content-type", response_model=ContentTypeResult)
async def content_type_validator(req: ContentTypeRequest) -> ContentTypeResult:
    declared = req.content_type.split(";")[0].strip().lower() if req.content_type else ""
    detected = _detect_type(req.body)

    # Normalize for comparison
    match = False
    if declared == detected:
        match = True
    elif declared in ("text/xml", "application/xml") and detected == "application/xml":
        match = True
    elif declared == "text/html" and detected == "text/html":
        match = True

    details = "Content types match" if match else f"Declared '{declared}' but body looks like '{detected}'"

    return ContentTypeResult(
        declared=declared or "(none)",
        detected=detected,
        match=match,
        details=details,
    )
