"""Tests for cURL parse / generate round-trip."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from theridion_sidecar.api.curl import generate_curl, parse_curl, GenerateInput


# ---- parse unit tests -----------------------------------------------------


def test_simple_get() -> None:
    result = parse_curl("curl https://example.com")
    assert result.method == "GET"
    assert result.url == "https://example.com"
    assert result.body is None
    assert result.auth is None


def test_get_with_headers() -> None:
    result = parse_curl(
        "curl -H 'Accept: application/json' -H 'X-Custom: foo' https://api.example.com/data"
    )
    assert result.method == "GET"
    assert result.headers["Accept"] == "application/json"
    assert result.headers["X-Custom"] == "foo"


def test_post_with_data() -> None:
    result = parse_curl(
        """curl -X POST -H 'Content-Type: application/json' -d '{"key":"value"}' https://api.example.com"""
    )
    assert result.method == "POST"
    assert result.body == '{"key":"value"}'
    assert result.headers["Content-Type"] == "application/json"


def test_implicit_post_with_data() -> None:
    result = parse_curl("curl -d 'hello=world' https://example.com")
    assert result.method == "POST"
    assert result.body == "hello=world"


def test_data_raw_flag() -> None:
    result = parse_curl("curl --data-raw '{\"a\":1}' https://example.com")
    assert result.method == "POST"
    assert result.body == '{"a":1}'


def test_bearer_auth_from_header() -> None:
    result = parse_curl(
        "curl -H 'Authorization: Bearer my-token' https://api.example.com"
    )
    assert result.auth is not None
    assert result.auth.type == "bearer"
    assert result.auth.token == "my-token"
    assert "Authorization" not in result.headers


def test_basic_auth_from_user_flag() -> None:
    result = parse_curl("curl -u alice:s3cret https://example.com")
    assert result.auth is not None
    assert result.auth.type == "basic"
    assert result.auth.username == "alice"
    assert result.auth.password == "s3cret"


def test_user_flag_no_password() -> None:
    result = parse_curl("curl -u alice https://example.com")
    assert result.auth is not None
    assert result.auth.type == "basic"
    assert result.auth.username == "alice"
    assert result.auth.password == ""


def test_multiline_curl() -> None:
    cmd = """curl -X PUT \\
  -H 'Content-Type: application/json' \\
  -d '{"name":"test"}' \\
  https://api.example.com/items/1"""
    result = parse_curl(cmd)
    assert result.method == "PUT"
    assert result.url == "https://api.example.com/items/1"
    assert result.body == '{"name":"test"}'


def test_leading_dollar_stripped() -> None:
    result = parse_curl("$ curl https://example.com")
    assert result.url == "https://example.com"


def test_compressed_and_insecure_flags_ignored() -> None:
    result = parse_curl("curl --compressed -k https://example.com")
    assert result.url == "https://example.com"
    assert result.method == "GET"


def test_empty_string_returns_empty() -> None:
    result = parse_curl("")
    assert result.url == ""


def test_non_curl_returns_empty() -> None:
    result = parse_curl("wget https://example.com")
    assert result.url == ""


def test_location_flag_ignored() -> None:
    result = parse_curl("curl -L https://example.com/redirect")
    assert result.url == "https://example.com/redirect"


# ---- generate unit tests --------------------------------------------------


def test_generate_simple_get() -> None:
    result = generate_curl(GenerateInput(method="GET", url="https://example.com"))
    assert "curl" in result
    assert "'https://example.com'" in result
    assert "-X" not in result  # GET is default, omit -X


def test_generate_post_with_body() -> None:
    result = generate_curl(
        GenerateInput(
            method="POST",
            url="https://api.example.com",
            headers={"Content-Type": "application/json"},
            body='{"key":"value"}',
        )
    )
    assert "-X POST" in result
    assert "-H 'Content-Type: application/json'" in result
    assert "--data-raw" in result


def test_generate_with_bearer_auth() -> None:
    from theridion_sidecar.models import AuthConfig

    result = generate_curl(
        GenerateInput(
            method="GET",
            url="https://api.example.com",
            auth=AuthConfig(type="bearer", token="tok123"),
        )
    )
    assert "Authorization: Bearer tok123" in result


def test_generate_with_basic_auth() -> None:
    from theridion_sidecar.models import AuthConfig

    result = generate_curl(
        GenerateInput(
            method="GET",
            url="https://api.example.com",
            auth=AuthConfig(type="basic", username="bob", password="pass"),
        )
    )
    assert "-u 'bob:pass'" in result


def test_generate_apikey_in_header() -> None:
    from theridion_sidecar.models import AuthConfig

    result = generate_curl(
        GenerateInput(
            method="GET",
            url="https://api.example.com",
            auth=AuthConfig(type="apikey", key="X-API-Key", value="abc", add_to="header"),
        )
    )
    assert "-H 'X-API-Key: abc'" in result


def test_generate_apikey_in_query() -> None:
    from theridion_sidecar.models import AuthConfig

    result = generate_curl(
        GenerateInput(
            method="GET",
            url="https://api.example.com",
            auth=AuthConfig(type="apikey", key="api_key", value="abc", add_to="query"),
        )
    )
    assert "api_key=abc" in result


# ---- integration tests via endpoint ---------------------------------------


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar.main import create_app

    return TestClient(create_app())


def test_parse_endpoint(client: TestClient) -> None:
    res = client.post(
        "/api/curl/parse",
        json={"curl": "curl -X POST -d 'test' https://example.com"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["method"] == "POST"
    assert data["url"] == "https://example.com"
    assert data["body"] == "test"


def test_generate_endpoint(client: TestClient) -> None:
    res = client.post(
        "/api/curl/generate",
        json={"method": "DELETE", "url": "https://example.com/1"},
    )
    assert res.status_code == 200
    assert "-X DELETE" in res.json()["curl"]


def test_round_trip(client: TestClient) -> None:
    original = "curl -X PUT -H 'Content-Type: application/json' -d '{\"a\":1}' https://api.example.com/items/1"
    parsed = client.post("/api/curl/parse", json={"curl": original}).json()
    assert parsed["method"] == "PUT"
    assert parsed["url"] == "https://api.example.com/items/1"

    generated = client.post("/api/curl/generate", json=parsed).json()["curl"]
    assert "-X PUT" in generated
    assert "https://api.example.com/items/1" in generated
    assert "--data-raw" in generated
