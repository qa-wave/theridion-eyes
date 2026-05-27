"""Tests for the Silk frontend-testing module (/api/silk/*).

Covers (original 17):
  - GET  /api/silk/browsers/check — happy path + missing cache
  - POST /api/silk/run            — spec_path + inline_code + validation errors
  - GET  /api/silk/trace/{id}     — 404 for unknown run, 400 for bad id
  - POST /api/silk/screenshot-diff — pixel diff math with synthetic images
  - POST /api/silk/auto-spec      — generated code structure
  - POST /api/silk/install-browsers/sync — npx absent path

New (v2 — ~30 additional):
  - POST /api/silk/run multi-browser, mocks, a11y fields
  - POST /api/silk/record/start — codegen subprocess
  - POST /api/silk/record/stop  — terminate + spec capture
  - POST /api/silk/baseline/save + /baseline/compare
  - GET  /api/silk/runs + /runs/{id} — history persistence
  - silk_storage module directly
  - _build_mock_wrapper helper

Token auth is handled globally by conftest.py (_pin_sidecar_token + patched
TestClient.__init__), so individual tests do not need HEADERS dicts or env
patches.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """App client with isolated THERIDION_HOME."""
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar.main import create_app

    return TestClient(create_app())


# ---------------------------------------------------------------------------
# 1. Browser presence check
# ---------------------------------------------------------------------------


def test_check_browsers_no_cache(client: TestClient) -> None:
    """Returns 200 with installed bool when no ms-playwright dirs exist."""
    res = client.get("/api/silk/browsers/check")
    assert res.status_code == 200
    data = res.json()
    assert "installed" in data
    assert isinstance(data["paths"], list)


def test_check_browsers_with_cache(
    client: TestClient, tmp_path: Path
) -> None:
    """Returns installed=True when a chromium-* dir is present."""
    cache_dir = tmp_path / ".cache" / "ms-playwright" / "chromium-123"
    cache_dir.mkdir(parents=True)

    with patch("pathlib.Path.home", return_value=tmp_path):
        res = client.get("/api/silk/browsers/check")

    assert res.status_code == 200
    data = res.json()
    assert data["installed"] is True
    assert len(data["paths"]) >= 1


# ---------------------------------------------------------------------------
# 2. POST /api/silk/run
# ---------------------------------------------------------------------------


def test_run_requires_spec_or_code(client: TestClient) -> None:
    """Returns 400 when neither spec_path nor inline_code is provided."""
    res = client.post("/api/silk/run", json={})
    assert res.status_code == 400
    assert "spec_path" in res.json()["detail"] or "inline_code" in res.json()["detail"]


def test_run_spec_path_not_found(client: TestClient, tmp_path: Path) -> None:
    """Returns 404 when spec_path points to a missing file."""
    res = client.post(
        "/api/silk/run",
        json={"spec_path": str(tmp_path / "missing.spec.ts")},
    )
    assert res.status_code == 404


def test_run_npx_not_found(client: TestClient, tmp_path: Path) -> None:
    """Returns 400 when npx is not on PATH."""
    spec = tmp_path / "sample.spec.ts"
    spec.write_text("test('hi', () => {})", encoding="utf-8")

    with patch("shutil.which", return_value=None):
        res = client.post(
            "/api/silk/run",
            json={"spec_path": str(spec)},
        )

    assert res.status_code == 400
    assert "npx" in res.json()["detail"]


def test_run_inline_code_success(client: TestClient) -> None:
    """Inline code path writes temp file and returns a run result."""
    fake_json_report = {
        "stats": {"expected": 1, "unexpected": 0, "skipped": 0},
        "suites": [],
    }

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = json.dumps(fake_json_report)
    mock_result.stderr = ""

    with patch("shutil.which", return_value="/usr/bin/npx"), \
         patch("subprocess.run", return_value=mock_result):
        res = client.post(
            "/api/silk/run",
            json={"inline_code": "import { test } from '@playwright/test';"},
        )

    assert res.status_code == 200
    data = res.json()
    assert "run_id" in data
    assert data["exit_code"] == 0
    assert data["passed"] == 1
    assert data["failed"] == 0


def test_run_captures_failed_tests(client: TestClient, tmp_path: Path) -> None:
    """failed field reflects unexpected count from Playwright JSON report."""
    fake_report = {
        "stats": {"expected": 0, "unexpected": 2, "skipped": 0},
        "suites": [],
    }

    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = json.dumps(fake_report)
    mock_result.stderr = "FAIL my.spec.ts"

    spec = tmp_path / "fail.spec.ts"
    spec.write_text("", encoding="utf-8")

    with patch("shutil.which", return_value="/usr/bin/npx"), \
         patch("subprocess.run", return_value=mock_result):
        res = client.post(
            "/api/silk/run",
            json={"spec_path": str(spec)},
        )

    assert res.status_code == 200
    data = res.json()
    assert data["failed"] == 2
    assert data["exit_code"] == 1


def test_run_timeout_raises_504(client: TestClient, tmp_path: Path) -> None:
    """Returns 504 when the subprocess times out."""
    spec = tmp_path / "slow.spec.ts"
    spec.write_text("", encoding="utf-8")

    with patch("shutil.which", return_value="/usr/bin/npx"), \
         patch("subprocess.run", side_effect=subprocess.TimeoutExpired("npx", 1)):
        res = client.post(
            "/api/silk/run",
            json={"spec_path": str(spec), "timeout_ms": 1000},
        )

    assert res.status_code == 504


# ---------------------------------------------------------------------------
# 3. GET /api/silk/trace/{run_id}
# ---------------------------------------------------------------------------


def test_trace_bad_run_id_path_traversal(client: TestClient) -> None:
    """Rejects run IDs that look like path traversal."""
    # The router will URL-encode or 404 depending on routing rules.
    res = client.get("/api/silk/trace/..%2Fetc%2Fpasswd")
    assert res.status_code in (400, 404, 422)


def test_trace_unknown_run(client: TestClient) -> None:
    """Returns 404 for a run ID that was never created."""
    res = client.get("/api/silk/trace/deadbeef00000000")
    assert res.status_code == 404


def test_trace_returns_zip(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Returns 200 + application/zip when a trace ZIP exists."""
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))

    from theridion_sidecar.api.silk import _run_dir

    run_id = "abc123"
    run_d = _run_dir(run_id)
    trace_dir = run_d / "traces"
    trace_dir.mkdir(parents=True)
    zip_file = trace_dir / "trace.zip"
    zip_file.write_bytes(b"PK")

    res = client.get(f"/api/silk/trace/{run_id}")
    assert res.status_code == 200
    assert "zip" in res.headers["content-type"]


# ---------------------------------------------------------------------------
# 4. POST /api/silk/screenshot-diff
# ---------------------------------------------------------------------------


def test_screenshot_diff_missing_file(client: TestClient) -> None:
    """Returns 404 when a path does not exist."""
    res = client.post(
        "/api/silk/screenshot-diff",
        json={
            "baseline_path": "/nonexistent/baseline.png",
            "current_path": "/nonexistent/current.png",
        },
    )
    assert res.status_code == 404


def test_screenshot_diff_identical_images(
    client: TestClient, tmp_path: Path
) -> None:
    """Identical images produce diff_ratio=0 and passed=True."""
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("Pillow not installed")

    img = Image.new("RGB", (100, 100), color=(128, 0, 0))
    baseline = tmp_path / "baseline.png"
    current = tmp_path / "current.png"
    img.save(str(baseline))
    img.save(str(current))

    res = client.post(
        "/api/silk/screenshot-diff",
        json={
            "baseline_path": str(baseline),
            "current_path": str(current),
        },
    )

    assert res.status_code == 200
    data = res.json()
    assert data["pixel_diff_count"] == 0
    assert data["diff_ratio"] == 0.0
    assert data["passed"] is True


def test_screenshot_diff_different_images(
    client: TestClient, tmp_path: Path
) -> None:
    """Completely different images produce diff_ratio > 0."""
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("Pillow not installed")

    red = Image.new("RGB", (50, 50), color=(255, 0, 0))
    blue = Image.new("RGB", (50, 50), color=(0, 0, 255))
    baseline = tmp_path / "baseline.png"
    current = tmp_path / "current.png"
    red.save(str(baseline))
    blue.save(str(current))

    res = client.post(
        "/api/silk/screenshot-diff",
        json={"baseline_path": str(baseline), "current_path": str(current)},
    )

    assert res.status_code == 200
    data = res.json()
    assert data["pixel_diff_count"] > 0
    assert data["diff_ratio"] > 0
    assert "diff_path" in data
    assert data["total_pixels"] == 50 * 50


def test_screenshot_diff_threshold_fail(
    client: TestClient, tmp_path: Path
) -> None:
    """passed=False when diff exceeds threshold."""
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("Pillow not installed")

    red = Image.new("RGB", (50, 50), color=(255, 0, 0))
    blue = Image.new("RGB", (50, 50), color=(0, 0, 255))
    baseline = tmp_path / "b.png"
    current = tmp_path / "c.png"
    red.save(str(baseline))
    blue.save(str(current))

    res = client.post(
        "/api/silk/screenshot-diff",
        json={
            "baseline_path": str(baseline),
            "current_path": str(current),
            "threshold": 0.0,
        },
    )

    assert res.status_code == 200
    assert res.json()["passed"] is False


# ---------------------------------------------------------------------------
# 5. POST /api/silk/auto-spec
# ---------------------------------------------------------------------------


def test_auto_spec_generates_file(client: TestClient, tmp_path: Path) -> None:
    """Generated spec contains the request ID and URL."""
    res = client.post(
        "/api/silk/auto-spec",
        json={
            "request_id": "req-001",
            "method": "POST",
            "url": "https://api.example.com/users",
            "headers": {"Content-Type": "application/json"},
            "body": '{"name": "Alice"}',
            "status_code": 201,
            "workspace_dir": str(tmp_path),
        },
    )

    assert res.status_code == 200
    data = res.json()
    assert "spec_path" in data
    assert "spec_code" in data
    assert "req-001" in data["spec_code"]
    assert "https://api.example.com/users" in data["spec_code"]
    assert "201" in data["spec_code"]
    assert Path(data["spec_path"]).exists()


def test_auto_spec_no_workspace_uses_silk_dir(client: TestClient) -> None:
    """When workspace_dir is absent the spec goes into the silk home dir."""
    res = client.post(
        "/api/silk/auto-spec",
        json={
            "request_id": "req-002",
            "method": "GET",
            "url": "https://example.com/health",
        },
    )

    assert res.status_code == 200
    data = res.json()
    assert Path(data["spec_path"]).exists()
    assert "request.get(" in data["spec_code"]
    assert "toBeTruthy" in data["spec_code"]


# ---------------------------------------------------------------------------
# 6. POST /api/silk/install-browsers/sync
# ---------------------------------------------------------------------------


def test_install_browsers_sync_no_npx(client: TestClient) -> None:
    """Returns 400 when npx is absent."""
    with patch("shutil.which", return_value=None):
        res = client.post("/api/silk/install-browsers/sync")

    assert res.status_code == 400
    assert "npx" in res.json()["detail"]


def test_install_browsers_sync_failure(client: TestClient) -> None:
    """Returns 500 when playwright install exits non-zero."""
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    mock_result.stderr = "fatal error"

    with patch("shutil.which", return_value="/usr/bin/npx"), \
         patch("subprocess.run", return_value=mock_result):
        res = client.post("/api/silk/install-browsers/sync")

    assert res.status_code == 500


def test_install_browsers_sync_success(client: TestClient) -> None:
    """Returns ok=True when playwright install exits 0."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Chromium 123 downloaded to /home/user/.cache/ms-playwright/chromium-123"
    mock_result.stderr = ""

    with patch("shutil.which", return_value="/usr/bin/npx"), \
         patch("subprocess.run", return_value=mock_result):
        res = client.post("/api/silk/install-browsers/sync")

    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "chromium" in (data["browser_path"] or "").lower()


# ===========================================================================
# V2 — multi-browser, mocks, a11y
# ===========================================================================


def test_run_multi_browser_aggregates(client: TestClient, tmp_path: Path) -> None:
    """Multi-browser run aggregates passed/failed across browsers."""
    fake_report = {
        "stats": {"expected": 1, "unexpected": 0, "skipped": 0},
        "suites": [],
    }
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = json.dumps(fake_report)
    mock_result.stderr = ""

    spec = tmp_path / "multi.spec.ts"
    spec.write_text("import {test} from '@playwright/test';", encoding="utf-8")

    with patch("shutil.which", return_value="/usr/bin/npx"), \
         patch("subprocess.run", return_value=mock_result):
        res = client.post(
            "/api/silk/run",
            json={
                "spec_path": str(spec),
                "browsers": ["chromium", "firefox"],
            },
        )

    assert res.status_code == 200
    data = res.json()
    assert data["exit_code"] == 0
    assert "chromium" in data["per_browser_results"]
    assert "firefox" in data["per_browser_results"]
    # Aggregated passed = 1 (chromium) + 1 (firefox)
    assert data["passed"] == 2


def test_run_unknown_browser_returns_400(client: TestClient, tmp_path: Path) -> None:
    """Unknown browser name returns HTTP 400."""
    spec = tmp_path / "bad.spec.ts"
    spec.write_text("", encoding="utf-8")

    with patch("shutil.which", return_value="/usr/bin/npx"):
        res = client.post(
            "/api/silk/run",
            json={
                "spec_path": str(spec),
                "browsers": ["ie6"],
            },
        )

    assert res.status_code == 400
    assert "ie6" in res.json()["detail"]


def test_run_a11y_field_present_in_output(client: TestClient, tmp_path: Path) -> None:
    """Run output always contains a11y_violations key (even when empty)."""
    fake_report = {"stats": {"expected": 1, "unexpected": 0, "skipped": 0}, "suites": []}
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = json.dumps(fake_report)
    mock_result.stderr = ""

    spec = tmp_path / "a11y.spec.ts"
    spec.write_text("test('x', () => {})", encoding="utf-8")

    with patch("shutil.which", return_value="/usr/bin/npx"), \
         patch("subprocess.run", return_value=mock_result):
        res = client.post(
            "/api/silk/run",
            json={"spec_path": str(spec), "run_accessibility_audit": True},
        )

    assert res.status_code == 200
    data = res.json()
    assert "a11y_violations" in data
    assert isinstance(data["a11y_violations"], list)


def test_run_with_mocks_injects_wrapper(client: TestClient, tmp_path: Path) -> None:
    """Mock rules cause wrapper spec to be written (temp file contains route calls)."""
    captured_cmds: list[list[str]] = []

    fake_report = {"stats": {"expected": 1, "unexpected": 0, "skipped": 0}, "suites": []}
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = json.dumps(fake_report)
    mock_result.stderr = ""

    written_specs: list[str] = []

    original_write = Path.write_text

    def patched_write(self: Path, data: str, **kw: object) -> None:  # type: ignore[override]
        if "wrapped.spec.ts" in str(self):
            written_specs.append(data)
        return original_write(self, data, **kw)

    spec = tmp_path / "mock_test.spec.ts"
    spec.write_text("import { test } from '@playwright/test';", encoding="utf-8")

    with patch("shutil.which", return_value="/usr/bin/npx"), \
         patch("subprocess.run", return_value=mock_result), \
         patch.object(Path, "write_text", patched_write):
        res = client.post(
            "/api/silk/run",
            json={
                "spec_path": str(spec),
                "mocks": [
                    {"pattern": "**/api/users/*", "status": 200, "body": {"id": 1}},
                ],
            },
        )

    assert res.status_code == 200
    assert any("route.fulfill" in s for s in written_specs), \
        "Expected page.route wrapper to be injected into spec"


# ===========================================================================
# V2 — _build_mock_wrapper unit tests
# ===========================================================================


def test_build_mock_wrapper_injects_route() -> None:
    """Mock wrapper inserts page.route call for given pattern."""
    from theridion_sidecar.api.silk import _build_mock_wrapper, MockRule

    code = "import { test } from '@playwright/test';\ntest('x', () => {});"
    rules = [MockRule(pattern="**/api/**", status=404, body={"error": "nf"})]
    result = _build_mock_wrapper(code, rules)
    assert "page.route" in result
    assert "**/api/**" in result
    assert "route.fulfill" in result


def test_build_mock_wrapper_empty_rules_passthrough() -> None:
    """Empty mock list returns original code unchanged."""
    from theridion_sidecar.api.silk import _build_mock_wrapper

    code = "import { test } from '@playwright/test';"
    assert _build_mock_wrapper(code, []) == code


# ===========================================================================
# V2 — Recording (codegen subprocess)
# ===========================================================================


def test_record_start_no_npx(client: TestClient) -> None:
    """Returns 400 when npx is absent."""
    with patch("shutil.which", return_value=None):
        res = client.post("/api/silk/record/start", json={"url": "http://localhost:3000"})
    assert res.status_code == 400
    assert "npx" in res.json()["detail"]


def test_record_stop_unknown_session(client: TestClient) -> None:
    """Returns 404 for an unknown session_id."""
    res = client.post("/api/silk/record/stop", json={"session_id": "nonexistent123"})
    assert res.status_code == 404


def test_record_stop_traversal_rejected(client: TestClient) -> None:
    """Rejects session_id with path-traversal characters."""
    res = client.post("/api/silk/record/stop", json={"session_id": "../etc/passwd"})
    assert res.status_code == 400


def test_record_stream_unknown_session(client: TestClient) -> None:
    """Returns 404 when streaming an unknown session."""
    res = client.get("/api/silk/record/stream/nonexistent999")
    assert res.status_code == 404


# ===========================================================================
# V2 — Visual regression baselines
# ===========================================================================


def test_baseline_save_and_compare_identical(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Saving then comparing identical images yields passed=True, diff_ratio=0."""
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("Pillow not installed")

    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))

    img = Image.new("RGB", (80, 80), color=(0, 200, 100))
    screenshot = tmp_path / "cap.png"
    img.save(str(screenshot))

    # Save as baseline.
    res = client.post(
        "/api/silk/baseline/save",
        json={
            "screenshot_path": str(screenshot),
            "test_id": "login-flow",
            "browser": "chromium",
            "viewport": "1280x720",
        },
    )
    assert res.status_code == 200
    save_data = res.json()
    assert "baseline_path" in save_data
    assert Path(save_data["baseline_path"]).exists()

    # Compare same image → should pass.
    res2 = client.post(
        "/api/silk/baseline/compare",
        json={
            "current_path": str(screenshot),
            "test_id": "login-flow",
            "browser": "chromium",
            "viewport": "1280x720",
            "threshold": 0.01,
        },
    )
    assert res2.status_code == 200
    cmp_data = res2.json()
    assert cmp_data["passed"] is True
    assert cmp_data["diff_ratio"] == 0.0
    assert cmp_data["pixel_diff_count"] == 0


def test_baseline_compare_different_images(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Different current image vs baseline produces diff_ratio > 0, passed=False at threshold=0."""
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("Pillow not installed")

    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))

    baseline_img = Image.new("RGB", (60, 60), color=(255, 0, 0))
    current_img = Image.new("RGB", (60, 60), color=(0, 0, 255))
    baseline_file = tmp_path / "baseline_orig.png"
    current_file = tmp_path / "current.png"
    baseline_img.save(str(baseline_file))
    current_img.save(str(current_file))

    # Save red image as baseline.
    client.post(
        "/api/silk/baseline/save",
        json={
            "screenshot_path": str(baseline_file),
            "test_id": "diff-test",
            "browser": "chromium",
            "viewport": "800x600",
        },
    )

    # Compare with blue image.
    res = client.post(
        "/api/silk/baseline/compare",
        json={
            "current_path": str(current_file),
            "test_id": "diff-test",
            "browser": "chromium",
            "viewport": "800x600",
            "threshold": 0.0,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["passed"] is False
    assert data["diff_ratio"] > 0
    assert Path(data["diff_path"]).exists()


def test_baseline_save_missing_screenshot(client: TestClient) -> None:
    """Returns 404 when screenshot file does not exist."""
    res = client.post(
        "/api/silk/baseline/save",
        json={
            "screenshot_path": "/nonexistent/screenshot.png",
            "test_id": "x",
        },
    )
    assert res.status_code == 404


def test_baseline_compare_no_baseline(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Returns 404 when no baseline has been saved for given test_id."""
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("Pillow not installed")

    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    img = Image.new("RGB", (40, 40), color=(50, 50, 50))
    current_file = tmp_path / "cur.png"
    img.save(str(current_file))

    res = client.post(
        "/api/silk/baseline/compare",
        json={
            "current_path": str(current_file),
            "test_id": "never-saved",
            "browser": "chromium",
            "viewport": "1280x720",
        },
    )
    assert res.status_code == 404


# ===========================================================================
# V2 — Run history (SQLite)
# ===========================================================================


def test_run_history_initially_empty(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET /api/silk/runs returns empty list on fresh DB."""
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    res = client.get("/api/silk/runs")
    assert res.status_code == 200
    assert res.json() == []


def test_run_saved_to_history(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After a successful run, GET /api/silk/runs returns it."""
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    fake_report = {"stats": {"expected": 1, "unexpected": 0, "skipped": 0}, "suites": []}
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = json.dumps(fake_report)
    mock_result.stderr = ""

    with patch("shutil.which", return_value="/usr/bin/npx"), \
         patch("subprocess.run", return_value=mock_result):
        run_res = client.post(
            "/api/silk/run",
            json={"inline_code": "test('x', () => {});"},
        )
    assert run_res.status_code == 200
    run_id = run_res.json()["run_id"]

    # History should now have one entry.
    hist_res = client.get("/api/silk/runs")
    assert hist_res.status_code == 200
    entries = hist_res.json()
    assert len(entries) >= 1
    ids = [e["id"] for e in entries]
    assert run_id in ids


def test_run_history_single_entry(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET /api/silk/runs/{id} returns full entry with status field."""
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    fake_report = {"stats": {"expected": 0, "unexpected": 1, "skipped": 0}, "suites": []}
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = json.dumps(fake_report)
    mock_result.stderr = "FAIL"

    with patch("shutil.which", return_value="/usr/bin/npx"), \
         patch("subprocess.run", return_value=mock_result):
        run_res = client.post(
            "/api/silk/run",
            json={"inline_code": "test('fail', () => { expect(1).toBe(2); });"},
        )
    assert run_res.status_code == 200
    run_id = run_res.json()["run_id"]

    detail_res = client.get(f"/api/silk/runs/{run_id}")
    assert detail_res.status_code == 200
    d = detail_res.json()
    assert d["id"] == run_id
    assert d["status"] == "failed"
    assert "started_at" in d


def test_run_history_not_found(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET /api/silk/runs/{id} returns 404 for unknown id."""
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    res = client.get("/api/silk/runs/deadbeef00000000")
    assert res.status_code == 404


def test_run_history_limit_param(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET /api/silk/runs?limit=1 returns at most 1 entry."""
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))

    fake_report = {"stats": {"expected": 1, "unexpected": 0, "skipped": 0}, "suites": []}
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = json.dumps(fake_report)
    mock_result.stderr = ""

    with patch("shutil.which", return_value="/usr/bin/npx"), \
         patch("subprocess.run", return_value=mock_result):
        for _ in range(3):
            client.post("/api/silk/run", json={"inline_code": "test('x', ()=>{})"})

    res = client.get("/api/silk/runs?limit=1")
    assert res.status_code == 200
    assert len(res.json()) == 1


# ===========================================================================
# V2 — silk_storage module unit tests
# ===========================================================================


def test_silk_storage_save_and_retrieve(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """save_run then get_run returns the same data."""
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar import silk_storage

    run_id = "testrun001"
    silk_storage.save_run(
        run_id=run_id,
        spec_path="tests/login.spec.ts",
        exit_code=0,
        duration_ms=1234,
        browsers=["chromium"],
        trace_path="/tmp/trace.zip",
        a11y_violations_count=2,
        stderr_tail="",
    )

    result = silk_storage.get_run(run_id)
    assert result is not None
    assert result["id"] == run_id
    assert result["status"] == "passed"
    assert result["duration_ms"] == 1234
    assert result["browsers"] == ["chromium"]
    assert result["a11y_violations_count"] == 2


def test_silk_storage_list_runs_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """list_runs returns newest-first ordering."""
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar import silk_storage
    import time

    for i in range(3):
        silk_storage.save_run(
            run_id=f"run-{i}",
            spec_path=f"spec-{i}.ts",
            exit_code=0,
            duration_ms=i * 100,
            browsers=["chromium"],
        )
        time.sleep(0.01)  # Ensure distinct timestamps.

    runs = silk_storage.list_runs(limit=10)
    ids = [r["id"] for r in runs]
    # Newest = run-2
    assert ids[0] == "run-2"
    assert ids[-1] == "run-0"


def test_silk_storage_unknown_id_returns_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """get_run returns None for unknown id."""
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar import silk_storage

    assert silk_storage.get_run("no-such-run") is None


def test_silk_storage_exit_code_maps_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Exit codes 0/1/other map to passed/failed/error status."""
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar import silk_storage

    for code, expected in [(0, "passed"), (1, "failed"), (2, "error")]:
        rid = f"code-{code}"
        silk_storage.save_run(run_id=rid, spec_path="x.ts", exit_code=code, duration_ms=0, browsers=["chromium"])
        r = silk_storage.get_run(rid)
        assert r is not None
        assert r["status"] == expected, f"exit {code} should give status {expected!r}"

