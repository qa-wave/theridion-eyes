"""Sensitive data scanner — regex scan for PII, secrets, tokens."""

from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/security", tags=["security"])


class SensitiveDataRequest(BaseModel):
    body: str = ""
    headers: dict[str, str] = Field(default_factory=dict)


class SensitiveFinding(BaseModel):
    type: str
    value_preview: str
    location: str
    line: int


class SensitiveDataResult(BaseModel):
    findings: list[SensitiveFinding]
    count: int
    risk_level: Literal["none", "low", "medium", "high"]


_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    ("email", "Email address", re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")),
    ("credit_card", "Credit card number", re.compile(r"\b(?:\d[ -]*?){13,19}\b")),
    ("ssn", "Social Security Number", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("aws_key", "AWS Access Key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("aws_secret", "AWS Secret Key", re.compile(r"(?i)aws.{0,20}['\"][0-9a-zA-Z/+]{40}['\"]")),
    ("jwt", "JWT Token", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("private_key", "Private Key", re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----")),
    ("api_key", "API Key pattern", re.compile(r"(?i)(?:api[_-]?key|apikey|api_secret)['\"]?\s*[:=]\s*['\"]?[a-zA-Z0-9_-]{16,}")),
]


def _preview(value: str, max_len: int = 20) -> str:
    if len(value) <= max_len:
        return value
    return value[:8] + "..." + value[-4:]


def _luhn_check(number: str) -> bool:
    """Basic Luhn algorithm check for credit card numbers."""
    digits = [int(d) for d in number if d.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    reverse = digits[::-1]
    for i, d in enumerate(reverse):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def _scan_text(text: str, location: str) -> list[SensitiveFinding]:
    findings: list[SensitiveFinding] = []
    lines = text.split("\n")
    for line_num, line in enumerate(lines, 1):
        for type_name, _, pattern in _PATTERNS:
            for match in pattern.finditer(line):
                value = match.group(0)
                # Extra validation for credit cards
                if type_name == "credit_card":
                    if not _luhn_check(value):
                        continue
                findings.append(SensitiveFinding(
                    type=type_name,
                    value_preview=_preview(value),
                    location=location,
                    line=line_num,
                ))
    return findings


@router.post("/sensitive-scan", response_model=SensitiveDataResult)
async def sensitive_scan(req: SensitiveDataRequest) -> SensitiveDataResult:
    findings: list[SensitiveFinding] = []

    if req.body:
        findings.extend(_scan_text(req.body, "body"))

    header_text = "\n".join(f"{k}: {v}" for k, v in req.headers.items())
    if header_text:
        for f in _scan_text(header_text, "header"):
            findings.append(f)

    count = len(findings)
    if count == 0:
        risk = "none"
    elif count <= 2:
        risk = "low"
    elif count <= 5:
        risk = "medium"
    else:
        risk = "high"

    return SensitiveDataResult(
        findings=findings,
        count=count,
        risk_level=risk,
    )
