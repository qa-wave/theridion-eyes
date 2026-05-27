"""Cookie jar API — view, manage, and clear cookies per environment."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import cookies

router = APIRouter(prefix="/api/cookies", tags=["cookies"])


class AllCookieJars(BaseModel):
    jars: dict[str, cookies.CookieJar]


class SetCookieInput(BaseModel):
    name: str
    value: str
    domain: str = ""
    path: str = "/"
    expires: str | None = None
    httponly: bool = False
    secure: bool = False
    samesite: str | None = None


@router.get("", response_model=AllCookieJars)
def list_cookies(env_id: str | None = None) -> AllCookieJars:
    """List all cookie jars, optionally filtered to a single environment."""
    if env_id:
        jar = cookies.load(env_id)
        return AllCookieJars(jars={env_id: jar})
    return AllCookieJars(jars=cookies.list_all())


@router.delete("", status_code=204)
def clear_all_cookies(env_id: str | None = None) -> None:
    """Clear cookies for a specific env, or all environments."""
    if env_id:
        cookies.clear(env_id)
    else:
        for eid in list(cookies.list_all().keys()):
            cookies.clear(eid)


@router.get("/{env_id}", response_model=cookies.CookieJar)
def get_cookies(env_id: str) -> cookies.CookieJar:
    return cookies.load(env_id)


@router.delete("/{env_id}", status_code=204)
def clear_cookies(env_id: str) -> None:
    cookies.clear(env_id)


@router.delete("/{env_id}/{cookie_name}", status_code=204)
def delete_cookie(env_id: str, cookie_name: str) -> None:
    """Delete a specific cookie by name from an environment's jar."""
    if not cookies.delete_cookie(env_id, cookie_name):
        raise HTTPException(status_code=404, detail="cookie not found")


@router.put("/{env_id}", response_model=cookies.CookieJar)
def set_cookie(env_id: str, body: SetCookieInput) -> cookies.CookieJar:
    """Manually set (add or update) a cookie in an environment's jar."""
    cookie = cookies.StoredCookie(
        name=body.name,
        value=body.value,
        domain=body.domain,
        path=body.path,
        expires=body.expires,
        httponly=body.httponly,
        secure=body.secure,
        samesite=body.samesite,
    )
    return cookies.set_cookie(env_id, cookie)
