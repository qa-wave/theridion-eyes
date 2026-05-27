"""Spin workflow — YAML parsing and dry-run validation for multi-step scenarios."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import SpinScenario, SpinStep


# ── Validation ────────────────────────────────────────────────────────────────

VALID_STEP_TYPES = {
    "http_request",
    "sql_query",
    "sql_assert",
    "kafka_produce",
    "kafka_consume_assert",
    "mqtt_publish",
    "mqtt_subscribe_assert",
    "wait_seconds",
}


class WorkflowValidationError(Exception):
    pass


def _validate_step(step: SpinStep, idx: int) -> list[str]:
    """Return a list of validation error strings for a single step."""
    errors: list[str] = []
    name = step.name or f"step[{idx}]"

    # Ensure exactly one step type is configured
    configured = [
        t for t in VALID_STEP_TYPES
        if getattr(step, t, None) is not None
        or (t == "wait_seconds" and step.wait_seconds is not None)
    ]
    if len(configured) == 0:
        errors.append(f"{name}: no step type defined (must have one of: {', '.join(VALID_STEP_TYPES)})")
    if len(configured) > 1:
        errors.append(f"{name}: multiple step types defined: {configured}")

    # HTTP-specific
    if step.http_request:
        req = step.http_request
        if not req.url:
            errors.append(f"{name}.http_request: 'url' is required")
        if req.method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
            errors.append(f"{name}.http_request: invalid method '{req.method}'")
        for var, path in req.capture.items():
            if not path.startswith("$"):
                errors.append(f"{name}.http_request.capture.{var}: JSONPath must start with '$'")

    # SQL assert
    if step.sql_assert:
        if not step.sql_assert.connection_string:
            errors.append(f"{name}.sql_assert: 'connection_string' is required")
        if not step.sql_assert.query:
            errors.append(f"{name}.sql_assert: 'query' is required")

    # Kafka produce
    if step.kafka_produce:
        if not step.kafka_produce.bootstrap_servers:
            errors.append(f"{name}.kafka_produce: 'bootstrap_servers' is required")
        if not step.kafka_produce.topic:
            errors.append(f"{name}.kafka_produce: 'topic' is required")

    # Kafka consume assert
    if step.kafka_consume_assert:
        if not step.kafka_consume_assert.bootstrap_servers:
            errors.append(f"{name}.kafka_consume_assert: 'bootstrap_servers' is required")
        if not step.kafka_consume_assert.topic:
            errors.append(f"{name}.kafka_consume_assert: 'topic' is required")

    return errors


def validate_workflow(scenario: SpinScenario) -> list[str]:
    """Validate a SpinScenario structure without executing it.

    Returns a list of error strings. Empty list means the workflow is valid.
    """
    errors: list[str] = []

    if not scenario.name or not scenario.name.strip():
        errors.append("scenario: 'name' is required")

    if not scenario.steps:
        errors.append("scenario: at least one step is required")

    for idx, step in enumerate(scenario.steps):
        errors.extend(_validate_step(step, idx))

    return errors


def parse_workflow_yaml(content: str) -> SpinScenario:
    """Parse a .spin.yaml string into a SpinScenario model."""
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise WorkflowValidationError(f"YAML parse error: {exc}") from exc

    if not isinstance(data, dict):
        raise WorkflowValidationError("Workflow YAML must be a mapping at the top level")

    try:
        return SpinScenario.model_validate(data)
    except Exception as exc:
        raise WorkflowValidationError(f"Schema validation error: {exc}") from exc


def load_workflow_file(path: str | Path) -> SpinScenario:
    """Load a .spin.yaml file from disk."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Workflow file not found: {path}")
    return parse_workflow_yaml(p.read_text(encoding="utf-8"))


def workflow_to_yaml(scenario: SpinScenario) -> str:
    """Serialize a SpinScenario back to YAML string."""
    data = scenario.model_dump(exclude_none=True, by_alias=True)
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False, indent=2)


def list_scenario_files(workspace_dir: str | Path) -> list[dict[str, Any]]:
    """Return info about all .spin.yaml files found under workspace_dir."""
    root = Path(workspace_dir)
    results: list[dict[str, Any]] = []
    for p in sorted(root.rglob("*.spin.yaml")):
        try:
            scenario = load_workflow_file(p)
            errors = validate_workflow(scenario)
            results.append({
                "path": str(p),
                "relative_path": str(p.relative_to(root)),
                "name": scenario.name,
                "step_count": len(scenario.steps),
                "environment": scenario.environment,
                "valid": len(errors) == 0,
                "errors": errors,
            })
        except Exception as exc:
            results.append({
                "path": str(p),
                "relative_path": str(p.relative_to(root)),
                "name": None,
                "step_count": 0,
                "environment": None,
                "valid": False,
                "errors": [str(exc)],
            })
    return results
