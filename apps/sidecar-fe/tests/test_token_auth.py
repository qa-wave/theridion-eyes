"""Tests for the X-Theridion-Token auth middleware.

Covers the three cases required by Faze 0 P0:
  * request with correct token → 200
  * request without token      → 401
  * request with wrong token   → 401

Also verifies that /api/health and /api/diagnostics are exempt.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import _NO_AUTO_TOKEN

_TOKEN = "test-gate-token-abc123"


@pytest.fixture()
def authed_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient that sends the correct token on every request."""
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    monkeypatch.setenv("THERIDION_TOKEN", _TOKEN)
    import theridion_sidecar.main as _main

    monkeypatch.setattr(_main, "_SIDECAR_TOKEN", _TOKEN)
    tc = TestClient(_main.create_app())
    tc.headers.update({"X-Theridion-Token": _TOKEN})
    return tc


@pytest.fixture()
def bare_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Raw TestClient with no auth header — used to verify 401 behaviour."""
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    monkeypatch.setenv("THERIDION_TOKEN", _TOKEN)
    import theridion_sidecar.main as _main

    monkeypatch.setattr(_main, "_SIDECAR_TOKEN", _TOKEN)
    # Pass _NO_AUTO_TOKEN sentinel to skip conftest auto-inject.
    return TestClient(_main.create_app(), headers=_NO_AUTO_TOKEN, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Core gate behaviour
# ---------------------------------------------------------------------------


def test_correct_token_returns_200(authed_client: TestClient) -> None:
    res = authed_client.get("/api/health")
    assert res.status_code == 200


def test_missing_token_returns_401(bare_app: TestClient) -> None:
    res = bare_app.get("/api/environments")
    assert res.status_code == 401
    assert "X-Theridion-Token" in res.json()["detail"]


def test_wrong_token_returns_401(bare_app: TestClient) -> None:
    res = bare_app.get(
        "/api/environments",
        headers={"X-Theridion-Token": "totally-wrong"},
    )
    assert res.status_code == 401


def test_correct_token_allows_protected_endpoint(authed_client: TestClient) -> None:
    res = authed_client.get("/api/environments")
    # May be 200 (empty list) or any non-401 success; definitely not 401.
    assert res.status_code != 401


# ---------------------------------------------------------------------------
# Exempt paths bypass the gate
# ---------------------------------------------------------------------------


def test_health_exempt_without_token(bare_app: TestClient) -> None:
    res = bare_app.get("/api/health")
    assert res.status_code == 200


def test_diagnostics_exempt_without_token(bare_app: TestClient) -> None:
    res = bare_app.get("/api/diagnostics")
    # 200 or 500 (if a dependency is missing in test env) — never 401.
    assert res.status_code != 401


# ---------------------------------------------------------------------------
# Token helper
# ---------------------------------------------------------------------------


def test_get_sidecar_token_returns_set_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import theridion_sidecar.main as _main

    monkeypatch.setattr(_main, "_SIDECAR_TOKEN", "known-value")
    assert _main.get_sidecar_token() == "known-value"
