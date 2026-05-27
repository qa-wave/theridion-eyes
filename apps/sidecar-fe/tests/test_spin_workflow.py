"""Tests for Spin workflow YAML parsing and dry-run validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from theridion_sidecar.spin.workflow import (
    WorkflowValidationError,
    list_scenario_files,
    load_workflow_file,
    parse_workflow_yaml,
    validate_workflow,
    workflow_to_yaml,
)
from theridion_sidecar.spin.models import SpinScenario, SpinStep, HttpRequestStep


# ── parse_workflow_yaml ───────────────────────────────────────────────────────

def test_parse_minimal_yaml():
    yaml_str = """
name: Simple workflow
steps:
  - name: Health check
    http_request:
      method: GET
      url: https://api.example.com/health
    assert:
      status: 200
"""
    scenario = parse_workflow_yaml(yaml_str)
    assert scenario.name == "Simple workflow"
    assert len(scenario.steps) == 1
    assert scenario.steps[0].http_request is not None


def test_parse_yaml_with_variables():
    yaml_str = """
name: Vars test
variables:
  api_url: https://api.example.com
steps:
  - name: Get users
    http_request:
      url: "{{api_url}}/users"
      method: GET
"""
    scenario = parse_workflow_yaml(yaml_str)
    assert scenario.variables["api_url"] == "https://api.example.com"
    assert "{{api_url}}" in scenario.steps[0].http_request.url  # type: ignore[union-attr]


def test_parse_yaml_with_setup_teardown():
    yaml_str = """
name: DB test
setup:
  - db.snapshot:
      connection_string: sqlite:///test.db
      table: orders
steps:
  - name: Create order
    http_request:
      method: POST
      url: https://api.example.com/orders
teardown:
  - db.expect_changes:
      connection_string: sqlite:///test.db
      table: orders
      delta: 1
"""
    scenario = parse_workflow_yaml(yaml_str)
    assert len(scenario.setup) == 1
    assert len(scenario.teardown) == 1
    assert "db.snapshot" in scenario.setup[0]


def test_parse_yaml_with_wait_step():
    yaml_str = """
name: Wait test
steps:
  - name: Wait 0.5s
    wait_seconds: 0.5
"""
    scenario = parse_workflow_yaml(yaml_str)
    assert scenario.steps[0].wait_seconds == 0.5


def test_parse_invalid_yaml_raises():
    with pytest.raises(WorkflowValidationError):
        parse_workflow_yaml("{ invalid: yaml: :")


def test_parse_non_dict_yaml_raises():
    with pytest.raises(WorkflowValidationError):
        parse_workflow_yaml("- just a list")


def test_parse_yaml_missing_required_name():
    yaml_str = """
steps:
  - name: step1
    wait_seconds: 1
"""
    # Should still parse (name defaults to ""), validation catches it
    scenario = parse_workflow_yaml(yaml_str)
    assert scenario.name == ""
    errors = validate_workflow(scenario)
    assert any("name" in e for e in errors)


# ── validate_workflow ─────────────────────────────────────────────────────────

def test_validate_valid_scenario():
    scenario = SpinScenario(
        name="Valid",
        steps=[
            SpinStep(
                name="Step 1",
                http_request=HttpRequestStep(
                    method="GET",
                    url="https://api.example.com/users",
                ),
            )
        ],
    )
    errors = validate_workflow(scenario)
    assert errors == []


def test_validate_no_steps():
    scenario = SpinScenario(name="No steps", steps=[])
    errors = validate_workflow(scenario)
    assert any("step" in e.lower() for e in errors)


def test_validate_step_no_type():
    scenario = SpinScenario(
        name="Bad step",
        steps=[SpinStep(name="Empty step")],
    )
    errors = validate_workflow(scenario)
    assert any("no step type" in e for e in errors)


def test_validate_http_missing_url():
    scenario = SpinScenario(
        name="Missing URL",
        steps=[
            SpinStep(
                name="Step",
                http_request=HttpRequestStep(method="GET", url=""),
            )
        ],
    )
    errors = validate_workflow(scenario)
    assert any("url" in e for e in errors)


def test_validate_capture_bad_jsonpath():
    scenario = SpinScenario(
        name="Bad capture",
        steps=[
            SpinStep(
                name="Step",
                http_request=HttpRequestStep(
                    method="GET",
                    url="https://example.com",
                    capture={"var": "not_a_jsonpath"},
                ),
            )
        ],
    )
    errors = validate_workflow(scenario)
    assert any("JSONPath" in e for e in errors)


def test_validate_sql_assert_missing_fields():
    from theridion_sidecar.spin.models import SqlAssertStep
    scenario = SpinScenario(
        name="Bad SQL",
        steps=[
            SpinStep(
                name="SQL check",
                sql_assert=SqlAssertStep(
                    connection_string="",
                    query="SELECT 1",
                ),
            )
        ],
    )
    errors = validate_workflow(scenario)
    assert any("connection_string" in e for e in errors)


# ── workflow_to_yaml ──────────────────────────────────────────────────────────

def test_workflow_roundtrip():
    yaml_str = """
name: Roundtrip test
steps:
  - name: Health check
    http_request:
      method: GET
      url: https://api.example.com/health
"""
    scenario = parse_workflow_yaml(yaml_str)
    exported = workflow_to_yaml(scenario)
    reparsed = parse_workflow_yaml(exported)
    assert reparsed.name == scenario.name
    assert len(reparsed.steps) == len(scenario.steps)


# ── list_scenario_files ───────────────────────────────────────────────────────

def test_list_scenario_files_empty(tmp_path: Path):
    results = list_scenario_files(tmp_path)
    assert results == []


def test_list_scenario_files_finds_spin_yaml(tmp_path: Path):
    spin_file = tmp_path / "order.spin.yaml"
    spin_file.write_text("""
name: Order flow
steps:
  - name: Create
    http_request:
      method: POST
      url: https://api.example.com/orders
""", encoding="utf-8")

    results = list_scenario_files(tmp_path)
    assert len(results) == 1
    assert results[0]["name"] == "Order flow"
    assert results[0]["valid"] is True
    assert results[0]["step_count"] == 1


def test_list_scenario_files_reports_invalid(tmp_path: Path):
    spin_file = tmp_path / "broken.spin.yaml"
    spin_file.write_text("{ bad yaml: :", encoding="utf-8")

    results = list_scenario_files(tmp_path)
    assert len(results) == 1
    assert results[0]["valid"] is False
    assert results[0]["errors"]


def test_list_scenario_files_nested(tmp_path: Path):
    sub = tmp_path / "suite1"
    sub.mkdir()
    (sub / "test.spin.yaml").write_text("""
name: Nested
steps:
  - name: Get
    http_request:
      method: GET
      url: https://example.com
""", encoding="utf-8")

    results = list_scenario_files(tmp_path)
    assert len(results) == 1
    assert "suite1" in results[0]["relative_path"]


# ── load_workflow_file ────────────────────────────────────────────────────────

def test_load_workflow_file_not_found():
    with pytest.raises(FileNotFoundError):
        load_workflow_file("/nonexistent/scenario.spin.yaml")


def test_load_workflow_file_success(tmp_path: Path):
    f = tmp_path / "scenario.spin.yaml"
    f.write_text("""
name: File load test
steps:
  - name: Step
    wait_seconds: 0.1
""", encoding="utf-8")
    scenario = load_workflow_file(f)
    assert scenario.name == "File load test"
