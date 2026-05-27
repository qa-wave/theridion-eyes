"""Tests for Spin scenario runner — orchestration and variable substitution."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from theridion_sidecar.spin.models import (
    HttpRequestStep,
    SpinRunResult,
    SpinScenario,
    SpinStep,
    StepAssert,
    StepResult,
)
from theridion_sidecar.spin.runner import (
    _evaluate_assertions,
    _extract_jsonpath,
    run_scenario,
    substitute,
)


# ── Variable substitution ─────────────────────────────────────────────────────

def test_substitute_simple_string():
    assert substitute("Hello {{name}}!", {"name": "World"}) == "Hello World!"


def test_substitute_nested_dict():
    result = substitute({"url": "{{base}}/{{path}}"}, {"base": "https://api.io", "path": "users"})
    assert result == {"url": "https://api.io/users"}


def test_substitute_list():
    result = substitute(["{{a}}", "{{b}}"], {"a": "x", "b": "y"})
    assert result == ["x", "y"]


def test_substitute_missing_var_keeps_placeholder():
    result = substitute("{{missing}}", {})
    assert result == "{{missing}}"


def test_substitute_non_string_passthrough():
    assert substitute(42, {}) == 42
    assert substitute(None, {}) is None


def test_substitute_numeric_value():
    # Variable value is numeric — should be coerced to string in result
    result = substitute("order_id={{order_id}}", {"order_id": 12345})
    assert result == "order_id=12345"


# ── JSONPath extraction ───────────────────────────────────────────────────────

def test_extract_jsonpath_simple():
    body = {"id": 42, "name": "test"}
    assert _extract_jsonpath(body, "$.id") == 42


def test_extract_jsonpath_nested():
    body = {"order": {"id": "ABC"}}
    assert _extract_jsonpath(body, "$.order.id") == "ABC"


def test_extract_jsonpath_missing():
    body = {"id": 1}
    assert _extract_jsonpath(body, "$.nonexistent") is None


# ── Assertion evaluation ──────────────────────────────────────────────────────

def test_evaluate_status_assertion_pass():
    from theridion_sidecar.spin.models import StepAssert
    assert_obj = StepAssert(status=200)
    results = _evaluate_assertions(assert_obj, 200, {}, {}, 50.0, {})
    assert len(results) == 1
    assert results[0].passed is True


def test_evaluate_status_assertion_fail():
    assert_obj = StepAssert(status=201)
    results = _evaluate_assertions(assert_obj, 200, {}, {}, 50.0, {})
    assert results[0].passed is False
    assert results[0].actual == 200


def test_evaluate_response_time_pass():
    assert_obj = StepAssert(response_time_lt=1000.0)
    results = _evaluate_assertions(assert_obj, 200, {}, {}, 200.0, {})
    assert any(r.name == "response_time_lt" and r.passed for r in results)


def test_evaluate_response_time_fail():
    assert_obj = StepAssert(response_time_lt=100.0)
    results = _evaluate_assertions(assert_obj, 200, {}, {}, 500.0, {})
    assert any(r.name == "response_time_lt" and not r.passed for r in results)


def test_evaluate_json_path_assertion():
    assert_obj = StepAssert(**{"json_path": {"$.status": "active"}})
    body = {"status": "active"}
    results = _evaluate_assertions(assert_obj, 200, body, {}, 50.0, {})
    assert any(r.passed for r in results if "json_path" in r.name)


def test_evaluate_body_contains():
    assert_obj = StepAssert(body_contains="order_id")
    results = _evaluate_assertions(assert_obj, 200, {"order_id": 1}, {}, 50.0, {})
    assert any(r.name == "body_contains" and r.passed for r in results)


def test_evaluate_header_exists():
    assert_obj = StepAssert(header_exists=["content-type"])
    results = _evaluate_assertions(assert_obj, 200, {}, {"content-type": "application/json"}, 50.0, {})
    assert any(r.name == "header_exists:content-type" and r.passed for r in results)


def test_evaluate_header_equals():
    assert_obj = StepAssert(**{"header_equals": {"content-type": "application/json"}})
    results = _evaluate_assertions(assert_obj, 200, {}, {"content-type": "application/json"}, 50.0, {})
    assert any("header_equals" in r.name and r.passed for r in results)


def test_evaluate_body_regex():
    assert_obj = StepAssert(body_regex=r"order_\d+")
    results = _evaluate_assertions(assert_obj, 200, "order_12345 created", {}, 50.0, {})
    assert any(r.name == "body_regex" and r.passed for r in results)


def test_evaluate_none_assert_returns_empty():
    results = _evaluate_assertions(None, 200, {}, {}, 50.0, {})
    assert results == []


# ── Scenario execution ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_scenario_http_pass(httpserver: Any = None):
    """Test a simple HTTP step against a mock server."""
    import respx
    import httpx

    scenario = SpinScenario(
        name="Test HTTP pass",
        steps=[
            SpinStep(
                name="Get users",
                http_request=HttpRequestStep(
                    method="GET",
                    url="http://test.local/users",
                    capture={"first_user": "$.users[0].name"},
                ),
                **{"assert": StepAssert(status=200)},
            )
        ],
    )

    with respx.mock:
        respx.get("http://test.local/users").mock(
            return_value=httpx.Response(200, json={"users": [{"name": "Alice"}]})
        )
        result = await run_scenario(scenario, env_vars={})

    assert result.status == "passed"
    assert result.passed_steps == 1
    assert result.failed_steps == 0


@pytest.mark.asyncio
async def test_run_scenario_http_fail_status():
    import respx
    import httpx

    scenario = SpinScenario(
        name="HTTP fail test",
        steps=[
            SpinStep(
                name="Fail step",
                http_request=HttpRequestStep(
                    method="GET",
                    url="http://test.local/missing",
                ),
                **{"assert": StepAssert(status=200)},
            )
        ],
    )

    with respx.mock:
        respx.get("http://test.local/missing").mock(
            return_value=httpx.Response(404, json={"error": "not found"})
        )
        result = await run_scenario(scenario, env_vars={})

    assert result.status == "failed"
    assert result.failed_steps == 1


@pytest.mark.asyncio
async def test_run_scenario_variable_capture_and_reuse():
    """Capture {{order_id}} from step 1 and use in step 2 URL."""
    import respx
    import httpx

    scenario = SpinScenario(
        name="Variable chaining",
        steps=[
            SpinStep(
                name="Create order",
                http_request=HttpRequestStep(
                    method="POST",
                    url="http://test.local/orders",
                    capture={"order_id": "$.id"},
                ),
                **{"assert": StepAssert(status=201)},
            ),
            SpinStep(
                name="Get order",
                http_request=HttpRequestStep(
                    method="GET",
                    url="http://test.local/orders/{{order_id}}",
                ),
                **{"assert": StepAssert(status=200)},
            ),
        ],
    )

    with respx.mock:
        respx.post("http://test.local/orders").mock(
            return_value=httpx.Response(201, json={"id": "ABC-123"})
        )
        respx.get("http://test.local/orders/ABC-123").mock(
            return_value=httpx.Response(200, json={"id": "ABC-123", "status": "pending"})
        )
        result = await run_scenario(scenario, env_vars={})

    assert result.status == "passed"
    assert result.passed_steps == 2


@pytest.mark.asyncio
async def test_run_scenario_wait_step():
    scenario = SpinScenario(
        name="Wait test",
        steps=[
            SpinStep(name="Short wait", wait_seconds=0.01),
        ],
    )
    result = await run_scenario(scenario)
    assert result.status == "passed"
    assert result.steps[0].step_type == "wait_seconds"


@pytest.mark.asyncio
async def test_run_scenario_no_steps():
    scenario = SpinScenario(name="Empty", steps=[])
    result = await run_scenario(scenario)
    assert result.total_steps == 0
    assert result.status == "passed"
