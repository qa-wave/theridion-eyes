"""Tests for the enhanced OpenAPI/Swagger import endpoint."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from theridion_sidecar.main import app

client = TestClient(app)

# ---------------------------------------------------------------------------
# Fixtures: minimal specs
# ---------------------------------------------------------------------------

OPENAPI_30_SPEC = json.dumps({
    "openapi": "3.0.3",
    "info": {"title": "Pet Store", "version": "1.0.0"},
    "servers": [{"url": "https://api.petstore.io/v1"}],
    "paths": {
        "/pets": {
            "get": {
                "tags": ["Pets"],
                "summary": "List all pets",
                "operationId": "listPets",
                "parameters": [
                    {"name": "limit", "in": "query", "schema": {"type": "integer"}},
                ],
                "responses": {"200": {"description": "OK"}},
            },
            "post": {
                "tags": ["Pets"],
                "summary": "Create a pet",
                "operationId": "createPet",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "tag": {"type": "string"},
                                },
                            }
                        }
                    }
                },
                "responses": {"201": {"description": "Created"}},
            },
        },
        "/pets/{petId}": {
            "get": {
                "tags": ["Pets"],
                "summary": "Get pet by ID",
                "operationId": "getPet",
                "parameters": [
                    {"name": "petId", "in": "path", "required": True, "schema": {"type": "string"}},
                ],
                "responses": {"200": {"description": "OK"}},
            },
        },
        "/owners": {
            "get": {
                "tags": ["Owners"],
                "summary": "List owners",
                "responses": {"200": {"description": "OK"}},
            },
        },
    },
    "components": {
        "securitySchemes": {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
            }
        }
    },
    "security": [{"BearerAuth": []}],
})


SWAGGER_20_SPEC = json.dumps({
    "swagger": "2.0",
    "info": {"title": "Legacy API", "version": "2.0.0"},
    "host": "api.legacy.com",
    "basePath": "/v2",
    "schemes": ["https"],
    "consumes": ["application/json"],
    "produces": ["application/json"],
    "paths": {
        "/users": {
            "get": {
                "tags": ["Users"],
                "summary": "List users",
                "responses": {"200": {"description": "OK"}},
            },
            "post": {
                "tags": ["Users"],
                "summary": "Create user",
                "parameters": [
                    {
                        "name": "body",
                        "in": "body",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "username": {"type": "string"},
                                "email": {"type": "string", "format": "email"},
                            },
                        },
                    }
                ],
                "responses": {"201": {"description": "Created"}},
            },
        },
        "/users/{id}": {
            "get": {
                "tags": ["Users"],
                "summary": "Get user",
                "parameters": [
                    {"name": "id", "in": "path", "required": True, "type": "integer"},
                ],
                "responses": {"200": {"description": "OK"}},
            },
        },
    },
    "securityDefinitions": {
        "ApiKey": {
            "type": "apiKey",
            "name": "X-API-Key",
            "in": "header",
        }
    },
})


OPENAPI_31_WITH_REFS = json.dumps({
    "openapi": "3.1.0",
    "info": {"title": "Ref API", "version": "0.1.0"},
    "servers": [
        {"url": "https://{env}.example.com/api", "variables": {"env": {"default": "prod"}}}
    ],
    "paths": {
        "/items": {
            "post": {
                "summary": "Create item",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Item"}
                        }
                    }
                },
                "responses": {"201": {"description": "Created"}},
            }
        }
    },
    "components": {
        "schemas": {
            "Item": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "active": {"type": "boolean"},
                    "price": {"type": "number"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
            }
        }
    },
})


# ---------------------------------------------------------------------------
# Test: OpenAPI 3.0 import
# ---------------------------------------------------------------------------

class TestOpenApi30Import:
    def test_import_creates_collection(self, tmp_path, monkeypatch):
        monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
        r = client.post("/api/import/openapi", json={"source": OPENAPI_30_SPEC})
        assert r.status_code == 200
        data = r.json()
        assert data["collection_name"] == "Pet Store"
        assert data["request_count"] == 4
        assert data["folder_count"] == 2  # Pets, Owners
        assert data["collection_id"]

    def test_import_with_custom_name(self, tmp_path, monkeypatch):
        monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
        r = client.post("/api/import/openapi", json={
            "source": OPENAPI_30_SPEC,
            "collection_name": "My Custom API",
        })
        assert r.status_code == 200
        assert r.json()["collection_name"] == "My Custom API"

    def test_import_base_url_in_urls(self, tmp_path, monkeypatch):
        monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
        r = client.post("/api/import/openapi", json={"source": OPENAPI_30_SPEC})
        coll_id = r.json()["collection_id"]
        # Verify by fetching the collection
        coll_r = client.get(f"/api/collections/{coll_id}")
        assert coll_r.status_code == 200
        coll = coll_r.json()
        # Find a non-folder item
        all_urls = []
        for item in coll["items"]:
            if item.get("is_folder"):
                for sub in item.get("items", []):
                    if sub.get("url"):
                        all_urls.append(sub["url"])
            elif item.get("url"):
                all_urls.append(item["url"])
        assert any("https://api.petstore.io/v1" in u for u in all_urls)

    def test_auth_detected_as_bearer(self, tmp_path, monkeypatch):
        monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
        r = client.post("/api/import/openapi", json={"source": OPENAPI_30_SPEC})
        coll_id = r.json()["collection_id"]
        coll_r = client.get(f"/api/collections/{coll_id}")
        coll = coll_r.json()
        # Check that at least one request has bearer auth
        found_auth = False
        for item in coll["items"]:
            subitems = item.get("items", [item])
            for sub in subitems:
                if sub.get("auth") and sub["auth"].get("type") == "bearer":
                    found_auth = True
        assert found_auth


# ---------------------------------------------------------------------------
# Test: Swagger 2.0 import
# ---------------------------------------------------------------------------

def _collect_all_requests(items: list[dict]) -> list[dict]:
    """Recursively collect all non-folder items from a collection tree."""
    out: list[dict] = []
    for item in items:
        if item.get("is_folder"):
            out.extend(_collect_all_requests(item.get("items", [])))
        else:
            out.append(item)
    return out


class TestSwagger20Import:
    def test_import_creates_collection(self, tmp_path, monkeypatch):
        monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
        r = client.post("/api/import/openapi", json={"source": SWAGGER_20_SPEC})
        assert r.status_code == 200
        data = r.json()
        assert data["collection_name"] == "Legacy API"
        assert data["request_count"] == 3

    def test_base_url_from_host(self, tmp_path, monkeypatch):
        monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
        r = client.post("/api/import/openapi", json={"source": SWAGGER_20_SPEC})
        coll_id = r.json()["collection_id"]
        coll_r = client.get(f"/api/collections/{coll_id}")
        coll = coll_r.json()
        all_requests = _collect_all_requests(coll["items"])
        all_urls = [req["url"] for req in all_requests if req.get("url")]
        assert any("https://api.legacy.com/v2" in u for u in all_urls)

    def test_body_parameter_generates_example(self, tmp_path, monkeypatch):
        monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
        r = client.post("/api/import/openapi", json={"source": SWAGGER_20_SPEC})
        coll_id = r.json()["collection_id"]
        coll_r = client.get(f"/api/collections/{coll_id}")
        coll = coll_r.json()
        all_requests = _collect_all_requests(coll["items"])
        post_items = [req for req in all_requests if req.get("method") == "POST"]
        assert len(post_items) >= 1
        body = json.loads(post_items[0]["body"])
        assert "username" in body
        assert "email" in body

    def test_apikey_auth_detected(self, tmp_path, monkeypatch):
        monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
        r = client.post("/api/import/openapi", json={"source": SWAGGER_20_SPEC})
        coll_id = r.json()["collection_id"]
        coll_r = client.get(f"/api/collections/{coll_id}")
        coll = coll_r.json()
        all_requests = _collect_all_requests(coll["items"])
        found_apikey = any(
            req.get("auth") and req["auth"].get("type") == "apikey"
            for req in all_requests
        )
        assert found_apikey


# ---------------------------------------------------------------------------
# Test: Schema-based example generation
# ---------------------------------------------------------------------------

class TestSchemaExampleGeneration:
    def test_ref_resolution_and_body_generation(self, tmp_path, monkeypatch):
        monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
        r = client.post("/api/import/openapi", json={"source": OPENAPI_31_WITH_REFS})
        assert r.status_code == 200
        coll_id = r.json()["collection_id"]
        coll_r = client.get(f"/api/collections/{coll_id}")
        coll = coll_r.json()
        # Find the POST item
        post_items = []
        for item in coll["items"]:
            if item.get("is_folder"):
                for sub in item.get("items", []):
                    if sub.get("method") == "POST":
                        post_items.append(sub)
            elif item.get("method") == "POST":
                post_items.append(item)
        assert len(post_items) == 1
        body = json.loads(post_items[0]["body"])
        assert "id" in body
        assert isinstance(body["id"], int)
        assert "name" in body
        assert isinstance(body["name"], str)
        assert "active" in body
        assert isinstance(body["active"], bool)
        assert "tags" in body
        assert isinstance(body["tags"], list)

    def test_server_variable_substitution(self, tmp_path, monkeypatch):
        monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
        r = client.post("/api/import/openapi", json={"source": OPENAPI_31_WITH_REFS})
        coll_id = r.json()["collection_id"]
        coll_r = client.get(f"/api/collections/{coll_id}")
        coll = coll_r.json()
        all_urls = []
        for item in coll["items"]:
            if item.get("is_folder"):
                for sub in item.get("items", []):
                    if sub.get("url"):
                        all_urls.append(sub["url"])
            elif item.get("url"):
                all_urls.append(item["url"])
        # {env} should be replaced with "prod"
        assert any("prod.example.com" in u for u in all_urls)


# ---------------------------------------------------------------------------
# Test: Tag-based folder creation
# ---------------------------------------------------------------------------

class TestTagBasedFolders:
    def test_multiple_tags_create_folders(self, tmp_path, monkeypatch):
        monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
        r = client.post("/api/import/openapi", json={"source": OPENAPI_30_SPEC})
        coll_id = r.json()["collection_id"]
        coll_r = client.get(f"/api/collections/{coll_id}")
        coll = coll_r.json()
        folders = [i for i in coll["items"] if i.get("is_folder")]
        folder_names = {f["name"] for f in folders}
        assert "Pets" in folder_names
        assert "Owners" in folder_names

    def test_no_tags_uses_path_prefix(self, tmp_path, monkeypatch):
        monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
        spec = json.dumps({
            "openapi": "3.0.0",
            "info": {"title": "No Tags", "version": "1.0.0"},
            "paths": {
                "/alpha/one": {"get": {"summary": "Alpha one", "responses": {"200": {"description": "OK"}}}},
                "/alpha/two": {"post": {"summary": "Alpha two", "responses": {"200": {"description": "OK"}}}},
                "/beta/three": {"get": {"summary": "Beta three", "responses": {"200": {"description": "OK"}}}},
                "/beta/four": {"delete": {"summary": "Beta four", "responses": {"200": {"description": "OK"}}}},
                "/gamma/five": {"put": {"summary": "Gamma five", "responses": {"200": {"description": "OK"}}}},
                "/gamma/six": {"patch": {"summary": "Gamma six", "responses": {"200": {"description": "OK"}}}},
            },
        })
        r = client.post("/api/import/openapi", json={"source": spec})
        assert r.status_code == 200
        data = r.json()
        assert data["request_count"] == 6
        # Should create folders from path prefixes
        coll_r = client.get(f"/api/collections/{data['collection_id']}")
        coll = coll_r.json()
        folders = [i for i in coll["items"] if i.get("is_folder")]
        folder_names = {f["name"] for f in folders}
        assert "Alpha" in folder_names
        assert "Beta" in folder_names
        assert "Gamma" in folder_names


# ---------------------------------------------------------------------------
# Test: Preview mode (no save)
# ---------------------------------------------------------------------------

class TestPreviewMode:
    def test_preview_returns_structure(self, tmp_path, monkeypatch):
        monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
        r = client.post("/api/import/openapi/preview", json={"source": OPENAPI_30_SPEC})
        assert r.status_code == 200
        data = r.json()
        assert data["title"] == "Pet Store"
        assert data["version"] == "1.0.0"
        assert data["base_url"] == "https://api.petstore.io/v1"
        assert data["request_count"] == 4
        assert data["folder_count"] == 2
        assert len(data["folders"]) == 2
        assert data["auth_detected"] is not None
        assert "Bearer" in data["auth_detected"]

    def test_preview_does_not_save(self, tmp_path, monkeypatch):
        monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
        # Get initial collection count
        before = client.get("/api/collections").json()
        before_count = len(before)
        # Preview
        client.post("/api/import/openapi/preview", json={"source": OPENAPI_30_SPEC})
        # Count should not change
        after = client.get("/api/collections").json()
        assert len(after) == before_count

    def test_preview_swagger_20(self, tmp_path, monkeypatch):
        monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
        r = client.post("/api/import/openapi/preview", json={"source": SWAGGER_20_SPEC})
        assert r.status_code == 200
        data = r.json()
        assert data["title"] == "Legacy API"
        assert data["request_count"] == 3


# ---------------------------------------------------------------------------
# Test: Invalid spec handling
# ---------------------------------------------------------------------------

class TestInvalidSpecs:
    def test_invalid_json(self, tmp_path, monkeypatch):
        monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
        r = client.post("/api/import/openapi", json={"source": "not valid json or yaml {{{}"})
        assert r.status_code == 400

    def test_valid_json_but_not_openapi(self, tmp_path, monkeypatch):
        monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
        r = client.post("/api/import/openapi", json={"source": json.dumps({"foo": "bar"})})
        assert r.status_code == 400
        assert "OpenAPI" in r.json()["detail"] or "Swagger" in r.json()["detail"]

    def test_empty_source_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
        r = client.post("/api/import/openapi", json={"source": ""})
        assert r.status_code == 422  # pydantic min_length=1

    def test_no_paths_warns(self, tmp_path, monkeypatch):
        monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
        spec = json.dumps({"openapi": "3.0.0", "info": {"title": "Empty", "version": "1.0.0"}})
        r = client.post("/api/import/openapi", json={"source": spec})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Test: base_url_override + path filtering
# ---------------------------------------------------------------------------

class TestAdvancedOptions:
    def test_base_url_override(self, tmp_path, monkeypatch):
        monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
        r = client.post("/api/import/openapi", json={
            "source": OPENAPI_30_SPEC,
            "base_url_override": "http://localhost:3000",
        })
        coll_id = r.json()["collection_id"]
        coll_r = client.get(f"/api/collections/{coll_id}")
        coll = coll_r.json()
        all_urls = []
        for item in coll["items"]:
            subitems = item.get("items", [item])
            for sub in subitems:
                if sub.get("url"):
                    all_urls.append(sub["url"])
        assert all("http://localhost:3000" in u for u in all_urls)

    def test_path_template_conversion(self, tmp_path, monkeypatch):
        monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
        r = client.post("/api/import/openapi", json={"source": OPENAPI_30_SPEC})
        coll_id = r.json()["collection_id"]
        coll_r = client.get(f"/api/collections/{coll_id}")
        coll = coll_r.json()
        # /pets/{petId} should become /pets/{{petId}}
        all_urls = []
        for item in coll["items"]:
            subitems = item.get("items", [item])
            for sub in subitems:
                if sub.get("url"):
                    all_urls.append(sub["url"])
        pet_id_urls = [u for u in all_urls if "petId" in u]
        assert len(pet_id_urls) >= 1
        assert "{{petId}}" in pet_id_urls[0]
        # The single-brace {petId} must not appear outside of double-braces
        cleaned = pet_id_urls[0].replace("{{petId}}", "")
        assert "{petId}" not in cleaned  # raw OpenAPI param should be gone

    def test_query_params_as_template_vars(self, tmp_path, monkeypatch):
        monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
        r = client.post("/api/import/openapi", json={"source": OPENAPI_30_SPEC})
        coll_id = r.json()["collection_id"]
        coll_r = client.get(f"/api/collections/{coll_id}")
        coll = coll_r.json()
        all_urls = []
        for item in coll["items"]:
            subitems = item.get("items", [item])
            for sub in subitems:
                if sub.get("url"):
                    all_urls.append(sub["url"])
        limit_urls = [u for u in all_urls if "limit" in u]
        assert len(limit_urls) >= 1
        assert "{{limit}}" in limit_urls[0]
