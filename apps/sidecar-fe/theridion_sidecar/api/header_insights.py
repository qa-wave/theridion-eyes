"""Response header insights — security scoring, caching analysis, recommendations."""

from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/headers", tags=["headers"])


# ---- Models ----


class HeaderFinding(BaseModel):
    category: Literal["security", "caching", "performance", "info_leak", "compression"]
    header: str
    status: Literal["good", "warning", "missing", "info"]
    message: str
    recommendation: str = ""


class Recommendation(BaseModel):
    header: str
    severity: Literal["high", "medium", "low"]
    message: str
    suggested_value: str = ""


class CachingAnalysis(BaseModel):
    strategy: Literal["none", "private", "public", "aggressive"]
    directives: list[str]
    effective_ttl: int | None = None  # seconds
    summary: str


class CompressionAnalysis(BaseModel):
    encoding: str | None = None
    is_compressed: bool = False
    message: str


class HeaderInsightsRequest(BaseModel):
    headers: dict[str, str]


class HeaderInsightsResponse(BaseModel):
    score: int
    grade: Literal["A", "B", "C", "D", "F"]
    findings: list[HeaderFinding]
    recommendations: list[Recommendation]
    caching: CachingAnalysis
    compression: CompressionAnalysis


# ---- Security header definitions ----

SECURITY_HEADERS = [
    {"name": "strict-transport-security", "label": "HSTS", "weight": 15, "severity": "high",
     "suggested": "max-age=31536000; includeSubDomains"},
    {"name": "content-security-policy", "label": "CSP", "weight": 15, "severity": "high",
     "suggested": "default-src 'self'"},
    {"name": "x-frame-options", "label": "X-Frame-Options", "weight": 12, "severity": "medium",
     "suggested": "DENY"},
    {"name": "x-content-type-options", "label": "X-Content-Type-Options", "weight": 12, "severity": "medium",
     "suggested": "nosniff"},
    {"name": "referrer-policy", "label": "Referrer-Policy", "weight": 10, "severity": "medium",
     "suggested": "strict-origin-when-cross-origin"},
    {"name": "permissions-policy", "label": "Permissions-Policy", "weight": 10, "severity": "medium",
     "suggested": "geolocation=(), microphone=(), camera=()"},
    {"name": "cross-origin-opener-policy", "label": "COOP", "weight": 8, "severity": "low",
     "suggested": "same-origin"},
    {"name": "cross-origin-resource-policy", "label": "CORP", "weight": 8, "severity": "low",
     "suggested": "same-origin"},
    {"name": "cross-origin-embedder-policy", "label": "COEP", "weight": 5, "severity": "low",
     "suggested": "require-corp"},
    {"name": "x-permitted-cross-domain-policies", "label": "X-Permitted-Cross-Domain-Policies", "weight": 5, "severity": "low",
     "suggested": "none"},
]

# Total possible weight
_MAX_WEIGHT = sum(h["weight"] for h in SECURITY_HEADERS)


def _normalize_headers(headers: dict[str, str]) -> dict[str, str]:
    """Lowercase all header names for consistent lookup."""
    return {k.lower(): v for k, v in headers.items()}


def _analyze_security(lower: dict[str, str]) -> tuple[int, list[HeaderFinding], list[Recommendation]]:
    """Check security headers, return (score_points, findings, recommendations)."""
    earned = 0
    findings: list[HeaderFinding] = []
    recommendations: list[Recommendation] = []

    for hdef in SECURITY_HEADERS:
        name = hdef["name"]
        if name in lower:
            earned += hdef["weight"]
            findings.append(HeaderFinding(
                category="security",
                header=hdef["label"],
                status="good",
                message=f"{hdef['label']} is set: {lower[name][:80]}",
            ))
        else:
            findings.append(HeaderFinding(
                category="security",
                header=hdef["label"],
                status="missing",
                message=f"{hdef['label']} header is missing",
                recommendation=f"Add {name}: {hdef['suggested']}",
            ))
            recommendations.append(Recommendation(
                header=name,
                severity=hdef["severity"],  # type: ignore[arg-type]
                message=f"Missing {hdef['label']} header",
                suggested_value=hdef["suggested"],
            ))

    # CORS analysis
    if "access-control-allow-origin" in lower:
        origin = lower["access-control-allow-origin"]
        if origin == "*":
            findings.append(HeaderFinding(
                category="security",
                header="Access-Control-Allow-Origin",
                status="warning",
                message="CORS allows all origins (*) — overly permissive",
                recommendation="Restrict to specific trusted origins",
            ))
            recommendations.append(Recommendation(
                header="access-control-allow-origin",
                severity="medium",
                message="CORS allows all origins — restrict to trusted domains",
                suggested_value="https://yourdomain.com",
            ))
        else:
            findings.append(HeaderFinding(
                category="security",
                header="Access-Control-Allow-Origin",
                status="good",
                message=f"CORS restricted to: {origin}",
            ))

    score = round((earned / _MAX_WEIGHT) * 100) if _MAX_WEIGHT > 0 else 0
    return score, findings, recommendations


def _analyze_caching(lower: dict[str, str]) -> tuple[CachingAnalysis, list[HeaderFinding]]:
    """Parse Cache-Control and related headers."""
    findings: list[HeaderFinding] = []
    cc = lower.get("cache-control", "")

    if not cc:
        # No cache-control at all
        findings.append(HeaderFinding(
            category="caching",
            header="Cache-Control",
            status="missing",
            message="No Cache-Control header — browser will use heuristic caching",
            recommendation="Add Cache-Control header to control caching behavior",
        ))
        return CachingAnalysis(
            strategy="none",
            directives=[],
            effective_ttl=None,
            summary="No caching directives present",
        ), findings

    directives = [d.strip().lower() for d in cc.split(",")]

    # Determine strategy
    strategy: Literal["none", "private", "public", "aggressive"] = "none"
    ttl: int | None = None

    if "no-store" in directives or "no-cache" in directives:
        strategy = "none"
        findings.append(HeaderFinding(
            category="caching",
            header="Cache-Control",
            status="info",
            message="Caching disabled (no-store/no-cache)",
        ))
    elif "private" in directives:
        strategy = "private"
        findings.append(HeaderFinding(
            category="caching",
            header="Cache-Control",
            status="info",
            message="Private caching — only browser cache, no CDN/proxy",
        ))
    elif "public" in directives:
        strategy = "public"
        findings.append(HeaderFinding(
            category="caching",
            header="Cache-Control",
            status="good",
            message="Public caching enabled — CDN/proxy can cache",
        ))
    elif any(d.startswith("max-age") for d in directives):
        strategy = "private"  # default is private when not specified

    # Extract max-age / s-maxage
    for d in directives:
        m = re.match(r"s-maxage=(\d+)", d)
        if m:
            ttl = int(m.group(1))
            break
        m = re.match(r"max-age=(\d+)", d)
        if m:
            ttl = int(m.group(1))

    if ttl is not None:
        if ttl >= 31536000:
            strategy = "aggressive"
            findings.append(HeaderFinding(
                category="caching",
                header="Cache-Control",
                status="good",
                message=f"Aggressive caching (TTL={ttl}s / ~{ttl // 86400} days)",
            ))
        elif ttl > 0:
            findings.append(HeaderFinding(
                category="caching",
                header="Cache-Control",
                status="good",
                message=f"TTL={ttl}s (~{ttl // 60} minutes)",
            ))

    # Check for immutable
    if "immutable" in directives:
        strategy = "aggressive"
        findings.append(HeaderFinding(
            category="caching",
            header="Cache-Control",
            status="good",
            message="immutable directive — content will not change",
        ))

    summary_map = {
        "none": "No caching — every request goes to server",
        "private": "Private/browser-only caching",
        "public": "Public caching — CDN and proxies can cache",
        "aggressive": "Aggressive caching — long TTL or immutable",
    }

    return CachingAnalysis(
        strategy=strategy,
        directives=directives,
        effective_ttl=ttl,
        summary=summary_map[strategy],
    ), findings


def _analyze_compression(lower: dict[str, str]) -> tuple[CompressionAnalysis, list[HeaderFinding]]:
    """Check Content-Encoding for compression."""
    findings: list[HeaderFinding] = []
    encoding = lower.get("content-encoding")

    if encoding:
        findings.append(HeaderFinding(
            category="compression",
            header="Content-Encoding",
            status="good",
            message=f"Response is compressed with {encoding}",
        ))
        return CompressionAnalysis(
            encoding=encoding,
            is_compressed=True,
            message=f"Compressed with {encoding}",
        ), findings

    # Not compressed
    ct = lower.get("content-type", "")
    compressible = any(t in ct for t in ["json", "xml", "html", "text", "javascript", "css"])

    if compressible:
        findings.append(HeaderFinding(
            category="compression",
            header="Content-Encoding",
            status="warning",
            message="Response is not compressed (text-based content detected)",
            recommendation="Enable gzip/br compression to reduce transfer size (~60-80% savings)",
        ))
    else:
        findings.append(HeaderFinding(
            category="compression",
            header="Content-Encoding",
            status="info",
            message="No compression (content type may not benefit from compression)",
        ))

    return CompressionAnalysis(
        encoding=None,
        is_compressed=False,
        message="Not compressed" + (" — compressible content detected" if compressible else ""),
    ), findings


def _analyze_info_leak(lower: dict[str, str]) -> tuple[list[HeaderFinding], list[Recommendation]]:
    """Check for information leakage headers."""
    findings: list[HeaderFinding] = []
    recommendations: list[Recommendation] = []

    server = lower.get("server")
    if server:
        # Check if it reveals version info
        has_version = bool(re.search(r"\d+\.\d+", server))
        if has_version:
            findings.append(HeaderFinding(
                category="info_leak",
                header="Server",
                status="warning",
                message=f"Server header exposes version info: {server}",
                recommendation="Remove or generalize the Server header",
            ))
            recommendations.append(Recommendation(
                header="server",
                severity="medium",
                message=f"Server header reveals technology/version: {server}",
                suggested_value="(remove or set to generic value)",
            ))
        else:
            findings.append(HeaderFinding(
                category="info_leak",
                header="Server",
                status="info",
                message=f"Server: {server}",
            ))

    x_powered = lower.get("x-powered-by")
    if x_powered:
        findings.append(HeaderFinding(
            category="info_leak",
            header="X-Powered-By",
            status="warning",
            message=f"X-Powered-By exposes technology: {x_powered}",
            recommendation="Remove X-Powered-By header",
        ))
        recommendations.append(Recommendation(
            header="x-powered-by",
            severity="medium",
            message=f"X-Powered-By reveals framework: {x_powered}",
            suggested_value="(remove this header entirely)",
        ))

    x_aspnet = lower.get("x-aspnet-version")
    if x_aspnet:
        findings.append(HeaderFinding(
            category="info_leak",
            header="X-AspNet-Version",
            status="warning",
            message=f"X-AspNet-Version exposes framework version: {x_aspnet}",
            recommendation="Remove X-AspNet-Version header",
        ))
        recommendations.append(Recommendation(
            header="x-aspnet-version",
            severity="medium",
            message=f"Reveals ASP.NET version: {x_aspnet}",
            suggested_value="(remove this header entirely)",
        ))

    return findings, recommendations


def _analyze_performance(lower: dict[str, str]) -> list[HeaderFinding]:
    """Analyze performance-related headers."""
    findings: list[HeaderFinding] = []

    # Connection / Keep-Alive
    connection = lower.get("connection", "").lower()
    if connection == "keep-alive" or "keep-alive" in lower:
        findings.append(HeaderFinding(
            category="performance",
            header="Connection",
            status="good",
            message="Keep-Alive enabled — connection reuse",
        ))
    elif connection == "close":
        findings.append(HeaderFinding(
            category="performance",
            header="Connection",
            status="warning",
            message="Connection: close — no connection reuse",
            recommendation="Consider enabling keep-alive for better performance",
        ))

    # Transfer-Encoding
    te = lower.get("transfer-encoding", "").lower()
    if "chunked" in te:
        findings.append(HeaderFinding(
            category="performance",
            header="Transfer-Encoding",
            status="info",
            message="Chunked transfer encoding — streaming response",
        ))

    # Content-Length presence
    if "content-length" in lower:
        findings.append(HeaderFinding(
            category="performance",
            header="Content-Length",
            status="good",
            message=f"Content-Length present: {lower['content-length']} bytes",
        ))

    # ETag / Last-Modified for conditional requests
    if "etag" in lower:
        findings.append(HeaderFinding(
            category="performance",
            header="ETag",
            status="good",
            message="ETag present — supports conditional requests (304)",
        ))
    if "last-modified" in lower:
        findings.append(HeaderFinding(
            category="performance",
            header="Last-Modified",
            status="good",
            message="Last-Modified present — supports conditional requests",
        ))

    return findings


def _compute_grade(score: int) -> Literal["A", "B", "C", "D", "F"]:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 55:
        return "C"
    if score >= 35:
        return "D"
    return "F"


@router.post("/analyze", response_model=HeaderInsightsResponse)
async def analyze_headers(req: HeaderInsightsRequest) -> HeaderInsightsResponse:
    """Analyze response headers for security, caching, performance, and info leaks."""
    lower = _normalize_headers(req.headers)

    # Security analysis
    score, sec_findings, sec_recs = _analyze_security(lower)

    # Caching analysis
    caching, cache_findings = _analyze_caching(lower)

    # Compression analysis
    compression, comp_findings = _analyze_compression(lower)

    # Info leak analysis
    leak_findings, leak_recs = _analyze_info_leak(lower)

    # Performance analysis
    perf_findings = _analyze_performance(lower)

    # Combine all
    all_findings = sec_findings + cache_findings + comp_findings + leak_findings + perf_findings
    all_recommendations = sec_recs + leak_recs

    # Add cache recommendation if missing
    if caching.strategy == "none" and not any(r.header == "cache-control" for r in all_recommendations):
        all_recommendations.append(Recommendation(
            header="cache-control",
            severity="low",
            message="No caching strategy defined",
            suggested_value="public, max-age=3600",
        ))

    # Add compression recommendation
    if not compression.is_compressed:
        ct = lower.get("content-type", "")
        if any(t in ct for t in ["json", "xml", "html", "text", "javascript", "css"]):
            all_recommendations.append(Recommendation(
                header="content-encoding",
                severity="low",
                message="Enable compression for text-based content",
                suggested_value="gzip (or br for Brotli)",
            ))

    grade = _compute_grade(score)

    return HeaderInsightsResponse(
        score=score,
        grade=grade,
        findings=all_findings,
        recommendations=all_recommendations,
        caching=caching,
        compression=compression,
    )
