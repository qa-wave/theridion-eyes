"""Silk — Frontend testing module (Playwright runner integration).

Endpoints
---------
GET  /api/silk/frameworks                — List supported test frameworks
GET  /api/silk/browsers/check            — Playwright Chromium presence check
POST /api/silk/install-browsers          — SSE-stream Chromium install
POST /api/silk/install-browsers/sync     — Blocking Chromium install
POST /api/silk/run                       — Execute a .spec.ts (multi-browser, mocks, a11y)
GET  /api/silk/trace/{id}                — Stream back a trace ZIP
POST /api/silk/screenshot-diff           — Pixel-diff two PNG images
POST /api/silk/auto-spec                 — Generate spec from a Strand failure
POST /api/silk/record/start              — Start Playwright codegen session (SSE)
POST /api/silk/record/stop               — Stop codegen, return spec text
POST /api/silk/record/save-and-run       — Save captured spec then immediately run it
POST /api/silk/spec/save                 — Manually save a test spec (any framework)
POST /api/silk/baseline/save             — Save screenshot as visual-regression baseline
POST /api/silk/baseline/compare          — Diff current screenshot vs saved baseline
POST /api/silk/baseline/approve          — Promote candidate screenshot to baseline (persist who/when/diff_ratio)
GET  /api/silk/runs                      — Run history (last N)
GET  /api/silk/runs/{id}                 — Single run detail

All paths require X-Theridion-Token (enforced by main.py middleware).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import AsyncGenerator
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from .. import storage
from .. import silk_storage
from .. import silk_transpile
from . import silk_frameworks

router = APIRouter(prefix="/api/silk", tags=["silk"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SILK_DIR_NAME = "silk"

# Registry of active codegen subprocesses keyed by session_id
_codegen_procs: dict[str, asyncio.subprocess.Process] = {}

# Maps session_id → absolute path of the output file written by codegen
_codegen_output_files: dict[str, Path] = {}

# Maps session_id → user-requested framework id when it differs from codegen target
# (i.e. for transpile-via-playwright-test frameworks like cypress/selenium-*/webdriverio)
_codegen_request_framework: dict[str, str] = {}


async def shutdown_codegen_procs() -> None:
    """Kill any codegen subprocesses still running at sidecar shutdown.

    Called from the FastAPI lifespan teardown so an abrupt exit doesn't leak
    orphaned ``playwright codegen`` browser processes.
    """
    _codegen_request_framework.clear()
    while _codegen_procs:
        _session_id, proc = _codegen_procs.popitem()
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


def _silk_dir() -> Path:
    """~/.theridion/silk/ — stores run artefacts and screenshots."""
    d = storage.home_dir() / _SILK_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _run_dir(run_id: str) -> Path:
    d = _silk_dir() / "runs" / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _baselines_dir() -> Path:
    d = _silk_dir() / "baselines"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _node_bin(name: str) -> str | None:
    """Return the absolute path of a node binary if resolvable."""
    return shutil.which(name)


def _safe_path_under(base: Path, filename: str) -> Path:
    """Resolve *base / filename* and raise ValueError if it escapes *base*.

    This is the containment check used by spec/save to prevent path traversal.
    """
    resolved_base = base.resolve()
    resolved_target = (base / filename).resolve()
    if not str(resolved_target).startswith(str(resolved_base) + "/") and resolved_target != resolved_base:
        raise ValueError(f"filename {filename!r} escapes the target directory")
    return resolved_target


def _monotonic_ns() -> int:
    import time as _time
    return _time.monotonic_ns()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class FrameworkInfo(BaseModel):
    id: str
    label: str
    kind: str
    file_extension: str
    codegen_target: str | None
    recordable: bool
    recordable_via_transpile: bool = False
    runnable: bool
    template: str


class FrameworksOutput(BaseModel):
    frameworks: list[FrameworkInfo]


class SpecSaveInput(BaseModel):
    framework: str = Field(..., description="Framework id from /api/silk/frameworks.")
    filename: str = Field(..., description="Filename for the spec (without or with extension).")
    code: str = Field(..., description="Source code of the test spec.")
    workspace_dir: str | None = Field(
        None,
        description="Target directory; defaults to ~/.theridion/silk/specs/ when omitted.",
    )


class SpecSaveOutput(BaseModel):
    spec_path: str


class InstallBrowsersResponse(BaseModel):
    ok: bool
    message: str
    browser_path: str | None = None


class MockRule(BaseModel):
    pattern: str = Field(..., description="URL glob pattern, e.g. '**/api/users/*'")
    status: int = Field(200)
    body: dict | list | str | None = Field(None)
    content_type: str = Field("application/json")


class SilkRunInput(BaseModel):
    spec_path: str | None = Field(
        None,
        description="Absolute or workspace-relative path to a .spec.ts file.",
    )
    inline_code: str | None = Field(
        None,
        description="TypeScript spec source; written to a temp file when spec_path is absent.",
    )
    env_vars: dict[str, str] = Field(
        default_factory=dict,
        description="Extra environment variables injected into the subprocess.",
    )
    timeout_ms: int = Field(
        60_000,
        ge=1_000,
        le=600_000,
        description="Wall-clock timeout for the entire Playwright run (ms).",
    )
    workspace_dir: str | None = Field(
        None,
        description="Working directory for the npx call (must contain package.json with @playwright/test).",
    )
    browsers: list[str] = Field(
        default_factory=lambda: ["chromium"],
        description="Browser engines to run against (chromium/firefox/webkit).",
    )
    mocks: list[MockRule] = Field(
        default_factory=list,
        description="Network mock rules injected as page.route() wrappers.",
    )
    run_accessibility_audit: bool = Field(
        False,
        description="Inject axe-core accessibility check after each navigation.",
    )


class A11yViolation(BaseModel):
    rule: str
    impact: str
    description: str
    nodes: list[str]


class BrowserRunResult(BaseModel):
    browser: str
    exit_code: int
    passed: int
    failed: int
    errors: int
    duration_ms: int
    trace_path: str | None = None
    stderr_tail: str = ""
    json_report: dict | None = None
    a11y_violations: list[A11yViolation] = Field(default_factory=list)


class SilkRunOutput(BaseModel):
    run_id: str
    exit_code: int
    passed: int
    failed: int
    errors: int
    duration_ms: int
    trace_path: str | None = None
    json_report: dict | None = None
    stderr_tail: str = ""
    per_browser_results: dict[str, BrowserRunResult] = Field(default_factory=dict)
    a11y_violations: list[A11yViolation] = Field(default_factory=list)


class ScreenshotDiffInput(BaseModel):
    baseline_path: str = Field(..., description="Absolute path to the baseline PNG.")
    current_path: str = Field(..., description="Absolute path to the current PNG.")
    threshold: float = Field(
        0.1,
        ge=0.0,
        le=1.0,
        description="Pixel-diff threshold as a fraction of total pixels (0–1).",
    )


class ScreenshotDiffOutput(BaseModel):
    diff_path: str
    pixel_diff_count: int
    total_pixels: int
    diff_ratio: float
    passed: bool


class BaselineSaveInput(BaseModel):
    screenshot_path: str = Field(..., description="Absolute path to the source PNG.")
    test_id: str = Field(..., description="Stable test identifier.")
    browser: str = Field("chromium")
    viewport: str = Field("1280x720", description="Viewport string e.g. '1280x720'.")


class BaselineSaveOutput(BaseModel):
    baseline_path: str
    test_id: str
    browser: str
    viewport: str


class BaselineCompareInput(BaseModel):
    current_path: str = Field(..., description="Absolute path to the current screenshot PNG.")
    test_id: str = Field(..., description="Stable test identifier matching a saved baseline.")
    browser: str = Field("chromium")
    viewport: str = Field("1280x720")
    threshold: float = Field(0.1, ge=0.0, le=1.0)


class BaselineCompareOutput(BaseModel):
    baseline_path: str
    diff_path: str
    pixel_diff_count: int
    total_pixels: int
    diff_ratio: float
    passed: bool
    approved: bool = False


class BaselineApproveInput(BaseModel):
    test_id: str = Field(..., description="Stable test identifier.")
    candidate_path: str = Field(..., description="Absolute path to the candidate screenshot PNG to promote.")
    browser: str = Field("chromium")
    viewport: str = Field("1280x720")
    approved_by: str = Field("", description="Username or email of the approver (optional).")
    diff_ratio: float = Field(0.0, ge=0.0, le=1.0, description="Pixel-diff ratio from the compare step.")


class BaselineApproveOutput(BaseModel):
    baseline_path: str
    test_id: str
    browser: str
    viewport: str
    approved: bool
    approved_by: str
    approved_at: str
    diff_ratio: float


class RecordSaveAndRunInput(BaseModel):
    """Bridge: save a recorded spec then immediately run it."""
    session_id: str = Field(..., description="Active (or just-stopped) codegen session_id.")
    framework: str = Field("playwright-ts")
    filename: str = Field("recorded", description="Base filename for the saved spec (no extension).")
    workspace_dir: str | None = None
    browsers: list[str] = Field(default_factory=lambda: ["chromium"])
    timeout_ms: int = Field(60_000, ge=1_000, le=600_000)


class RecordSaveAndRunOutput(BaseModel):
    spec_path: str
    run: SilkRunOutput


class RecordStartInput(BaseModel):
    url: str = Field(..., description="URL for Playwright codegen to open.")
    workspace_dir: str | None = None
    framework: str = Field(
        "playwright-ts",
        description="Target framework for codegen output (must be recordable).",
    )


class RecordStartOutput(BaseModel):
    session_id: str
    message: str


class RecordStopOutput(BaseModel):
    session_id: str
    spec_text: str
    spec_path: str | None = None


class AutoSpecInput(BaseModel):
    request_id: str = Field(..., description="ID of the failed Strand request.")
    method: str = Field("GET")
    url: str = Field(..., min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    status_code: int | None = None
    workspace_dir: str | None = None


class AutoSpecOutput(BaseModel):
    spec_path: str
    spec_code: str


class BrowserCheckOutput(BaseModel):
    installed: bool
    paths: list[str]


# ---------------------------------------------------------------------------
# 0. Framework registry
# ---------------------------------------------------------------------------


@router.get("/frameworks", response_model=FrameworksOutput)
def list_frameworks() -> FrameworksOutput:
    """Return all supported test frameworks with their metadata."""
    frameworks = [
        FrameworkInfo(
            id=fw.id,
            label=fw.label,
            kind=fw.kind,
            file_extension=fw.file_extension,
            codegen_target=fw.codegen_target,
            recordable=fw.recordable,
            recordable_via_transpile=fw.recordable_via_transpile,
            runnable=fw.runnable,
            template=fw.template,
        )
        for fw in silk_frameworks.all_frameworks()
    ]
    return FrameworksOutput(frameworks=frameworks)


# ---------------------------------------------------------------------------
# 1. Install browsers (SSE stream)
# ---------------------------------------------------------------------------


@router.post("/install-browsers")
async def install_browsers() -> StreamingResponse:
    """Stream Playwright Chromium download progress via SSE.

    Each SSE event is ``data: <line>\\n\\n``.  The final event is
    ``data: DONE path=<path>\\n\\n`` on success or
    ``data: ERROR <message>\\n\\n`` on failure.
    """

    async def _stream() -> AsyncGenerator[str, None]:
        npx = _node_bin("npx")
        if not npx:
            yield "data: ERROR npx not found — install Node.js 18+\n\n"
            return

        yield "data: Starting Playwright Chromium install…\n\n"

        proc = await asyncio.create_subprocess_exec(
            npx,
            "playwright",
            "install",
            "chromium",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={**os.environ},
        )

        assert proc.stdout is not None
        browser_path: str | None = None

        async for raw in proc.stdout:
            line = raw.decode(errors="replace").rstrip()
            if not line:
                continue
            yield f"data: {line}\n\n"
            if "downloaded to" in line.lower() or "chromium" in line.lower():
                parts = line.split("downloaded to", 1)
                if len(parts) == 2:
                    browser_path = parts[1].strip()

        await proc.wait()

        if proc.returncode == 0:
            if not browser_path:
                cache_candidates = [
                    Path.home() / ".cache" / "ms-playwright",
                    Path.home() / "Library" / "Caches" / "ms-playwright",
                    Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")) if os.environ.get("PLAYWRIGHT_BROWSERS_PATH") else None,
                ]
                for c in cache_candidates:
                    if c and c.exists():
                        browser_path = str(c)
                        break
            yield f"data: DONE path={browser_path or 'unknown'}\n\n"
        else:
            yield f"data: ERROR exit code {proc.returncode}\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/install-browsers/sync", response_model=InstallBrowsersResponse)
def install_browsers_sync() -> InstallBrowsersResponse:
    """Blocking install — for clients that cannot handle SSE."""
    npx = _node_bin("npx")
    if not npx:
        raise HTTPException(400, detail="npx not found — install Node.js 18+")

    result = subprocess.run(
        [npx, "playwright", "install", "chromium"],
        capture_output=True,
        text=True,
        timeout=300,
        env={**os.environ},
    )

    browser_path: str | None = None
    for line in result.stdout.splitlines():
        if "downloaded to" in line.lower():
            parts = line.split("downloaded to", 1)
            if len(parts) == 2:
                browser_path = parts[1].strip()
                break

    if result.returncode == 0:
        return InstallBrowsersResponse(
            ok=True,
            message="Chromium installed successfully",
            browser_path=browser_path,
        )

    raise HTTPException(
        500,
        detail=f"playwright install failed (exit {result.returncode}): {result.stderr[:500]}",
    )


# ---------------------------------------------------------------------------
# 2. Run a spec (multi-browser, mocks, a11y)
# ---------------------------------------------------------------------------


def _build_mock_wrapper(original_code: str, mocks: list[MockRule]) -> str:
    """Wrap spec code to inject page.route() mock handlers."""
    if not mocks:
        return original_code

    route_calls = []
    for m in mocks:
        if isinstance(m.body, (dict, list)):
            body_str = json.dumps(m.body)
        else:
            body_str = str(m.body or "")
        escaped_body = body_str.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
        escaped_pattern = m.pattern.replace("'", "\\'")
        content_type = m.content_type
        status = m.status
        route_calls.append(
            f"  await page.route('{escaped_pattern}', route => route.fulfill({{"
            f"status: {status}, contentType: '{content_type}', "
            f"body: `{escaped_body}`"
            f"}}))"
        )

    routes_ts = "\n".join(route_calls)

    wrapper = f"""\
import {{ test as _base, expect, Page }} from '@playwright/test';

// Silk mock wrapper — auto-generated
const test = _base.extend<{{ page: Page }}>({{}});

test.beforeEach(async ({{ page }}) => {{
{routes_ts}
}});

// ---- Original spec follows ----
"""
    # Strip only the '@playwright/test' import (re-declared by the wrapper above)
    # so user imports of other modules are preserved.
    lines = original_code.splitlines()
    filtered = [l for l in lines if not _is_playwright_test_import(l)]
    return wrapper + "\n".join(filtered)


def _is_playwright_test_import(line: str) -> bool:
    """True if *line* is an import statement sourced from '@playwright/test'."""
    stripped = line.strip()
    if not stripped.startswith("import "):
        return False
    return "'@playwright/test'" in stripped or '"@playwright/test"' in stripped


def _build_a11y_wrapper(original_code: str) -> str:
    """Wrap spec code to inject a real axe-core accessibility audit.

    Injects an ``afterEach`` fixture that:
    1. Runs ``AxeBuilder().analyze()`` on the current page.
    2. Attaches the raw axe result as a JSON attachment named
       ``axe-results.json`` so it appears in the Playwright report.
    3. Fails the surrounding test when critical/serious violations are found
       (the attachment is always written, even on pass, so the UI can read it).

    The wrapper skips injection when the spec already imports AxeBuilder.
    """
    if "AxeBuilder" in original_code:
        return original_code

    a11y_snippet = """\
import AxeBuilder from '@axe-core/playwright';
import type { TestInfo } from '@playwright/test';

// ---------------------------------------------------------------------------
// Silk a11y fixture — injected by Silk backend
// ---------------------------------------------------------------------------
//
// Re-export `test` extended with an afterEach that runs axe on every page and
// attaches results. Specs that import from '@playwright/test' have that import
// stripped below so they pick up this extended fixture instead.
//
import { test as _silkBase, expect as _silkExpect } from '@playwright/test';

const test = _silkBase.extend<{ page: import('@playwright/test').Page }>({
  page: async ({ page }, use, testInfo: TestInfo) => {
    await use(page);
    // afterEach: run axe audit.
    try {
      const axeResults = await new AxeBuilder({ page }).analyze();
      // Attach raw results so the Silk UI can parse them.
      await testInfo.attach('axe-results.json', {
        contentType: 'application/json',
        body: JSON.stringify(axeResults),
      });
      // Fail test if critical or serious violations exist.
      const blocking = axeResults.violations.filter(
        (v) => v.impact === 'critical' || v.impact === 'serious',
      );
      if (blocking.length > 0) {
        throw new Error(
          `axe-core found ${blocking.length} critical/serious violation(s): ` +
            blocking.map((v) => `${v.id} (${v.impact})`).join(', '),
        );
      }
    } catch (axeErr) {
      // If axe itself throws (e.g. page already closed), attach error text.
      await testInfo.attach('axe-error.txt', {
        contentType: 'text/plain',
        body: String(axeErr),
      });
    }
  },
});

const expect = _silkExpect;

// ---- Original spec follows (playwright/test import stripped below) ----
"""
    # Strip @playwright/test import — re-declared above.
    lines = original_code.splitlines()
    filtered = [line for line in lines if not _is_playwright_test_import(line)]
    return a11y_snippet + "\n".join(filtered)


def _parse_a11y_violations(json_report: dict | None) -> list[A11yViolation]:
    """Extract axe-core violations from Playwright JSON report attachments.

    Playwright's JSON reporter stores test attachments in:
      suites[].specs[].tests[].results[].attachments[]
    Each attachment has ``name``, ``contentType``, and ``body`` (base64 text)
    or ``path`` (file path on disk).

    We look for attachments named ``axe-results.json`` and parse the axe
    ``violations`` array, mapping each violation + its affected nodes into our
    ``A11yViolation`` model.
    """
    if not json_report:
        return []

    violations: list[A11yViolation] = []

    def _walk_suites(suites: list) -> None:
        for suite in suites:
            for spec in suite.get("specs", []):
                for test in spec.get("tests", []):
                    for result in test.get("results", []):
                        for att in result.get("attachments", []):
                            if att.get("name") != "axe-results.json":
                                continue
                            raw = att.get("body") or ""
                            if not raw and att.get("path"):
                                try:
                                    raw = Path(att["path"]).read_text(encoding="utf-8")
                                except OSError:
                                    continue
                            if not raw:
                                continue
                            # body may be base64-encoded.
                            try:
                                axe_data = json.loads(raw)
                            except (json.JSONDecodeError, ValueError):
                                import base64
                                try:
                                    axe_data = json.loads(base64.b64decode(raw).decode("utf-8"))
                                except Exception:
                                    continue
                            for v in axe_data.get("violations", []):
                                nodes = [
                                    n.get("target", [""])[0] if n.get("target") else ""
                                    for n in v.get("nodes", [])
                                ]
                                violations.append(
                                    A11yViolation(
                                        rule=v.get("id", "unknown"),
                                        impact=v.get("impact", "minor"),
                                        description=v.get("description", ""),
                                        nodes=[str(nd) for nd in nodes if nd],
                                    )
                                )
            _walk_suites(suite.get("suites", []))

    _walk_suites(json_report.get("suites", []))
    return violations


def _parse_network_entries(json_report: dict | None) -> list[dict]:
    """Extract network request entries from Playwright JSON report attachments.

    Playwright can attach a ``network.json`` (HAR-like) to test results.
    We return the raw entries list so the UI can display them.
    """
    if not json_report:
        return []

    entries: list[dict] = []

    def _walk_suites(suites: list) -> None:
        for suite in suites:
            for spec in suite.get("specs", []):
                for test in spec.get("tests", []):
                    for result in test.get("results", []):
                        for att in result.get("attachments", []):
                            if att.get("name") not in ("network.json", "har.json"):
                                continue
                            raw = att.get("body") or ""
                            if not raw and att.get("path"):
                                try:
                                    raw = Path(att["path"]).read_text(encoding="utf-8")
                                except OSError:
                                    continue
                            if not raw:
                                continue
                            try:
                                net_data = json.loads(raw)
                            except (json.JSONDecodeError, ValueError):
                                continue
                            # HAR format: { "log": { "entries": [...] } }
                            ents = net_data.get("log", {}).get("entries", net_data if isinstance(net_data, list) else [])
                            entries.extend(ents)
            _walk_suites(suite.get("suites", []))

    _walk_suites(json_report.get("suites", []))
    return entries


def _parse_screenshot_paths(json_report: dict | None) -> list[str]:
    """Extract screenshot file paths from Playwright JSON report attachments.

    Playwright stores on-failure screenshots as attachments with
    contentType ``image/png`` or name matching ``screenshot``.
    """
    if not json_report:
        return []

    paths: list[str] = []

    def _walk_suites(suites: list) -> None:
        for suite in suites:
            for spec in suite.get("specs", []):
                for test in spec.get("tests", []):
                    for result in test.get("results", []):
                        for att in result.get("attachments", []):
                            ct = att.get("contentType", "")
                            name = att.get("name", "")
                            path = att.get("path", "")
                            if path and (
                                ct.startswith("image/")
                                or "screenshot" in name.lower()
                                or path.endswith(".png")
                            ):
                                paths.append(path)
            _walk_suites(suite.get("suites", []))

    _walk_suites(json_report.get("suites", []))
    return paths


async def _run_single_browser_async(
    *,
    npx: str,
    spec_path_str: str,
    browser: str,
    run_d: Path,
    env: dict[str, str],
    timeout_s: float,
    workspace_dir: str | None,
) -> BrowserRunResult:
    """Execute Playwright for one browser engine asynchronously.

    Uses ``asyncio.create_subprocess_exec`` so multiple browser runs can
    execute concurrently via ``asyncio.gather``.
    """
    browser_dir = run_d / browser
    browser_dir.mkdir(exist_ok=True)

    trace_dir = browser_dir / "traces"
    trace_dir.mkdir(exist_ok=True)

    env_copy = dict(env)
    env_copy["PLAYWRIGHT_TRACE_DEST"] = str(trace_dir)

    valid_browsers = {"chromium", "firefox", "webkit"}
    if browser not in valid_browsers:
        raise HTTPException(400, detail=f"Unknown browser '{browser}'. Choose from: {valid_browsers}")

    cmd = [
        npx,
        "playwright",
        "test",
        spec_path_str,
        "--reporter=json",
        f"--project={browser}",
        f"--output={browser_dir / 'results'}",
    ]

    cwd = workspace_dir or str(run_d)

    start_ns = _monotonic_ns()
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env_copy,
            cwd=cwd,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_s
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            return BrowserRunResult(
                browser=browser,
                exit_code=-1,
                passed=0,
                failed=0,
                errors=1,
                duration_ms=int(timeout_s * 1000),
                stderr_tail=f"Timed out after {timeout_s:.0f}s",
            )
    except Exception as exc:
        return BrowserRunResult(
            browser=browser,
            exit_code=-1,
            passed=0,
            failed=0,
            errors=1,
            duration_ms=0,
            stderr_tail=f"Failed to launch subprocess: {exc}",
        )

    duration_ms = (_monotonic_ns() - start_ns) // 1_000_000

    json_report: dict | None = None
    passed = 0
    failed = 0
    errors = 0

    raw_out = stdout_bytes.decode(errors="replace").strip()
    if raw_out:
        json_start = raw_out.find("{")
        if json_start != -1:
            try:
                json_report = json.loads(raw_out[json_start:])
                stats = json_report.get("stats", {})
                passed = stats.get("expected", 0)
                failed = stats.get("unexpected", 0)
                errors = stats.get("skipped", 0)
            except json.JSONDecodeError:
                pass

    # Extract a11y violations from axe attachments in the report.
    a11y_violations = _parse_a11y_violations(json_report)

    trace_zips = list(trace_dir.rglob("*.zip"))
    trace_path: str | None = str(trace_zips[0]) if trace_zips else None
    stderr_str = stderr_bytes.decode(errors="replace") if stderr_bytes else ""
    stderr_tail = "\n".join(stderr_str.splitlines()[-20:])

    return BrowserRunResult(
        browser=browser,
        exit_code=proc.returncode if proc.returncode is not None else -1,
        passed=passed,
        failed=failed,
        errors=errors,
        duration_ms=duration_ms,
        trace_path=trace_path,
        stderr_tail=stderr_tail,
        json_report=json_report,
        a11y_violations=a11y_violations,
    )


# Keep a thin sync shim for tests that patch subprocess.run directly.
def _run_single_browser(
    *,
    npx: str,
    spec_path_str: str,
    browser: str,
    run_d: Path,
    env: dict[str, str],
    timeout_s: float,
    workspace_dir: str | None,
) -> BrowserRunResult:
    """Synchronous wrapper around the async implementation.

    Used only by legacy code paths and tests that patch ``subprocess.run``.
    In production, ``run_spec`` calls the async variant directly.
    """
    browser_dir = run_d / browser
    browser_dir.mkdir(exist_ok=True)

    trace_dir = browser_dir / "traces"
    trace_dir.mkdir(exist_ok=True)

    env_copy = dict(env)
    env_copy["PLAYWRIGHT_TRACE_DEST"] = str(trace_dir)

    valid_browsers = {"chromium", "firefox", "webkit"}
    if browser not in valid_browsers:
        raise HTTPException(400, detail=f"Unknown browser '{browser}'. Choose from: {valid_browsers}")

    cmd = [
        npx,
        "playwright",
        "test",
        spec_path_str,
        "--reporter=json",
        f"--project={browser}",
        f"--output={browser_dir / 'results'}",
    ]

    cwd = workspace_dir or str(run_d)

    start_ns = _monotonic_ns()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env_copy,
            cwd=cwd,
        )
    except subprocess.TimeoutExpired:
        return BrowserRunResult(
            browser=browser,
            exit_code=-1,
            passed=0,
            failed=0,
            errors=1,
            duration_ms=int(timeout_s * 1000),
            stderr_tail=f"Timed out after {timeout_s:.0f}s",
        )

    duration_ms = (_monotonic_ns() - start_ns) // 1_000_000

    json_report: dict | None = None
    passed = 0
    failed = 0
    errors = 0

    raw_out = proc.stdout.strip() if proc.stdout else ""
    if raw_out:
        json_start = raw_out.find("{")
        if json_start != -1:
            try:
                json_report = json.loads(raw_out[json_start:])
                stats = json_report.get("stats", {})
                passed = stats.get("expected", 0)
                failed = stats.get("unexpected", 0)
                errors = stats.get("skipped", 0)
            except json.JSONDecodeError:
                pass

    a11y_violations = _parse_a11y_violations(json_report)

    trace_zips = list(trace_dir.rglob("*.zip"))
    trace_path: str | None = str(trace_zips[0]) if trace_zips else None
    stderr_tail = "\n".join(proc.stderr.splitlines()[-20:]) if proc.stderr else ""

    return BrowserRunResult(
        browser=browser,
        exit_code=proc.returncode,
        passed=passed,
        failed=failed,
        errors=errors,
        duration_ms=duration_ms,
        trace_path=trace_path,
        stderr_tail=stderr_tail,
        json_report=json_report,
        a11y_violations=a11y_violations,
    )


@router.post("/run", response_model=SilkRunOutput)
async def run_spec(body: SilkRunInput) -> SilkRunOutput:
    """Execute a Playwright .spec.ts via *npx playwright test*.

    Runs all requested browsers **concurrently** via asyncio.gather so that
    a 3-browser run takes roughly as long as the slowest single browser rather
    than the sum.  Supports network mocking and axe-core a11y audits.
    """
    npx = _node_bin("npx")
    if not npx:
        raise HTTPException(400, detail="npx not found — install Node.js 18+")

    # Validate browsers eagerly before spawning anything.
    valid_browsers = {"chromium", "firefox", "webkit"}
    browsers = body.browsers if body.browsers else ["chromium"]
    for b in browsers:
        if b not in valid_browsers:
            raise HTTPException(400, detail=f"Unknown browser '{b}'. Choose from: {valid_browsers}")

    run_id = uuid.uuid4().hex
    run_d = _run_dir(run_id)

    # Resolve spec path.
    if body.spec_path:
        spec = Path(body.spec_path)
        if not spec.is_absolute() and body.workspace_dir:
            spec = Path(body.workspace_dir) / spec
        if not spec.exists():
            raise HTTPException(404, detail=f"spec file not found: {spec}")
        original_code = spec.read_text(encoding="utf-8")
        spec_label = body.spec_path
    elif body.inline_code:
        original_code = body.inline_code
        spec_label = "<inline>"
    else:
        raise HTTPException(400, detail="provide either spec_path or inline_code")

    # Apply wrappers for mocks and a11y.
    code = original_code
    if body.mocks:
        code = _build_mock_wrapper(code, body.mocks)
    if body.run_accessibility_audit:
        code = _build_a11y_wrapper(code)

    tmp_file = run_d / "wrapped.spec.ts"
    tmp_file.write_text(code, encoding="utf-8")
    spec_path_str = str(tmp_file)

    env = {**os.environ, **body.env_vars}
    timeout_s = body.timeout_ms / 1000

    total_start_ns = _monotonic_ns()

    # Run all browsers concurrently.
    results: list[BrowserRunResult] = await asyncio.gather(
        *[
            _run_single_browser_async(
                npx=npx,
                spec_path_str=spec_path_str,
                browser=b,
                run_d=run_d,
                env=env,
                timeout_s=timeout_s,
                workspace_dir=body.workspace_dir,
            )
            for b in browsers
        ]
    )

    total_duration_ms = (_monotonic_ns() - total_start_ns) // 1_000_000

    per_browser: dict[str, BrowserRunResult] = dict(zip(browsers, results))

    # Propagate timeout as HTTP 504 if any browser timed out.
    for r in results:
        if r.exit_code == -1 and "Timed out" in r.stderr_tail:
            raise HTTPException(504, detail=f"spec run timed out after {body.timeout_ms} ms")

    # Aggregate across browsers.
    agg_passed = sum(r.passed for r in results)
    agg_failed = sum(r.failed for r in results)
    agg_errors = sum(r.errors for r in results)
    # Overall exit code: 0 only if all browsers passed.
    overall_exit = 0 if all(r.exit_code == 0 for r in results) else 1
    # Aggregate a11y violations across browsers (deduplicate by rule+impact).
    all_violations: list[A11yViolation] = []
    seen_rules: set[str] = set()
    for r in results:
        for v in r.a11y_violations:
            key = f"{v.rule}:{v.impact}"
            if key not in seen_rules:
                seen_rules.add(key)
                all_violations.append(v)

    # Use first browser's trace/report as the canonical reference.
    first = results[0]
    canonical_trace = first.trace_path
    canonical_report = first.json_report
    canonical_stderr = first.stderr_tail

    # Parse screenshots from JSON report for history.
    screenshot_paths = _parse_screenshot_paths(canonical_report)

    # Persist to run history.
    silk_storage.save_run(
        run_id=run_id,
        spec_path=spec_label,
        exit_code=overall_exit,
        duration_ms=total_duration_ms,
        browsers=browsers,
        trace_path=canonical_trace,
        screenshot_paths=screenshot_paths,
        a11y_violations_count=len(all_violations),
        stderr_tail=canonical_stderr,
        json_report=canonical_report,
    )

    # Emit cross-module event if any browser failed.
    if agg_failed > 0:
        _emit_silk_failed(
            run_id=run_id,
            spec_path=spec_label,
            browsers=browsers,
            failed_count=agg_failed,
        )

    # Best-effort RunResult v2 publish to Hub/Weave (non-blocking).
    asyncio.create_task(
        _publish_run_result_v2(
            run_id=run_id,
            spec_label=spec_label,
            browsers=browsers,
            per_browser=per_browser,
            overall_exit=overall_exit,
            agg_passed=agg_passed,
            agg_failed=agg_failed,
            duration_ms=total_duration_ms,
        )
    )

    return SilkRunOutput(
        run_id=run_id,
        exit_code=overall_exit,
        passed=agg_passed,
        failed=agg_failed,
        errors=agg_errors,
        duration_ms=total_duration_ms,
        trace_path=canonical_trace,
        json_report=canonical_report,
        stderr_tail=canonical_stderr,
        per_browser_results=per_browser,
        a11y_violations=all_violations,
    )


def _emit_silk_failed(
    *,
    run_id: str,
    spec_path: str,
    browsers: list[str],
    failed_count: int,
) -> None:
    """Fire silk.failed cross-module event (best-effort, non-blocking)."""
    try:
        from ..api.events import write_event
        from datetime import datetime, timezone

        workspace = storage.home_dir()
        event_dict = {
            "version": "1",
            "type": "silk.failed",
            "source": "silk",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "context": {
                "request_id": run_id,
                "summary": f"{failed_count} test(s) failed in {spec_path} [{', '.join(browsers)}]",
            },
            "actions": [],
        }
        write_event(workspace, event_dict)
    except Exception:
        pass  # Event emission is best-effort.


async def _publish_run_result_v2(
    *,
    run_id: str,
    spec_label: str,
    browsers: list[str],
    per_browser: dict[str, "BrowserRunResult"],
    overall_exit: int,
    agg_passed: int,
    agg_failed: int,
    duration_ms: int,
) -> None:
    """Publish a RunResult v2 payload to Hub and Weave (best-effort).

    Reads target URLs and token from environment:
      EYES_HUB_URL   — Hub /api/ingest endpoint (optional)
      EYES_WEAVE_URL — Weave /api/runs/ingest endpoint (optional)
      EYES_TOKEN     — Bearer token for both endpoints (optional)

    If neither env var is set, this is a no-op.  Failures are silently
    swallowed — this is explicitly best-effort and must never block the run.
    """
    hub_url = os.environ.get("EYES_HUB_URL", "").rstrip("/")
    weave_url = os.environ.get("EYES_WEAVE_URL", "").rstrip("/")
    token = os.environ.get("EYES_TOKEN", "")

    if not hub_url and not weave_url:
        return

    from datetime import datetime, timezone

    now = datetime.now(tz=timezone.utc).isoformat()

    # Build requests list — one entry per browser per spec.
    requests_list: list[dict] = []
    for browser, br in per_browser.items():
        # Try to get per-test entries from the JSON report.
        report = br.json_report or {}
        suites = report.get("suites", [])
        if suites:
            def _flatten(suite: dict) -> list[dict]:
                out: list[dict] = []
                for spec in suite.get("specs", []):
                    for test in spec.get("tests", []):
                        result = (test.get("results") or [{}])[0]
                        status_str = "pass" if test.get("ok") else "fail"
                        entry: dict = {
                            "name": spec.get("title", "unknown"),
                            "status": status_str,
                            "browser": browser,
                            "duration_ms": result.get("duration", 0),
                        }
                        err = result.get("error", {})
                        if err and isinstance(err, dict):
                            entry["error"] = err.get("message", "")
                        elif err and isinstance(err, str):
                            entry["error"] = err
                        out.append(entry)
                for sub in suite.get("suites", []):
                    out.extend(_flatten(sub))
                return out

            for suite in suites:
                requests_list.extend(_flatten(suite))
        else:
            # No suite data — emit a single aggregate entry.
            requests_list.append({
                "name": spec_label,
                "status": "pass" if br.exit_code == 0 else "fail",
                "browser": browser,
                "duration_ms": br.duration_ms,
                "evidence": br.trace_path or None,
            })

    payload: dict = {
        "schema_version": 2,
        "run_id": run_id,
        "product": "eyes",
        "suite_type": "e2e",
        "started_at": now,
        "finished_at": now,
        "duration_ms": duration_ms,
        "total": agg_passed + agg_failed,
        "passed": agg_passed,
        "failed": agg_failed,
        "flaky": 0,
        "requests": requests_list,
    }

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Idempotency-Key": run_id,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    import httpx as _httpx

    targets = []
    if hub_url:
        targets.append(f"{hub_url}/api/ingest")
    if weave_url:
        targets.append(f"{weave_url}/api/runs/ingest")

    try:
        async with _httpx.AsyncClient(timeout=10.0) as client:
            for url in targets:
                try:
                    await client.post(url, json=payload, headers=headers)
                except Exception:
                    pass  # Best-effort — individual endpoint failure is silent.
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 3. Trace download
# ---------------------------------------------------------------------------


@router.get("/trace/{run_id}")
def get_trace(run_id: str) -> FileResponse:
    """Return the Playwright trace ZIP for a previous run."""
    if ".." in run_id or "/" in run_id or "\\" in run_id:
        raise HTTPException(400, detail="invalid run_id")

    run_d = _silk_dir() / "runs" / run_id
    if not run_d.exists():
        raise HTTPException(404, detail=f"run {run_id!r} not found")

    trace_zips = list(run_d.rglob("*.zip"))
    if not trace_zips:
        raise HTTPException(404, detail=f"no trace found for run {run_id!r}")

    zip_path = trace_zips[0]
    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=f"trace-{run_id}.zip",
    )


# ---------------------------------------------------------------------------
# 4. Screenshot diff
# ---------------------------------------------------------------------------


@router.post("/screenshot-diff", response_model=ScreenshotDiffOutput)
def screenshot_diff(body: ScreenshotDiffInput) -> ScreenshotDiffOutput:
    """Compute a pixel diff between two PNG images using Pillow ImageChops."""
    from .ws_security import _safe_resolve_path

    try:
        baseline_p = _safe_resolve_path(body.baseline_path)
        current_p = _safe_resolve_path(body.current_path)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc

    for p in (baseline_p, current_p):
        if not p.exists():
            raise HTTPException(404, detail=f"image not found: {p}")

    try:
        from PIL import Image, ImageChops, ImageFilter
    except ImportError:
        raise HTTPException(500, detail="Pillow is not installed — run: uv add pillow")

    try:
        baseline_img = Image.open(baseline_p).convert("RGB")
        current_img = Image.open(current_p).convert("RGB")
    except Exception as exc:
        raise HTTPException(400, detail=f"could not open image: {exc}") from exc

    if baseline_img.size != current_img.size:
        current_img = current_img.resize(baseline_img.size, Image.LANCZOS)

    diff_img = ImageChops.difference(baseline_img, current_img)
    diff_arr = diff_img.convert("L")
    thresholded = diff_arr.point(lambda x: 255 if x > 10 else 0)

    pixel_diff_count = sum(1 for px in thresholded.getdata() if px > 0)
    total_pixels = baseline_img.width * baseline_img.height
    diff_ratio = pixel_diff_count / total_pixels if total_pixels > 0 else 0.0

    enhanced = diff_img.filter(ImageFilter.SHARPEN)
    diff_out_path = _silk_dir() / "diffs" / f"{uuid.uuid4().hex}.png"
    diff_out_path.parent.mkdir(parents=True, exist_ok=True)
    enhanced.save(str(diff_out_path))

    return ScreenshotDiffOutput(
        diff_path=str(diff_out_path),
        pixel_diff_count=pixel_diff_count,
        total_pixels=total_pixels,
        diff_ratio=round(diff_ratio, 6),
        passed=diff_ratio <= body.threshold,
    )


# ---------------------------------------------------------------------------
# 5. Browser presence check (lightweight)
# ---------------------------------------------------------------------------


@router.get("/browsers/check", response_model=BrowserCheckOutput)
def check_browsers() -> BrowserCheckOutput:
    """Check if Playwright Chromium binaries are present in the local cache."""
    candidates = [
        Path.home() / ".cache" / "ms-playwright",
        Path.home() / "Library" / "Caches" / "ms-playwright",
    ]
    custom = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if custom:
        candidates.append(Path(custom))

    found: list[str] = []
    for c in candidates:
        if c.exists():
            chromium_dirs = list(c.glob("chromium-*"))
            if chromium_dirs:
                found.extend(str(d) for d in chromium_dirs)

    return BrowserCheckOutput(installed=bool(found), paths=found)


# ---------------------------------------------------------------------------
# 6. Auto-spec from Strand failure
# ---------------------------------------------------------------------------


@router.post("/auto-spec", response_model=AutoSpecOutput)
def auto_spec(body: AutoSpecInput) -> AutoSpecOutput:
    """Generate a minimal Playwright spec that reproduces a failed Strand request."""
    headers_ts = "\n".join(
        f"      '{k}': '{v}'," for k, v in body.headers.items()
    )
    body_ts = ""
    if body.body:
        escaped = body.body.replace("`", "\\`")
        body_ts = f"    body: `{escaped}`,"

    status_assert = ""
    if body.status_code:
        status_assert = f"\n  expect(response.status()).toBe({body.status_code});"

    spec_code = f"""\
import {{ test, expect }} from '@playwright/test';

// Auto-generated from Strand request {body.request_id!r}
// Reproduce the failed request and verify the response.

test('reproduce {body.request_id}', async ({{ request }}) => {{
  const response = await request.{body.method.lower()}('{body.url}', {{
    headers: {{
{headers_ts}
    }},
{body_ts}
  }});
{status_assert}
  // TODO: add your assertions here
  expect(response.ok()).toBeTruthy();
}});
"""

    if body.workspace_dir:
        out_dir = Path(body.workspace_dir) / ".theridion" / "silk" / "auto-generated"
    else:
        out_dir = _silk_dir() / "auto-generated"
    out_dir.mkdir(parents=True, exist_ok=True)

    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", body.request_id)
    if not safe_id:
        raise HTTPException(400, detail="request_id is empty or invalid")
    spec_path = out_dir / f"{safe_id}.spec.ts"
    spec_path.write_text(spec_code, encoding="utf-8")

    return AutoSpecOutput(spec_path=str(spec_path), spec_code=spec_code)


# ---------------------------------------------------------------------------
# 7. Spec recording — Playwright codegen
# ---------------------------------------------------------------------------


@router.post("/record/start", response_model=RecordStartOutput)
async def record_start(body: RecordStartInput) -> RecordStartOutput:
    """Launch Playwright codegen subprocess and return a session_id.

    The caller should open GET /api/silk/record/stream/{session_id} (SSE)
    to receive the generated spec lines in real-time, then POST
    /api/silk/record/stop to finalize.
    """
    if urlparse(body.url).scheme not in ("http", "https"):
        raise HTTPException(400, detail="record URL must use http or https scheme")

    fw = silk_frameworks.get_framework(body.framework)
    if fw is None:
        raise HTTPException(400, detail=f"unknown framework: {body.framework}")
    if not fw.recordable:
        raise HTTPException(
            400,
            detail=f"recording not yet supported for {fw.label}; use manual authoring",
        )

    npx = _node_bin("npx")
    if not npx:
        raise HTTPException(400, detail="npx not found — install Node.js 18+")

    session_id = uuid.uuid4().hex
    output_dir = _silk_dir() / "codegen" / session_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # For transpile-via-playwright frameworks we always record as playwright-test TS
    # and convert to the requested framework on stop.
    is_transpile_target = fw.recordable_via_transpile and fw.codegen_target is None
    effective_codegen_target = fw.codegen_target or "playwright-test"
    effective_extension = ".spec.ts" if is_transpile_target else fw.file_extension
    output_file = output_dir / f"spec{effective_extension}"

    if is_transpile_target:
        _codegen_request_framework[session_id] = fw.id

    env = {**os.environ}
    cwd = body.workspace_dir or str(output_dir)

    proc = await asyncio.create_subprocess_exec(
        npx,
        "playwright",
        "codegen",
        f"--target={effective_codegen_target}",
        f"--output={output_file}",
        body.url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
        cwd=cwd,
    )

    _codegen_procs[session_id] = proc
    _codegen_output_files[session_id] = output_file

    return RecordStartOutput(
        session_id=session_id,
        message=f"Codegen started. Open browser at {body.url}. Call /record/stop when done.",
    )


@router.get("/record/stream/{session_id}")
async def record_stream(session_id: str) -> StreamingResponse:
    """SSE stream of codegen output for an active recording session."""
    if ".." in session_id or "/" in session_id:
        raise HTTPException(400, detail="invalid session_id")

    proc = _codegen_procs.get(session_id)
    if not proc:
        raise HTTPException(404, detail=f"session {session_id!r} not found")

    async def _stream() -> AsyncGenerator[str, None]:
        if proc.stdout is None:
            yield "data: ERROR no stdout\n\n"
            return
        async for raw in proc.stdout:
            line = raw.decode(errors="replace").rstrip()
            if line:
                yield f"data: {line}\n\n"
        yield "data: DONE\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/record/stop", response_model=RecordStopOutput)
async def record_stop(body: dict) -> RecordStopOutput:
    """Terminate the codegen subprocess and return the captured spec text."""
    session_id = body.get("session_id", "")
    if not session_id or ".." in session_id or "/" in session_id:
        raise HTTPException(400, detail="provide valid session_id")

    proc = _codegen_procs.pop(session_id, None)
    if not proc:
        raise HTTPException(404, detail=f"session {session_id!r} not found or already stopped")

    try:
        proc.terminate()
        await asyncio.wait_for(proc.wait(), timeout=5.0)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass

    # Use the output file path recorded at start time; fall back to legacy spec.ts for
    # sessions that were started before _codegen_output_files tracking was introduced.
    output_file = _codegen_output_files.pop(session_id, None) or (
        _silk_dir() / "codegen" / session_id / "spec.ts"
    )

    # Retrieve (and remove) any pending transpile-target framework for this session.
    requested_framework = _codegen_request_framework.pop(session_id, None)

    spec_text = ""
    spec_path_str: str | None = None

    if output_file.exists():
        raw_pw_text = output_file.read_text(encoding="utf-8")

        if requested_framework is not None:
            # Transpile Playwright-test TS into the user's requested framework.
            try:
                spec_text = silk_transpile.transpile_playwright_spec(
                    requested_framework, raw_pw_text
                )
                # Write transpiled output next to the raw file so it has the right extension.
                fw = silk_frameworks.get_framework(requested_framework)
                ext = fw.file_extension if fw is not None else f".{requested_framework}"
                transpiled_path = output_file.parent / f"spec{ext}"
                transpiled_path.write_text(spec_text, encoding="utf-8")
                spec_path_str = str(transpiled_path)
            except Exception as exc:  # noqa: BLE001
                # Fallback: return raw Playwright text with an error note.
                spec_text = (
                    f"// Transpilation failed ({exc}); raw Playwright output below.\n"
                    + raw_pw_text
                )
                spec_path_str = str(output_file)
        else:
            spec_text = raw_pw_text
            spec_path_str = str(output_file)

    return RecordStopOutput(
        session_id=session_id,
        spec_text=spec_text,
        spec_path=spec_path_str,
    )


# ---------------------------------------------------------------------------
# 8. Manual spec save (any framework)
# ---------------------------------------------------------------------------


@router.post("/spec/save", response_model=SpecSaveOutput)
def spec_save(body: SpecSaveInput) -> SpecSaveOutput:
    """Save a manually authored test spec to disk.

    The file is written to *workspace_dir* when provided, otherwise to
    ``~/.theridion/silk/specs/``.  The filename must not contain path-traversal
    sequences; the framework's file extension is appended when missing.
    """
    fw = silk_frameworks.get_framework(body.framework)
    if fw is None:
        raise HTTPException(400, detail=f"unknown framework: {body.framework}")

    # Sanitise filename — reject empty, traversal, and absolute paths.
    fn = body.filename
    if not fn or "/" in fn or "\\" in fn or ".." in fn:
        raise HTTPException(
            400,
            detail="filename must not be empty, contain '/', '\\\\', or '..'",
        )

    # Append framework extension when missing.
    if not fn.endswith(fw.file_extension):
        fn = fn + fw.file_extension

    # Resolve target directory.
    if body.workspace_dir:
        target_base = Path(body.workspace_dir)
    else:
        target_base = _silk_dir() / "specs"
        target_base.mkdir(parents=True, exist_ok=True)

    # Containment check — prevent escaping the base directory.
    try:
        dest = _safe_path_under(target_base, fn)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(body.code, encoding="utf-8")

    return SpecSaveOutput(spec_path=str(dest))


# ---------------------------------------------------------------------------
# 9. Visual regression — baseline management
# ---------------------------------------------------------------------------


def _baseline_filename(test_id: str, browser: str, viewport: str) -> str:
    safe_id = test_id.replace("/", "_").replace(" ", "_")
    safe_viewport = viewport.replace("x", "_")
    return f"{safe_id}-{browser}-{safe_viewport}.png"


@router.post("/baseline/save", response_model=BaselineSaveOutput)
def baseline_save(body: BaselineSaveInput) -> BaselineSaveOutput:
    """Copy a screenshot as the approved baseline for a given test+browser+viewport."""
    src = Path(body.screenshot_path)
    if not src.exists():
        raise HTTPException(404, detail=f"screenshot not found: {src}")

    try:
        from PIL import Image
    except ImportError:
        raise HTTPException(500, detail="Pillow is not installed — run: uv add pillow")

    try:
        img = Image.open(src)
        img.verify()
    except Exception as exc:
        raise HTTPException(400, detail=f"not a valid PNG: {exc}") from exc

    dest_name = _baseline_filename(body.test_id, body.browser, body.viewport)
    dest = _baselines_dir() / dest_name

    # Atomic copy: write to temp then replace.
    import tempfile as _tempfile
    fd, tmp = _tempfile.mkstemp(dir=_baselines_dir(), suffix=".tmp")
    try:
        os.close(fd)
        shutil.copy2(str(src), tmp)
        os.replace(tmp, str(dest))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    return BaselineSaveOutput(
        baseline_path=str(dest),
        test_id=body.test_id,
        browser=body.browser,
        viewport=body.viewport,
    )


@router.post("/baseline/compare", response_model=BaselineCompareOutput)
def baseline_compare(body: BaselineCompareInput) -> BaselineCompareOutput:
    """Diff current screenshot against saved baseline, return pixel stats + threshold."""
    dest_name = _baseline_filename(body.test_id, body.browser, body.viewport)
    baseline_p = _baselines_dir() / dest_name

    if not baseline_p.exists():
        raise HTTPException(
            404,
            detail=f"no baseline for test_id={body.test_id!r} browser={body.browser} viewport={body.viewport}",
        )

    current_p = Path(body.current_path)
    if not current_p.exists():
        raise HTTPException(404, detail=f"current screenshot not found: {current_p}")

    try:
        from PIL import Image, ImageChops, ImageFilter
    except ImportError:
        raise HTTPException(500, detail="Pillow is not installed — run: uv add pillow")

    try:
        baseline_img = Image.open(baseline_p).convert("RGB")
        current_img = Image.open(current_p).convert("RGB")
    except Exception as exc:
        raise HTTPException(400, detail=f"could not open image: {exc}") from exc

    if baseline_img.size != current_img.size:
        current_img = current_img.resize(baseline_img.size, Image.LANCZOS)

    diff_img = ImageChops.difference(baseline_img, current_img)
    diff_arr = diff_img.convert("L")
    thresholded = diff_arr.point(lambda x: 255 if x > 10 else 0)

    pixel_diff_count = sum(1 for px in thresholded.getdata() if px > 0)
    total_pixels = baseline_img.width * baseline_img.height
    diff_ratio = pixel_diff_count / total_pixels if total_pixels > 0 else 0.0

    enhanced = diff_img.filter(ImageFilter.SHARPEN)
    diff_out_path = _silk_dir() / "diffs" / f"{uuid.uuid4().hex}.png"
    diff_out_path.parent.mkdir(parents=True, exist_ok=True)
    enhanced.save(str(diff_out_path))

    return BaselineCompareOutput(
        baseline_path=str(baseline_p),
        diff_path=str(diff_out_path),
        pixel_diff_count=pixel_diff_count,
        total_pixels=total_pixels,
        diff_ratio=round(diff_ratio, 6),
        passed=diff_ratio <= body.threshold,
        approved=False,
    )


@router.post("/baseline/approve", response_model=BaselineApproveOutput)
def baseline_approve(body: BaselineApproveInput) -> BaselineApproveOutput:
    """Promote a candidate screenshot to the approved baseline.

    Copies *candidate_path* over the stored baseline file, then persists
    approval metadata (approver, timestamp, diff_ratio) in a sidecar
    ``<baseline>.approved.json`` file next to the PNG.  This is the
    ``approved=True`` workflow — the compare endpoint always returns
    ``approved=False``; you call approve explicitly after human review.
    """
    from datetime import datetime, timezone

    candidate_p = Path(body.candidate_path)
    if not candidate_p.exists():
        raise HTTPException(404, detail=f"candidate screenshot not found: {candidate_p}")

    try:
        from PIL import Image
    except ImportError:
        raise HTTPException(500, detail="Pillow is not installed — run: uv add pillow")

    # Validate it is actually an image.
    try:
        img = Image.open(candidate_p)
        img.verify()
    except Exception as exc:
        raise HTTPException(400, detail=f"not a valid PNG: {exc}") from exc

    dest_name = _baseline_filename(body.test_id, body.browser, body.viewport)
    dest = _baselines_dir() / dest_name

    # Atomic copy: write to temp then replace.
    import tempfile as _tempfile
    fd, tmp = _tempfile.mkstemp(dir=_baselines_dir(), suffix=".tmp")
    try:
        os.close(fd)
        shutil.copy2(str(candidate_p), tmp)
        os.replace(tmp, str(dest))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    approved_at = datetime.now(tz=timezone.utc).isoformat()

    # Persist metadata next to the baseline file.
    meta_path = _baselines_dir() / f"{dest_name}.approved.json"
    meta = {
        "test_id": body.test_id,
        "browser": body.browser,
        "viewport": body.viewport,
        "approved": True,
        "approved_by": body.approved_by,
        "approved_at": approved_at,
        "diff_ratio": round(body.diff_ratio, 6),
        "candidate_path": str(candidate_p),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return BaselineApproveOutput(
        baseline_path=str(dest),
        test_id=body.test_id,
        browser=body.browser,
        viewport=body.viewport,
        approved=True,
        approved_by=body.approved_by,
        approved_at=approved_at,
        diff_ratio=round(body.diff_ratio, 6),
    )


# ---------------------------------------------------------------------------
# 9b. Record → save → run bridge
# ---------------------------------------------------------------------------


@router.post("/record/save-and-run", response_model=RecordSaveAndRunOutput)
async def record_save_and_run(body: RecordSaveAndRunInput) -> RecordSaveAndRunOutput:
    """Stop an active codegen session, save the spec, then immediately run it.

    This closes the record→run loop: instead of the UI discarding the captured
    spec, it is persisted and the run result is returned in one call.
    """
    npx = _node_bin("npx")
    if not npx:
        raise HTTPException(400, detail="npx not found — install Node.js 18+")

    session_id = body.session_id
    if not session_id or ".." in session_id or "/" in session_id:
        raise HTTPException(400, detail="invalid session_id")

    # Stop the codegen session (terminate subprocess, read output file).
    proc = _codegen_procs.pop(session_id, None)
    if proc is not None:
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    output_file = _codegen_output_files.pop(session_id, None) or (
        _silk_dir() / "codegen" / session_id / "spec.ts"
    )
    requested_framework = _codegen_request_framework.pop(session_id, None)

    if not output_file.exists():
        raise HTTPException(404, detail=f"no captured spec for session {session_id!r}")

    raw_pw_text = output_file.read_text(encoding="utf-8")

    # Transpile if the session used a transpile-target framework.
    if requested_framework is not None:
        try:
            spec_text = silk_transpile.transpile_playwright_spec(requested_framework, raw_pw_text)
            fw = silk_frameworks.get_framework(requested_framework)
            ext = fw.file_extension if fw is not None else f".{requested_framework}"
        except Exception as exc:
            spec_text = raw_pw_text
            ext = ".spec.ts"
            requested_framework = None
    else:
        spec_text = raw_pw_text
        ext = ".spec.ts"

    # Save spec to disk.
    framework_id = requested_framework or body.framework
    fw = silk_frameworks.get_framework(framework_id)
    if fw is None:
        fw = silk_frameworks.get_framework("playwright-ts")

    fn = body.filename
    if fw and not fn.endswith(fw.file_extension):
        fn = fn + fw.file_extension

    if body.workspace_dir:
        target_base = Path(body.workspace_dir)
    else:
        target_base = _silk_dir() / "specs"
        target_base.mkdir(parents=True, exist_ok=True)

    try:
        dest = _safe_path_under(target_base, fn)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(spec_text, encoding="utf-8")
    spec_path_str = str(dest)

    # Run the saved spec immediately.
    run_body = SilkRunInput(
        spec_path=spec_path_str,
        workspace_dir=body.workspace_dir,
        browsers=body.browsers,
        timeout_ms=body.timeout_ms,
    )
    run_result = await run_spec(run_body)

    return RecordSaveAndRunOutput(spec_path=spec_path_str, run=run_result)


# ---------------------------------------------------------------------------
# 10. Run history
# ---------------------------------------------------------------------------


@router.get("/runs")
def list_run_history(limit: int = 50) -> list[dict]:
    """Return recent Silk run summaries ordered newest-first."""
    if limit < 1 or limit > 500:
        raise HTTPException(400, detail="limit must be 1–500")
    return silk_storage.list_runs(limit=limit)


@router.get("/runs/{run_id}")
def get_run_history(run_id: str) -> dict:
    """Return a single run with full json_report."""
    if ".." in run_id or "/" in run_id or "\\" in run_id:
        raise HTTPException(400, detail="invalid run_id")
    run = silk_storage.get_run(run_id)
    if run is None:
        raise HTTPException(404, detail=f"run {run_id!r} not found in history")
    return run
