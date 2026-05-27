"""API-level tests for cookie jar endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from theridion_sidecar.cookies import CookieJar, StoredCookie, save

_ENV_ID = "00000000-0000-0000-0000-000000000001"
_ENV_ID2 = "00000000-0000-0000-0000-000000000002"


def test_list_cookies_empty(client: TestClient) -> None:
    r = client.get("/api/cookies")
    assert r.status_code == 200
    assert r.json()["jars"] == {}


def test_list_cookies_with_env_filter(client: TestClient) -> None:
    save(CookieJar(environment_id=_ENV_ID, cookies=[StoredCookie(name="a", value="1")]))
    save(CookieJar(environment_id=_ENV_ID2, cookies=[StoredCookie(name="b", value="2")]))
    r = client.get(f"/api/cookies?env_id={_ENV_ID}")
    assert r.status_code == 200
    jars = r.json()["jars"]
    assert _ENV_ID in jars
    assert _ENV_ID2 not in jars


def test_get_cookies_for_env(client: TestClient) -> None:
    save(CookieJar(environment_id=_ENV_ID, cookies=[StoredCookie(name="s", value="v")]))
    r = client.get(f"/api/cookies/{_ENV_ID}")
    assert r.status_code == 200
    data = r.json()
    assert len(data["cookies"]) == 1
    assert data["cookies"][0]["name"] == "s"


def test_set_cookie_via_put(client: TestClient) -> None:
    r = client.put(
        f"/api/cookies/{_ENV_ID}",
        json={
            "name": "session",
            "value": "abc123",
            "domain": "example.com",
            "httponly": True,
            "secure": True,
            "samesite": "Strict",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data["cookies"]) == 1
    c = data["cookies"][0]
    assert c["name"] == "session"
    assert c["value"] == "abc123"
    assert c["httponly"] is True
    assert c["secure"] is True
    assert c["samesite"] == "Strict"


def test_delete_specific_cookie(client: TestClient) -> None:
    save(CookieJar(
        environment_id=_ENV_ID,
        cookies=[
            StoredCookie(name="keep", value="1"),
            StoredCookie(name="remove", value="2"),
        ],
    ))
    r = client.delete(f"/api/cookies/{_ENV_ID}/remove")
    assert r.status_code == 204
    # Verify only "keep" remains.
    r2 = client.get(f"/api/cookies/{_ENV_ID}")
    cookies = r2.json()["cookies"]
    assert len(cookies) == 1
    assert cookies[0]["name"] == "keep"


def test_delete_specific_cookie_not_found(client: TestClient) -> None:
    save(CookieJar(environment_id=_ENV_ID, cookies=[]))
    r = client.delete(f"/api/cookies/{_ENV_ID}/nope")
    assert r.status_code == 404


def test_clear_cookies_for_env(client: TestClient) -> None:
    save(CookieJar(environment_id=_ENV_ID, cookies=[StoredCookie(name="x", value="y")]))
    r = client.delete(f"/api/cookies/{_ENV_ID}")
    assert r.status_code == 204
    r2 = client.get(f"/api/cookies/{_ENV_ID}")
    assert r2.json()["cookies"] == []


def test_clear_all_cookies(client: TestClient) -> None:
    save(CookieJar(environment_id=_ENV_ID, cookies=[StoredCookie(name="a", value="1")]))
    save(CookieJar(environment_id=_ENV_ID2, cookies=[StoredCookie(name="b", value="2")]))
    r = client.delete("/api/cookies")
    assert r.status_code == 204
    r2 = client.get("/api/cookies")
    assert r2.json()["jars"] == {}
