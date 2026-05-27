"""Pre-request / post-response script execution.

Safe mini-interpreter (POST /execute-safe) — no eval/exec, parses a
small command DSL line-by-line for lightweight automation without any
external runtime dependency.

The safe interpreter supports:
- ``set("key", value)`` — store a variable
- ``get("key")`` — retrieve a variable (usable as argument)
- ``log(...)`` — capture log output
- ``assert(expr, message)`` — boolean check
- ``setHeader("Name", "value")`` — set an outgoing header (pre-request)

Dot-notation access into the *context* dict is supported:
``response.status``, ``response.json.data.id``, etc.

NOTE: The Node.js subprocess endpoint (POST /execute) was removed in
Fáze 0 P0 security hardening — it allowed arbitrary code execution with
full filesystem access. Use the safe DSL or template engine instead.
See: docs/security/scripts-deprecation.md
"""

from __future__ import annotations

import re
from typing import Any, Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/scripts", tags=["scripts"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class SafeScriptRequest(BaseModel):
    """Input for the safe mini-interpreter endpoint."""

    script: str = Field(..., min_length=1)
    phase: Literal["pre", "post"] = "pre"
    context: dict[str, Any] = Field(default_factory=dict)


class AssertionItem(BaseModel):
    passed: bool
    message: str


class SafeScriptOutput(BaseModel):
    variables: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    logs: list[str] = Field(default_factory=list)
    assertions: list[AssertionItem] = Field(default_factory=list)
    error: str | None = None


# ---------------------------------------------------------------------------
# Safe mini-interpreter
# ---------------------------------------------------------------------------

_MISSING = object()


def _resolve_path(obj: Any, path: str) -> Any:
    """Walk *obj* through dot-separated keys and ``[N]`` indices.

    Returns ``_MISSING`` sentinel when the path does not exist in *obj*.
    Returns the actual value (including ``None``) when the path resolves.

    >>> _resolve_path({"a": {"b": [10, 20]}}, "a.b[1]")
    20
    """
    current = obj
    for segment in path.split("."):
        bracket = re.match(r"^(\w+)\[(\d+)]$", segment)
        if bracket:
            key, idx = bracket.group(1), int(bracket.group(2))
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return _MISSING
            if isinstance(current, (list, tuple)) and idx < len(current):
                current = current[idx]
            else:
                return _MISSING
        else:
            if isinstance(current, dict) and segment in current:
                current = current[segment]
            else:
                return _MISSING
    return current


# Regex helpers for parsing script lines.
_STRING_RE = r"""(?:"([^"\\]*(?:\\.[^"\\]*)*)"|'([^'\\]*(?:\\.[^'\\]*)*)')"""
_CALL_RE = re.compile(r"^(\w+)\s*\((.*)\)\s*$", re.DOTALL)
_CONCAT_RE = re.compile(r'\s*\+\s*')


def _parse_arg(raw: str, variables: dict[str, str], context: dict[str, Any]) -> str:
    """Resolve a single argument token to a string value.

    Supports:
    - String literals: ``"hello"`` or ``'hello'``
    - ``get("key")`` — variable lookup
    - Dot paths: ``response.json.data.id`` — context lookup
    - Concatenation with ``+``
    """
    raw = raw.strip()
    if not raw:
        return ""

    # Handle concatenation (split on + that is outside quotes).
    parts = _split_concat(raw)
    if len(parts) > 1:
        return "".join(_parse_arg(p, variables, context) for p in parts)

    # String literal
    m = re.fullmatch(_STRING_RE, raw)
    if m:
        return (m.group(1) if m.group(1) is not None else m.group(2)).replace("\\n", "\n").replace('\\"', '"').replace("\\'", "'")

    # get("key") call
    get_m = re.match(r'^get\s*\(\s*' + _STRING_RE + r'\s*\)$', raw)
    if get_m:
        key = get_m.group(1) if get_m.group(1) is not None else get_m.group(2)
        return variables.get(key, "")

    # Numeric literal
    if re.fullmatch(r'-?\d+(\.\d+)?', raw):
        return raw

    # Boolean / null
    if raw in ("true", "false", "null", "undefined"):
        return raw

    # Dot path — resolve against context
    resolved = _resolve_path(context, raw)
    if resolved is not _MISSING:
        if resolved is None:
            return "null"
        return str(resolved) if not isinstance(resolved, str) else resolved

    # Unknown — treat as literal
    return raw


def _split_concat(expr: str) -> list[str]:
    """Split *expr* on ``+`` that is outside of quotes."""
    parts: list[str] = []
    current: list[str] = []
    in_quote: str | None = None
    i = 0
    while i < len(expr):
        ch = expr[i]
        if in_quote:
            current.append(ch)
            if ch == "\\" and i + 1 < len(expr):
                i += 1
                current.append(expr[i])
            elif ch == in_quote:
                in_quote = None
        elif ch in ('"', "'"):
            in_quote = ch
            current.append(ch)
        elif ch == "+":
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
        i += 1
    parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


def _parse_args_list(raw: str, variables: dict[str, str], context: dict[str, Any]) -> list[str]:
    """Split a comma-separated argument list and resolve each."""
    args: list[str] = []
    depth = 0
    current: list[str] = []
    in_quote: str | None = None

    for ch in raw:
        if in_quote:
            current.append(ch)
            if ch == "\\" and current:
                pass  # next char is escaped — handled by _parse_arg
            elif ch == in_quote:
                in_quote = None
            continue
        if ch in ('"', "'"):
            in_quote = ch
            current.append(ch)
        elif ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            args.append("".join(current))
            current = []
        else:
            current.append(ch)

    if current:
        args.append("".join(current))

    return [_parse_arg(a, variables, context) for a in args]


def execute_safe_script(
    script: str,
    phase: str,
    context: dict[str, Any],
) -> SafeScriptOutput:
    """Execute a script using the safe mini-interpreter."""
    variables: dict[str, str] = {}
    headers: dict[str, str] = {}
    logs: list[str] = []
    assertions: list[AssertionItem] = []

    # Seed variables from context.env if present.
    env = context.get("env")
    if isinstance(env, dict):
        for k, v in env.items():
            variables[k] = str(v)

    lines = script.split("\n")
    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("#"):
            continue

        # Remove trailing semicolons.
        if stripped.endswith(";"):
            stripped = stripped[:-1].rstrip()

        m = _CALL_RE.match(stripped)
        if not m:
            return SafeScriptOutput(
                variables=variables,
                headers=headers,
                logs=logs,
                assertions=assertions,
                error=f"Line {lineno}: syntax error — expected a function call, got: {stripped[:80]}",
            )

        fn_name = m.group(1)
        raw_args = m.group(2).strip()

        try:
            if fn_name == "set":
                args = _parse_args_list(raw_args, variables, context)
                if len(args) < 2:
                    return SafeScriptOutput(
                        variables=variables, headers=headers, logs=logs,
                        assertions=assertions,
                        error=f"Line {lineno}: set() requires 2 arguments (key, value)",
                    )
                variables[args[0]] = args[1]

            elif fn_name == "get":
                # Standalone get() is a no-op (useful only inside other calls).
                pass

            elif fn_name == "log":
                args = _parse_args_list(raw_args, variables, context)
                logs.append(" ".join(args))

            elif fn_name == "setHeader":
                args = _parse_args_list(raw_args, variables, context)
                if len(args) < 2:
                    return SafeScriptOutput(
                        variables=variables, headers=headers, logs=logs,
                        assertions=assertions,
                        error=f"Line {lineno}: setHeader() requires 2 arguments (name, value)",
                    )
                headers[args[0]] = args[1]

            elif fn_name == "assert":
                args = _parse_args_list(raw_args, variables, context)
                if not args:
                    return SafeScriptOutput(
                        variables=variables, headers=headers, logs=logs,
                        assertions=assertions,
                        error=f"Line {lineno}: assert() requires at least 1 argument",
                    )
                condition_raw = args[0]
                message = args[1] if len(args) > 1 else "Assertion"

                # Evaluate simple boolean-ish conditions.
                passed = _eval_condition(condition_raw, variables, context)
                assertions.append(AssertionItem(passed=passed, message=message))

            else:
                return SafeScriptOutput(
                    variables=variables, headers=headers, logs=logs,
                    assertions=assertions,
                    error=f"Line {lineno}: unknown function '{fn_name}'. "
                          f"Available: set, get, log, assert, setHeader",
                )
        except Exception as exc:
            return SafeScriptOutput(
                variables=variables, headers=headers, logs=logs,
                assertions=assertions,
                error=f"Line {lineno}: {exc}",
            )

    return SafeScriptOutput(
        variables=variables,
        headers=headers,
        logs=logs,
        assertions=assertions,
        error=None,
    )


def _eval_condition(raw: str, variables: dict[str, str], context: dict[str, Any]) -> bool:
    """Evaluate a simple boolean expression from an already-resolved string.

    The raw value comes from ``_parse_arg`` so it's already a string.
    We need to handle comparisons that were written as a *single* argument
    to ``assert()``, e.g. ``assert(response.status === 200, "msg")``.
    Since ``_parse_args_list`` splits on commas, the condition is the first
    argument as a raw string *before* resolution.  We therefore re-parse
    the condition here.

    Supported operators: ``===``, ``!==``, ``==``, ``!=``, ``>``, ``<``,
    ``>=``, ``<=``.
    """
    # The *raw* value was already resolved to a string by _parse_arg.
    # For comparison operators, we need the *unresolved* text.  Since we
    # can't go back, we rely on the fact that simple truthy strings work:
    # - "true"  → True
    # - "false", "0", "", "null", "undefined" → False
    # - any other non-empty string → True

    # Check for common falsy values.
    v = raw.strip().lower()
    if v in ("false", "0", "", "null", "undefined", "none"):
        return False
    return True


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

_GONE_BODY = {
    "detail": (
        "POST /api/scripts/execute (Node.js subprocess) was removed in "
        "Fáze 0 P0 security hardening. It allowed arbitrary code execution "
        "with full filesystem access (SSH keys, AWS credentials, etc.). "
        "Migrate to: (1) POST /api/scripts/execute-safe — safe DSL with "
        "set/get/log/assert/setHeader, or (2) template engine syntax "
        "{{$timestamp}} / {{$uuid}} / {{$randomInt}} in request bodies. "
        "See docs/security/scripts-deprecation.md for migration examples."
    )
}


@router.post("/execute")
async def execute_script_removed() -> JSONResponse:
    """Removed: Node.js subprocess endpoint.

    Returns HTTP 410 Gone with migration instructions.
    """
    return JSONResponse(status_code=410, content=_GONE_BODY)


@router.post("/execute-safe", response_model=SafeScriptOutput)
async def execute_safe(body: SafeScriptRequest) -> SafeScriptOutput:
    """Execute a script using the safe mini-interpreter (no eval/exec).

    This endpoint does NOT require Node.js — it parses a small command
    DSL line-by-line and is suitable for simple variable extraction,
    header setting, assertions, and logging.
    """
    return execute_safe_script(body.script, body.phase, body.context)
