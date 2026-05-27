"""Integration tests for collections CRUD against the live FastAPI app.

Each test gets a temporary THERIDION_HOME so they're hermetic — there's
no shared state between tests and no contamination of the user's real
home directory.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    # Import inside the fixture so the env var is already set when the
    # storage module is first imported.
    from theridion_sidecar.main import create_app

    return TestClient(create_app())


def test_list_is_empty_initially(client: TestClient) -> None:
    res = client.get("/api/collections")
    assert res.status_code == 200
    assert res.json() == []


def test_create_then_list_roundtrip(client: TestClient) -> None:
    res = client.post("/api/collections", json={"name": "Smoke"})
    assert res.status_code == 201
    coll = res.json()
    assert coll["name"] == "Smoke"
    assert coll["items"] == []

    listed = client.get("/api/collections").json()
    assert len(listed) == 1
    assert listed[0]["id"] == coll["id"]
    assert listed[0]["request_count"] == 0


def test_save_request_appends_then_replaces(client: TestClient) -> None:
    coll = client.post("/api/collections", json={"name": "Repo"}).json()
    cid = coll["id"]

    r1 = client.post(
        f"/api/collections/{cid}/requests",
        json={"name": "Get", "method": "GET", "url": "https://example.com"},
    ).json()
    assert len(r1["items"]) == 1
    rid = r1["items"][0]["id"]

    # Same id → replace, not append.
    r2 = client.post(
        f"/api/collections/{cid}/requests",
        json={"id": rid, "name": "Get (renamed)", "method": "GET", "url": "https://example.com/v2"},
    ).json()
    assert len(r2["items"]) == 1
    assert r2["items"][0]["name"] == "Get (renamed)"
    assert r2["items"][0]["url"] == "https://example.com/v2"

    # Different id → append.
    r3 = client.post(
        f"/api/collections/{cid}/requests",
        json={"name": "Post", "method": "POST", "url": "https://example.com"},
    ).json()
    assert len(r3["items"]) == 2


def test_delete_request_removes_only_that_one(client: TestClient) -> None:
    coll = client.post("/api/collections", json={"name": "C"}).json()
    cid = coll["id"]
    a = client.post(
        f"/api/collections/{cid}/requests",
        json={"name": "A", "url": "https://a.example"},
    ).json()
    b = client.post(
        f"/api/collections/{cid}/requests",
        json={"name": "B", "url": "https://b.example"},
    ).json()
    assert len(b["items"]) == 2

    rid_a = a["items"][0]["id"]
    after_del = client.delete(f"/api/collections/{cid}/requests/{rid_a}").json()
    assert [r["name"] for r in after_del["items"]] == ["B"]


def test_delete_collection_removes_file(client: TestClient, tmp_path: Path) -> None:
    coll = client.post("/api/collections", json={"name": "Doomed"}).json()
    cid = coll["id"]
    file_path = tmp_path / "collections" / f"{cid}.json"
    assert file_path.exists()

    res = client.delete(f"/api/collections/{cid}")
    assert res.status_code == 204
    assert not file_path.exists()


def test_get_unknown_collection_404s(client: TestClient) -> None:
    res = client.get("/api/collections/00000000-0000-0000-0000-000000000000")
    assert res.status_code == 404


def test_atomic_write_does_not_leave_temp_files(client: TestClient, tmp_path: Path) -> None:
    coll = client.post("/api/collections", json={"name": "Atomic"}).json()
    cid = coll["id"]
    client.post(
        f"/api/collections/{cid}/requests",
        json={"name": "X", "url": "https://example.com"},
    )
    leftover = list((tmp_path / "collections").glob("*.tmp"))
    assert leftover == [], f"unexpected temp files: {leftover}"


def test_storage_root_respects_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path / "x"))
    from theridion_sidecar import storage

    # Re-resolve since tests use monkeypatch, not module-level constants.
    assert storage.home_dir() == (tmp_path / "x").resolve()
    assert os.path.isdir(storage.collections_dir())


# ---- folders ------------------------------------------------------------

def test_create_folder_at_root(client: TestClient) -> None:
    coll = client.post("/api/collections", json={"name": "C"}).json()
    cid = coll["id"]
    res = client.post(
        f"/api/collections/{cid}/folders",
        json={"name": "API v1"},
    )
    assert res.status_code == 201
    body = res.json()
    assert len(body["items"]) == 1
    folder = body["items"][0]
    assert folder["is_folder"] is True
    assert folder["name"] == "API v1"
    assert folder["items"] == []


def test_create_nested_folder(client: TestClient) -> None:
    coll = client.post("/api/collections", json={"name": "C"}).json()
    cid = coll["id"]
    parent = client.post(
        f"/api/collections/{cid}/folders", json={"name": "API"}
    ).json()
    parent_id = parent["items"][0]["id"]
    nested = client.post(
        f"/api/collections/{cid}/folders",
        json={"name": "v2", "parent_folder_id": parent_id},
    ).json()
    # The nested folder should live inside the parent, not at root.
    assert len(nested["items"]) == 1
    parent_after = nested["items"][0]
    assert parent_after["id"] == parent_id
    assert len(parent_after["items"]) == 1
    assert parent_after["items"][0]["name"] == "v2"


def test_save_request_into_folder(client: TestClient) -> None:
    coll = client.post("/api/collections", json={"name": "C"}).json()
    cid = coll["id"]
    folder = client.post(
        f"/api/collections/{cid}/folders", json={"name": "Repos"}
    ).json()
    fid = folder["items"][0]["id"]
    saved = client.post(
        f"/api/collections/{cid}/requests",
        json={
            "name": "List",
            "method": "GET",
            "url": "https://example.com/repos",
            "parent_folder_id": fid,
        },
    ).json()
    folder_after = saved["items"][0]
    assert folder_after["id"] == fid
    assert len(folder_after["items"]) == 1
    assert folder_after["items"][0]["name"] == "List"


def test_save_to_unknown_folder_404s(client: TestClient) -> None:
    coll = client.post("/api/collections", json={"name": "C"}).json()
    res = client.post(
        f"/api/collections/{coll['id']}/requests",
        json={
            "name": "X",
            "url": "https://example.com",
            "parent_folder_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert res.status_code == 404


def test_replace_request_inside_folder_keeps_position(client: TestClient) -> None:
    coll = client.post("/api/collections", json={"name": "C"}).json()
    cid = coll["id"]
    f = client.post(
        f"/api/collections/{cid}/folders", json={"name": "F"}
    ).json()["items"][0]
    a = client.post(
        f"/api/collections/{cid}/requests",
        json={"name": "A", "url": "https://a.example", "parent_folder_id": f["id"]},
    ).json()
    rid = a["items"][0]["items"][0]["id"]

    after = client.post(
        f"/api/collections/{cid}/requests",
        json={"id": rid, "name": "A2", "url": "https://a2.example"},
    ).json()
    # Should stay inside the folder, not jump to root.
    assert len(after["items"]) == 1
    assert after["items"][0]["is_folder"] is True
    assert after["items"][0]["items"][0]["name"] == "A2"


def test_delete_folder_removes_children(client: TestClient) -> None:
    coll = client.post("/api/collections", json={"name": "C"}).json()
    cid = coll["id"]
    f = client.post(
        f"/api/collections/{cid}/folders", json={"name": "F"}
    ).json()["items"][0]
    client.post(
        f"/api/collections/{cid}/requests",
        json={"name": "child", "url": "https://x.example", "parent_folder_id": f["id"]},
    )
    after = client.delete(f"/api/collections/{cid}/folders/{f['id']}").json()
    assert after["items"] == []


def test_count_requests_excludes_folders(client: TestClient) -> None:
    """The summary count surfaces leaf requests only."""
    coll = client.post("/api/collections", json={"name": "C"}).json()
    cid = coll["id"]
    f = client.post(
        f"/api/collections/{cid}/folders", json={"name": "F"}
    ).json()["items"][0]
    client.post(
        f"/api/collections/{cid}/requests",
        json={"name": "in folder", "url": "https://x.example", "parent_folder_id": f["id"]},
    )
    client.post(
        f"/api/collections/{cid}/requests",
        json={"name": "at root", "url": "https://y.example"},
    )
    summaries = client.get("/api/collections").json()
    [me] = [s for s in summaries if s["id"] == cid]
    assert me["request_count"] == 2  # 2 requests, 1 folder


def test_legacy_files_without_is_folder_still_load(
    client: TestClient, tmp_path: Path
) -> None:
    """Old collections written before folders existed must still parse."""
    legacy = {
        "id": "11111111-1111-1111-1111-111111111111",
        "name": "Legacy",
        "version": 1,
        "items": [
            {
                "id": "22222222-2222-2222-2222-222222222222",
                "name": "Old request",
                "method": "GET",
                "url": "https://legacy.example",
                "headers": {},
                "body": None,
            }
        ],
    }
    import json as _json

    (tmp_path / "collections" / f"{legacy['id']}.json").parent.mkdir(
        parents=True, exist_ok=True
    )
    (tmp_path / "collections" / f"{legacy['id']}.json").write_text(
        _json.dumps(legacy)
    )
    res = client.get(f"/api/collections/{legacy['id']}")
    assert res.status_code == 200
    data = res.json()
    assert data["items"][0]["is_folder"] is False
    assert data["items"][0]["name"] == "Old request"
