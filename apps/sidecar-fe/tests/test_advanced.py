"""Tests for advanced API lifecycle endpoints."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar.main import create_app

    return TestClient(create_app())


OPENAPI = {
    "openapi": "3.1.0",
    "info": {"title": "Pets", "version": "1.0"},
    "servers": [{"url": "https://api.example.com"}],
    "paths": {
        "/pets/{id}": {
            "get": {
                "summary": "Get pet",
                "operationId": "getPet",
                "parameters": [
                    {"name": "id", "in": "path", "schema": {"type": "string"}}
                ],
                "responses": {
                    "200": {
                        "description": "OK",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["id", "name"],
                                    "properties": {
                                        "id": {"type": "string"},
                                        "name": {"type": "string"},
                                    },
                                }
                            }
                        },
                    }
                },
            }
        },
        "/pets": {
            "post": {
                "summary": "Create pet",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "example": {"name": "Mina"}
                        }
                    }
                },
                "responses": {"201": {"description": "Created"}},
            }
        },
    },
}


def test_openapi_import_export_and_contract_validation(client: TestClient) -> None:
    imported = client.post(
        "/api/advanced/openapi/import",
        json={"content": json.dumps(OPENAPI)},
    )
    assert imported.status_code == 200
    payload = imported.json()
    assert payload["collection_name"] == "Pets"
    assert payload["request_count"] == 2

    exported = client.get(f"/api/advanced/openapi/export/{payload['collection_id']}")
    assert exported.status_code == 200
    assert "/pets/{id}" in exported.json()["openapi"]["paths"]

    valid = client.post(
        "/api/advanced/contracts/validate",
        json={
            "openapi_content": json.dumps(OPENAPI),
            "method": "GET",
            "path": "/pets/123",
            "status": 200,
            "body": json.dumps({"id": "123", "name": "Pip"}),
        },
    ).json()
    assert valid["passed"] is True

    invalid = client.post(
        "/api/advanced/contracts/validate",
        json={
            "openapi_content": json.dumps(OPENAPI),
            "method": "GET",
            "path": "/pets/123",
            "status": 200,
            "body": json.dumps({"id": "123"}),
        },
    ).json()
    assert invalid["passed"] is False
    assert "name" in invalid["violations"][0]["message"]


def test_examples_variable_inspector_and_dependency_graph(client: TestClient) -> None:
    coll = client.post("/api/collections", json={"name": "Flow"}).json()
    cid = coll["id"]
    first = client.post(
        f"/api/collections/{cid}/requests",
        json={
            "name": "Login",
            "method": "POST",
            "url": "https://example.com/login",
            "captures": [{"name": "token", "source": "body", "path": "token"}],
        },
    ).json()["items"][0]
    second = client.post(
        f"/api/collections/{cid}/requests",
        json={
            "name": "Profile",
            "method": "GET",
            "url": "https://example.com/me?token={{token}}&region={{region}}",
        },
    ).json()["items"][1]

    examples = client.patch(
        f"/api/advanced/collections/{cid}/requests/{second['id']}/examples",
        json={
            "examples": [
                {
                    "name": "Happy path",
                    "method": "GET",
                    "url": "https://example.com/me?token={{token}}",
                    "notes": "uses token from login",
                }
            ]
        },
    ).json()
    assert examples["items"][1]["examples"][0]["name"] == "Happy path"

    client.patch(
        f"/api/collections/{cid}/variables",
        json={"variables": [{"name": "region", "value": "eu", "enabled": True}]},
    )
    inspected = client.post(
        "/api/advanced/variables/inspect",
        json={
            "text": "{{region}} {{runtimeOnly}}",
            "collection_id": cid,
            "runtime": {"runtimeOnly": "R"},
        },
    ).json()
    assert inspected["resolved_text"] == "eu R"
    assert [v["source"] for v in inspected["variables"]] == ["collection", "runtime"]

    graph = client.get(f"/api/advanced/collections/{cid}/dependency-graph").json()
    assert graph["edges"] == [{"from_id": first["id"], "to_id": second["id"], "variable": "token"}]


def test_vault_snapshot_diff_and_har_roundtrip(client: TestClient) -> None:
    written = client.put(
        "/api/advanced/secrets/api_token",
        json={"passphrase": "correct horse", "value": "secret-value"},
    )
    assert written.status_code == 200
    listed = client.get("/api/advanced/secrets").json()
    assert listed["entries"][0]["name"] == "api_token"
    revealed = client.post(
        "/api/advanced/secrets/api_token/reveal",
        json={"passphrase": "correct horse"},
    ).json()
    assert revealed["value"] == "secret-value"

    client.put(
        "/api/advanced/snapshots/user",
        json={"value": json.dumps({"id": 1, "items": [2, 1], "ts": "old"})},
    )
    snap = client.post(
        "/api/advanced/snapshots/user/compare",
        json={
            "value": json.dumps({"id": 1, "items": [1, 2], "ts": "new"}),
            "ignore_paths": ["ts"],
        },
    ).json()
    assert snap["exists"] is True
    assert snap["diff"]["equal"] is True

    har = {
        "log": {
            "entries": [
                {
                    "request": {
                        "method": "POST",
                        "url": "https://api.example.com/pets",
                        "headers": [{"name": "content-type", "value": "application/json"}],
                        "postData": {"text": json.dumps({"name": "Pip"})},
                    }
                }
            ]
        }
    }
    imported = client.post(
        "/api/advanced/har/import",
        json={"content": json.dumps(har), "collection_name": "Captured"},
    ).json()
    assert imported["request_count"] == 1
    exported = client.get(f"/api/advanced/har/export/{imported['collection_id']}").json()
    assert exported["log"]["entries"][0]["request"]["method"] == "POST"


def test_flow_runner_and_collection_backed_mock(client: TestClient) -> None:
    mock = client.post(
        "/api/mock/start",
        json={
            "routes": [
                {"path": "/login", "method": "POST", "body": json.dumps({"token": "abc"})},
                {"path": "/me", "method": "GET", "body": json.dumps({"ok": True})},
                {"path": "/cleanup", "method": "DELETE", "body": "{}"},
            ]
        },
    ).json()
    port = mock["port"]
    try:
        flow = client.post(
            "/api/advanced/flows/run",
            json={
                "dataset": [{"user": "a"}, {"user": "b"}],
                "steps": [
                    {
                        "id": "login",
                        "name": "Login",
                        "method": "POST",
                        "url": f"http://127.0.0.1:{port}/login",
                        "captures": [{"name": "token", "source": "body", "path": "token"}],
                    },
                    {
                        "id": "me",
                        "name": "Me",
                        "method": "GET",
                        "url": f"http://127.0.0.1:{port}/me?token={{{{token}}}}",
                    },
                ],
                "cleanup_steps": [
                    {
                        "id": "cleanup",
                        "name": "Cleanup",
                        "method": "DELETE",
                        "url": f"http://127.0.0.1:{port}/cleanup",
                    }
                ],
            },
        ).json()
        assert len(flow["datasets"]) == 2
        assert flow["datasets"][0]["runtime"]["token"] == "abc"
        assert len(flow["trace"]) == 6
    finally:
        client.post("/api/mock/stop", json={"port": port})

    coll = client.post("/api/collections", json={"name": "Mockable"}).json()
    cid = coll["id"]
    client.post(
        f"/api/collections/{cid}/requests",
        json={
            "name": "Ping",
            "method": "GET",
            "url": "https://api.example.com/ping",
            "body": "{\"pong\":true}",
        },
    )
    started = client.post(f"/api/advanced/mock/start-from-collection/{cid}").json()
    try:
        res = httpx.get(f"http://127.0.0.1:{started['port']}/ping")
        assert res.json() == {"pong": True}
    finally:
        client.post("/api/mock/stop", json={"port": started["port"]})


def test_contract_drift_reports_collection_and_observation_gaps(
    client: TestClient,
) -> None:
    coll = client.post("/api/collections", json={"name": "Drift"}).json()
    cid = coll["id"]
    client.post(
        f"/api/collections/{cid}/requests",
        json={
            "name": "Undocumented",
            "method": "GET",
            "url": "https://api.example.com/internal",
        },
    )

    drift = client.post(
        "/api/advanced/contracts/drift",
        json={
            "openapi_content": json.dumps(OPENAPI),
            "collection_id": cid,
            "observed": [
                {
                    "method": "GET",
                    "path": "/pets/123",
                    "status": 200,
                    "body": json.dumps({"id": "123"}),
                },
                {
                    "method": "POST",
                    "path": "/pets",
                    "status": 201,
                    "body": json.dumps({"name": "Pip"}),
                },
            ],
        },
    ).json()

    assert drift["missing_in_collection"] == ["GET /pets/{id}", "POST /pets"]
    assert drift["undocumented_requests"] == ["GET /internal"]
    assert drift["passed_observations"] == 1
    assert drift["failing_observations"][0]["passed"] is False


def test_proxy_recorder_captures_har_entries(client: TestClient) -> None:
    mock = client.post(
        "/api/mock/start",
        json={
            "routes": [
                {
                    "path": "/target",
                    "method": "GET",
                    "body": json.dumps({"proxied": True}),
                }
            ]
        },
    ).json()
    mock_port = mock["port"]
    proxy = client.post(
        "/api/advanced/proxy/start",
        json={"target_base_url": f"http://127.0.0.1:{mock_port}"},
    ).json()

    try:
        proxied = httpx.get(f"http://127.0.0.1:{proxy['port']}/target?via=proxy")
        assert proxied.json() == {"proxied": True}

        har = client.get(f"/api/advanced/proxy/{proxy['session_id']}/har").json()
        entry = har["log"]["entries"][0]
        assert entry["request"]["method"] == "GET"
        assert entry["request"]["url"].endswith("/target?via=proxy")
        assert entry["response"]["status"] == 200
    finally:
        client.post(f"/api/advanced/proxy/{proxy['session_id']}/stop")
        client.post("/api/mock/stop", json={"port": mock_port})


def test_tls_inspector_reports_certificate_fields(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from theridion_sidecar.api.advanced import security_ops

    class FakeSocket:
        def __enter__(self) -> FakeSocket:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    class FakeTls:
        def __enter__(self) -> FakeTls:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def getpeercert(self) -> dict[str, object]:
            return {
                "subject": ((("commonName", "api.example.com"),),),
                "issuer": ((("organizationName", "Example CA"),),),
                "notBefore": "Jan  1 00:00:00 2026 GMT",
                "notAfter": "Jan  1 00:00:00 2027 GMT",
                "subjectAltName": (("DNS", "api.example.com"),),
            }

        def cipher(self) -> tuple[str, str, int]:
            return ("TLS_AES_256_GCM_SHA384", "TLSv1.3", 256)

        def version(self) -> str:
            return "TLSv1.3"

    class FakeContext:
        def wrap_socket(self, _sock: object, server_hostname: str) -> FakeTls:
            assert server_hostname == "api.example.com"
            return FakeTls()

    monkeypatch.setattr(
        security_ops.socket,
        "create_connection",
        lambda *_args, **_kwargs: FakeSocket(),
    )
    monkeypatch.setattr(security_ops.ssl, "create_default_context", lambda: FakeContext())

    inspected = client.post(
        "/api/advanced/tls/inspect",
        json={"url": "https://api.example.com"},
    ).json()

    assert inspected["host"] == "api.example.com"
    assert inspected["subject"]["commonName"] == "api.example.com"
    assert inspected["issuer"]["organizationName"] == "Example CA"
    assert inspected["san"] == ["api.example.com"]
    assert inspected["tls_version"] == "TLSv1.3"


def test_git_review_summarizes_collection_json_changes(
    client: TestClient, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    collection_path = repo / "collection.json"
    base_collection = {
        "id": "collection",
        "name": "Original",
        "items": [
            {
                "id": "req-1",
                "name": "List pets",
                "method": "GET",
                "url": "https://api.example.com/pets",
            }
        ],
    }
    collection_path.write_text(json.dumps(base_collection), encoding="utf-8")

    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Theridion Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "add", "collection.json"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial collection"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    changed_collection = {
        **base_collection,
        "name": "Renamed",
        "items": [
            {
                **base_collection["items"][0],
                "url": "https://api.example.com/v2/pets",
                "assertions": [{"type": "status", "expected": "200"}],
            },
            {
                "id": "req-2",
                "name": "Create pet",
                "method": "POST",
                "url": "https://api.example.com/pets",
            },
        ],
    }
    collection_path.write_text(json.dumps(changed_collection), encoding="utf-8")

    reviewed = client.post(
        "/api/advanced/git/review",
        json={"repo_path": str(repo)},
    ).json()

    assert reviewed["changes"][0]["file"] == "collection.json"
    assert reviewed["changes"][0]["summary"] == "4 collection-level changes"
    assert reviewed["changes"][0]["details"] == [
        "Renamed collection: Original -> Renamed",
        "Added request: Create pet",
        "Changed url on List pets",
        "Changed assertions on List pets",
    ]
