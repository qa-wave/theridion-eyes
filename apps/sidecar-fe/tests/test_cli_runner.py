"""Tests for the CLI runner endpoints."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from theridion_sidecar.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_collection(name: str = "Test Collection", items: list | None = None):
    """Return a fake collection object for patching."""
    from theridion_sidecar.models import Collection, CollectionItem

    if items is None:
        items = [
            CollectionItem(id="r1", name="Get Users", method="GET", url="http://example.com/users"),
            CollectionItem(id="r2", name="Create User", method="POST", url="http://example.com/users"),
        ]
    return Collection(id="coll-1", name=name, items=items)


def _mock_httpx_response(status_code: int = 200, text: str = '{"ok":true}', headers: dict | None = None):
    """Create a mock httpx response."""
    from unittest.mock import MagicMock
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.headers = headers or {"content-type": "application/json"}
    return resp


# ---------------------------------------------------------------------------
# POST /api/runner/cli — basic output format
# ---------------------------------------------------------------------------

class TestCliOutput:
    def test_cli_pass_markers(self) -> None:
        """CLI output contains pass markers for successful requests."""
        with patch("theridion_sidecar.api.cli_runner.storage.get", return_value=_mock_collection()), \
             patch("theridion_sidecar.api.cli_runner.httpx.AsyncClient") as mock_client:
            mock_resp = _mock_httpx_response()
            mock_client.return_value.__aenter__.return_value.request.return_value = mock_resp

            resp = client.post(
                "/api/runner/cli",
                params={"collection_id": "coll-1"},
                json={"environment_id": None},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["passed"] == 2
        assert data["failed"] == 0
        assert data["skipped"] == 0
        # Check ANSI pass marker present
        assert "\u2713" in data["output"]
        assert "Get Users" in data["output"]
        assert "Create User" in data["output"]
        assert "2 passed" in data["output"]

    def test_cli_fail_markers(self) -> None:
        """CLI output contains fail markers for errored requests."""
        from theridion_sidecar.models import CollectionItem

        items = [
            CollectionItem(id="r1", name="Bad Request", method="GET", url="http://example.com/fail"),
        ]
        with patch("theridion_sidecar.api.cli_runner.storage.get", return_value=_mock_collection(items=items)), \
             patch("theridion_sidecar.api.cli_runner.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.request.side_effect = Exception("connection refused")

            # Use httpx.RequestError for proper handling
            import httpx
            mock_client.return_value.__aenter__.return_value.request.side_effect = httpx.ConnectError("connection refused")

            resp = client.post(
                "/api/runner/cli",
                params={"collection_id": "coll-1"},
                json={"environment_id": None},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["passed"] == 0
        assert data["failed"] == 1
        assert "\u2717" in data["output"]
        assert "1 failed" in data["output"]

    def test_cli_empty_collection(self) -> None:
        """Empty collections produce a summary with zeros."""
        with patch("theridion_sidecar.api.cli_runner.storage.get", return_value=_mock_collection(items=[])):
            resp = client.post(
                "/api/runner/cli",
                params={"collection_id": "coll-1"},
                json={"environment_id": None},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["passed"] == 0
        assert data["failed"] == 0
        assert data["skipped"] == 0
        assert data["total_ms"] == 0

    def test_cli_collection_not_found(self) -> None:
        """Returns 404 for missing collections."""
        with patch("theridion_sidecar.api.cli_runner.storage.get", return_value=None):
            resp = client.post(
                "/api/runner/cli",
                params={"collection_id": "nonexistent"},
                json={"environment_id": None},
            )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/runner/cli/trace — trace file generation
# ---------------------------------------------------------------------------

class TestCliTrace:
    def test_trace_file_generated(self, tmp_path: Path) -> None:
        """Trace endpoint creates a JSON trace file."""
        with patch("theridion_sidecar.api.cli_runner.storage.get", return_value=_mock_collection()), \
             patch("theridion_sidecar.api.cli_runner.httpx.AsyncClient") as mock_client, \
             patch("theridion_sidecar.api.cli_runner._trace_dir", return_value=tmp_path):
            mock_resp = _mock_httpx_response()
            mock_client.return_value.__aenter__.return_value.request.return_value = mock_resp

            resp = client.post(
                "/api/runner/cli/trace",
                params={"collection_id": "coll-1"},
                json={"environment_id": None},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["trace_id"]
        assert data["trace_path"]
        assert data["passed"] == 2
        assert "\u2713" in data["output"]

        # Verify the trace file exists and is valid JSON
        trace_file = Path(data["trace_path"])
        assert trace_file.exists()
        trace_data = json.loads(trace_file.read_text())
        assert trace_data["collection_name"] == "Test Collection"
        assert len(trace_data["results"]) == 2


# ---------------------------------------------------------------------------
# POST /api/runner/trace/html — HTML trace conversion
# ---------------------------------------------------------------------------

class TestTraceHtml:
    def test_html_trace_output(self, tmp_path: Path) -> None:
        """HTML trace endpoint returns a self-contained HTML document."""
        trace_id = "test-trace-123"
        trace_data = {
            "id": trace_id,
            "collection_name": "My Collection",
            "timestamp": 1700000000,
            "total_ms": 1234.5,
            "results": [
                {
                    "request_id": "r1",
                    "request_name": "Get Users",
                    "method": "GET",
                    "url": "http://example.com/users",
                    "status": 200,
                    "elapsed_ms": 123.4,
                    "error": None,
                    "assertion_results": [],
                    "assertions_passed": 0,
                    "assertions_failed": 0,
                }
            ],
        }
        trace_file = tmp_path / f"{trace_id}.json"
        trace_file.write_text(json.dumps(trace_data))

        with patch("theridion_sidecar.api.cli_runner._trace_dir", return_value=tmp_path):
            resp = client.post(
                "/api/runner/trace/html",
                params={"trace_id": trace_id},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "<!DOCTYPE html>" in data["html"]
        assert "My Collection" in data["html"]

    def test_html_trace_not_found(self, tmp_path: Path) -> None:
        """Returns 404 for missing trace files."""
        with patch("theridion_sidecar.api.cli_runner._trace_dir", return_value=tmp_path):
            resp = client.post(
                "/api/runner/trace/html",
                params={"trace_id": "nonexistent"},
            )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/runner/trace/{trace_id} — download
# ---------------------------------------------------------------------------

class TestTraceDownload:
    def test_download_trace(self, tmp_path: Path) -> None:
        """Download endpoint returns the trace file."""
        trace_id = "dl-trace-456"
        trace_data = {"id": trace_id, "results": []}
        trace_file = tmp_path / f"{trace_id}.json"
        trace_file.write_text(json.dumps(trace_data))

        with patch("theridion_sidecar.api.cli_runner._trace_dir", return_value=tmp_path):
            resp = client.get(f"/api/runner/trace/{trace_id}")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/json"
        assert json.loads(resp.content) == trace_data

    def test_download_trace_not_found(self, tmp_path: Path) -> None:
        """Returns 404 for missing trace."""
        with patch("theridion_sidecar.api.cli_runner._trace_dir", return_value=tmp_path):
            resp = client.get("/api/runner/trace/nonexistent")

        assert resp.status_code == 404
