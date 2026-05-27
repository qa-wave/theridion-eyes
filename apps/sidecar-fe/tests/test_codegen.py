"""Tests for the code generation endpoint."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar.main import create_app

    return TestClient(create_app())


_BASE_INPUT = {
    "method": "POST",
    "url": "https://api.example.com/items",
    "headers": {"Content-Type": "application/json", "Authorization": "Bearer tok"},
    "body": '{"name": "test"}',
}


def _generate(client: TestClient, language: str) -> str:
    payload = {**_BASE_INPUT, "language": language}
    res = client.post("/api/codegen/generate", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["language"] == language
    return data["code"]


# ---------------------------------------------------------------------------
# curl
# ---------------------------------------------------------------------------

def test_curl(client: TestClient) -> None:
    code = _generate(client, "curl")
    assert "curl" in code
    assert "-X POST" in code
    assert "api.example.com/items" in code
    assert "Content-Type: application/json" in code
    assert "--data-raw" in code


def test_curl_get_no_method_flag(client: TestClient) -> None:
    res = client.post("/api/codegen/generate", json={
        "method": "GET",
        "url": "https://example.com",
        "language": "curl",
    })
    code = res.json()["code"]
    assert "-X GET" not in code  # curl defaults to GET


# ---------------------------------------------------------------------------
# python
# ---------------------------------------------------------------------------

def test_python(client: TestClient) -> None:
    code = _generate(client, "python")
    assert "import requests" in code
    assert "requests.post" in code
    assert "api.example.com/items" in code
    assert "headers" in code


# ---------------------------------------------------------------------------
# javascript
# ---------------------------------------------------------------------------

def test_javascript(client: TestClient) -> None:
    code = _generate(client, "javascript")
    assert "fetch(" in code
    assert "POST" in code
    assert "api.example.com/items" in code


# ---------------------------------------------------------------------------
# go
# ---------------------------------------------------------------------------

def test_go(client: TestClient) -> None:
    code = _generate(client, "go")
    assert "package main" in code
    assert "net/http" in code
    assert "http.NewRequest" in code
    assert '"POST"' in code


# ---------------------------------------------------------------------------
# java
# ---------------------------------------------------------------------------

def test_java(client: TestClient) -> None:
    code = _generate(client, "java")
    assert "HttpClient" in code
    assert "URI.create" in code
    assert "api.example.com/items" in code


# ---------------------------------------------------------------------------
# csharp
# ---------------------------------------------------------------------------

def test_csharp(client: TestClient) -> None:
    code = _generate(client, "csharp")
    assert "HttpClient" in code
    assert "HttpRequestMessage" in code
    assert "SendAsync" in code


# ---------------------------------------------------------------------------
# php
# ---------------------------------------------------------------------------

def test_php(client: TestClient) -> None:
    code = _generate(client, "php")
    assert "curl_init" in code
    assert "CURLOPT_URL" in code
    assert "CURLOPT_CUSTOMREQUEST" in code


# ---------------------------------------------------------------------------
# ruby
# ---------------------------------------------------------------------------

def test_ruby(client: TestClient) -> None:
    code = _generate(client, "ruby")
    assert "net/http" in code
    assert "Net::HTTP" in code
    assert "api.example.com/items" in code


# ---------------------------------------------------------------------------
# languages list endpoint
# ---------------------------------------------------------------------------

def test_list_languages(client: TestClient) -> None:
    res = client.get("/api/codegen/languages")
    assert res.status_code == 200
    langs = res.json()
    ids = [l["id"] for l in langs]
    assert "curl" in ids
    assert "python" in ids
    assert "javascript" in ids
    assert len(ids) == 8
