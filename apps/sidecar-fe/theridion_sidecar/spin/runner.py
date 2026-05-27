"""Spin scenario runner — orchestrates step execution with variable substitution."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

from .models import (
    AssertionResult,
    DbExpectChangesAction,
    DbSnapshotAction,
    KafkaConsumeAssertStep,
    KafkaProduceStep,
    SpinRunResult,
    SpinScenario,
    SpinStep,
    StepResult,
)


# ── Variable substitution ────────────────────────────────────────────────────

_VAR_PATTERN = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


def substitute(value: Any, variables: dict[str, Any]) -> Any:
    """Recursively replace {{var}} placeholders in strings and nested structures."""
    if isinstance(value, str):
        def _replace(m: re.Match[str]) -> str:
            key = m.group(1)
            resolved = variables.get(key, m.group(0))
            return str(resolved)
        return _VAR_PATTERN.sub(_replace, value)
    if isinstance(value, dict):
        return {k: substitute(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute(item, variables) for item in value]
    return value


# ── JSON path extraction ─────────────────────────────────────────────────────

def _extract_jsonpath(body: Any, path: str) -> Any:
    """Very simple jsonpath-like extraction: $.field or $.a.b.c or $.a[0].b."""
    try:
        from jsonpath_ng import parse as _jp_parse  # type: ignore[import-untyped]
        matches = _jp_parse(path).find(body)
        if matches:
            return matches[0].value
    except Exception:
        pass
    return None


# ── Assertion evaluation ─────────────────────────────────────────────────────

def _evaluate_assertions(
    assert_obj: Any,
    response_status: int | None,
    response_body: Any,
    response_headers: dict[str, str],
    duration_ms: float,
    variables: dict[str, Any],
) -> list[AssertionResult]:
    if assert_obj is None:
        return []
    results: list[AssertionResult] = []

    if assert_obj.status is not None:
        ok = response_status == assert_obj.status
        results.append(AssertionResult(
            name="status",
            passed=ok,
            expected=assert_obj.status,
            actual=response_status,
        ))

    if assert_obj.status_in:
        ok = response_status in assert_obj.status_in
        results.append(AssertionResult(
            name="status_in",
            passed=ok,
            expected=assert_obj.status_in,
            actual=response_status,
        ))

    if assert_obj.response_time_lt is not None:
        ok = duration_ms < assert_obj.response_time_lt
        results.append(AssertionResult(
            name="response_time_lt",
            passed=ok,
            expected=f"< {assert_obj.response_time_lt} ms",
            actual=f"{duration_ms:.1f} ms",
        ))

    for path, expected in (assert_obj.json_path or {}).items():
        actual = _extract_jsonpath(response_body, path)
        expected_sub = substitute(expected, variables)
        ok = actual == expected_sub
        results.append(AssertionResult(
            name=f"json_path:{path}",
            passed=ok,
            expected=expected_sub,
            actual=actual,
        ))

    for header_name in (assert_obj.header_exists or []):
        ok = header_name.lower() in {k.lower() for k in response_headers}
        results.append(AssertionResult(
            name=f"header_exists:{header_name}",
            passed=ok,
            expected="present",
            actual="present" if ok else "missing",
        ))

    for header_name, expected_val in (assert_obj.header_equals or {}).items():
        actual_val = next(
            (v for k, v in response_headers.items() if k.lower() == header_name.lower()),
            None,
        )
        expected_sub = substitute(expected_val, variables)
        ok = actual_val == expected_sub
        results.append(AssertionResult(
            name=f"header_equals:{header_name}",
            passed=ok,
            expected=expected_sub,
            actual=actual_val,
        ))

    if assert_obj.body_contains is not None:
        needle = substitute(assert_obj.body_contains, variables)
        body_str = str(response_body) if not isinstance(response_body, str) else response_body
        ok = needle in body_str
        results.append(AssertionResult(
            name="body_contains",
            passed=ok,
            expected=needle,
            actual=f"body ({len(body_str)} chars)",
        ))

    if assert_obj.body_regex is not None:
        pattern = substitute(assert_obj.body_regex, variables)
        body_str = str(response_body) if not isinstance(response_body, str) else response_body
        ok = bool(re.search(pattern, body_str))
        results.append(AssertionResult(
            name="body_regex",
            passed=ok,
            expected=f"/{pattern}/",
            actual="matches" if ok else "no match",
        ))

    return results


# ── Step executors ───────────────────────────────────────────────────────────

async def _execute_http_step(
    step: SpinStep,
    variables: dict[str, Any],
) -> StepResult:
    req = step.http_request
    assert req is not None
    url = substitute(req.url, variables)
    headers = {k: substitute(v, variables) for k, v in req.headers.items()}
    body = substitute(req.body, variables)

    t0 = time.monotonic()
    response_status = None
    response_body: Any = None
    response_headers: dict[str, str] = {}
    captured_vars: dict[str, Any] = {}
    error: str | None = None

    try:
        async with httpx.AsyncClient(timeout=req.timeout_seconds) as client:
            kwargs: dict[str, Any] = {"headers": headers}
            if body is not None:
                if isinstance(body, (dict, list)):
                    kwargs["json"] = body
                else:
                    kwargs["content"] = str(body).encode()
            resp = await client.request(req.method, url, **kwargs)
            duration_ms = (time.monotonic() - t0) * 1000
            response_status = resp.status_code
            response_headers = dict(resp.headers)
            try:
                response_body = resp.json()
            except Exception:
                response_body = resp.text

        # Capture variables via JSONPath
        for var_name, path in (req.capture or {}).items():
            val = _extract_jsonpath(response_body, path)
            if val is not None:
                captured_vars[var_name] = val
                variables[var_name] = val

    except Exception as exc:
        duration_ms = (time.monotonic() - t0) * 1000
        error = str(exc)

    assertions = _evaluate_assertions(
        step.assert_,
        response_status,
        response_body,
        response_headers,
        duration_ms,
        variables,
    )
    all_passed = all(a.passed for a in assertions)
    status = "error" if error else ("passed" if all_passed else "failed")

    body_snippet: str | None = None
    if response_body is not None:
        body_str = str(response_body)
        body_snippet = body_str[:200] + ("..." if len(body_str) > 200 else "")

    return StepResult(
        step_name=step.name,
        step_type="http_request",
        status=status,
        duration_ms=duration_ms,
        assertions=assertions,
        captured_vars=captured_vars,
        error=error,
        response_status=response_status,
        response_body_snippet=body_snippet,
    )


async def _execute_sql_assert_step(
    step: SpinStep,
    variables: dict[str, Any],
) -> StepResult:
    from ..api.jdbc_query import _run_sqlite, _run_postgres

    sql = step.sql_assert
    assert sql is not None

    conn_str = substitute(sql.connection_string, variables)
    query = substitute(sql.query, variables)
    params = [substitute(p, variables) for p in sql.params]

    t0 = time.monotonic()
    error: str | None = None
    assertions: list[AssertionResult] = []

    try:
        cs_lower = conn_str.lower()
        if "sqlite" in cs_lower or cs_lower.endswith(".db"):
            result = _run_sqlite(conn_str, query, params, max_rows=10)
        else:
            result = _run_postgres(conn_str, query, params, max_rows=10)

        if result.error:
            error = result.error
        elif result.rows:
            row = result.rows[0]
            row_dict = dict(zip(result.columns, row))
            for col, expected_val in (sql.expect or {}).items():
                expected_sub = substitute(expected_val, variables)
                actual_val = row_dict.get(col)
                # Coerce types for comparison
                try:
                    if isinstance(expected_sub, str) and actual_val is not None:
                        if str(actual_val) == expected_sub:
                            actual_val = expected_sub
                except Exception:
                    pass
                ok = actual_val == expected_sub or str(actual_val) == str(expected_sub)
                assertions.append(AssertionResult(
                    name=f"sql:{col}",
                    passed=ok,
                    expected=expected_sub,
                    actual=actual_val,
                ))
        else:
            error = "Query returned no rows"

    except Exception as exc:
        error = str(exc)

    duration_ms = (time.monotonic() - t0) * 1000
    all_passed = all(a.passed for a in assertions)
    status = "error" if error else ("passed" if all_passed else "failed")
    return StepResult(
        step_name=step.name,
        step_type="sql_assert",
        status=status,
        duration_ms=duration_ms,
        assertions=assertions,
        error=error,
    )


async def _execute_kafka_produce_step(
    step: SpinStep,
    variables: dict[str, Any],
) -> StepResult:
    """Produce a Kafka message using the existing kafka module."""
    from ..api.kafka import ProduceInput, _produce_message

    kp: KafkaProduceStep = step.kafka_produce  # type: ignore[assignment]
    t0 = time.monotonic()
    error: str | None = None

    try:
        inp = ProduceInput(
            bootstrap_servers=substitute(kp.bootstrap_servers, variables),
            topic=substitute(kp.topic, variables),
            key=substitute(kp.key, variables) if kp.key else None,
            value=str(substitute(kp.value, variables)),
            headers={k: substitute(v, variables) for k, v in kp.headers.items()},
        )
        await _produce_message(inp)
    except Exception as exc:
        error = str(exc)

    duration_ms = (time.monotonic() - t0) * 1000
    return StepResult(
        step_name=step.name,
        step_type="kafka_produce",
        status="error" if error else "passed",
        duration_ms=duration_ms,
        error=error,
    )


async def _execute_kafka_consume_assert_step(
    step: SpinStep,
    variables: dict[str, Any],
) -> StepResult:
    """Consume messages and assert payload contains expected fields."""
    import asyncio
    import json

    from aiokafka import AIOKafkaConsumer

    kc: KafkaConsumeAssertStep = step.kafka_consume_assert  # type: ignore[assignment]
    t0 = time.monotonic()
    error: str | None = None
    assertions: list[AssertionResult] = []
    captured_vars: dict[str, Any] = {}

    try:
        consumer = AIOKafkaConsumer(
            substitute(kc.topic, variables),
            bootstrap_servers=substitute(kc.bootstrap_servers, variables),
            auto_offset_reset="earliest",
            consumer_timeout_ms=int(kc.timeout_seconds * 1000),
        )
        await consumer.start()
        try:
            matched_payload: Any = None
            count = 0
            async for msg in consumer:
                count += 1
                try:
                    payload = json.loads(msg.value.decode("utf-8"))
                except Exception:
                    payload = msg.value.decode("utf-8", errors="replace")

                # Check if all expected keys match
                expected_sub = {
                    k: substitute(v, variables) for k, v in kc.payload_contains.items()
                }
                if all(
                    str(payload.get(k) if isinstance(payload, dict) else "") == str(v)
                    for k, v in expected_sub.items()
                ):
                    matched_payload = payload
                    # Capture variables from message
                    for var_name, path in (kc.capture or {}).items():
                        val = _extract_jsonpath(payload, path)
                        if val is not None:
                            captured_vars[var_name] = val
                            variables[var_name] = val
                    break
                if count >= kc.max_messages:
                    break
        finally:
            await consumer.stop()

        for k, v in (kc.payload_contains or {}).items():
            expected_sub = substitute(v, variables)
            actual = matched_payload.get(k) if isinstance(matched_payload, dict) else None
            ok = matched_payload is not None and str(actual) == str(expected_sub)
            assertions.append(AssertionResult(
                name=f"kafka_payload:{k}",
                passed=ok,
                expected=expected_sub,
                actual=actual,
            ))

    except Exception as exc:
        error = str(exc)

    duration_ms = (time.monotonic() - t0) * 1000
    all_passed = all(a.passed for a in assertions)
    status = "error" if error else ("passed" if all_passed else "failed")
    return StepResult(
        step_name=step.name,
        step_type="kafka_consume_assert",
        status=status,
        duration_ms=duration_ms,
        assertions=assertions,
        captured_vars=captured_vars,
        error=error,
    )


async def _execute_wait_step(step: SpinStep, _variables: dict[str, Any]) -> StepResult:
    import asyncio

    secs = step.wait_seconds or 1.0
    t0 = time.monotonic()
    await asyncio.sleep(secs)
    return StepResult(
        step_name=step.name,
        step_type="wait_seconds",
        status="passed",
        duration_ms=(time.monotonic() - t0) * 1000,
    )


async def _execute_step(step: SpinStep, variables: dict[str, Any]) -> StepResult:
    if step.http_request is not None:
        return await _execute_http_step(step, variables)
    if step.sql_assert is not None:
        return await _execute_sql_assert_step(step, variables)
    if step.kafka_produce is not None:
        return await _execute_kafka_produce_step(step, variables)
    if step.kafka_consume_assert is not None:
        return await _execute_kafka_consume_assert_step(step, variables)
    if step.wait_seconds is not None:
        return await _execute_wait_step(step, variables)
    return StepResult(
        step_name=step.name,
        step_type="unknown",
        status="error",
        error="No executable step type found",
    )


# ── Setup / Teardown ─────────────────────────────────────────────────────────

def _run_setup_action(action_dict: dict[str, Any], variables: dict[str, Any]) -> StepResult:
    """Execute a setup action (synchronous DB snapshot)."""
    if "db.snapshot" in action_dict:
        from .database import take_snapshot

        cfg = DbSnapshotAction(**action_dict["db.snapshot"])
        try:
            result = take_snapshot(
                substitute(cfg.connection_string, variables),
                substitute(cfg.table, variables),
            )
            variables[f"__snapshot_{cfg.table}"] = result
            return StepResult(
                step_name=f"setup:db.snapshot:{cfg.table}",
                step_type="db.snapshot",
                status="passed",
                captured_vars={f"__snapshot_{cfg.table}": result},
            )
        except Exception as exc:
            return StepResult(
                step_name=f"setup:db.snapshot:{cfg.table}",
                step_type="db.snapshot",
                status="error",
                error=str(exc),
            )
    return StepResult(
        step_name="setup:unknown",
        step_type="unknown",
        status="error",
        error=f"Unknown setup action: {list(action_dict.keys())}",
    )


def _run_teardown_action(action_dict: dict[str, Any], variables: dict[str, Any]) -> StepResult:
    """Execute a teardown action (DB expect_changes assertion)."""
    if "db.expect_changes" in action_dict:
        from .database import compare_snapshot

        cfg = DbExpectChangesAction(**action_dict["db.expect_changes"])
        snapshot_key = f"__snapshot_{cfg.table}"
        snapshot_before = variables.get(snapshot_key)
        try:
            ok, actual_delta = compare_snapshot(
                substitute(cfg.connection_string, variables),
                substitute(cfg.table, variables),
                snapshot_before,
                cfg.delta,
            )
            assertions = [AssertionResult(
                name=f"db.expect_changes:{cfg.table}",
                passed=ok,
                expected=cfg.delta,
                actual=actual_delta,
            )]
            return StepResult(
                step_name=f"teardown:db.expect_changes:{cfg.table}",
                step_type="db.expect_changes",
                status="passed" if ok else "failed",
                assertions=assertions,
            )
        except Exception as exc:
            return StepResult(
                step_name=f"teardown:db.expect_changes:{cfg.table}",
                step_type="db.expect_changes",
                status="error",
                error=str(exc),
            )
    return StepResult(
        step_name="teardown:unknown",
        step_type="unknown",
        status="error",
        error=f"Unknown teardown action: {list(action_dict.keys())}",
    )


# ── Public API ───────────────────────────────────────────────────────────────

def load_scenario(path: str | Path) -> SpinScenario:
    """Load and parse a .spin.yaml file into a SpinScenario."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Scenario file not found: {path}")
    with open(p, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return SpinScenario.model_validate(data)


async def run_scenario(
    scenario: SpinScenario,
    env_vars: dict[str, Any] | None = None,
) -> SpinRunResult:
    """Execute a Spin scenario end-to-end and return structured results."""
    t0 = time.monotonic()
    variables: dict[str, Any] = {}
    variables.update(scenario.variables)
    if env_vars:
        variables.update(env_vars)

    setup_results: list[StepResult] = []
    teardown_results: list[StepResult] = []
    step_results: list[StepResult] = []
    overall_error: str | None = None

    # Setup phase
    for action in scenario.setup:
        r = _run_setup_action(action, variables)
        setup_results.append(r)
        if r.status == "error":
            overall_error = f"Setup failed: {r.error}"
            break

    # Main steps
    if not overall_error:
        for step in scenario.steps:
            try:
                r = await _execute_step(step, variables)
            except Exception as exc:
                r = StepResult(
                    step_name=step.name,
                    step_type="unknown",
                    status="error",
                    error=str(exc),
                )
            step_results.append(r)
            # Merge captured vars back into global variables
            variables.update(r.captured_vars)

    # Teardown always runs
    for action in scenario.teardown:
        r = _run_teardown_action(action, variables)
        teardown_results.append(r)

    total_duration = (time.monotonic() - t0) * 1000
    passed = sum(1 for r in step_results if r.status == "passed")
    failed = sum(1 for r in step_results if r.status in ("failed", "error"))

    all_ok = (
        failed == 0
        and all(r.status == "passed" for r in setup_results + teardown_results if r.status != "skipped")
        and overall_error is None
    )

    return SpinRunResult(
        scenario_name=scenario.name,
        status="passed" if all_ok else ("error" if overall_error else "failed"),
        total_steps=len(step_results),
        passed_steps=passed,
        failed_steps=failed,
        duration_ms=total_duration,
        steps=step_results,
        setup_results=setup_results,
        teardown_results=teardown_results,
        error=overall_error,
    )
