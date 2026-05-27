"""Tests for the rate limit detector API."""

from __future__ import annotations

import time

import pytest
from httpx import ASGITransport, AsyncClient

from theridion_sidecar.main import create_app


@pytest.fixture()
def app():
    return create_app()


@pytest.fixture()
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.anyio
async def test_detect_standard_x_ratelimit_headers(client: AsyncClient):
    """Standard X-RateLimit-* headers are detected."""
    resp = await client.post("/api/ratelimit/analyze", json={
        "headers": {
            "X-RateLimit-Limit": "100",
            "X-RateLimit-Remaining": "42",
            "X-RateLimit-Reset": "1700000000",
        }
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["detected"] is True
    assert data["limit"] == 100
    assert data["remaining"] == 42
    assert data["percentage_used"] == 58.0
    assert "x-ratelimit-limit" in data["headers_found"]
    assert "x-ratelimit-remaining" in data["headers_found"]
    assert "x-ratelimit-reset" in data["headers_found"]


@pytest.mark.anyio
async def test_detect_ietf_ratelimit_headers(client: AsyncClient):
    """IETF draft RateLimit-* headers are detected."""
    resp = await client.post("/api/ratelimit/analyze", json={
        "headers": {
            "RateLimit-Limit": "1000",
            "RateLimit-Remaining": "999",
            "RateLimit-Reset": "60",
        }
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["detected"] is True
    assert data["limit"] == 1000
    assert data["remaining"] == 999
    assert data["percentage_used"] == 0.1
    assert data["provider"] == "IETF Standard"


@pytest.mark.anyio
async def test_detect_retry_after_seconds(client: AsyncClient):
    """Retry-After header with seconds value is detected."""
    resp = await client.post("/api/ratelimit/analyze", json={
        "headers": {
            "Retry-After": "120",
        }
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["detected"] is True
    assert data["retry_after"] == 120
    assert "retry-after" in data["headers_found"]


@pytest.mark.anyio
async def test_detect_retry_after_http_date(client: AsyncClient):
    """Retry-After header with HTTP-date value is detected."""
    # Use a date in the future
    from email.utils import formatdate
    future_ts = time.time() + 300
    http_date = formatdate(timeval=future_ts, usegmt=True)

    resp = await client.post("/api/ratelimit/analyze", json={
        "headers": {
            "Retry-After": http_date,
        }
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["detected"] is True
    assert data["retry_after"] is not None
    # Should be roughly 300 seconds (allow some slack)
    assert 290 <= data["retry_after"] <= 310


@pytest.mark.anyio
async def test_no_rate_limit_headers(client: AsyncClient):
    """When no rate limit headers are present, detected is False."""
    resp = await client.post("/api/ratelimit/analyze", json={
        "headers": {
            "Content-Type": "application/json",
            "Server": "nginx",
        }
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["detected"] is False
    assert data["limit"] is None
    assert data["remaining"] is None
    assert data["headers_found"] == []


@pytest.mark.anyio
async def test_percentage_calculation(client: AsyncClient):
    """Percentage used is calculated correctly."""
    resp = await client.post("/api/ratelimit/analyze", json={
        "headers": {
            "X-RateLimit-Limit": "200",
            "X-RateLimit-Remaining": "50",
        }
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["percentage_used"] == 75.0


@pytest.mark.anyio
async def test_percentage_zero_remaining(client: AsyncClient):
    """Percentage is 100 when remaining is 0."""
    resp = await client.post("/api/ratelimit/analyze", json={
        "headers": {
            "X-RateLimit-Limit": "100",
            "X-RateLimit-Remaining": "0",
        }
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["percentage_used"] == 100.0


@pytest.mark.anyio
async def test_track_and_retrieve_status(client: AsyncClient):
    """Track a URL and retrieve its status."""
    # Track with rate limit headers
    resp = await client.post("/api/ratelimit/track", json={
        "url": "https://api.example.com/v1/users",
        "headers": {
            "X-RateLimit-Limit": "500",
            "X-RateLimit-Remaining": "123",
        }
    })
    assert resp.status_code == 200
    track_data = resp.json()
    assert track_data["tracked"] is True
    url_hash = track_data["url_hash"]

    # Get status
    resp = await client.get("/api/ratelimit/status")
    assert resp.status_code == 200
    status_data = resp.json()
    assert len(status_data["entries"]) >= 1
    entry = next(e for e in status_data["entries"] if e["url_hash"] == url_hash)
    assert entry["limit"] == 500
    assert entry["remaining"] == 123

    # Get history
    resp = await client.get(f"/api/ratelimit/history/{url_hash}")
    assert resp.status_code == 200
    history_data = resp.json()
    assert len(history_data["points"]) == 1
    assert history_data["points"][0]["limit"] == 500


@pytest.mark.anyio
async def test_track_no_ratelimit_headers(client: AsyncClient):
    """Track returns tracked=False when no rate limit headers found."""
    resp = await client.post("/api/ratelimit/track", json={
        "url": "https://api.example.com/no-limits",
        "headers": {
            "Content-Type": "text/html",
        }
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["tracked"] is False


@pytest.mark.anyio
async def test_detect_x_rate_limit_variant(client: AsyncClient):
    """X-Rate-Limit-* (hyphenated) variant is detected as Twitter/X provider."""
    resp = await client.post("/api/ratelimit/analyze", json={
        "headers": {
            "X-Rate-Limit-Limit": "900",
            "X-Rate-Limit-Remaining": "899",
            "X-Rate-Limit-Reset": "1700000000",
        }
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["detected"] is True
    assert data["limit"] == 900
    assert data["remaining"] == 899
    assert data["provider"] == "Twitter/X"


@pytest.mark.anyio
async def test_detect_policy_header(client: AsyncClient):
    """X-RateLimit-Policy header is detected."""
    resp = await client.post("/api/ratelimit/analyze", json={
        "headers": {
            "X-RateLimit-Limit": "100",
            "X-RateLimit-Policy": "100;w=3600",
        }
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["policy"] == "100;w=3600"


@pytest.mark.anyio
async def test_history_empty_for_unknown_hash(client: AsyncClient):
    """History for unknown url_hash returns empty points."""
    resp = await client.get("/api/ratelimit/history/nonexistent123")
    assert resp.status_code == 200
    data = resp.json()
    assert data["points"] == []
