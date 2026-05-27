"""Security header audit — analyze response headers for best practices."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class SecurityAuditRequest(BaseModel):
    headers: dict[str, str] = Field(default_factory=dict)


class Finding(BaseModel):
    header: str
    status: Literal["pass", "warn", "fail"]
    message: str


class SecurityAuditResult(BaseModel):
    score: int = Field(ge=0, le=100)
    findings: list[Finding]


_CHECKS: list[tuple[str, str, bool]] = [
    ("strict-transport-security", "HSTS header protects against protocol downgrade attacks", True),
    ("content-security-policy", "CSP header mitigates XSS and injection attacks", True),
    ("x-frame-options", "X-Frame-Options prevents clickjacking", True),
    ("x-content-type-options", "X-Content-Type-Options prevents MIME sniffing", True),
    ("referrer-policy", "Referrer-Policy controls referrer information leakage", False),
    ("permissions-policy", "Permissions-Policy restricts browser feature access", False),
]


def _check_cookies(headers: dict[str, str]) -> list[Finding]:
    findings: list[Finding] = []
    set_cookie = headers.get("set-cookie", "")
    if not set_cookie:
        return findings
    lower = set_cookie.lower()
    if "secure" not in lower:
        findings.append(Finding(header="Set-Cookie", status="fail", message="Cookie missing Secure flag"))
    else:
        findings.append(Finding(header="Set-Cookie:Secure", status="pass", message="Secure flag present"))
    if "httponly" not in lower:
        findings.append(Finding(header="Set-Cookie", status="warn", message="Cookie missing HttpOnly flag"))
    else:
        findings.append(Finding(header="Set-Cookie:HttpOnly", status="pass", message="HttpOnly flag present"))
    if "samesite" not in lower:
        findings.append(Finding(header="Set-Cookie", status="warn", message="Cookie missing SameSite attribute"))
    else:
        findings.append(Finding(header="Set-Cookie:SameSite", status="pass", message="SameSite attribute present"))
    return findings


@router.post("/security-audit", response_model=SecurityAuditResult)
async def security_audit(req: SecurityAuditRequest) -> SecurityAuditResult:
    lower_headers = {k.lower(): v for k, v in req.headers.items()}
    findings: list[Finding] = []
    max_score = 0
    earned = 0

    for header_name, description, critical in _CHECKS:
        weight = 15 if critical else 5
        max_score += weight
        if header_name in lower_headers:
            findings.append(Finding(header=header_name, status="pass", message=f"{description} — present"))
            earned += weight
        else:
            status: Literal["pass", "warn", "fail"] = "fail" if critical else "warn"
            findings.append(Finding(header=header_name, status=status, message=f"{description} — missing"))

    # CORS check
    max_score += 10
    acao = lower_headers.get("access-control-allow-origin", "")
    if acao == "*":
        findings.append(Finding(header="access-control-allow-origin", status="warn", message="Wildcard CORS origin — consider restricting"))
        earned += 5
    elif acao:
        findings.append(Finding(header="access-control-allow-origin", status="pass", message="CORS origin is restricted"))
        earned += 10
    else:
        findings.append(Finding(header="access-control-allow-origin", status="pass", message="No CORS header — same-origin only"))
        earned += 10

    cookie_findings = _check_cookies(lower_headers)
    if cookie_findings:
        cookie_max = len(cookie_findings) * 5
        max_score += cookie_max
        for f in cookie_findings:
            findings.append(f)
            if f.status == "pass":
                earned += 5

    score = round(earned / max_score * 100) if max_score > 0 else 100
    return SecurityAuditResult(score=score, findings=findings)
