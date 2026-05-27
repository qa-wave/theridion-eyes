"""Shared test fixtures for sidecar tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

# Fixed test token shared across the entire test session.
_TEST_TOKEN = "test-token-fixture"


# ---------------------------------------------------------------------------
# Session-scoped: pin _SIDECAR_TOKEN so the middleware always validates the
# fixed test token regardless of when modules were first imported.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True, scope="session")
def _pin_sidecar_token():  # type: ignore[return]
    import theridion_sidecar.main as _main

    original = _main._SIDECAR_TOKEN
    _main._SIDECAR_TOKEN = _TEST_TOKEN
    yield
    _main._SIDECAR_TOKEN = original


# ---------------------------------------------------------------------------
# Monkey-patch TestClient.__init__ so every TestClient instance automatically
# sends X-Theridion-Token without needing changes to individual test files.
# ---------------------------------------------------------------------------

_orig_tc_init = TestClient.__init__

# Sentinel value: pass headers=_NO_AUTO_TOKEN to skip the auto-inject.
_NO_AUTO_TOKEN: dict[str, str] = {}


def _patched_tc_init(self: Any, *args: Any, **kwargs: Any) -> None:
    skip_inject = kwargs.get("headers") is _NO_AUTO_TOKEN
    if skip_inject:
        # Replace sentinel with an empty real dict so starlette is happy.
        kwargs["headers"] = {}
    _orig_tc_init(self, *args, **kwargs)
    if not skip_inject and "X-Theridion-Token" not in self.headers:
        self.headers["X-Theridion-Token"] = _TEST_TOKEN


TestClient.__init__ = _patched_tc_init  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# Monkey-patch httpx.AsyncClient so async test clients also pass the token.
# Many test files use: AsyncClient(transport=ASGITransport(app=app), ...)
# ---------------------------------------------------------------------------

try:
    from httpx import AsyncClient as _AsyncClient

    _orig_ac_init = _AsyncClient.__init__

    def _patched_ac_init(self: Any, *args: Any, **kwargs: Any) -> None:
        # Inject default headers before calling original __init__.
        existing = kwargs.get("headers") or {}
        if isinstance(existing, dict):
            if "X-Theridion-Token" not in existing:
                existing["X-Theridion-Token"] = _TEST_TOKEN
        kwargs["headers"] = existing
        _orig_ac_init(self, *args, **kwargs)

    _AsyncClient.__init__ = _patched_ac_init  # type: ignore[method-assign]

except ImportError:
    pass  # httpx not installed — tests that need it will fail on import anyway


# ---------------------------------------------------------------------------
# Default shared client fixture (used by tests that don't define their own).
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    import theridion_sidecar.main as _main

    monkeypatch.setattr(_main, "_SIDECAR_TOKEN", _TEST_TOKEN)
    tc = TestClient(_main.create_app())
    # Header already injected by the patched __init__; this is belt-and-suspenders.
    tc.headers["X-Theridion-Token"] = _TEST_TOKEN
    return tc
