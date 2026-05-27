"""Tests for the Agentic API Explorer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar.main import create_app

    return TestClient(create_app())


def _httpx_response(
    status_code: int = 200,
    json_body: Any = None,
    text: str = "",
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """Build a real httpx.Response for mocking."""
    hdrs = dict(headers or {})
    if json_body is not None:
        content = json.dumps(json_body).encode()
        hdrs.setdefault("content-type", "application/json")
    else:
        content = text.encode() if text else b""
    return httpx.Response(
        status_code=status_code,
        content=content,
        headers=hdrs,
        request=httpx.Request("GET", "http://test"),
    )


def _make_openapi_spec() -> dict:
    return {
        "openapi": "3.0.0",
        "info": {"title": "Test", "version": "1.0"},
        "paths": {
            "/api/users": {
                "get": {"summary": "List users"},
                "post": {
                    "summary": "Create user",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "age": {"type": "integer"},
                                    },
                                    "required": ["name"],
                                }
                            }
                        }
                    },
                },
            },
            "/api/users/{id}": {
                "get": {"summary": "Get user"},
                "put": {"summary": "Update user"},
                "delete": {"summary": "Delete user"},
            },
            "/api/health": {
                "get": {"summary": "Health check"},
            },
        },
    }


def _make_mock_client(
    get_handler=None,
    request_handler=None,
) -> MagicMock:
    """Create a mock httpx.AsyncClient context manager."""
    mock_client = AsyncMock()

    if get_handler:
        mock_client.get = AsyncMock(side_effect=get_handler)
    else:
        mock_client.get = AsyncMock(return_value=_httpx_response(404))

    if request_handler:
        mock_client.request = AsyncMock(side_effect=request_handler)
    else:
        mock_client.request = AsyncMock(return_value=_httpx_response(200))

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# ---- Test 1: Discovery from OpenAPI spec -----------------------------------

def test_openapi_discovery(client: TestClient) -> None:
    """When an OpenAPI spec is found, endpoints are extracted from it."""
    spec = _make_openapi_spec()

    def get_handler(url, **kwargs):
        if "/openapi.json" in str(url):
            return _httpx_response(200, json_body=spec)
        return _httpx_response(404)

    def req_handler(method, url, **kwargs):
        return _httpx_response(200, json_body={"ok": True})

    mock_ctx = _make_mock_client(get_handler, req_handler)

    with patch("theridion_sidecar.api.agent_explorer.httpx.AsyncClient", return_value=mock_ctx):
        res = client.post("/api/agent/explore", json={
            "base_url": "http://fakeapi.local",
            "max_requests": 10,
            "save_as_collection": False,
        })

    assert res.status_code == 200
    data = res.json()
    assert data["endpoints_discovered"] >= 5
    assert data["requests_sent"] >= 5


# ---- Test 2: Fallback to common paths -------------------------------------

def test_common_path_fallback(client: TestClient) -> None:
    """When no OpenAPI spec exists, common paths are probed."""

    def get_handler(url, **kwargs):
        u = str(url)
        if any(p in u for p in ("/openapi.json", "/swagger.json", "/api-docs",
                                 "/openapi.yaml", "/swagger/v1/swagger.json")):
            return _httpx_response(404, text="not found")
        return _httpx_response(200, json_body={"status": "ok"})

    def req_handler(method, url, **kwargs):
        return _httpx_response(200, json_body={"status": "ok"})

    mock_ctx = _make_mock_client(get_handler, req_handler)

    with patch("theridion_sidecar.api.agent_explorer.httpx.AsyncClient", return_value=mock_ctx):
        res = client.post("/api/agent/explore", json={
            "base_url": "http://fakeapi.local",
            "save_as_collection": False,
        })

    assert res.status_code == 200
    data = res.json()
    assert data["endpoints_discovered"] >= 1


# ---- Test 3: 500 error detection ------------------------------------------

def test_server_error_detection(client: TestClient) -> None:
    """500 responses generate error-level issues."""
    spec = {"openapi": "3.0.0", "paths": {"/api/broken": {"get": {}}}}

    def get_handler(url, **kwargs):
        if "/openapi.json" in str(url):
            return _httpx_response(200, json_body=spec)
        return _httpx_response(404)

    def req_handler(method, url, **kwargs):
        if "/broken" in str(url):
            return _httpx_response(500, text="Internal Server Error")
        return _httpx_response(200)

    mock_ctx = _make_mock_client(get_handler, req_handler)

    with patch("theridion_sidecar.api.agent_explorer.httpx.AsyncClient", return_value=mock_ctx):
        res = client.post("/api/agent/explore", json={
            "base_url": "http://fakeapi.local",
            "save_as_collection": False,
        })

    data = res.json()
    error_issues = [i for i in data["issues"] if i["severity"] == "error"]
    assert any("Server error" in i["message"] for i in error_issues)


# ---- Test 4: Slow endpoint detection --------------------------------------

def test_slow_endpoint_detection(client: TestClient) -> None:
    """Endpoints taking >2s are flagged as warnings."""
    import time as _time

    spec = {"openapi": "3.0.0", "paths": {"/api/slow": {"get": {}}}}

    def get_handler(url, **kwargs):
        if "/openapi.json" in str(url):
            return _httpx_response(200, json_body=spec)
        return _httpx_response(404)

    def req_handler(method, url, **kwargs):
        if "/slow" in str(url):
            _time.sleep(2.1)
        return _httpx_response(200, json_body={})

    mock_ctx = _make_mock_client(get_handler, req_handler)

    with patch("theridion_sidecar.api.agent_explorer.httpx.AsyncClient", return_value=mock_ctx):
        res = client.post("/api/agent/explore", json={
            "base_url": "http://fakeapi.local",
            "save_as_collection": False,
        })

    data = res.json()
    warnings = [i for i in data["issues"] if i["severity"] == "warning"]
    assert any("Slow endpoint" in i["message"] for i in warnings)


# ---- Test 5: No auth on mutating endpoint ----------------------------------

def test_no_auth_detection(client: TestClient) -> None:
    """Mutating endpoints returning 200 (not 401/403) are flagged."""
    spec = {"openapi": "3.0.0", "paths": {"/api/items": {"post": {}}}}

    def get_handler(url, **kwargs):
        if "/openapi.json" in str(url):
            return _httpx_response(200, json_body=spec)
        return _httpx_response(404)

    def req_handler(method, url, **kwargs):
        return _httpx_response(200, json_body={"created": True})

    mock_ctx = _make_mock_client(get_handler, req_handler)

    with patch("theridion_sidecar.api.agent_explorer.httpx.AsyncClient", return_value=mock_ctx):
        res = client.post("/api/agent/explore", json={
            "base_url": "http://fakeapi.local",
            "save_as_collection": False,
        })

    data = res.json()
    warnings = [i for i in data["issues"] if i["severity"] == "warning"]
    assert any("No auth on" in i["message"] for i in warnings)


# ---- Test 6: Collection generation ----------------------------------------

def test_collection_generation(client: TestClient) -> None:
    """When save_as_collection=True, a collection is created."""
    spec = {"openapi": "3.0.0", "paths": {
        "/api/users": {"get": {}},
        "/api/health": {"get": {}},
    }}

    def get_handler(url, **kwargs):
        if "/openapi.json" in str(url):
            return _httpx_response(200, json_body=spec)
        return _httpx_response(404)

    def req_handler(method, url, **kwargs):
        return _httpx_response(200, json_body={"ok": True})

    mock_ctx = _make_mock_client(get_handler, req_handler)

    with patch("theridion_sidecar.api.agent_explorer.httpx.AsyncClient", return_value=mock_ctx):
        res = client.post("/api/agent/explore", json={
            "base_url": "http://fakeapi.local",
            "save_as_collection": True,
            "collection_name": "My API",
        })

    data = res.json()
    assert data["collection_id"] is not None

    # Verify the collection was persisted.
    coll_res = client.get(f"/api/collections/{data['collection_id']}")
    assert coll_res.status_code == 200
    coll = coll_res.json()
    assert coll["name"] == "My API"


# ---- Test 7: No collection when save disabled ------------------------------

def test_no_collection_when_disabled(client: TestClient) -> None:
    """When save_as_collection=False, no collection is created."""
    spec = {"openapi": "3.0.0", "paths": {"/api/ping": {"get": {}}}}

    def get_handler(url, **kwargs):
        if "/openapi.json" in str(url):
            return _httpx_response(200, json_body=spec)
        return _httpx_response(404)

    def req_handler(method, url, **kwargs):
        return _httpx_response(200, json_body={})

    mock_ctx = _make_mock_client(get_handler, req_handler)

    with patch("theridion_sidecar.api.agent_explorer.httpx.AsyncClient", return_value=mock_ctx):
        res = client.post("/api/agent/explore", json={
            "base_url": "http://fakeapi.local",
            "save_as_collection": False,
        })

    data = res.json()
    assert data["collection_id"] is None


# ---- Test 8: Max requests cap ---------------------------------------------

def test_max_requests_caps_probing(client: TestClient) -> None:
    """The max_requests parameter limits how many endpoints are probed."""
    paths: dict = {}
    for i in range(30):
        paths[f"/api/item{i}"] = {"get": {}}
    spec = {"openapi": "3.0.0", "paths": paths}

    def get_handler(url, **kwargs):
        if "/openapi.json" in str(url):
            return _httpx_response(200, json_body=spec)
        return _httpx_response(404)

    def req_handler(method, url, **kwargs):
        return _httpx_response(200, json_body={})

    mock_ctx = _make_mock_client(get_handler, req_handler)

    with patch("theridion_sidecar.api.agent_explorer.httpx.AsyncClient", return_value=mock_ctx):
        res = client.post("/api/agent/explore", json={
            "base_url": "http://fakeapi.local",
            "max_requests": 5,
            "save_as_collection": False,
        })

    data = res.json()
    assert data["requests_sent"] <= 5


# ---- Test 9: Missing Content-Type detection --------------------------------

def test_missing_content_type_detection(client: TestClient) -> None:
    """Responses missing Content-Type are flagged as info issues."""
    spec = {"openapi": "3.0.0", "paths": {"/api/bare": {"get": {}}}}

    def get_handler(url, **kwargs):
        if "/openapi.json" in str(url):
            return _httpx_response(200, json_body=spec)
        return _httpx_response(404)

    def req_handler(method, url, **kwargs):
        return _httpx_response(200, text="ok", headers={})

    mock_ctx = _make_mock_client(get_handler, req_handler)

    with patch("theridion_sidecar.api.agent_explorer.httpx.AsyncClient", return_value=mock_ctx):
        res = client.post("/api/agent/explore", json={
            "base_url": "http://fakeapi.local",
            "save_as_collection": False,
        })

    data = res.json()
    info_issues = [i for i in data["issues"] if i["severity"] == "info"]
    assert any("No Content-Type" in i["message"] for i in info_issues)


# ---- Test 10: Versioning pattern detection ---------------------------------

def test_versioning_detection(client: TestClient) -> None:
    """Paths containing /v1/ or /v2/ trigger an info-level pattern detection."""
    spec = {"openapi": "3.0.0", "paths": {
        "/api/v1/items": {"get": {}},
        "/api/v2/items": {"get": {}},
    }}

    def get_handler(url, **kwargs):
        if "/openapi.json" in str(url):
            return _httpx_response(200, json_body=spec)
        return _httpx_response(404)

    def req_handler(method, url, **kwargs):
        return _httpx_response(200, json_body={})

    mock_ctx = _make_mock_client(get_handler, req_handler)

    with patch("theridion_sidecar.api.agent_explorer.httpx.AsyncClient", return_value=mock_ctx):
        res = client.post("/api/agent/explore", json={
            "base_url": "http://fakeapi.local",
            "save_as_collection": False,
        })

    data = res.json()
    info_issues = [i for i in data["issues"] if i["severity"] == "info"]
    assert any("versioning" in i["message"].lower() for i in info_issues)
