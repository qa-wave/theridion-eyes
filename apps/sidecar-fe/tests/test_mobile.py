"""Tests for the Mobile device/server management module (/api/mobile/*).

Covers:
  - GET  /api/mobile/tooling         — availability based on patched shutil.which
  - GET  /api/mobile/devices         — adb + simctl parsing; graceful degradation
  - POST /api/mobile/simulator/boot  — input validation; xcrun absent; success
  - POST /api/mobile/emulator/start  — input validation; emulator absent; success
  - POST /api/mobile/appium/start    — tracking; already-running; appium absent
  - POST /api/mobile/appium/stop     — success; untracked port → 404
  - GET  /api/mobile/appium/status   — running:false when probe connection fails

All external-tool calls go through the ``_run`` helper or
``asyncio.create_subprocess_exec``; tests patch those seams so CI has no
dependency on adb/xcrun/appium/emulator.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Sample subprocess outputs
# ---------------------------------------------------------------------------

_ADB_DEVICES_STDOUT = """\
List of devices attached
emulator-5554\tdevice  model:Pixel_3a  transport_id:1
R3CN70P2V6J\tdevice  model:SM_G991B  transport_id:2
"""

_SIMCTL_DEVICES_JSON = json.dumps(
    {
        "devices": {
            "com.apple.CoreSimulator.SimRuntime.iOS-17-4": [
                {
                    "udid": "E1A2B3C4-0000-0000-0000-111111111111",
                    "name": "iPhone 15",
                    "state": "Shutdown",
                },
                {
                    "udid": "E1A2B3C4-0000-0000-0000-222222222222",
                    "name": "iPhone 15 Pro",
                    "state": "Booted",
                },
                # State that should be skipped
                {
                    "udid": "E1A2B3C4-0000-0000-0000-333333333333",
                    "name": "iPad Air",
                    "state": "Creating",
                },
            ]
        }
    }
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """App client with isolated THERIDION_HOME and a clean mobile proc registry."""
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    import theridion_sidecar.api.mobile as _mobile

    # Clear any stale procs between tests
    _mobile._appium_procs.clear()

    from theridion_sidecar.main import create_app

    return TestClient(create_app())


# ---------------------------------------------------------------------------
# 1. GET /api/mobile/tooling
# ---------------------------------------------------------------------------


def test_tooling_all_present(client: TestClient) -> None:
    """Reports available=True for all tools when shutil.which returns paths."""
    which_map = {
        "adb": "/usr/bin/adb",
        "xcrun": "/usr/bin/xcrun",
        "appium": "/usr/local/bin/appium",
        "emulator": "/usr/local/bin/emulator",
    }

    with patch("shutil.which", side_effect=lambda name: which_map.get(name)):
        res = client.get("/api/mobile/tooling")

    assert res.status_code == 200
    data = res.json()
    tools = {t["name"]: t for t in data["tools"]}
    for name in ("adb", "xcrun", "appium", "emulator"):
        assert tools[name]["available"] is True
        assert tools[name]["path"] == which_map[name]


def test_tooling_none_present(client: TestClient) -> None:
    """Reports available=False for all tools when nothing is on PATH."""
    with patch("shutil.which", return_value=None):
        res = client.get("/api/mobile/tooling")

    assert res.status_code == 200
    data = res.json()
    for tool in data["tools"]:
        assert tool["available"] is False
        assert tool["path"] is None


def test_tooling_partial(client: TestClient) -> None:
    """Reports mixed availability."""
    with patch("shutil.which", side_effect=lambda n: "/bin/adb" if n == "adb" else None):
        res = client.get("/api/mobile/tooling")

    assert res.status_code == 200
    tools = {t["name"]: t for t in res.json()["tools"]}
    assert tools["adb"]["available"] is True
    assert tools["appium"]["available"] is False


# ---------------------------------------------------------------------------
# 2. GET /api/mobile/devices
# ---------------------------------------------------------------------------


def _make_run_mock(rc: int, out: str) -> object:
    async def _fake_run(cmd: list[str]) -> tuple[int, str]:
        return rc, out

    return _fake_run  # type: ignore[return-value]


def test_devices_android_parsed(client: TestClient) -> None:
    """Parses adb devices -l output into the unified device shape."""
    with (
        patch("shutil.which", side_effect=lambda n: "/bin/adb" if n == "adb" else None),
        patch("theridion_sidecar.api.mobile._run", _make_run_mock(0, _ADB_DEVICES_STDOUT)),
    ):
        res = client.get("/api/mobile/devices")

    assert res.status_code == 200
    devs = res.json()["devices"]
    assert len(devs) == 2
    ids = {d["id"] for d in devs}
    assert "emulator-5554" in ids
    assert "R3CN70P2V6J" in ids
    for d in devs:
        assert d["platform"] == "android"
        assert d["state"] == "device"


@pytest.mark.skipif(sys.platform != "darwin", reason="iOS parsing only tested on macOS")
def test_devices_ios_parsed(client: TestClient) -> None:
    """Parses xcrun simctl list devices --json into the unified device shape."""

    async def _fake_run(cmd: list[str]) -> tuple[int, str]:
        # xcrun path is first element
        if "simctl" in cmd:
            return 0, _SIMCTL_DEVICES_JSON
        return 0, ""

    with (
        patch("shutil.which", side_effect=lambda n: f"/bin/{n}" if n in ("adb", "xcrun") else None),
        patch("theridion_sidecar.api.mobile._run", _fake_run),
    ):
        res = client.get("/api/mobile/devices")

    assert res.status_code == 200
    devs = res.json()["devices"]
    ios_devs = [d for d in devs if d["platform"] == "ios"]
    # Only Shutdown and Booted states are included (Creating is skipped)
    assert len(ios_devs) == 2
    states = {d["state"] for d in ios_devs}
    assert "booted" in states
    assert "shutdown" in states


def test_devices_adb_absent_returns_empty(client: TestClient) -> None:
    """When adb is not on PATH, devices list is empty and 200 is returned."""
    with patch("shutil.which", return_value=None):
        res = client.get("/api/mobile/devices")

    assert res.status_code == 200
    assert res.json()["devices"] == []


def test_devices_adb_error_degrades(client: TestClient) -> None:
    """When adb returns non-zero, the platform is silently omitted."""
    with (
        patch("shutil.which", side_effect=lambda n: "/bin/adb" if n == "adb" else None),
        patch("theridion_sidecar.api.mobile._run", _make_run_mock(1, "error")),
    ):
        res = client.get("/api/mobile/devices")

    assert res.status_code == 200
    assert res.json()["devices"] == []


# ---------------------------------------------------------------------------
# 3. POST /api/mobile/simulator/boot
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "darwin", reason="simulator boot is macOS-only")
def test_boot_simulator_success(client: TestClient) -> None:
    """Boots a simulator when xcrun is present and UDID is valid."""
    udid = "AABBCCDD-1234-5678-ABCD-000000000000"

    async def _fake_run(cmd: list[str]) -> tuple[int, str]:
        return 0, ""

    present = {"xcrun", "open"}
    with (
        patch("shutil.which", side_effect=lambda n: f"/bin/{n}" if n in present else None),
        patch("theridion_sidecar.api.mobile._run", _fake_run),
    ):
        res = client.post("/api/mobile/simulator/boot", json={"udid": udid})

    assert res.status_code == 200
    data = res.json()
    assert data["udid"] == udid
    assert "booted" in data["message"].lower()


@pytest.mark.skipif(sys.platform != "darwin", reason="simulator boot is macOS-only")
def test_boot_simulator_xcrun_absent(client: TestClient) -> None:
    """Returns 400 when xcrun is not available."""
    with patch("shutil.which", return_value=None):
        res = client.post(
            "/api/mobile/simulator/boot",
            json={"udid": "AABBCCDD-1234-5678-ABCD-000000000000"},
        )

    assert res.status_code == 400
    assert "xcrun" in res.json()["detail"]


def test_boot_simulator_bad_udid(client: TestClient) -> None:
    """Returns 400 when UDID contains invalid characters."""
    bad_values = [
        "../etc/passwd",
        "hello world",
        "abc/def",
        "",
    ]
    for bad in bad_values:
        res = client.post("/api/mobile/simulator/boot", json={"udid": bad})
        assert res.status_code == 400, f"expected 400 for udid={bad!r}, got {res.status_code}"


def test_boot_simulator_non_macos(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Returns 400 on non-macOS platforms."""
    monkeypatch.setattr("theridion_sidecar.api.mobile.sys.platform", "linux")
    res = client.post(
        "/api/mobile/simulator/boot",
        json={"udid": "AABBCCDD-1234-5678-ABCD-000000000000"},
    )
    assert res.status_code == 400
    assert "macos" in res.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 4. POST /api/mobile/emulator/start
# ---------------------------------------------------------------------------


def test_emulator_start_success(client: TestClient) -> None:
    """Launches emulator detached and returns 200 immediately."""
    avd = "Pixel7-API34"

    mock_proc = MagicMock()
    mock_proc.pid = 12345

    async def _fake_exec(*args: object, **kwargs: object) -> MagicMock:
        return mock_proc

    with (
        patch("shutil.which", side_effect=lambda n: "/bin/emulator" if n == "emulator" else None),
        patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
    ):
        res = client.post("/api/mobile/emulator/start", json={"avd": avd})

    assert res.status_code == 200
    data = res.json()
    assert data["avd"] == avd
    assert "launched" in data["message"].lower()


def test_emulator_start_absent(client: TestClient) -> None:
    """Returns 400 when emulator binary is not on PATH."""
    with patch("shutil.which", return_value=None):
        res = client.post("/api/mobile/emulator/start", json={"avd": "Pixel7"})

    assert res.status_code == 400
    assert "emulator" in res.json()["detail"]


def test_emulator_start_bad_avd(client: TestClient) -> None:
    """Returns 400 when AVD name contains invalid characters."""
    bad_values = [
        "my avd",
        "../evil",
        "avd/name",
        "",
    ]
    for bad in bad_values:
        res = client.post("/api/mobile/emulator/start", json={"avd": bad})
        assert res.status_code == 400, f"expected 400 for avd={bad!r}, got {res.status_code}"


# ---------------------------------------------------------------------------
# 5. POST /api/mobile/appium/start
# ---------------------------------------------------------------------------


def test_appium_start_success(client: TestClient) -> None:
    """Starts an Appium process and tracks it."""
    mock_proc = MagicMock()
    mock_proc.pid = 9001
    mock_proc.returncode = None  # still running

    async def _fake_exec(*args: object, **kwargs: object) -> MagicMock:
        return mock_proc

    with (
        patch("shutil.which", side_effect=lambda n: "/bin/appium" if n == "appium" else None),
        patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
    ):
        res = client.post("/api/mobile/appium/start", json={"port": 4723})

    assert res.status_code == 200
    data = res.json()
    assert data["port"] == 4723
    assert data["pid"] == 9001


def test_appium_start_already_running(client: TestClient) -> None:
    """Returns 400 when a process is already tracked on the given port."""
    import theridion_sidecar.api.mobile as _mobile

    mock_proc = MagicMock()
    mock_proc.returncode = None  # simulate still running
    _mobile._appium_procs[4724] = mock_proc  # type: ignore[assignment]

    with patch("shutil.which", side_effect=lambda n: "/bin/appium" if n == "appium" else None):
        res = client.post("/api/mobile/appium/start", json={"port": 4724})

    assert res.status_code == 400
    assert "already running" in res.json()["detail"]

    # Cleanup
    _mobile._appium_procs.pop(4724, None)


def test_appium_start_absent(client: TestClient) -> None:
    """Returns 400 when appium binary is not on PATH."""
    with patch("shutil.which", return_value=None):
        res = client.post("/api/mobile/appium/start", json={"port": 4723})

    assert res.status_code == 400
    assert "appium" in res.json()["detail"]


def test_appium_start_stale_proc_allows_restart(client: TestClient) -> None:
    """Allows starting on a port whose previous proc has already exited."""
    import theridion_sidecar.api.mobile as _mobile

    stale_proc = MagicMock()
    stale_proc.returncode = 1  # exited
    _mobile._appium_procs[4725] = stale_proc  # type: ignore[assignment]

    new_proc = MagicMock()
    new_proc.pid = 5000
    new_proc.returncode = None

    async def _fake_exec(*args: object, **kwargs: object) -> MagicMock:
        return new_proc

    with (
        patch("shutil.which", side_effect=lambda n: "/bin/appium" if n == "appium" else None),
        patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
    ):
        res = client.post("/api/mobile/appium/start", json={"port": 4725})

    assert res.status_code == 200
    assert res.json()["pid"] == 5000

    _mobile._appium_procs.pop(4725, None)


# ---------------------------------------------------------------------------
# 6. POST /api/mobile/appium/stop
# ---------------------------------------------------------------------------


def test_appium_stop_success(client: TestClient) -> None:
    """Terminates a tracked Appium process."""
    import theridion_sidecar.api.mobile as _mobile

    mock_proc = MagicMock()
    mock_proc.returncode = None

    async def _fake_wait() -> int:
        return 0

    mock_proc.wait = _fake_wait

    _mobile._appium_procs[4726] = mock_proc  # type: ignore[assignment]

    res = client.post("/api/mobile/appium/stop", json={"port": 4726})

    assert res.status_code == 200
    data = res.json()
    assert data["port"] == 4726
    assert "stopped" in data["message"].lower()
    assert 4726 not in _mobile._appium_procs


def test_appium_stop_untracked_port(client: TestClient) -> None:
    """Returns 404 when no Appium server is tracked on the given port."""
    res = client.post("/api/mobile/appium/stop", json={"port": 19999})
    assert res.status_code == 404
    assert "19999" in res.json()["detail"]


def test_appium_stop_already_exited(client: TestClient) -> None:
    """Handles the case where the tracked process has already exited."""
    import theridion_sidecar.api.mobile as _mobile

    mock_proc = MagicMock()
    mock_proc.returncode = 0  # already done — skip terminate

    _mobile._appium_procs[4727] = mock_proc  # type: ignore[assignment]

    res = client.post("/api/mobile/appium/stop", json={"port": 4727})
    assert res.status_code == 200
    assert 4727 not in _mobile._appium_procs


# ---------------------------------------------------------------------------
# 7. GET /api/mobile/appium/status
#
# The status endpoint reads request.app.state.http_client, which is set by the
# lifespan.  Use TestClient as a context manager so the lifespan runs.
# ---------------------------------------------------------------------------


@pytest.fixture()
def lifespan_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient that runs the app lifespan (sets app.state.http_client)."""
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    import theridion_sidecar.api.mobile as _mobile

    _mobile._appium_procs.clear()
    from theridion_sidecar.main import create_app

    tc = TestClient(create_app(), raise_server_exceptions=True)
    tc.__enter__()
    yield tc  # type: ignore[misc]
    tc.__exit__(None, None, None)


def test_appium_status_running_false_on_connect_error(lifespan_client: TestClient) -> None:
    """Returns running:false when the Appium server probe fails to connect."""

    async def _fake_get(url: str, **kwargs: object) -> None:
        raise httpx.ConnectError("connection refused")

    with patch.object(httpx.AsyncClient, "get", side_effect=_fake_get):
        res = lifespan_client.get("/api/mobile/appium/status", params={"port": 4723})

    assert res.status_code == 200
    data = res.json()
    assert data["running"] is False
    assert data["port"] == 4723


def test_appium_status_running_true(lifespan_client: TestClient) -> None:
    """Returns running:true when the Appium /status endpoint responds 200."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    async def _fake_get(url: str, **kwargs: object) -> MagicMock:
        return mock_resp

    with patch.object(httpx.AsyncClient, "get", side_effect=_fake_get):
        res = lifespan_client.get("/api/mobile/appium/status", params={"port": 4723})

    assert res.status_code == 200
    data = res.json()
    assert data["running"] is True
    assert data["port"] == 4723


def test_appium_status_default_port(lifespan_client: TestClient) -> None:
    """Default port is 4723 when query param is omitted."""

    async def _fake_get(url: str, **kwargs: object) -> None:
        assert ":4723/" in url
        raise httpx.ConnectError("no server")

    with patch.object(httpx.AsyncClient, "get", side_effect=_fake_get):
        res = lifespan_client.get("/api/mobile/appium/status")

    assert res.status_code == 200
    assert res.json()["port"] == 4723
