"""Tests for cookie jar persistence and manipulation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from theridion_sidecar.cookies import (
    CookieJar,
    StoredCookie,
    clear,
    from_httpx_response,
    load,
    save,
    to_httpx_cookies,
)


# Use a fixed UUID for all tests.
_ENV_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def _set_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))


# ---------------------------------------------------------------------------
# load
# ---------------------------------------------------------------------------

def test_load_empty_jar() -> None:
    jar = load(_ENV_ID)
    assert jar.environment_id == _ENV_ID
    assert jar.cookies == []


def test_load_invalid_uuid_raises() -> None:
    with pytest.raises(ValueError):
        load("not-a-uuid")


# ---------------------------------------------------------------------------
# save + load round trip
# ---------------------------------------------------------------------------

def test_save_and_load_round_trip() -> None:
    jar = CookieJar(
        environment_id=_ENV_ID,
        cookies=[
            StoredCookie(name="session", value="abc123", domain="example.com"),
            StoredCookie(name="csrf", value="token456"),
        ],
    )
    save(jar)
    loaded = load(_ENV_ID)
    assert loaded.environment_id == _ENV_ID
    assert len(loaded.cookies) == 2
    assert loaded.cookies[0].name == "session"
    assert loaded.cookies[0].value == "abc123"
    assert loaded.cookies[1].name == "csrf"


def test_save_overwrites_previous() -> None:
    jar1 = CookieJar(
        environment_id=_ENV_ID,
        cookies=[StoredCookie(name="old", value="1")],
    )
    save(jar1)

    jar2 = CookieJar(
        environment_id=_ENV_ID,
        cookies=[StoredCookie(name="new", value="2")],
    )
    save(jar2)

    loaded = load(_ENV_ID)
    assert len(loaded.cookies) == 1
    assert loaded.cookies[0].name == "new"


# ---------------------------------------------------------------------------
# from_httpx_response
# ---------------------------------------------------------------------------

def test_from_httpx_response_merge_new() -> None:
    existing = CookieJar(
        environment_id=_ENV_ID,
        cookies=[StoredCookie(name="a", value="1")],
    )
    merged = from_httpx_response(_ENV_ID, existing, {"b": "2"})
    names = {c.name for c in merged.cookies}
    assert names == {"a", "b"}


def test_from_httpx_response_overwrites_existing() -> None:
    existing = CookieJar(
        environment_id=_ENV_ID,
        cookies=[StoredCookie(name="a", value="old")],
    )
    merged = from_httpx_response(_ENV_ID, existing, {"a": "new"})
    assert len(merged.cookies) == 1
    assert merged.cookies[0].value == "new"


def test_from_httpx_response_empty_response() -> None:
    existing = CookieJar(
        environment_id=_ENV_ID,
        cookies=[StoredCookie(name="keep", value="me")],
    )
    merged = from_httpx_response(_ENV_ID, existing, {})
    assert len(merged.cookies) == 1


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------

def test_clear_existing() -> None:
    jar = CookieJar(
        environment_id=_ENV_ID,
        cookies=[StoredCookie(name="x", value="y")],
    )
    save(jar)
    assert clear(_ENV_ID) is True
    # After clear, loading returns empty.
    assert load(_ENV_ID).cookies == []


def test_clear_nonexistent() -> None:
    assert clear(_ENV_ID) is False


# ---------------------------------------------------------------------------
# to_httpx_cookies
# ---------------------------------------------------------------------------

def test_to_httpx_cookies_flat_dict() -> None:
    jar = CookieJar(
        environment_id=_ENV_ID,
        cookies=[
            StoredCookie(name="a", value="1"),
            StoredCookie(name="b", value="2"),
        ],
    )
    result = to_httpx_cookies(jar)
    assert result == {"a": "1", "b": "2"}


def test_to_httpx_cookies_empty() -> None:
    jar = CookieJar(environment_id=_ENV_ID)
    assert to_httpx_cookies(jar) == {}


# ---------------------------------------------------------------------------
# delete_cookie
# ---------------------------------------------------------------------------

def test_delete_cookie_existing() -> None:
    from theridion_sidecar.cookies import delete_cookie

    jar = CookieJar(
        environment_id=_ENV_ID,
        cookies=[
            StoredCookie(name="a", value="1"),
            StoredCookie(name="b", value="2"),
        ],
    )
    save(jar)
    assert delete_cookie(_ENV_ID, "a") is True
    loaded = load(_ENV_ID)
    assert len(loaded.cookies) == 1
    assert loaded.cookies[0].name == "b"


def test_delete_cookie_nonexistent() -> None:
    from theridion_sidecar.cookies import delete_cookie

    jar = CookieJar(
        environment_id=_ENV_ID,
        cookies=[StoredCookie(name="a", value="1")],
    )
    save(jar)
    assert delete_cookie(_ENV_ID, "nope") is False


# ---------------------------------------------------------------------------
# set_cookie
# ---------------------------------------------------------------------------

def test_set_cookie_new() -> None:
    from theridion_sidecar.cookies import set_cookie

    cookie = StoredCookie(name="new", value="val", domain="example.com")
    result = set_cookie(_ENV_ID, cookie)
    assert len(result.cookies) == 1
    assert result.cookies[0].name == "new"
    assert result.cookies[0].domain == "example.com"


def test_set_cookie_replace() -> None:
    from theridion_sidecar.cookies import set_cookie

    jar = CookieJar(
        environment_id=_ENV_ID,
        cookies=[StoredCookie(name="x", value="old", domain="a.com")],
    )
    save(jar)
    updated = set_cookie(_ENV_ID, StoredCookie(name="x", value="new", domain="a.com"))
    assert len(updated.cookies) == 1
    assert updated.cookies[0].value == "new"


# ---------------------------------------------------------------------------
# list_all
# ---------------------------------------------------------------------------

def test_list_all_empty() -> None:
    from theridion_sidecar.cookies import list_all

    result = list_all()
    assert result == {}


def test_list_all_with_jars() -> None:
    from theridion_sidecar.cookies import list_all

    env2 = "00000000-0000-0000-0000-000000000002"
    save(CookieJar(environment_id=_ENV_ID, cookies=[StoredCookie(name="a", value="1")]))
    save(CookieJar(environment_id=env2, cookies=[StoredCookie(name="b", value="2")]))
    result = list_all()
    assert len(result) == 2
    assert _ENV_ID in result
    assert env2 in result


# ---------------------------------------------------------------------------
# StoredCookie extended fields
# ---------------------------------------------------------------------------

def test_stored_cookie_extended_fields() -> None:
    jar = CookieJar(
        environment_id=_ENV_ID,
        cookies=[
            StoredCookie(
                name="session",
                value="abc",
                domain="example.com",
                httponly=True,
                secure=True,
                samesite="Lax",
                expires="2026-12-31T23:59:59Z",
            ),
        ],
    )
    save(jar)
    loaded = load(_ENV_ID)
    c = loaded.cookies[0]
    assert c.httponly is True
    assert c.secure is True
    assert c.samesite == "Lax"
    assert c.expires == "2026-12-31T23:59:59Z"
