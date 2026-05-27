"""Tests for the visual dependency graph endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _create_collection_with_chaining(client: TestClient) -> str:
    """Create a collection with 3 chained requests: login -> get user -> update user."""
    resp = client.post("/api/collections", json={"name": "Chained"})
    coll_id = resp.json()["id"]

    # Request 1: Login (produces auth_token)
    client.post(f"/api/collections/{coll_id}/requests", json={
        "name": "Login",
        "method": "POST",
        "url": "https://api.example.com/login",
        "headers": {"Content-Type": "application/json"},
        "body": '{"username": "admin", "password": "secret"}',
        "captures": [{"name": "auth_token", "source": "body", "path": "token"}],
    })

    # Request 2: Get User (consumes auth_token, produces user_id)
    client.post(f"/api/collections/{coll_id}/requests", json={
        "name": "Get User",
        "method": "GET",
        "url": "https://api.example.com/users/me",
        "headers": {"Authorization": "Bearer {{auth_token}}"},
        "captures": [{"name": "user_id", "source": "body", "path": "id"}],
    })

    # Request 3: Update User (consumes auth_token + user_id)
    client.post(f"/api/collections/{coll_id}/requests", json={
        "name": "Update User",
        "method": "PUT",
        "url": "https://api.example.com/users/{{user_id}}",
        "headers": {"Authorization": "Bearer {{auth_token}}"},
        "body": '{"name": "Updated"}',
    })

    return coll_id


def _create_collection_no_deps(client: TestClient) -> str:
    """Create a collection with independent requests (no chaining)."""
    resp = client.post("/api/collections", json={"name": "Independent"})
    coll_id = resp.json()["id"]

    client.post(f"/api/collections/{coll_id}/requests", json={
        "name": "Health Check",
        "method": "GET",
        "url": "https://api.example.com/health",
    })
    client.post(f"/api/collections/{coll_id}/requests", json={
        "name": "List Items",
        "method": "GET",
        "url": "https://api.example.com/items",
    })

    return coll_id


def _create_collection_circular(client: TestClient) -> str:
    """Create a collection with circular dependencies."""
    resp = client.post("/api/collections", json={"name": "Circular"})
    coll_id = resp.json()["id"]

    # A produces x, consumes y
    client.post(f"/api/collections/{coll_id}/requests", json={
        "name": "Request A",
        "method": "GET",
        "url": "https://api.example.com/a?token={{var_y}}",
        "captures": [{"name": "var_x", "source": "body", "path": "x"}],
    })
    # B produces y, consumes x
    client.post(f"/api/collections/{coll_id}/requests", json={
        "name": "Request B",
        "method": "GET",
        "url": "https://api.example.com/b?token={{var_x}}",
        "captures": [{"name": "var_y", "source": "body", "path": "y"}],
    })

    return coll_id


def _create_collection_with_folders(client: TestClient) -> str:
    """Create a collection with requests inside folders for grouping test."""
    resp = client.post("/api/collections", json={"name": "Grouped"})
    coll_id = resp.json()["id"]

    # Create folder
    resp = client.post(f"/api/collections/{coll_id}/folders", json={"name": "Auth"})
    folder_item = [i for i in resp.json()["items"] if i["is_folder"]][0]
    folder_id = folder_item["id"]

    # Add request inside the folder
    client.post(f"/api/collections/{coll_id}/requests", json={
        "name": "Login",
        "method": "POST",
        "url": "https://api.example.com/login",
        "parent_folder_id": folder_id,
        "captures": [{"name": "token", "source": "body", "path": "token"}],
    })

    # Add request at root level that consumes the token
    client.post(f"/api/collections/{coll_id}/requests", json={
        "name": "Get Data",
        "method": "GET",
        "url": "https://api.example.com/data",
        "headers": {"Authorization": "Bearer {{token}}"},
    })

    return coll_id


def test_chained_collection(client: TestClient) -> None:
    """3 chained requests produce correct nodes, edges, and execution order."""
    coll_id = _create_collection_with_chaining(client)

    resp = client.post("/api/graph/collection", json={"collection_id": coll_id})
    assert resp.status_code == 200
    data = resp.json()

    # 3 nodes
    assert len(data["nodes"]) == 3
    names = [n["name"] for n in data["nodes"]]
    assert "Login" in names
    assert "Get User" in names
    assert "Update User" in names

    # Login produces auth_token
    login_node = next(n for n in data["nodes"] if n["name"] == "Login")
    assert "auth_token" in login_node["produces"]
    assert login_node["consumes"] == []

    # Get User consumes auth_token, produces user_id
    get_user = next(n for n in data["nodes"] if n["name"] == "Get User")
    assert "auth_token" in get_user["consumes"]
    assert "user_id" in get_user["produces"]

    # Update User consumes both
    update_user = next(n for n in data["nodes"] if n["name"] == "Update User")
    assert "auth_token" in update_user["consumes"]
    assert "user_id" in update_user["consumes"]

    # Edges: Login -> Get User (auth_token), Login -> Update User (auth_token),
    # Get User -> Update User (user_id)
    assert len(data["edges"]) == 3
    edge_tuples = [(e["from_id"], e["to_id"], e["variable"]) for e in data["edges"]]
    assert (login_node["id"], get_user["id"], "auth_token") in edge_tuples
    assert (login_node["id"], update_user["id"], "auth_token") in edge_tuples
    assert (get_user["id"], update_user["id"], "user_id") in edge_tuples

    # Execution order: Login first, then Get User, then Update User
    order = data["execution_order"]
    assert order.index(login_node["id"]) < order.index(get_user["id"])
    assert order.index(get_user["id"]) < order.index(update_user["id"])

    assert data["has_cycle"] is False


def test_no_dependencies(client: TestClient) -> None:
    """Collection with no variable chaining returns no edges."""
    coll_id = _create_collection_no_deps(client)

    resp = client.post("/api/graph/collection", json={"collection_id": coll_id})
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["nodes"]) == 2
    assert len(data["edges"]) == 0
    assert data["has_cycle"] is False
    # All nodes should still appear in execution_order
    assert len(data["execution_order"]) == 2


def test_circular_dependency(client: TestClient) -> None:
    """Circular dependencies are detected and reported."""
    coll_id = _create_collection_circular(client)

    resp = client.post("/api/graph/collection", json={"collection_id": coll_id})
    assert resp.status_code == 200
    data = resp.json()

    assert data["has_cycle"] is True
    assert len(data["cycle_members"]) == 2
    # Both nodes in cycle
    node_ids = [n["id"] for n in data["nodes"]]
    for cm in data["cycle_members"]:
        assert cm in node_ids


def test_folder_grouping(client: TestClient) -> None:
    """Requests inside folders produce correct groups."""
    coll_id = _create_collection_with_folders(client)

    resp = client.post("/api/graph/collection", json={"collection_id": coll_id})
    assert resp.status_code == 200
    data = resp.json()

    # Should have a group for "Auth" folder
    assert len(data["groups"]) >= 1
    auth_group = next((g for g in data["groups"] if g["name"] == "Auth"), None)
    assert auth_group is not None
    assert len(auth_group["node_ids"]) == 1

    # Edge from login to get data
    assert len(data["edges"]) == 1
    assert data["edges"][0]["variable"] == "token"


def test_nonexistent_collection(client: TestClient) -> None:
    """Nonexistent collection returns empty graph."""
    resp = client.post("/api/graph/collection", json={"collection_id": "nonexistent"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["nodes"] == []
    assert data["edges"] == []
    assert data["execution_order"] == []


def test_builtin_vars_excluded(client: TestClient) -> None:
    """Built-in template vars like {{$timestamp}} are not treated as dependencies."""
    resp = client.post("/api/collections", json={"name": "Builtins"})
    coll_id = resp.json()["id"]

    client.post(f"/api/collections/{coll_id}/requests", json={
        "name": "With Builtins",
        "method": "POST",
        "url": "https://api.example.com/data",
        "headers": {"X-Request-Id": "{{$uuid}}", "X-Time": "{{$timestamp}}"},
        "body": '{"date": "{{$isoDate}}"}',
    })

    resp = client.post("/api/graph/collection", json={"collection_id": coll_id})
    assert resp.status_code == 200
    data = resp.json()

    node = data["nodes"][0]
    assert node["consumes"] == []
    assert data["edges"] == []
