"""Silk — Frontend testing module (Playwright runner integration).

Endpoints
---------
GET  /api/silk/browsers/check            — Playwright Chromium presence check
POST /api/silk/install-browsers          — SSE-stream Chromium install
POST /api/silk/install-browsers/sync     — Blocking Chromium install
POST /api/silk/run                       — Execute a .spec.ts (multi-browser, mocks, a11y)
GET  /api/silk/trace/{id}                — Stream back a trace ZIP
POST /api/silk/screenshot-diff           — Pixel-diff two PNG images
POST /api/silk/auto-spec                 — Generate spec from a Strand failure
POST /api/silk/record/start              — Start Playwright codegen session (SSE)
POST /api/silk/record/stop               — Stop codegen, return spec text
POST /api/silk/baseline/save             — Save screenshot as visual-regression baseline
POST /api/silk/baseline/compare          — Diff current screenshot vs saved baseline
GET  /api/silk/runs                      — Run history (last N)
GET  /api/silk/runs/{id}                 — Single run detail

All paths require X-Theridion-Token (enforced by main.py middleware).
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from .. import storage
from .. import silk_storage

router = APIRouter(prefix="/api/silk", tags=["silk"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SILK_DIR_NAME = "silk"

# Registry of active codegen subprocesses keyed by session_id
_codegen_procs: dict[str, asyncio.subprocess.Process] = {}


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


def _monotonic_ns() -> int:
    import time as _time
    return _time.monotonic_ns()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


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


class RecordStartInput(BaseModel):
    url: str = Field(..., description="URL for Playwright codegen to open.")
    workspace_dir: str | None = None


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
    # Strip existing imports from original to avoid duplicate
    lines = original_code.splitlines()
    filtered = [l for l in lines if not l.strip().startswith("import {")]
    return wrapper + "\n".join(filtered)


def _build_a11y_wrapper(original_code: str) -> str:
    """Wrap spec code to inject axe-core accessibility audit after navigation."""
    a11y_snippet = """\
import AxeBuilder from '@axe-core/playwright';

// Silk a11y wrapper — injected by Silk backend
"""
    if "AxeBuilder" in original_code:
        return original_code
    return a11y_snippet + original_code


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
    """Execute Playwright for one browser engine and return structured result."""
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
    )


@router.post("/run", response_model=SilkRunOutput)
def run_spec(body: SilkRunInput) -> SilkRunOutput:
    """Execute a Playwright .spec.ts via *npx playwright test*.

    Supports multi-browser runs, network mocking, and axe-core a11y audits.
    """
    npx = _node_bin("npx")
    if not npx:
        raise HTTPException(400, detail="npx not found — install Node.js 18+")

    run_id = uuid.uuid4().hex
    run_d = _run_dir(run_id)
    tmp_file: Path | None = None

    try:
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
        browsers = body.browsers if body.browsers else ["chromium"]

        per_browser: dict[str, BrowserRunResult] = {}
        total_start_ns = _monotonic_ns()

        for browser in browsers:
            result = _run_single_browser(
                npx=npx,
                spec_path_str=spec_path_str,
                browser=browser,
                run_d=run_d,
                env=env,
                timeout_s=body.timeout_ms / 1000,
                workspace_dir=body.workspace_dir,
            )
            # Propagate timeout as HTTP 504.
            if result.exit_code == -1 and "Timed out" in result.stderr_tail:
                raise HTTPException(
                    504, detail=f"spec run timed out after {body.timeout_ms} ms"
                )
            per_browser[browser] = result

        total_duration_ms = (_monotonic_ns() - total_start_ns) // 1_000_000

        # Aggregate across browsers.
        agg_passed = sum(r.passed for r in per_browser.values())
        agg_failed = sum(r.failed for r in per_browser.values())
        agg_errors = sum(r.errors for r in per_browser.values())
        # Overall exit code: 0 only if all browsers passed.
        overall_exit = 0 if all(r.exit_code == 0 for r in per_browser.values()) else 1

        # Use first browser's trace/report as the canonical reference.
        first = per_browser[browsers[0]]
        canonical_trace = first.trace_path
        canonical_report = first.json_report
        canonical_stderr = first.stderr_tail

        # Persist to run history.
        silk_storage.save_run(
            run_id=run_id,
            spec_path=spec_label,
            exit_code=overall_exit,
            duration_ms=total_duration_ms,
            browsers=browsers,
            trace_path=canonical_trace,
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
        )

    except subprocess.TimeoutExpired:
        raise HTTPException(504, detail=f"spec run timed out after {body.timeout_ms} ms")


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
    baseline_p = Path(body.baseline_path)
    current_p = Path(body.current_path)

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

    spec_path = out_dir / f"{body.request_id}.spec.ts"
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
    npx = _node_bin("npx")
    if not npx:
        raise HTTPException(400, detail="npx not found — install Node.js 18+")

    session_id = uuid.uuid4().hex
    output_dir = _silk_dir() / "codegen" / session_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "spec.ts"

    env = {**os.environ}
    cwd = body.workspace_dir or str(output_dir)

    proc = await asyncio.create_subprocess_exec(
        npx,
        "playwright",
        "codegen",
        "--target=playwright-test",
        f"--output={output_file}",
        body.url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
        cwd=cwd,
    )

    _codegen_procs[session_id] = proc

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

    output_file = _silk_dir() / "codegen" / session_id / "spec.ts"
    spec_text = ""
    spec_path_str: str | None = None

    if output_file.exists():
        spec_text = output_file.read_text(encoding="utf-8")
        spec_path_str = str(output_file)

    return RecordStopOutput(
        session_id=session_id,
        spec_text=spec_text,
        spec_path=spec_path_str,
    )


# ---------------------------------------------------------------------------
# 8. Visual regression — baseline management
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


# ---------------------------------------------------------------------------
# 9. Run history
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
