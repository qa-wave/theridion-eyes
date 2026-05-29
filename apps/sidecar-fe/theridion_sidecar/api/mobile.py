"""Mobile — device & Appium server management.

Endpoints
---------
GET  /api/mobile/tooling           — Report which tools are present on PATH
GET  /api/mobile/devices           — Unified device list (Android + iOS simulators)
POST /api/mobile/simulator/boot    — Boot an iOS simulator by UDID (macOS only)
POST /api/mobile/emulator/start    — Launch an Android emulator by AVD name (detached)
POST /api/mobile/appium/start      — Start an Appium server on a given port
POST /api/mobile/appium/stop       — Stop a tracked Appium server
GET  /api/mobile/appium/status     — Probe liveness of an Appium server

All paths require X-Theridion-Token (enforced by main.py middleware).
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import sys
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/mobile", tags=["mobile"])

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

# Maps port → active Appium subprocess
_appium_procs: dict[int, asyncio.subprocess.Process] = {}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"^[A-Za-z0-9\-]+$")

_TOOL_NAMES = ["adb", "xcrun", "appium", "emulator"]


def _validate_token(value: str, label: str) -> None:
    """Raise HTTPException(400) if *value* is not a safe alphanumeric+dash token."""
    if not value or not _TOKEN_RE.fullmatch(value):
        raise HTTPException(
            status_code=400,
            detail=f"{label!r} must contain only letters, digits, and dashes — got {value!r}",
        )


def _require_tool(name: str) -> str:
    """Return the path to *name* or raise HTTPException(400)."""
    path = shutil.which(name)
    if path is None:
        raise HTTPException(
            status_code=400,
            detail=f"'{name}' not found on PATH — install the required toolchain",
        )
    return path


async def _run(cmd: list[str]) -> tuple[int, str]:
    """Run *cmd* as a subprocess and return (returncode, stdout).

    This is the single patchable seam for all subprocess invocations in this
    module.  Tests patch ``theridion_sidecar.api.mobile._run``.
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, _ = await proc.communicate()
    rc = proc.returncode if proc.returncode is not None else -1
    return rc, stdout_bytes.decode(errors="replace")


# ---------------------------------------------------------------------------
# Shutdown helper (called from main.py lifespan)
# ---------------------------------------------------------------------------


async def shutdown_appium_procs() -> None:
    """Kill any tracked Appium processes at sidecar shutdown."""
    while _appium_procs:
        _port, proc = _appium_procs.popitem()
        if proc.returncode is not None:
            continue
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ToolInfo(BaseModel):
    name: str
    available: bool
    path: str | None


class ToolingOutput(BaseModel):
    tools: list[ToolInfo]


class DeviceInfo(BaseModel):
    id: str
    name: str
    platform: str
    state: str


class DevicesOutput(BaseModel):
    devices: list[DeviceInfo]


class BootInput(BaseModel):
    udid: str = Field(..., description="UDID of the iOS simulator to boot.")


class BootOutput(BaseModel):
    udid: str
    message: str


class EmulatorStartInput(BaseModel):
    avd: str = Field(..., description="Name of the Android Virtual Device to launch.")


class EmulatorStartOutput(BaseModel):
    avd: str
    message: str


class AppiumStartInput(BaseModel):
    port: int = Field(4723, ge=1024, le=65535, description="Port to run Appium on.")


class AppiumStartOutput(BaseModel):
    port: int
    pid: int
    message: str


class AppiumStopInput(BaseModel):
    port: int = Field(4723, ge=1024, le=65535)


class AppiumStopOutput(BaseModel):
    port: int
    message: str


class AppiumStatusOutput(BaseModel):
    running: bool
    port: int
    detail: str | None = None


# ---------------------------------------------------------------------------
# 1. GET /api/mobile/tooling
# ---------------------------------------------------------------------------


@router.get("/tooling", response_model=ToolingOutput)
def get_tooling() -> ToolingOutput:
    """Report which mobile tools are present on PATH."""
    tools: list[ToolInfo] = []
    for name in _TOOL_NAMES:
        p = shutil.which(name)
        # xcrun is macOS-only; still report availability on other platforms
        tools.append(ToolInfo(name=name, available=p is not None, path=p))
    return ToolingOutput(tools=tools)


# ---------------------------------------------------------------------------
# 2. GET /api/mobile/devices
# ---------------------------------------------------------------------------


def _parse_adb_devices(output: str) -> list[DeviceInfo]:
    """Parse ``adb devices -l`` stdout into DeviceInfo list."""
    devices: list[DeviceInfo] = []
    lines = output.splitlines()
    # Skip the header line "List of devices attached"
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        # Format: <serial>  <state>  model:<name> ...  or just  <serial>  <state>
        parts = line.split()
        if len(parts) < 2:
            continue
        serial = parts[0]
        state = parts[1]
        # Extract model name from key:value pairs if present
        name = serial
        for kv in parts[2:]:
            if kv.startswith("model:"):
                name = kv[len("model:"):]
                break
        devices.append(DeviceInfo(id=serial, name=name, platform="android", state=state))
    return devices


def _parse_simctl_devices(output: str) -> list[DeviceInfo]:
    """Parse ``xcrun simctl list devices --json`` stdout into DeviceInfo list."""
    devices: list[DeviceInfo] = []
    try:
        data: dict[str, Any] = json.loads(output)
    except json.JSONDecodeError:
        return devices

    device_map: dict[str, list[dict[str, Any]]] = data.get("devices", {})
    for _runtime, sims in device_map.items():
        for sim in sims:
            state = sim.get("state", "unknown")
            # Only include booted or available simulators
            if state.lower() not in ("booted", "shutdown", "available"):
                continue
            devices.append(
                DeviceInfo(
                    id=sim.get("udid", ""),
                    name=sim.get("name", ""),
                    platform="ios",
                    state=state.lower(),
                )
            )
    return devices


@router.get("/devices", response_model=DevicesOutput)
async def list_devices() -> DevicesOutput:
    """Return a unified device list across Android and iOS platforms.

    Gracefully degrades: if a tool is absent the corresponding platform is
    omitted from the result (no error is raised).
    """
    devices: list[DeviceInfo] = []

    # Android — adb devices -l
    adb = shutil.which("adb")
    if adb:
        rc, out = await _run([adb, "devices", "-l"])
        if rc == 0:
            devices.extend(_parse_adb_devices(out))

    # iOS — xcrun simctl (macOS only)
    if sys.platform == "darwin":
        xcrun = shutil.which("xcrun")
        if xcrun:
            rc, out = await _run([xcrun, "simctl", "list", "devices", "--json"])
            if rc == 0:
                devices.extend(_parse_simctl_devices(out))

    return DevicesOutput(devices=devices)


# ---------------------------------------------------------------------------
# 3. POST /api/mobile/simulator/boot
# ---------------------------------------------------------------------------


@router.post("/simulator/boot", response_model=BootOutput)
async def boot_simulator(body: BootInput) -> BootOutput:
    """Boot an iOS simulator by UDID.

    macOS only.  Returns 400 if xcrun is not available or UDID is invalid.
    """
    if sys.platform != "darwin":
        raise HTTPException(status_code=400, detail="iOS simulators require macOS")

    _validate_token(body.udid, "udid")
    xcrun = _require_tool("xcrun")

    rc, out = await _run([xcrun, "simctl", "boot", body.udid])
    if rc != 0 and "already booted" not in out.lower():
        raise HTTPException(
            status_code=400,
            detail=f"simctl boot failed (exit {rc}): {out.strip()[:300]}",
        )

    # Open Simulator.app so the UI is visible (best-effort; ignore failure)
    open_bin = shutil.which("open")
    if open_bin:
        await _run([open_bin, "-a", "Simulator"])

    return BootOutput(udid=body.udid, message=f"Simulator {body.udid} booted")


# ---------------------------------------------------------------------------
# 4. POST /api/mobile/emulator/start
# ---------------------------------------------------------------------------


@router.post("/emulator/start", response_model=EmulatorStartOutput)
async def start_emulator(body: EmulatorStartInput) -> EmulatorStartOutput:
    """Launch an Android emulator by AVD name (detached — returns immediately).

    Returns 400 if the ``emulator`` binary is not available or AVD name is invalid.
    """
    _validate_token(body.avd, "avd")
    emulator_bin = _require_tool("emulator")

    # Launch detached — do NOT await completion; the emulator runs until closed.
    await asyncio.create_subprocess_exec(
        emulator_bin,
        "-avd",
        body.avd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )

    return EmulatorStartOutput(avd=body.avd, message=f"Emulator AVD '{body.avd}' launched")


# ---------------------------------------------------------------------------
# 5. POST /api/mobile/appium/start
# ---------------------------------------------------------------------------


@router.post("/appium/start", response_model=AppiumStartOutput)
async def start_appium(body: AppiumStartInput) -> AppiumStartOutput:
    """Start an Appium server on the given port.

    Returns 400 if appium is not available or the port is already tracked.
    """
    appium_bin = _require_tool("appium")

    if body.port in _appium_procs:
        proc = _appium_procs[body.port]
        if proc.returncode is None:
            raise HTTPException(
                status_code=400,
                detail=f"Appium server already running on port {body.port}",
            )
        # Process has exited — clean up stale entry and allow restart
        del _appium_procs[body.port]

    proc = await asyncio.create_subprocess_exec(
        appium_bin,
        "--port",
        str(body.port),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )

    _appium_procs[body.port] = proc
    pid = proc.pid

    return AppiumStartOutput(
        port=body.port,
        pid=pid,
        message=f"Appium server started on port {body.port} (pid {pid})",
    )


# ---------------------------------------------------------------------------
# 6. POST /api/mobile/appium/stop
# ---------------------------------------------------------------------------


@router.post("/appium/stop", response_model=AppiumStopOutput)
async def stop_appium(body: AppiumStopInput) -> AppiumStopOutput:
    """Stop the tracked Appium server on the given port.

    Returns 404 if no server is tracked on that port.
    """
    proc = _appium_procs.pop(body.port, None)
    if proc is None:
        raise HTTPException(
            status_code=404,
            detail=f"No tracked Appium server on port {body.port}",
        )

    if proc.returncode is None:
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    return AppiumStopOutput(port=body.port, message=f"Appium server on port {body.port} stopped")


# ---------------------------------------------------------------------------
# 7. GET /api/mobile/appium/status
# ---------------------------------------------------------------------------


@router.get("/appium/status", response_model=AppiumStatusOutput)
async def appium_status(request: Request, port: int = 4723) -> AppiumStatusOutput:
    """Probe liveness of an Appium server by hitting its /status endpoint.

    Uses the shared httpx.AsyncClient from app state.  Connection errors are
    treated as *running: false* — never raises 500.
    """
    http_client: httpx.AsyncClient = request.app.state.http_client
    url = f"http://127.0.0.1:{port}/status"

    try:
        resp = await http_client.get(url)
        running = resp.status_code < 500
        return AppiumStatusOutput(running=running, port=port)
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, OSError) as exc:
        return AppiumStatusOutput(running=False, port=port, detail=str(exc))
    except Exception as exc:
        return AppiumStatusOutput(running=False, port=port, detail=str(exc))
