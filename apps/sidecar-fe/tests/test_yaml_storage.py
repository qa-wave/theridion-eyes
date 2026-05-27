"""Tests for git-native YAML project storage and OAuth2 PKCE."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient


# ---- YAML storage unit tests (via API) ------------------------------------


def test_create_project(client: TestClient) -> None:
    r = client.post("/api/projects", json={"name": "My API"})
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "My API"
    assert body["created_at"] is not None
    assert body["collections"] == []
    assert body["environments"] == []


def test_create_project_duplicate(client: TestClient) -> None:
    client.post("/api/projects", json={"name": "Dup"})
    r = client.post("/api/projects", json={"name": "Dup"})
    assert r.status_code == 409


def test_list_projects(client: TestClient) -> None:
    client.post("/api/projects", json={"name": "Alpha"})
    client.post("/api/projects", json={"name": "Beta"})
    r = client.get("/api/projects")
    assert r.status_code == 200
    names = [p["name"] for p in r.json()]
    assert "Alpha" in names
    assert "Beta" in names


def test_get_project(client: TestClient) -> None:
    client.post("/api/projects", json={"name": "Detail"})
    r = client.get("/api/projects/Detail")
    assert r.status_code == 200
    assert r.json()["name"] == "Detail"


def test_get_project_not_found(client: TestClient) -> None:
    r = client.get("/api/projects/nonexistent")
    assert r.status_code == 404


def test_delete_project(client: TestClient) -> None:
    client.post("/api/projects", json={"name": "ToDelete"})
    r = client.delete("/api/projects/ToDelete")
    assert r.status_code == 204
    r = client.get("/api/projects/ToDelete")
    assert r.status_code == 404


def test_save_and_load_request_roundtrip(
    client: TestClient, tmp_path: Path
) -> None:
    """Save a request YAML file directly, then verify it loads back."""
    import os
    os.environ["THERIDION_HOME"] = str(tmp_path)

    from theridion_sidecar import yaml_storage

    yaml_storage.create_project("RoundTrip")
    req_data = {
        "name": "Create User",
        "method": "POST",
        "url": "{{base_url}}/users",
        "headers": {"Content-Type": "application/json"},
        "body": '{"name": "Alice"}',
    }
    yaml_storage.save_request("RoundTrip", "Users", "create-user", req_data)

    proj = yaml_storage.get_project("RoundTrip")
    assert proj is not None
    assert len(proj.collections) == 1
    assert proj.collections[0].name == "Users"
    assert len(proj.collections[0].requests) == 1
    loaded = proj.collections[0].requests[0]
    assert loaded["name"] == "Create User"
    assert loaded["method"] == "POST"
    assert loaded["url"] == "{{base_url}}/users"


def test_delete_request(client: TestClient, tmp_path: Path) -> None:
    import os
    os.environ["THERIDION_HOME"] = str(tmp_path)

    from theridion_sidecar import yaml_storage

    yaml_storage.create_project("DelReq")
    yaml_storage.save_request("DelReq", "Col1", "req1", {"name": "R1", "method": "GET", "url": "/a"})
    yaml_storage.save_request("DelReq", "Col1", "req2", {"name": "R2", "method": "GET", "url": "/b"})

    yaml_storage.delete_request("DelReq", "Col1", "req1")
    proj = yaml_storage.get_project("DelReq")
    assert proj is not None
    assert len(proj.collections[0].requests) == 1
    assert proj.collections[0].requests[0]["name"] == "R2"


def test_folder_hierarchy_preserved(
    client: TestClient, tmp_path: Path
) -> None:
    """Requests saved in subfolders should appear in nested structure."""
    import os
    os.environ["THERIDION_HOME"] = str(tmp_path)

    from theridion_sidecar import yaml_storage

    yaml_storage.create_project("Hierarchy")
    yaml_storage.save_request(
        "Hierarchy", "API", "auth/login",
        {"name": "Login", "method": "POST", "url": "/login"},
    )
    yaml_storage.save_request(
        "Hierarchy", "API", "auth/logout",
        {"name": "Logout", "method": "POST", "url": "/logout"},
    )
    yaml_storage.save_request(
        "Hierarchy", "API", "health",
        {"name": "Health", "method": "GET", "url": "/health"},
    )

    proj = yaml_storage.get_project("Hierarchy")
    assert proj is not None
    col = proj.collections[0]
    # Should have folder "auth" + request "health"
    names = [r["name"] for r in col.requests]
    assert "auth" in names  # folder
    assert "Health" in names  # top-level request

    auth_folder = next(r for r in col.requests if r.get("is_folder"))
    assert len(auth_folder["items"]) == 2


def test_export_json_collection_to_yaml(
    client: TestClient, tmp_path: Path
) -> None:
    """Export an existing JSON collection into a YAML project."""
    # Create a JSON collection first
    r = client.post("/api/collections", json={"name": "ExportMe"})
    assert r.status_code in (200, 201)
    coll_id = r.json()["id"]

    # Add a request to it
    client.post(
        f"/api/collections/{coll_id}/requests",
        json={
            "name": "Get Users",
            "method": "GET",
            "url": "https://example.com/users",
        },
    )

    # Export to YAML project
    r = client.post(f"/api/projects/_/export-from-collection/{coll_id}")
    assert r.status_code == 200
    project_name = r.json()["project_name"]
    assert project_name == "ExportMe"

    # Verify the project was created
    r = client.get(f"/api/projects/{project_name}")
    assert r.status_code == 200
    proj = r.json()
    assert len(proj["collections"]) == 1
    assert len(proj["collections"][0]["requests"]) == 1
    assert proj["collections"][0]["requests"][0]["name"] == "Get Users"


# ---- OAuth2 PKCE unit tests -----------------------------------------------


def test_pkce_generate() -> None:
    from theridion_sidecar.api.oauth2 import generate_pkce

    verifier, challenge = generate_pkce()
    assert len(verifier) > 40
    assert len(challenge) > 20
    # Verify the challenge matches the verifier
    import base64, hashlib
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    assert challenge == expected


def test_authorize_url_with_pkce(client: TestClient) -> None:
    r = client.post("/api/auth/oauth2/authorize-url", json={
        "auth_url": "https://auth.example.com/authorize",
        "client_id": "test-client",
        "scope": "openid profile",
        "use_pkce": True,
    })
    assert r.status_code == 200
    body = r.json()
    assert "code_challenge=" in body["url"]
    assert "code_challenge_method=S256" in body["url"]
    assert body["code_verifier"] is not None
    assert body["code_challenge"] is not None
    assert body["state"] is not None


def test_authorize_url_without_pkce(client: TestClient) -> None:
    r = client.post("/api/auth/oauth2/authorize-url", json={
        "auth_url": "https://auth.example.com/authorize",
        "client_id": "test-client",
        "use_pkce": False,
    })
    assert r.status_code == 200
    body = r.json()
    assert "code_challenge" not in body["url"]
    assert body["code_verifier"] is None
    assert body["code_challenge"] is None


def test_callback_server_result_not_running(client: TestClient) -> None:
    r = client.get("/api/auth/oauth2/callback-server/result")
    assert r.status_code == 200
    assert r.json()["status"] == "not_running"
