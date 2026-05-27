"""Tests for the FastMCP-based MCP server (mcp_server_v2)."""

from __future__ import annotations

import json
import uuid

import pytest

from theridion_sidecar.mcp_server_v2 import (
    compare_responses,
    create_request,
    execute_request,
    generate_assertions,
    get_collection,
    heal_assertion,
    list_collections,
    list_environments,
    mcp,
)
from theridion_sidecar import storage, environments


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def _clean_storage(tmp_path, monkeypatch):
    """Point storage + environments at a temp dir so tests are isolated."""
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))


# ---------------------------------------------------------------------------
# 1. All tools are registered
# ---------------------------------------------------------------------------


def test_all_tools_registered():
    """All 10 tools should be registered on the FastMCP instance."""
    # FastMCP stores tools internally; we can list them via the
    # _tool_manager or by inspecting the server's tool list.
    tool_names = set(mcp._tool_manager._tools.keys())
    expected = {
        "execute_request",
        "list_collections",
        "get_collection",
        "run_collection",
        "list_environments",
        "create_request",
        "inspect_api",
        "generate_assertions",
        "heal_assertion",
        "compare_responses",
    }
    assert expected.issubset(tool_names), f"Missing tools: {expected - tool_names}"


# ---------------------------------------------------------------------------
# 2. list_collections returns correct format
# ---------------------------------------------------------------------------


def test_list_collections_empty(_clean_storage):
    result = list_collections()
    assert isinstance(result, list)
    assert len(result) == 0


def test_list_collections_with_data(_clean_storage):
    storage.create("Test Collection")
    result = list_collections()
    assert len(result) == 1
    assert result[0]["name"] == "Test Collection"
    assert result[0]["request_count"] == 0
    assert "id" in result[0]


# ---------------------------------------------------------------------------
# 3. get_collection
# ---------------------------------------------------------------------------


def test_get_collection_not_found(_clean_storage):
    fake_id = str(uuid.uuid4())
    result = get_collection(fake_id)
    assert result == {"error": "Collection not found"}


def test_get_collection_found(_clean_storage):
    coll = storage.create("My API")
    result = get_collection(coll.id)
    assert result["name"] == "My API"
    assert result["id"] == coll.id
    assert "items" in result


# ---------------------------------------------------------------------------
# 4. execute_request (integration — hits real URL, skip if offline)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_request_invalid_url():
    result = await execute_request(
        method="GET",
        url="http://localhost:1/nonexistent",
    )
    assert "error" in result


# ---------------------------------------------------------------------------
# 5. generate_assertions — JSON object body
# ---------------------------------------------------------------------------


def test_generate_assertions_json_object():
    body = json.dumps({"id": 1, "name": "Alice", "email": "a@b.com"})
    result = generate_assertions(
        response_status=200,
        response_body=body,
    )
    assert isinstance(result, list)
    # Should have at least status assertion + json_path assertions.
    assert len(result) >= 2
    types = {a["type"] for a in result}
    assert "status" in types
    assert "json_path" in types
    # Status assertion should match input.
    status_a = next(a for a in result if a["type"] == "status")
    assert status_a["expected"] == "200"


def test_generate_assertions_plain_text():
    result = generate_assertions(
        response_status=404,
        response_body="Not Found",
    )
    assert len(result) >= 1
    assert result[0]["type"] == "status"
    assert result[0]["expected"] == "404"


# ---------------------------------------------------------------------------
# 6. heal_assertion with known renamed key
# ---------------------------------------------------------------------------


def test_heal_assertion_renamed_key():
    body = json.dumps({"user_name": "Alice", "age": 30})
    result = heal_assertion(
        assertion_type="json_path",
        assertion_path="username",
        assertion_expected="Alice",
        response_body=body,
    )
    assert "candidates" in result
    assert len(result["candidates"]) > 0
    paths = [c["path"] for c in result["candidates"]]
    assert "user_name" in paths


# ---------------------------------------------------------------------------
# 7. compare_responses
# ---------------------------------------------------------------------------


def test_compare_responses_identical():
    body = json.dumps({"a": 1, "b": 2})
    result = compare_responses(body, body)
    assert result["identical"] is True
    assert result["diff_count"] == 0


def test_compare_responses_different():
    a = json.dumps({"name": "Alice", "age": 30})
    b = json.dumps({"name": "Bob", "age": 30, "new_field": True})
    result = compare_responses(a, b)
    assert result["identical"] is False
    assert result["diff_count"] >= 1
    diff_paths = [d["path"] for d in result["diffs"]]
    assert "name" in diff_paths


def test_compare_responses_invalid_json():
    result = compare_responses("not json", '{"a":1}')
    assert "error" in result


# ---------------------------------------------------------------------------
# 8. list_environments
# ---------------------------------------------------------------------------


def test_list_environments_empty(_clean_storage):
    result = list_environments()
    assert isinstance(result, list)
    assert len(result) == 0


def test_list_environments_with_data(_clean_storage):
    environments.create("Production")
    result = list_environments()
    assert len(result) == 1
    assert result[0]["name"] == "Production"
    assert result[0]["variable_count"] == 0


# ---------------------------------------------------------------------------
# 9. create_request
# ---------------------------------------------------------------------------


def test_create_request_success(_clean_storage):
    coll = storage.create("My Collection")
    result = create_request(
        collection_id=coll.id,
        name="Get Users",
        method="GET",
        url="https://api.example.com/users",
    )
    assert "id" in result
    assert result["name"] == "Get Users"
    assert result["collection"] == "My Collection"

    # Verify it's actually saved.
    updated = storage.get(coll.id)
    assert updated is not None
    assert len(updated.items) == 1
    assert updated.items[0].name == "Get Users"


def test_create_request_collection_not_found(_clean_storage):
    result = create_request(
        collection_id=str(uuid.uuid4()),
        name="Test",
        method="GET",
        url="https://example.com",
    )
    assert result == {"error": "Collection not found"}


# ---------------------------------------------------------------------------
# 10. collections resource
# ---------------------------------------------------------------------------


def test_collections_resource_empty(_clean_storage):
    from theridion_sidecar.mcp_server_v2 import collections_resource

    result = collections_resource()
    assert result == "No collections saved yet."


def test_collections_resource_with_data(_clean_storage):
    from theridion_sidecar.mcp_server_v2 import collections_resource

    storage.create("API v1")
    result = collections_resource()
    assert "API v1" in result
    assert "0 requests" in result


# ---------------------------------------------------------------------------
# 11. Prompts are registered
# ---------------------------------------------------------------------------


def test_prompts_registered():
    prompt_names = set(mcp._prompt_manager._prompts.keys())
    assert "test_api" in prompt_names
    assert "debug_request" in prompt_names
