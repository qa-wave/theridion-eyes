"""Advanced template engine with conditionals, loops, filters, and expressions.

Extends the simple {{var}} substitution with:
- {{$if condition}}...{{$endif}} — conditional blocks
- {{$each items as item}}...{{$end}} — loop over JSON arrays
- {{expr | filter}} — pipe filters (upper, lower, base64, json, urlencode, trim, slice)
- {{$concat var1 "." var2}} — string concatenation
- {{$math 1 + 2}} — basic arithmetic
- {{$default var "fallback"}} — default value
- {{$env VAR_NAME}} — system environment variable (opt-in)
"""

from __future__ import annotations

import base64
import json
import math
import os
import re
import urllib.parse
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/template", tags=["template"])


# ---- Models ----


class RenderOptions(BaseModel):
    allow_env: bool = False


class RenderInput(BaseModel):
    template: str
    variables: dict[str, Any] = Field(default_factory=dict)
    options: RenderOptions | None = None


class RenderOutput(BaseModel):
    rendered: str
    variables_used: list[str]
    warnings: list[str]


class ValidateInput(BaseModel):
    template: str


class ValidateOutput(BaseModel):
    valid: bool
    errors: list[str]


class ExtractInput(BaseModel):
    template: str


class ExtractOutput(BaseModel):
    variables: list[str]


# ---- Filters ----

_FILTERS: dict[str, Any] = {
    "upper": lambda s: s.upper(),
    "lower": lambda s: s.lower(),
    "base64": lambda s: base64.b64encode(s.encode()).decode(),
    "json": lambda s: json.dumps(s),
    "urlencode": lambda s: urllib.parse.quote_plus(s),
    "trim": lambda s: s.strip(),
}


def _apply_filter(value: str, filter_expr: str) -> str:
    """Apply a filter expression (possibly with args) to a value."""
    parts = filter_expr.strip().split(":")
    name = parts[0].strip()
    args = parts[1:]

    if name == "slice":
        start = int(args[0]) if len(args) > 0 else 0
        end = int(args[1]) if len(args) > 1 else len(value)
        return value[start:end]

    fn = _FILTERS.get(name)
    if fn is None:
        return value  # unknown filter — pass through
    return fn(value)


# ---- Core engine ----


def _resolve_value(expr: str, variables: dict[str, Any]) -> str | None:
    """Resolve a simple variable name or dotted path from variables dict."""
    parts = expr.split(".")
    current: Any = variables
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    if current is None:
        return None
    return str(current)


def _eval_condition(condition: str, variables: dict[str, Any]) -> bool:
    """Evaluate a simple condition (truthy check on variable)."""
    condition = condition.strip()

    # Handle negation
    if condition.startswith("!"):
        return not _eval_condition(condition[1:].strip(), variables)

    # Handle equality: var == "value" or var == value
    if "==" in condition:
        left, right = condition.split("==", 1)
        left_val = _resolve_value(left.strip(), variables) or ""
        right_str = right.strip().strip('"').strip("'")
        return left_val == right_str

    # Handle inequality: var != "value"
    if "!=" in condition:
        left, right = condition.split("!=", 1)
        left_val = _resolve_value(left.strip(), variables) or ""
        right_str = right.strip().strip('"').strip("'")
        return left_val != right_str

    # Simple truthy check
    val = _resolve_value(condition, variables)
    if val is None:
        return False
    # Empty string, "0", "false", "null" are falsy
    return val not in ("", "0", "false", "null")


def _eval_math(expr: str) -> str:
    """Evaluate basic arithmetic: +, -, *, /."""
    # Only allow digits, operators, spaces, dots, parens
    if not re.match(r"^[\d\s+\-*/().]+$", expr):
        return expr
    try:
        result = eval(expr, {"__builtins__": {}}, {"math": math})  # noqa: S307
        if isinstance(result, float) and result == int(result):
            return str(int(result))
        return str(result)
    except Exception:
        return expr


def render_template(
    template: str,
    variables: dict[str, Any],
    allow_env: bool = False,
) -> RenderOutput:
    """Render a template string with full expression support."""
    warnings: list[str] = []
    variables_used: list[str] = []

    def track_var(name: str) -> None:
        if name not in variables_used:
            variables_used.append(name)

    # Phase 1: Process block-level constructs (if/each)
    result = _process_blocks(template, variables, warnings, variables_used, track_var, allow_env)

    # Phase 2: Process inline expressions
    result = _process_inline(result, variables, warnings, track_var, allow_env)

    return RenderOutput(rendered=result, variables_used=variables_used, warnings=warnings)


def _process_blocks(
    template: str,
    variables: dict[str, Any],
    warnings: list[str],
    variables_used: list[str],
    track_var: Any,
    allow_env: bool,
) -> str:
    """Process {{$if}}...{{$endif}} and {{$each}}...{{$end}} blocks."""
    result = template

    # Process $each blocks (innermost first)
    each_pattern = re.compile(
        r"\{\{\s*\$each\s+([A-Za-z_][A-Za-z0-9_.]*)\s+as\s+([A-Za-z_]\w*)\s*\}\}(.*?)\{\{\s*\$end\s*\}\}",
        re.DOTALL,
    )
    while each_pattern.search(result):
        def _replace_each(m: re.Match[str]) -> str:
            collection_name = m.group(1)
            item_name = m.group(2)
            body = m.group(3)
            track_var(collection_name)

            items = variables.get(collection_name)
            if not isinstance(items, list):
                warnings.append(f"'{collection_name}' is not a list")
                return ""

            output_parts = []
            for item in items:
                # Create a sub-scope with the loop variable
                sub_vars = {**variables, item_name: item}
                # Recursively render the body
                sub_result = render_template(body, sub_vars, allow_env)
                output_parts.append(sub_result.rendered)
                for w in sub_result.warnings:
                    if w not in warnings:
                        warnings.append(w)
            return "".join(output_parts)

        result = each_pattern.sub(_replace_each, result)

    # Process $if blocks (innermost first — body must not contain another $if)
    if_pattern = re.compile(
        r"\{\{\s*\$if\s+([^}]+?)\s*\}\}((?:(?!\{\{\s*\$if\s).)*?)\{\{\s*\$endif\s*\}\}",
        re.DOTALL,
    )
    while if_pattern.search(result):
        def _replace_if(m: re.Match[str]) -> str:
            condition = m.group(1)
            body = m.group(2)

            # Track variables used in condition
            cond_vars = re.findall(r"[A-Za-z_][A-Za-z0-9_.]*", condition)
            for v in cond_vars:
                if v not in ("true", "false", "null"):
                    track_var(v)

            if _eval_condition(condition, variables):
                sub_result = render_template(body, variables, allow_env)
                for w in sub_result.warnings:
                    if w not in warnings:
                        warnings.append(w)
                return sub_result.rendered
            return ""

        result = if_pattern.sub(_replace_if, result)

    return result


def _process_inline(
    template: str,
    variables: dict[str, Any],
    warnings: list[str],
    track_var: Any,
    allow_env: bool,
) -> str:
    """Process inline {{expressions}} including filters, $concat, $math, $default, $env."""

    # Match {{ ... }} but not block-level constructs
    pattern = re.compile(r"\{\{(.+?)\}\}")

    def _replace(m: re.Match[str]) -> str:
        expr = m.group(1).strip()

        # $concat var1 "." var2
        if expr.startswith("$concat "):
            parts_raw = expr[8:]  # after "$concat "
            parts = _parse_concat_args(parts_raw, variables)
            for p in re.findall(r"[A-Za-z_][A-Za-z0-9_.-]*", parts_raw):
                if not p.startswith('"') and not p.startswith("'"):
                    track_var(p)
            return "".join(parts)

        # $math expression
        if expr.startswith("$math "):
            math_expr = expr[6:]
            # Substitute variables in the math expression
            for var_name, var_val in variables.items():
                if isinstance(var_val, (int, float)):
                    math_expr = re.sub(
                        rf"\b{re.escape(var_name)}\b", str(var_val), math_expr
                    )
            return _eval_math(math_expr)

        # $default var "fallback"
        if expr.startswith("$default "):
            rest = expr[9:]
            match = re.match(r"(\S+)\s+(.+)", rest)
            if match:
                var_name = match.group(1)
                fallback = match.group(2).strip().strip('"').strip("'")
                track_var(var_name)
                val = _resolve_value(var_name, variables)
                return val if val is not None and val != "" else fallback
            return m.group(0)

        # $env VAR_NAME
        if expr.startswith("$env "):
            env_name = expr[5:].strip()
            if not allow_env:
                warnings.append(f"$env access denied for '{env_name}' (allow_env=false)")
                return m.group(0)
            return os.environ.get(env_name, "")

        # Built-in functions ($timestamp, $uuid, etc.) — pass through
        if expr.startswith("$"):
            from ..environments import _builtin
            result = _builtin(expr)
            if result is not None:
                return result
            return m.group(0)

        # Handle filters: expr | filter1 | filter2
        if "|" in expr:
            parts = expr.split("|")
            var_expr = parts[0].strip()
            track_var(var_expr)
            val = _resolve_value(var_expr, variables)
            if val is None:
                val = var_expr  # literal fallback
            for filt in parts[1:]:
                val = _apply_filter(val, filt)
            return val

        # Simple variable
        track_var(expr)
        val = _resolve_value(expr, variables)
        if val is None:
            return m.group(0)  # leave as-is
        return val

    return pattern.sub(_replace, template)


def _parse_concat_args(raw: str, variables: dict[str, Any]) -> list[str]:
    """Parse arguments for $concat: variable names and quoted literals."""
    parts: list[str] = []
    i = 0
    while i < len(raw):
        if raw[i] in (" ", "\t"):
            i += 1
            continue
        if raw[i] in ('"', "'"):
            quote = raw[i]
            end = raw.index(quote, i + 1)
            parts.append(raw[i + 1 : end])
            i = end + 1
        else:
            # Variable name
            match = re.match(r"[A-Za-z_][A-Za-z0-9_.-]*", raw[i:])
            if match:
                var_name = match.group(0)
                val = _resolve_value(var_name, variables)
                parts.append(val if val is not None else "")
                i += len(var_name)
            else:
                i += 1
    return parts


# ---- Validation ----


def validate_template(template: str) -> ValidateOutput:
    """Check for unclosed blocks, invalid expressions."""
    errors: list[str] = []

    # Count block openers/closers
    if_opens = len(re.findall(r"\{\{\s*\$if\s+", template))
    if_closes = len(re.findall(r"\{\{\s*\$endif\s*\}\}", template))
    if if_opens > if_closes:
        errors.append(f"Unclosed $if block(s): {if_opens - if_closes} opening(s) without $endif")
    elif if_closes > if_opens:
        errors.append(f"Extra $endif: {if_closes - if_opens} $endif without matching $if")

    each_opens = len(re.findall(r"\{\{\s*\$each\s+", template))
    each_closes = len(re.findall(r"\{\{\s*\$end\s*\}\}", template))
    if each_opens > each_closes:
        errors.append(f"Unclosed $each block(s): {each_opens - each_closes} opening(s) without $end")
    elif each_closes > each_opens:
        errors.append(f"Extra $end: {each_closes - each_opens} $end without matching $each")

    # Check for unclosed {{ without }}
    unclosed = re.findall(r"\{\{[^}]*$", template, re.MULTILINE)
    if unclosed:
        errors.append(f"Unclosed expression(s): {len(unclosed)} '{{{{' without matching '}}}}'")

    # Check for invalid filter names
    filter_matches = re.findall(r"\{\{[^}]+\|([^}]+)\}\}", template)
    valid_filters = set(_FILTERS.keys()) | {"slice"}
    for filter_chain in filter_matches:
        for filt in filter_chain.split("|"):
            name = filt.strip().split(":")[0].strip()
            if name and name not in valid_filters:
                errors.append(f"Unknown filter: '{name}'")

    return ValidateOutput(valid=len(errors) == 0, errors=errors)


# ---- Variable extraction ----


def extract_variables(template: str) -> list[str]:
    """Extract all variable names referenced in a template."""
    variables: list[str] = []

    # Simple {{var}} and {{var | filter}}
    for m in re.finditer(r"\{\{(.+?)\}\}", template):
        expr = m.group(1).strip()
        if expr.startswith("$if "):
            # Extract vars from condition
            cond = expr[4:]
            for v in re.findall(r"[A-Za-z_][A-Za-z0-9_.]*", cond):
                if v not in ("true", "false", "null") and v not in variables:
                    variables.append(v)
        elif expr.startswith("$each "):
            match = re.match(r"(\S+)\s+as\s+", expr[6:])
            if match and match.group(1) not in variables:
                variables.append(match.group(1))
        elif expr.startswith("$concat "):
            for v in re.findall(r"(?<![\"'])\b([A-Za-z_][A-Za-z0-9_.]*)\b", expr[8:]):
                if v not in variables:
                    variables.append(v)
        elif expr.startswith("$default "):
            match = re.match(r"(\S+)", expr[9:])
            if match and match.group(1) not in variables:
                variables.append(match.group(1))
        elif expr.startswith("$env "):
            pass  # env vars not tracked as template variables
        elif expr.startswith("$math "):
            for v in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expr[6:]):
                if v not in variables:
                    variables.append(v)
        elif expr in ("$endif", "$end"):
            pass
        elif expr.startswith("$"):
            pass  # built-in functions
        else:
            # May have filters
            var_name = expr.split("|")[0].strip()
            if var_name and var_name not in variables:
                variables.append(var_name)

    return variables


# ---- API endpoints ----


@router.post("/render", response_model=RenderOutput)
async def api_render(body: RenderInput) -> RenderOutput:
    opts = body.options or RenderOptions()
    return render_template(body.template, body.variables, allow_env=opts.allow_env)


@router.post("/validate", response_model=ValidateOutput)
async def api_validate(body: ValidateInput) -> ValidateOutput:
    return validate_template(body.template)


@router.post("/variables", response_model=ExtractOutput)
async def api_extract(body: ExtractInput) -> ExtractOutput:
    return ExtractOutput(variables=extract_variables(body.template))
