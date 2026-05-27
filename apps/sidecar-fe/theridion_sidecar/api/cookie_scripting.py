"""Cookie scripting: execute scripts with cookie helpers."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/scripts", tags=["cookie-scripting"])


class CookieScriptInput(BaseModel):
    script: str
    cookies: dict[str, str] = {}


class CookieScriptOutput(BaseModel):
    cookies_modified: dict[str, str] = {}
    result: str = ""
    error: str | None = None


@router.post("/cookie-api", response_model=CookieScriptOutput)
async def cookie_script(body: CookieScriptInput) -> CookieScriptOutput:
    # Simple script execution with cookie get/set
    # In a full impl this would use a JS sandbox; here we simulate
    cookies = dict(body.cookies)
    result_lines: list[str] = []

    for line in body.script.strip().split("\n"):
        line = line.strip()
        if line.startswith("setCookie("):
            # Parse setCookie("name", "value")
            try:
                args = line[len("setCookie("):-1]
                parts = [p.strip().strip("'\"") for p in args.split(",", 1)]
                if len(parts) == 2:
                    cookies[parts[0]] = parts[1]
                    result_lines.append(f"Set {parts[0]}={parts[1]}")
            except Exception:
                pass
        elif line.startswith("getCookie("):
            try:
                name = line[len("getCookie("):-1].strip("'\"")
                val = cookies.get(name, "")
                result_lines.append(f"{name}={val}")
            except Exception:
                pass

    return CookieScriptOutput(
        cookies_modified=cookies,
        result="\n".join(result_lines),
    )
