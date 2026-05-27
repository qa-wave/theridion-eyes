"""Tests for the header insights endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_perfect_security_headers(client: TestClient) -> None:
    """All security headers present -> high score."""
    headers = {
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "Content-Security-Policy": "default-src 'self'",
        "X-Frame-Options": "DENY",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "geolocation=(), microphone=()",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-origin",
        "Cross-Origin-Embedder-Policy": "require-corp",
        "X-Permitted-Cross-Domain-Policies": "none",
    }
    resp = client.post("/api/headers/analyze", json={"headers": headers})
    assert resp.status_code == 200
    data = resp.json()
    assert data["score"] == 100
    assert data["grade"] == "A"
    # No recommendations for missing security headers
    security_recs = [r for r in data["recommendations"] if r["severity"] == "high"]
    assert len(security_recs) == 0


def test_missing_all_security_headers(client: TestClient) -> None:
    """No security headers -> low score."""
    headers = {"Content-Type": "application/json"}
    resp = client.post("/api/headers/analyze", json={"headers": headers})
    assert resp.status_code == 200
    data = resp.json()
    assert data["score"] == 0
    assert data["grade"] == "F"
    # Should have recommendations for all missing headers
    assert len(data["recommendations"]) > 5
    missing_findings = [f for f in data["findings"] if f["status"] == "missing"]
    assert len(missing_findings) >= 10  # all security headers missing


def test_caching_no_cache(client: TestClient) -> None:
    """Cache-Control: no-store -> strategy=none."""
    headers = {"Cache-Control": "no-store, no-cache"}
    resp = client.post("/api/headers/analyze", json={"headers": headers})
    assert resp.status_code == 200
    data = resp.json()
    assert data["caching"]["strategy"] == "none"
    assert "no-store" in data["caching"]["directives"]


def test_caching_max_age(client: TestClient) -> None:
    """Cache-Control with max-age."""
    headers = {"Cache-Control": "public, max-age=3600"}
    resp = client.post("/api/headers/analyze", json={"headers": headers})
    assert resp.status_code == 200
    data = resp.json()
    assert data["caching"]["strategy"] == "public"
    assert data["caching"]["effective_ttl"] == 3600


def test_caching_s_maxage(client: TestClient) -> None:
    """s-maxage takes precedence."""
    headers = {"Cache-Control": "public, max-age=60, s-maxage=7200"}
    resp = client.post("/api/headers/analyze", json={"headers": headers})
    assert resp.status_code == 200
    data = resp.json()
    assert data["caching"]["effective_ttl"] == 7200


def test_caching_aggressive(client: TestClient) -> None:
    """Very long max-age -> aggressive strategy."""
    headers = {"Cache-Control": "public, max-age=31536000, immutable"}
    resp = client.post("/api/headers/analyze", json={"headers": headers})
    assert resp.status_code == 200
    data = resp.json()
    assert data["caching"]["strategy"] == "aggressive"


def test_server_info_leak_with_version(client: TestClient) -> None:
    """Server header with version number triggers warning."""
    headers = {"Server": "nginx/1.24.0", "X-Powered-By": "Express 4.18.2"}
    resp = client.post("/api/headers/analyze", json={"headers": headers})
    assert resp.status_code == 200
    data = resp.json()
    leak_findings = [f for f in data["findings"] if f["category"] == "info_leak"]
    assert len(leak_findings) == 2
    assert all(f["status"] == "warning" for f in leak_findings)
    leak_recs = [r for r in data["recommendations"] if r["header"] in ("server", "x-powered-by")]
    assert len(leak_recs) == 2


def test_server_header_no_version(client: TestClient) -> None:
    """Server header without version -> info, not warning."""
    headers = {"Server": "nginx"}
    resp = client.post("/api/headers/analyze", json={"headers": headers})
    assert resp.status_code == 200
    data = resp.json()
    leak_findings = [f for f in data["findings"] if f["category"] == "info_leak"]
    assert len(leak_findings) == 1
    assert leak_findings[0]["status"] == "info"


def test_compression_detected(client: TestClient) -> None:
    """Content-Encoding present -> compression good."""
    headers = {"Content-Encoding": "gzip", "Content-Type": "application/json"}
    resp = client.post("/api/headers/analyze", json={"headers": headers})
    assert resp.status_code == 200
    data = resp.json()
    assert data["compression"]["is_compressed"] is True
    assert data["compression"]["encoding"] == "gzip"


def test_compression_missing_for_text(client: TestClient) -> None:
    """No compression on JSON content -> warning."""
    headers = {"Content-Type": "application/json"}
    resp = client.post("/api/headers/analyze", json={"headers": headers})
    assert resp.status_code == 200
    data = resp.json()
    assert data["compression"]["is_compressed"] is False
    comp_findings = [f for f in data["findings"] if f["category"] == "compression"]
    assert any(f["status"] == "warning" for f in comp_findings)


def test_mixed_headers(client: TestClient) -> None:
    """Real-world mixed headers produce a valid analysis."""
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Content-Encoding": "br",
        "Cache-Control": "private, max-age=300",
        "Strict-Transport-Security": "max-age=63072000",
        "X-Content-Type-Options": "nosniff",
        "Server": "cloudflare",
        "ETag": '"abc123"',
        "Content-Length": "1234",
    }
    resp = client.post("/api/headers/analyze", json={"headers": headers})
    assert resp.status_code == 200
    data = resp.json()
    # Partial security = somewhere between 0 and 100
    assert 0 < data["score"] < 100
    assert data["grade"] in ("B", "C", "D", "F")
    assert data["caching"]["strategy"] == "private"
    assert data["caching"]["effective_ttl"] == 300
    assert data["compression"]["is_compressed"] is True
    assert data["compression"]["encoding"] == "br"
    # Performance findings should include ETag and Content-Length
    perf_findings = [f for f in data["findings"] if f["category"] == "performance"]
    perf_headers = {f["header"] for f in perf_findings}
    assert "ETag" in perf_headers
    assert "Content-Length" in perf_headers


def test_cors_wildcard_warning(client: TestClient) -> None:
    """Access-Control-Allow-Origin: * triggers warning."""
    headers = {"Access-Control-Allow-Origin": "*"}
    resp = client.post("/api/headers/analyze", json={"headers": headers})
    assert resp.status_code == 200
    data = resp.json()
    cors_findings = [
        f for f in data["findings"]
        if f["header"] == "Access-Control-Allow-Origin"
    ]
    assert len(cors_findings) == 1
    assert cors_findings[0]["status"] == "warning"


def test_performance_headers(client: TestClient) -> None:
    """Performance-related headers are detected."""
    headers = {
        "Connection": "keep-alive",
        "Transfer-Encoding": "chunked",
        "Last-Modified": "Thu, 01 Jan 2026 00:00:00 GMT",
    }
    resp = client.post("/api/headers/analyze", json={"headers": headers})
    assert resp.status_code == 200
    data = resp.json()
    perf_findings = [f for f in data["findings"] if f["category"] == "performance"]
    assert len(perf_findings) >= 3
    perf_headers = {f["header"] for f in perf_findings}
    assert "Connection" in perf_headers
    assert "Transfer-Encoding" in perf_headers
    assert "Last-Modified" in perf_headers
