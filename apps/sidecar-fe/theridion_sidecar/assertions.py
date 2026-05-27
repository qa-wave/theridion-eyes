"""Declarative assertion engine for API response testing.

Assertions are evaluated against an ExecuteResponse and return
pass/fail results with messages.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field


AssertionType = Literal[
    "status",
    "response_time",
    "json_path",
    "header_exists",
    "header_equals",
    "body_contains",
    "body_regex",
    "performance_budget",
]


class Assertion(BaseModel):
    type: AssertionType
    # status: expected status code
    expected: str = ""
    # json_path: the JSONPath expression (simple dot-notation)
    path: str = ""
    # comparison operator for json_path
    operator: str = "eq"  # eq, neq, gt, lt, gte, lte, contains, exists


class AssertionResult(BaseModel):
    assertion: Assertion
    passed: bool
    message: str


class ResponseData(BaseModel):
    """Subset of ExecuteResponse needed for assertion evaluation."""

    status: int
    headers: dict[str, str] = Field(default_factory=dict)
    body: str = ""
    elapsed_ms: float = 0


def evaluate(assertion: Assertion, response: ResponseData) -> AssertionResult:
    """Evaluate a single assertion against response data."""
    try:
        if assertion.type == "status":
            expected = int(assertion.expected)
            passed = response.status == expected
            msg = (
                f"Status is {response.status}"
                if passed
                else f"Expected status {expected}, got {response.status}"
            )
            return AssertionResult(assertion=assertion, passed=passed, message=msg)

        elif assertion.type == "response_time":
            max_ms = float(assertion.expected)
            passed = response.elapsed_ms <= max_ms
            msg = (
                f"Response time {response.elapsed_ms:.0f}ms <= {max_ms:.0f}ms"
                if passed
                else f"Response time {response.elapsed_ms:.0f}ms exceeded {max_ms:.0f}ms"
            )
            return AssertionResult(assertion=assertion, passed=passed, message=msg)

        elif assertion.type == "header_exists":
            key = assertion.path.lower()
            found = any(k.lower() == key for k in response.headers)
            msg = (
                f"Header '{assertion.path}' exists"
                if found
                else f"Header '{assertion.path}' not found"
            )
            return AssertionResult(assertion=assertion, passed=found, message=msg)

        elif assertion.type == "header_equals":
            key = assertion.path.lower()
            actual = next(
                (v for k, v in response.headers.items() if k.lower() == key), None
            )
            if actual is None:
                return AssertionResult(
                    assertion=assertion,
                    passed=False,
                    message=f"Header '{assertion.path}' not found",
                )
            passed = actual == assertion.expected
            msg = (
                f"Header '{assertion.path}' equals '{assertion.expected}'"
                if passed
                else f"Header '{assertion.path}': expected '{assertion.expected}', got '{actual}'"
            )
            return AssertionResult(assertion=assertion, passed=passed, message=msg)

        elif assertion.type == "body_contains":
            passed = assertion.expected in response.body
            msg = (
                f"Body contains '{assertion.expected}'"
                if passed
                else f"Body does not contain '{assertion.expected}'"
            )
            return AssertionResult(assertion=assertion, passed=passed, message=msg)

        elif assertion.type == "body_regex":
            try:
                pattern = re.compile(assertion.expected)
                passed = bool(pattern.search(response.body))
            except re.error as e:
                return AssertionResult(
                    assertion=assertion,
                    passed=False,
                    message=f"Invalid regex: {e}",
                )
            msg = (
                f"Body matches /{assertion.expected}/"
                if passed
                else f"Body does not match /{assertion.expected}/"
            )
            return AssertionResult(assertion=assertion, passed=passed, message=msg)

        elif assertion.type == "json_path":
            return _eval_json_path(assertion, response)

        elif assertion.type == "performance_budget":
            return _eval_performance_budget(assertion, response)

        else:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                message=f"Unknown assertion type: {assertion.type}",
            )
    except Exception as e:
        return AssertionResult(
            assertion=assertion,
            passed=False,
            message=f"Error: {e}",
        )


def evaluate_all(
    assertions: list[Assertion], response: ResponseData,
) -> list[AssertionResult]:
    return [evaluate(a, response) for a in assertions]


def _eval_performance_budget(assertion: Assertion, response: ResponseData) -> AssertionResult:
    """Evaluate a performance budget assertion.

    Expected format: "time<500,size<10240"
    Checks response time (ms) and body size (bytes) against budgets.
    """
    budget_str = assertion.expected.strip()
    if not budget_str:
        return AssertionResult(
            assertion=assertion,
            passed=False,
            message="Empty performance budget",
        )

    failures: list[str] = []
    checks: list[str] = []

    for part in budget_str.split(","):
        part = part.strip()
        if not part:
            continue
        # Parse "metric<value" or "metric>value"
        match = re.match(r"^(time|size)\s*(<|>|<=|>=)\s*(\d+(?:\.\d+)?)$", part)
        if not match:
            failures.append(f"Invalid budget spec: '{part}'")
            continue

        metric, op, threshold_str = match.group(1), match.group(2), match.group(3)
        threshold = float(threshold_str)

        if metric == "time":
            actual = response.elapsed_ms
            label = f"time={actual:.0f}ms"
        else:  # size
            actual = float(len(response.body.encode("utf-8")))
            label = f"size={actual:.0f}B"

        passed_check = False
        if op == "<":
            passed_check = actual < threshold
        elif op == ">":
            passed_check = actual > threshold
        elif op == "<=":
            passed_check = actual <= threshold
        elif op == ">=":
            passed_check = actual >= threshold

        if passed_check:
            checks.append(f"{label} {op} {threshold_str}")
        else:
            failures.append(f"{label} not {op} {threshold_str}")

    if failures:
        return AssertionResult(
            assertion=assertion,
            passed=False,
            message="Budget exceeded: " + "; ".join(failures),
        )

    return AssertionResult(
        assertion=assertion,
        passed=True,
        message="Budget met: " + "; ".join(checks) if checks else "No budget constraints",
    )


def _eval_json_path(assertion: Assertion, response: ResponseData) -> AssertionResult:
    """Evaluate a simple dot-notation JSON path assertion."""
    try:
        data = json.loads(response.body)
    except (json.JSONDecodeError, ValueError):
        return AssertionResult(
            assertion=assertion,
            passed=False,
            message="Response body is not valid JSON",
        )

    # Simple dot-notation path: "data.items[0].name"
    actual = _resolve_path(data, assertion.path)

    if assertion.operator == "exists":
        passed = actual is not _MISSING
        msg = (
            f"$.{assertion.path} exists"
            if passed
            else f"$.{assertion.path} does not exist"
        )
        return AssertionResult(assertion=assertion, passed=passed, message=msg)

    if actual is _MISSING:
        return AssertionResult(
            assertion=assertion,
            passed=False,
            message=f"$.{assertion.path} does not exist",
        )

    expected_str = assertion.expected
    passed = False
    op = assertion.operator

    if op == "eq":
        passed = _loose_eq(actual, expected_str)
    elif op == "neq":
        passed = not _loose_eq(actual, expected_str)
    elif op == "contains":
        passed = expected_str in str(actual)
    elif op in ("gt", "lt", "gte", "lte"):
        try:
            a_num = float(actual)
            b_num = float(expected_str)
            if op == "gt":
                passed = a_num > b_num
            elif op == "lt":
                passed = a_num < b_num
            elif op == "gte":
                passed = a_num >= b_num
            elif op == "lte":
                passed = a_num <= b_num
        except (ValueError, TypeError):
            return AssertionResult(
                assertion=assertion,
                passed=False,
                message=f"Cannot compare '{actual}' {op} '{expected_str}' as numbers",
            )

    actual_display = json.dumps(actual) if isinstance(actual, (dict, list)) else str(actual)
    msg = (
        f"$.{assertion.path} {op} '{expected_str}' (actual: {actual_display})"
        if passed
        else f"$.{assertion.path}: expected {op} '{expected_str}', got {actual_display}"
    )
    return AssertionResult(assertion=assertion, passed=passed, message=msg)


class _MissingSentinel:
    pass


_MISSING = _MissingSentinel()


def _resolve_path(data: Any, path: str) -> Any:
    """Resolve a simple dot-notation path with bracket indexing."""
    if not path:
        return data

    current = data
    # Split on dots, handling bracket notation like items[0]
    for part in path.split("."):
        # Handle array indexing: items[0]
        bracket_match = re.match(r"^(\w+)\[(\d+)]$", part)
        if bracket_match:
            key, idx = bracket_match.group(1), int(bracket_match.group(2))
            if isinstance(current, dict) and key in current:
                current = current[key]
                if isinstance(current, list) and 0 <= idx < len(current):
                    current = current[idx]
                else:
                    return _MISSING
            else:
                return _MISSING
        elif isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return _MISSING
        else:
            return _MISSING
    return current


def _loose_eq(actual: Any, expected_str: str) -> bool:
    """Compare actual value to expected string with type coercion."""
    if str(actual) == expected_str:
        return True
    if isinstance(actual, bool):
        return expected_str.lower() in ("true", "1") if actual else expected_str.lower() in ("false", "0")
    if isinstance(actual, (int, float)):
        try:
            return actual == float(expected_str)
        except ValueError:
            return False
    if actual is None:
        return expected_str.lower() in ("null", "none", "")
    return False
