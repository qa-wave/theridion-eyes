"""Unit tests for the declarative assertion engine."""

from __future__ import annotations

import json

import pytest

from theridion_sidecar.assertions import (
    Assertion,
    ResponseData,
    _MISSING,
    _loose_eq,
    _resolve_path,
    evaluate,
    evaluate_all,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resp(
    status: int = 200,
    body: str = "",
    headers: dict[str, str] | None = None,
    elapsed_ms: float = 50,
) -> ResponseData:
    return ResponseData(
        status=status,
        headers=headers or {},
        body=body,
        elapsed_ms=elapsed_ms,
    )


# ---------------------------------------------------------------------------
# status assertions
# ---------------------------------------------------------------------------

def test_status_pass() -> None:
    r = evaluate(Assertion(type="status", expected="200"), _resp(status=200))
    assert r.passed is True


def test_status_fail() -> None:
    r = evaluate(Assertion(type="status", expected="201"), _resp(status=200))
    assert r.passed is False
    assert "Expected status 201" in r.message


# ---------------------------------------------------------------------------
# response_time assertions
# ---------------------------------------------------------------------------

def test_response_time_pass() -> None:
    r = evaluate(
        Assertion(type="response_time", expected="100"),
        _resp(elapsed_ms=50),
    )
    assert r.passed is True


def test_response_time_fail() -> None:
    r = evaluate(
        Assertion(type="response_time", expected="30"),
        _resp(elapsed_ms=50),
    )
    assert r.passed is False
    assert "exceeded" in r.message


def test_response_time_exact_boundary() -> None:
    r = evaluate(
        Assertion(type="response_time", expected="50"),
        _resp(elapsed_ms=50),
    )
    assert r.passed is True  # <= comparison


# ---------------------------------------------------------------------------
# json_path assertions
# ---------------------------------------------------------------------------

_JSON_BODY = json.dumps({"data": {"items": [{"name": "alpha", "count": 3}], "total": 10}})


def test_json_path_eq_pass() -> None:
    r = evaluate(
        Assertion(type="json_path", path="data.total", operator="eq", expected="10"),
        _resp(body=_JSON_BODY),
    )
    assert r.passed is True


def test_json_path_eq_fail() -> None:
    r = evaluate(
        Assertion(type="json_path", path="data.total", operator="eq", expected="99"),
        _resp(body=_JSON_BODY),
    )
    assert r.passed is False


def test_json_path_neq() -> None:
    r = evaluate(
        Assertion(type="json_path", path="data.total", operator="neq", expected="99"),
        _resp(body=_JSON_BODY),
    )
    assert r.passed is True


def test_json_path_gt() -> None:
    r = evaluate(
        Assertion(type="json_path", path="data.total", operator="gt", expected="5"),
        _resp(body=_JSON_BODY),
    )
    assert r.passed is True


def test_json_path_lt() -> None:
    r = evaluate(
        Assertion(type="json_path", path="data.total", operator="lt", expected="100"),
        _resp(body=_JSON_BODY),
    )
    assert r.passed is True


def test_json_path_contains() -> None:
    r = evaluate(
        Assertion(type="json_path", path="data.items[0].name", operator="contains", expected="alp"),
        _resp(body=_JSON_BODY),
    )
    assert r.passed is True


def test_json_path_contains_fail() -> None:
    r = evaluate(
        Assertion(type="json_path", path="data.items[0].name", operator="contains", expected="zzz"),
        _resp(body=_JSON_BODY),
    )
    assert r.passed is False


def test_json_path_exists_pass() -> None:
    r = evaluate(
        Assertion(type="json_path", path="data.total", operator="exists"),
        _resp(body=_JSON_BODY),
    )
    assert r.passed is True


def test_json_path_exists_fail() -> None:
    r = evaluate(
        Assertion(type="json_path", path="data.missing", operator="exists"),
        _resp(body=_JSON_BODY),
    )
    assert r.passed is False


def test_json_path_invalid_json() -> None:
    r = evaluate(
        Assertion(type="json_path", path="foo", operator="eq", expected="bar"),
        _resp(body="not json"),
    )
    assert r.passed is False
    assert "not valid JSON" in r.message


def test_json_path_missing_path() -> None:
    r = evaluate(
        Assertion(type="json_path", path="nope.nope", operator="eq", expected="x"),
        _resp(body=_JSON_BODY),
    )
    assert r.passed is False
    assert "does not exist" in r.message


# ---------------------------------------------------------------------------
# header_exists assertions
# ---------------------------------------------------------------------------

def test_header_exists_pass() -> None:
    r = evaluate(
        Assertion(type="header_exists", path="Content-Type"),
        _resp(headers={"content-type": "application/json"}),
    )
    assert r.passed is True


def test_header_exists_fail() -> None:
    r = evaluate(
        Assertion(type="header_exists", path="X-Custom"),
        _resp(headers={"content-type": "text/plain"}),
    )
    assert r.passed is False


# ---------------------------------------------------------------------------
# header_equals assertions
# ---------------------------------------------------------------------------

def test_header_equals_pass() -> None:
    r = evaluate(
        Assertion(type="header_equals", path="Content-Type", expected="application/json"),
        _resp(headers={"Content-Type": "application/json"}),
    )
    assert r.passed is True


def test_header_equals_fail_value() -> None:
    r = evaluate(
        Assertion(type="header_equals", path="Content-Type", expected="text/html"),
        _resp(headers={"Content-Type": "application/json"}),
    )
    assert r.passed is False


def test_header_equals_fail_missing() -> None:
    r = evaluate(
        Assertion(type="header_equals", path="X-Missing", expected="x"),
        _resp(headers={}),
    )
    assert r.passed is False
    assert "not found" in r.message


# ---------------------------------------------------------------------------
# body_contains assertions
# ---------------------------------------------------------------------------

def test_body_contains_pass() -> None:
    r = evaluate(
        Assertion(type="body_contains", expected="hello"),
        _resp(body="say hello world"),
    )
    assert r.passed is True


def test_body_contains_fail() -> None:
    r = evaluate(
        Assertion(type="body_contains", expected="missing"),
        _resp(body="nothing here"),
    )
    assert r.passed is False


# ---------------------------------------------------------------------------
# body_regex assertions
# ---------------------------------------------------------------------------

def test_body_regex_pass() -> None:
    r = evaluate(
        Assertion(type="body_regex", expected=r"\d{3}-\d{4}"),
        _resp(body="call 555-1234 now"),
    )
    assert r.passed is True


def test_body_regex_fail() -> None:
    r = evaluate(
        Assertion(type="body_regex", expected=r"^exact$"),
        _resp(body="not exact match"),
    )
    assert r.passed is False


def test_body_regex_invalid() -> None:
    r = evaluate(
        Assertion(type="body_regex", expected="[invalid"),
        _resp(body="whatever"),
    )
    assert r.passed is False
    assert "Invalid regex" in r.message


# ---------------------------------------------------------------------------
# _resolve_path
# ---------------------------------------------------------------------------

def test_resolve_nested_object() -> None:
    data = {"a": {"b": {"c": 42}}}
    assert _resolve_path(data, "a.b.c") == 42


def test_resolve_array_index() -> None:
    data = {"items": [10, 20, 30]}
    assert _resolve_path(data, "items[1]") == 20


def test_resolve_nested_array() -> None:
    data = {"rows": [{"id": 1}, {"id": 2}]}
    assert _resolve_path(data, "rows[1].id") == 2


def test_resolve_bracket_out_of_range() -> None:
    data = {"items": [1]}
    assert isinstance(_resolve_path(data, "items[5]"), type(_MISSING))


def test_resolve_missing_key() -> None:
    data = {"a": 1}
    assert isinstance(_resolve_path(data, "b"), type(_MISSING))


def test_resolve_empty_path() -> None:
    data = {"x": 1}
    assert _resolve_path(data, "") == data


# ---------------------------------------------------------------------------
# _loose_eq
# ---------------------------------------------------------------------------

def test_loose_eq_int_vs_string() -> None:
    assert _loose_eq(42, "42") is True


def test_loose_eq_float_vs_string() -> None:
    assert _loose_eq(3.14, "3.14") is True


def test_loose_eq_bool_true() -> None:
    assert _loose_eq(True, "true") is True
    assert _loose_eq(True, "1") is True


def test_loose_eq_bool_false() -> None:
    assert _loose_eq(False, "false") is True
    assert _loose_eq(False, "0") is True


def test_loose_eq_none() -> None:
    assert _loose_eq(None, "null") is True
    assert _loose_eq(None, "none") is True
    assert _loose_eq(None, "") is True


def test_loose_eq_string_match() -> None:
    assert _loose_eq("hello", "hello") is True


def test_loose_eq_mismatch() -> None:
    assert _loose_eq("hello", "world") is False


# ---------------------------------------------------------------------------
# evaluate_all
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# performance_budget assertions
# ---------------------------------------------------------------------------

def test_performance_budget_time_pass() -> None:
    r = evaluate(
        Assertion(type="performance_budget", expected="time<500"),
        _resp(elapsed_ms=200),
    )
    assert r.passed is True
    assert "Budget met" in r.message


def test_performance_budget_time_fail() -> None:
    r = evaluate(
        Assertion(type="performance_budget", expected="time<100"),
        _resp(elapsed_ms=200),
    )
    assert r.passed is False
    assert "Budget exceeded" in r.message


def test_performance_budget_size_pass() -> None:
    r = evaluate(
        Assertion(type="performance_budget", expected="size<10240"),
        _resp(body="small body"),
    )
    assert r.passed is True


def test_performance_budget_size_fail() -> None:
    big_body = "x" * 20000
    r = evaluate(
        Assertion(type="performance_budget", expected="size<10240"),
        _resp(body=big_body),
    )
    assert r.passed is False


def test_performance_budget_combined() -> None:
    r = evaluate(
        Assertion(type="performance_budget", expected="time<500,size<10240"),
        _resp(elapsed_ms=100, body="ok"),
    )
    assert r.passed is True


def test_performance_budget_empty() -> None:
    r = evaluate(
        Assertion(type="performance_budget", expected=""),
        _resp(),
    )
    assert r.passed is False


# ---------------------------------------------------------------------------
# evaluate_all
# ---------------------------------------------------------------------------

def test_evaluate_all_mixed() -> None:
    assertions = [
        Assertion(type="status", expected="200"),
        Assertion(type="status", expected="404"),
    ]
    results = evaluate_all(assertions, _resp(status=200))
    assert len(results) == 2
    assert results[0].passed is True
    assert results[1].passed is False
