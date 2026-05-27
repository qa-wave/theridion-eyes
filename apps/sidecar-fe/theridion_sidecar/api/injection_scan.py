"""Injection scan — test parameters for SQL injection vulnerabilities."""

from __future__ import annotations

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/security", tags=["security"])

_SQL_PAYLOADS = [
    "' OR '1'='1",
    "1; DROP TABLE users--",
    "' UNION SELECT NULL--",
    "1' AND '1'='1",
    "admin'--",
]

_SUSPICIOUS_PATTERNS = [
    "sql", "syntax", "mysql", "postgresql", "sqlite",
    "ora-", "mssql", "unterminated", "unexpected",
    "warning", "error in your sql",
]


class InjectionScanRequest(BaseModel):
    url: str = Field(..., min_length=1)
    method: str = "GET"
    params: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)


class Finding(BaseModel):
    param: str
    payload: str
    response_status: int
    suspicious: bool
    evidence: str


class InjectionScanResult(BaseModel):
    vulnerable: bool
    findings: list[Finding]


@router.post("/injection-scan", response_model=InjectionScanResult)
async def injection_scan(req: InjectionScanRequest) -> InjectionScanResult:
    findings: list[Finding] = []

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        for param_name, original_value in req.params.items():
            for payload in _SQL_PAYLOADS:
                test_params = {**req.params, param_name: payload}
                try:
                    if req.method.upper() == "GET":
                        resp = await client.get(req.url, params=test_params,
                                                headers=req.headers)
                    else:
                        resp = await client.request(
                            method=req.method, url=req.url,
                            params=test_params, headers=req.headers,
                        )

                    body_lower = resp.text.lower()
                    suspicious = any(p in body_lower for p in _SUSPICIOUS_PATTERNS)
                    evidence = ""
                    if suspicious:
                        for p in _SUSPICIOUS_PATTERNS:
                            if p in body_lower:
                                idx = body_lower.index(p)
                                start = max(0, idx - 20)
                                end = min(len(resp.text), idx + len(p) + 20)
                                evidence = resp.text[start:end]
                                break

                    if suspicious or resp.status_code == 500:
                        findings.append(Finding(
                            param=param_name,
                            payload=payload,
                            response_status=resp.status_code,
                            suspicious=suspicious,
                            evidence=evidence,
                        ))
                except httpx.RequestError:
                    continue

    return InjectionScanResult(
        vulnerable=any(f.suspicious for f in findings),
        findings=findings,
    )
