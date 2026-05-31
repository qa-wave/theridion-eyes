"""Tests for publish-config persistence and _publish_run_result_v2 integration.

Coverage:
  - GET /api/silk/publish-config  — defaults when nothing saved
  - PUT /api/silk/publish-config  — roundtrip, token masking, token preservation
  - publish_config module          — load/save/defaults
  - _publish_run_result_v2         — uses persisted config over env vars (mocked network)
  - _publish_run_result_v2         — falls back to env when config disabled
  - _publish_run_result_v2         — no-op when nothing configured
  - Token is never returned in plain text from the GET endpoint
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    # Clear any inherited EYES_* env vars that could bleed into tests.
    for k in ("EYES_HUB_URL", "EYES_WEAVE_URL", "EYES_TOKEN"):
        monkeypatch.delenv(k, raising=False)

    import theridion_sidecar.main as _main

    return TestClient(_main.create_app())


# ---------------------------------------------------------------------------
# GET /api/silk/publish-config — defaults
# ---------------------------------------------------------------------------


def test_get_publish_config_defaults(client: TestClient) -> None:
    r = client.get("/api/silk/publish-config")
    assert r.status_code == 200
    data = r.json()
    assert data["weave_url"] == ""
    assert data["hub_url"] == ""
    assert data["enabled"] is False
    assert data["weave_token_set"] is False
    assert data["hub_token_set"] is False
    # Token values must never appear in response
    assert "weave_token" not in data
    assert "hub_token" not in data


# ---------------------------------------------------------------------------
# PUT /api/silk/publish-config — roundtrip
# ---------------------------------------------------------------------------


def test_put_publish_config_roundtrip(client: TestClient) -> None:
    payload = {
        "weave_url": "https://weave.example.com/api/runs/ingest",
        "weave_token": "secret-weave-token",
        "hub_url": "",
        "hub_token": "",
        "enabled": True,
    }
    r = client.put("/api/silk/publish-config", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["weave_url"] == "https://weave.example.com/api/runs/ingest"
    assert data["weave_token_set"] is True
    assert data["hub_token_set"] is False
    assert data["enabled"] is True
    # Plain token must NOT appear in response
    assert "weave_token" not in data

    # GET should return the same shape
    r2 = client.get("/api/silk/publish-config")
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["weave_url"] == "https://weave.example.com/api/runs/ingest"
    assert data2["weave_token_set"] is True
    assert data2["enabled"] is True


def test_put_publish_config_token_preserved_on_empty_resend(
    client: TestClient,
) -> None:
    """When the UI re-sends an empty token string the existing token is kept."""
    # First save with a real token.
    client.put(
        "/api/silk/publish-config",
        json={
            "weave_url": "https://w.example.com",
            "weave_token": "original-token",
            "hub_url": "",
            "hub_token": "",
            "enabled": True,
        },
    )

    # Re-save with empty token (as the UI would send when token is masked).
    r = client.put(
        "/api/silk/publish-config",
        json={
            "weave_url": "https://w.example.com",
            "weave_token": "",  # masked / not changed by user
            "hub_url": "",
            "hub_token": "",
            "enabled": True,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["weave_token_set"] is True  # token still there

    # Confirm by loading directly.
    from theridion_sidecar import publish_config as pc
    cfg = pc.load()
    assert cfg.weave_token == "original-token"


def test_put_publish_config_disabled_by_default(client: TestClient) -> None:
    r = client.put(
        "/api/silk/publish-config",
        json={"weave_url": "https://w.example.com", "weave_token": "tok", "hub_url": "", "hub_token": ""},
    )
    assert r.status_code == 200
    assert r.json()["enabled"] is False


def test_put_publish_config_trailing_slash_stripped(client: TestClient) -> None:
    r = client.put(
        "/api/silk/publish-config",
        json={
            "weave_url": "https://w.example.com/",
            "weave_token": "",
            "hub_url": "",
            "hub_token": "",
            "enabled": False,
        },
    )
    assert r.status_code == 200
    assert r.json()["weave_url"] == "https://w.example.com"


# ---------------------------------------------------------------------------
# publish_config module — direct unit tests
# ---------------------------------------------------------------------------


def test_publish_config_load_missing_returns_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar import publish_config as pc
    cfg = pc.load()
    assert cfg.weave_url == ""
    assert cfg.weave_token == ""
    assert cfg.enabled is False


def test_publish_config_save_and_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar import publish_config as pc
    original = pc.PublishConfig(
        weave_url="https://w.example.com/api/runs/ingest",
        weave_token="s3cr3t",
        hub_url="https://hub.example.com",
        hub_token="hub-tok",
        enabled=True,
    )
    pc.save(original)

    loaded = pc.load()
    assert loaded.weave_url == "https://w.example.com/api/runs/ingest"
    assert loaded.weave_token == "s3cr3t"
    assert loaded.hub_url == "https://hub.example.com"
    assert loaded.hub_token == "hub-tok"
    assert loaded.enabled is True


def test_publish_config_corrupted_file_returns_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar import publish_config as pc

    p = tmp_path / "publish-config.json"
    p.write_text("NOT VALID JSON", encoding="utf-8")

    cfg = pc.load()
    assert cfg.weave_url == ""
    assert cfg.enabled is False


# ---------------------------------------------------------------------------
# _publish_run_result_v2 — uses persisted config when enabled
# ---------------------------------------------------------------------------


async def test_publisher_uses_persisted_config_over_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When persisted config is enabled it is used in preference to env vars."""
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    # Set env vars pointing to a DIFFERENT target — must NOT be used.
    monkeypatch.setenv("EYES_WEAVE_URL", "https://env-weave.example.com")
    monkeypatch.setenv("EYES_TOKEN", "env-token")

    from theridion_sidecar import publish_config as pc
    pc.save(
        pc.PublishConfig(
            weave_url="https://cfg-weave.example.com",
            weave_token="cfg-token",
            hub_url="",
            hub_token="",
            enabled=True,
        )
    )

    from theridion_sidecar.api.silk import BrowserRunResult, _publish_run_result_v2

    captured: list[tuple[str, dict, str | None]] = []

    class _FakeResponse:
        status_code = 200

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def post(self, url: str, *, json: dict, headers: dict):
            captured.append((url, json, headers.get("Authorization")))
            return _FakeResponse()

    with patch("theridion_sidecar.api.silk._httpx") as mock_httpx:
        mock_httpx.AsyncClient.return_value = _FakeClient()
        await _publish_run_result_v2(
            run_id="test-run-1",
            spec_label="test.spec.ts",
            browsers=["chromium"],
            per_browser={
                "chromium": BrowserRunResult(
                    browser="chromium",
                    exit_code=0,
                    passed=1,
                    failed=0,
                    errors=0,
                    duration_ms=100,
                    trace_path=None,
                    stderr_tail="",
                    json_report=None,
                    a11y_violations=[],
                )
            },
            overall_exit=0,
            agg_passed=1,
            agg_failed=0,
            duration_ms=100,
        )

    assert len(captured) == 1
    url, _payload, auth = captured[0]
    assert "cfg-weave" in url
    assert auth == "Bearer cfg-token"
    # Env-based URL must NOT have been called.
    assert not any("env-weave" in u for u, _, _ in captured)


async def test_publisher_falls_back_to_env_when_config_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When persisted config is disabled, fall back to env vars."""
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    monkeypatch.setenv("EYES_WEAVE_URL", "https://env-weave.example.com")
    monkeypatch.setenv("EYES_TOKEN", "env-token")

    from theridion_sidecar import publish_config as pc
    # Save config but leave enabled=False.
    pc.save(
        pc.PublishConfig(
            weave_url="https://cfg-weave.example.com",
            weave_token="cfg-token",
            enabled=False,
        )
    )

    from theridion_sidecar.api.silk import BrowserRunResult, _publish_run_result_v2

    captured: list[tuple[str, str | None]] = []

    class _FakeResponse:
        status_code = 200

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def post(self, url: str, *, json: dict, headers: dict):
            captured.append((url, headers.get("Authorization")))
            return _FakeResponse()

    with patch("theridion_sidecar.api.silk._httpx") as mock_httpx:
        mock_httpx.AsyncClient.return_value = _FakeClient()
        await _publish_run_result_v2(
            run_id="test-run-2",
            spec_label="test.spec.ts",
            browsers=["chromium"],
            per_browser={
                "chromium": BrowserRunResult(
                    browser="chromium",
                    exit_code=0,
                    passed=1,
                    failed=0,
                    errors=0,
                    duration_ms=100,
                    trace_path=None,
                    stderr_tail="",
                    json_report=None,
                    a11y_violations=[],
                )
            },
            overall_exit=0,
            agg_passed=1,
            agg_failed=0,
            duration_ms=100,
        )

    assert len(captured) == 1
    url, auth = captured[0]
    assert "env-weave" in url
    assert auth == "Bearer env-token"


async def test_publisher_noop_when_nothing_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Publisher is a no-op when neither config nor env vars provide a URL."""
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    for k in ("EYES_HUB_URL", "EYES_WEAVE_URL", "EYES_TOKEN"):
        monkeypatch.delenv(k, raising=False)

    from theridion_sidecar.api.silk import BrowserRunResult, _publish_run_result_v2

    called = []

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def post(self, *a, **kw):
            called.append(1)

    with patch("theridion_sidecar.api.silk._httpx") as mock_httpx:
        mock_httpx.AsyncClient.return_value = _FakeClient()
        await _publish_run_result_v2(
            run_id="test-run-3",
            spec_label="test.spec.ts",
            browsers=["chromium"],
            per_browser={
                "chromium": BrowserRunResult(
                    browser="chromium",
                    exit_code=0,
                    passed=1,
                    failed=0,
                    errors=0,
                    duration_ms=100,
                    trace_path=None,
                    stderr_tail="",
                    json_report=None,
                    a11y_violations=[],
                )
            },
            overall_exit=0,
            agg_passed=1,
            agg_failed=0,
            duration_ms=100,
        )

    assert called == []  # No HTTP call made.
