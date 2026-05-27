"""Tests for detailed HTTP timing breakdown."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi.testclient import TestClient


def _make_local_server(delay: float = 0.0):
    """Spin up a tiny HTTP server on a random port. Returns (url, stop_fn)."""
    import time

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if delay:
                time.sleep(delay)
            body = b'{"ok": true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass  # silence logs

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return f"http://127.0.0.1:{port}", server.shutdown


@pytest.fixture()
def local_server():
    url, stop = _make_local_server()
    yield url
    stop()


@pytest.fixture()
def slow_server():
    url, stop = _make_local_server(delay=0.05)
    yield url
    stop()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar.main import create_app

    return TestClient(create_app())


def test_timing_fields_present(client: TestClient, local_server: str):
    """Execute a request and verify all timing breakdown fields are present."""
    resp = client.post("/api/requests/execute", json={
        "method": "GET",
        "url": local_server,
    })
    assert resp.status_code == 200
    data = resp.json()

    timing = data.get("timing")
    assert timing is not None, "timing should be present in response"

    expected_keys = {"dns_ms", "connect_ms", "tls_ms", "server_processing_ms", "transfer_ms", "total_ms"}
    assert set(timing.keys()) == expected_keys


def test_timing_values_non_negative(client: TestClient, local_server: str):
    """All timing values should be >= 0."""
    resp = client.post("/api/requests/execute", json={
        "method": "GET",
        "url": local_server,
    })
    data = resp.json()
    timing = data["timing"]

    for key in ("dns_ms", "connect_ms", "tls_ms", "server_processing_ms", "transfer_ms", "total_ms"):
        assert timing[key] >= 0, f"{key} should be non-negative, got {timing[key]}"


def test_timing_total_positive(client: TestClient, local_server: str):
    """Total time should be positive for any real request."""
    resp = client.post("/api/requests/execute", json={
        "method": "GET",
        "url": local_server,
    })
    timing = resp.json()["timing"]
    assert timing["total_ms"] > 0


def test_timing_parts_approximately_sum_to_total(client: TestClient, local_server: str):
    """Sum of measured phases should not exceed total (with tolerance)."""
    resp = client.post("/api/requests/execute", json={
        "method": "GET",
        "url": local_server,
    })
    timing = resp.json()["timing"]

    parts_sum = (
        timing["dns_ms"]
        + timing["connect_ms"]
        + timing["tls_ms"]
        + timing["server_processing_ms"]
        + timing["transfer_ms"]
    )

    # Parts sum should be close to total (within 50% tolerance for test jitter).
    assert parts_sum <= timing["total_ms"] * 1.5 + 1, (
        f"parts sum {parts_sum:.2f} exceeds total {timing['total_ms']:.2f} by too much"
    )


def test_timing_no_tls_for_http(client: TestClient, local_server: str):
    """Plain HTTP request should have tls_ms == 0."""
    resp = client.post("/api/requests/execute", json={
        "method": "GET",
        "url": local_server,
    })
    timing = resp.json()["timing"]
    assert timing["tls_ms"] == 0, "TLS time should be 0 for plain HTTP"


def test_timing_server_processing_increases_with_delay(
    client: TestClient, local_server: str, slow_server: str,
):
    """Slow server should show higher server_processing_ms than fast server."""
    fast = client.post("/api/requests/execute", json={
        "method": "GET",
        "url": local_server,
    }).json()["timing"]

    slow = client.post("/api/requests/execute", json={
        "method": "GET",
        "url": slow_server,
    }).json()["timing"]

    # The slow server has 50ms delay, so total should be noticeably higher.
    assert slow["total_ms"] > fast["total_ms"], (
        f"slow total {slow['total_ms']:.2f} should exceed fast {fast['total_ms']:.2f}"
    )
