"""Cookie jar persistence — stores cookies per environment.

Cookies are stored under ``$THERIDION_HOME/cookies/<env-uuid>.json``
and loaded/saved around each request execution. When no environment is
selected, cookies are discarded between requests.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .storage import home_dir


class StoredCookie(BaseModel):
    name: str
    value: str
    domain: str = ""
    path: str = "/"
    expires: str | None = None
    httponly: bool = False
    secure: bool = False
    samesite: str | None = None


class CookieJar(BaseModel):
    environment_id: str
    cookies: list[StoredCookie] = Field(default_factory=list)


def cookies_dir() -> Path:
    d = home_dir() / "cookies"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path_for(env_id: str) -> Path:
    safe = uuid.UUID(env_id)
    return cookies_dir() / f"{safe}.json"


def load(env_id: str) -> CookieJar:
    """Load cookie jar for an environment. Returns empty jar if none exists."""
    p = _path_for(env_id)
    if not p.exists():
        return CookieJar(environment_id=env_id)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return CookieJar(**data)
    except Exception:
        return CookieJar(environment_id=env_id)


def save(jar: CookieJar) -> None:
    """Persist cookie jar to disk."""
    p = _path_for(jar.environment_id)
    payload: dict[str, Any] = jar.model_dump(mode="json")
    fd, tmp_str = tempfile.mkstemp(
        prefix=f"{jar.environment_id}.", suffix=".json.tmp", dir=str(p.parent)
    )
    tmp = Path(tmp_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def clear(env_id: str) -> bool:
    """Delete all cookies for an environment."""
    p = _path_for(env_id)
    if not p.exists():
        return False
    p.unlink()
    return True


def delete_cookie(env_id: str, cookie_name: str) -> bool:
    """Remove a specific cookie by name from an environment's jar."""
    jar = load(env_id)
    original_count = len(jar.cookies)
    jar.cookies = [c for c in jar.cookies if c.name != cookie_name]
    if len(jar.cookies) == original_count:
        return False
    save(jar)
    return True


def set_cookie(env_id: str, cookie: StoredCookie) -> CookieJar:
    """Add or update a cookie in an environment's jar."""
    jar = load(env_id)
    # Replace if same name+domain already exists, otherwise append.
    replaced = False
    for i, existing in enumerate(jar.cookies):
        if existing.name == cookie.name and existing.domain == cookie.domain:
            jar.cookies[i] = cookie
            replaced = True
            break
    if not replaced:
        jar.cookies.append(cookie)
    save(jar)
    return jar


def list_all() -> dict[str, CookieJar]:
    """List cookie jars for all environments that have persisted cookies."""
    d = cookies_dir()
    result: dict[str, CookieJar] = {}
    for p in d.glob("*.json"):
        env_id = p.stem
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            jar = CookieJar(**data)
            result[env_id] = jar
        except Exception:
            continue
    return result


def to_httpx_cookies(jar: CookieJar) -> dict[str, str]:
    """Convert stored cookies to a flat dict for httpx."""
    return {c.name: c.value for c in jar.cookies}


def from_httpx_response(
    env_id: str, existing: CookieJar, response_cookies: dict[str, str],
) -> CookieJar:
    """Merge response cookies into an existing jar."""
    merged = {c.name: c for c in existing.cookies}
    for name, value in response_cookies.items():
        merged[name] = StoredCookie(name=name, value=value)
    return CookieJar(
        environment_id=env_id,
        cookies=list(merged.values()),
    )
