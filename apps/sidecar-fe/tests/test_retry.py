"""Tests for the configurable retry with backoff endpoint."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from theridion_sidecar.api.retry import compute_backoff_ms
from theridion_sidecar.main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_URL = "http://testserver"


def _make_execute_response(status: int = 200, headers: dict | None = None):
    """Build a minimal ExecuteResponse-like object."""
    from theridion_sidecar.api.requests import ExecuteResponse

    return ExecuteResponse(
        status=status,
        status_text="OK" if status == 200 else "Error",
        headers=headers or {},
        body="{}",
        body_size_bytes=2,
        elapsed_ms=42.0,
        timing=None,
        final_url="http://example.com/test",
        resolved_url=None,
        cookies={},
    )


@pytest.fixture()
def client():
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    return AsyncClient(transport=transport, base_url=_BASE_URL)


# ---------------------------------------------------------------------------
# Unit tests for backoff computation
# ---------------------------------------------------------------------------


class TestComputeBackoff:
    def test_fixed(self):
        assert compute_backoff_ms("fixed", 1, 1000, 30000) == 1000
        assert compute_backoff_ms("fixed", 3, 1000, 30000) == 1000

    def test_linear(self):
        assert compute_backoff_ms("linear", 1, 1000, 30000) == 1000
        assert compute_backoff_ms("linear", 3, 1000, 30000) == 3000

    def test_exponential(self):
        assert compute_backoff_ms("exponential", 1, 1000, 30000) == 2000
        assert compute_backoff_ms("exponential", 2, 1000, 30000) == 4000
        assert compute_backoff_ms("exponential", 3, 1000, 30000) == 8000

    def test_exponential_capped(self):
        result = compute_backoff_ms("exponential", 10, 1000, 5000)
        assert result == 5000

    def test_jitter_within_bounds(self):
        for _ in range(50):
            val = compute_backoff_ms("jitter", 1, 1000, 30000)
            # exponential part = 2000, jitter adds 0..1000, so range [2000, 3000]
            assert 2000 <= val <= 3000

    def test_linear_capped(self):
        result = compute_backoff_ms("linear", 100, 1000, 5000)
        assert result == 5000


# ---------------------------------------------------------------------------
# Integration tests (mocked execute)
# ---------------------------------------------------------------------------


@pytest.mark.anyio()
async def test_retry_on_503_then_success(client: AsyncClient):
    """503 twice then 200 => retried=True, 3 attempts."""
    call_count = 0

    async def mock_execute(req):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return _make_execute_response(503)
        return _make_execute_response(200)

    with patch("theridion_sidecar.api.retry.execute", side_effect=mock_execute):
        resp = await client.post("/api/requests/execute-with-retry", json={
            "method": "GET",
            "url": "http://example.com/test",
            "retry": {
                "max_retries": 5,
                "retry_on": [503],
                "backoff_strategy": "fixed",
                "backoff_base_ms": 10,
                "backoff_max_ms": 100,
            },
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["retried"] is True
    assert len(data["attempts"]) == 3
    assert data["attempts"][0]["status"] == 503
    assert data["attempts"][1]["status"] == 503
    assert data["attempts"][2]["status"] == 200
    assert data["final_response"]["status"] == 200


@pytest.mark.anyio()
async def test_max_retries_respected(client: AsyncClient):
    """Always 503 => stops after max_retries attempts."""
    async def mock_execute(req):
        return _make_execute_response(503)

    with patch("theridion_sidecar.api.retry.execute", side_effect=mock_execute):
        resp = await client.post("/api/requests/execute-with-retry", json={
            "method": "GET",
            "url": "http://example.com/test",
            "retry": {
                "max_retries": 3,
                "retry_on": [503],
                "backoff_strategy": "fixed",
                "backoff_base_ms": 10,
                "backoff_max_ms": 100,
            },
        })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["attempts"]) == 3
    assert data["final_response"]["status"] == 503
    assert data["retried"] is True


@pytest.mark.anyio()
async def test_no_retry_on_success(client: AsyncClient):
    """200 on first try => no retry."""
    async def mock_execute(req):
        return _make_execute_response(200)

    with patch("theridion_sidecar.api.retry.execute", side_effect=mock_execute):
        resp = await client.post("/api/requests/execute-with-retry", json={
            "method": "GET",
            "url": "http://example.com/test",
            "retry": {
                "max_retries": 3,
                "retry_on": [503],
                "backoff_strategy": "exponential",
                "backoff_base_ms": 1000,
                "backoff_max_ms": 30000,
            },
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["retried"] is False
    assert len(data["attempts"]) == 1
    assert data["attempts"][0]["status"] == 200
    assert data["attempts"][0]["waited_ms"] == 0


@pytest.mark.anyio()
async def test_retry_after_header_respected(client: AsyncClient):
    """Server sends Retry-After: 0.01 => we respect it."""
    call_count = 0

    async def mock_execute(req):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_execute_response(429, headers={"Retry-After": "0.01"})
        return _make_execute_response(200)

    with patch("theridion_sidecar.api.retry.execute", side_effect=mock_execute):
        resp = await client.post("/api/requests/execute-with-retry", json={
            "method": "GET",
            "url": "http://example.com/test",
            "retry": {
                "max_retries": 3,
                "retry_on": [429],
                "backoff_strategy": "exponential",
                "backoff_base_ms": 5000,
                "backoff_max_ms": 30000,
            },
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["retried"] is True
    # Retry-After = 0.01s = 10ms should override the exponential 10000ms
    assert data["attempts"][0]["waited_ms"] == 10.0


@pytest.mark.anyio()
async def test_non_retryable_status_not_retried(client: AsyncClient):
    """404 is not in retry_on => no retry."""
    async def mock_execute(req):
        return _make_execute_response(404)

    with patch("theridion_sidecar.api.retry.execute", side_effect=mock_execute):
        resp = await client.post("/api/requests/execute-with-retry", json={
            "method": "GET",
            "url": "http://example.com/test",
            "retry": {
                "max_retries": 3,
                "retry_on": [503],
                "backoff_strategy": "fixed",
                "backoff_base_ms": 10,
                "backoff_max_ms": 100,
            },
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["retried"] is False
    assert len(data["attempts"]) == 1
    assert data["final_response"]["status"] == 404


@pytest.mark.anyio()
async def test_backoff_timing_verification(client: AsyncClient):
    """Verify that waited_ms values follow the chosen strategy."""
    call_count = 0

    async def mock_execute(req):
        nonlocal call_count
        call_count += 1
        if call_count <= 3:
            return _make_execute_response(503)
        return _make_execute_response(200)

    with patch("theridion_sidecar.api.retry.execute", side_effect=mock_execute):
        resp = await client.post("/api/requests/execute-with-retry", json={
            "method": "GET",
            "url": "http://example.com/test",
            "retry": {
                "max_retries": 5,
                "retry_on": [503],
                "backoff_strategy": "linear",
                "backoff_base_ms": 10,
                "backoff_max_ms": 30000,
            },
        })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["attempts"]) == 4
    # Linear: attempt 1 = 10ms, attempt 2 = 20ms, attempt 3 = 30ms
    assert data["attempts"][0]["waited_ms"] == 10.0
    assert data["attempts"][1]["waited_ms"] == 20.0
    assert data["attempts"][2]["waited_ms"] == 30.0
    assert data["attempts"][3]["waited_ms"] == 0  # final success, no wait
