"""Pydantic models for .spin.yaml scenario format."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ── Step definitions ──────────────────────────────────────────────────────────

class HttpRequestStep(BaseModel):
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"] = "GET"
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None
    timeout_seconds: int = 30
    capture: dict[str, str] = Field(default_factory=dict)  # var_name -> jsonpath


class SqlQueryStep(BaseModel):
    connection_string: str
    query: str
    params: list[Any] = Field(default_factory=list)
    capture: dict[str, str] = Field(default_factory=dict)  # var_name -> column_name


class SqlAssertStep(BaseModel):
    connection_string: str
    query: str
    params: list[Any] = Field(default_factory=list)
    expect: dict[str, Any] = Field(default_factory=dict)


class KafkaProduceStep(BaseModel):
    bootstrap_servers: str
    topic: str
    key: str | None = None
    value: Any = None
    headers: dict[str, str] = Field(default_factory=dict)


class KafkaConsumeAssertStep(BaseModel):
    bootstrap_servers: str
    topic: str
    timeout_seconds: int = 10
    max_messages: int = 10
    payload_contains: dict[str, Any] = Field(default_factory=dict)
    capture: dict[str, str] = Field(default_factory=dict)


class MqttPublishStep(BaseModel):
    broker_url: str
    topic: str
    payload: Any = None
    qos: int = 0


class MqttSubscribeAssertStep(BaseModel):
    broker_url: str
    topic: str
    timeout_seconds: int = 10
    payload_contains: dict[str, Any] = Field(default_factory=dict)


class WaitStep(BaseModel):
    seconds: float = 1.0


# ── Assertions ────────────────────────────────────────────────────────────────

class StepAssert(BaseModel):
    status: int | None = None
    status_in: list[int] = Field(default_factory=list)
    response_time_lt: float | None = None  # ms
    json_path: dict[str, Any] = Field(default_factory=dict)  # path -> expected_value
    header_exists: list[str] = Field(default_factory=list)
    header_equals: dict[str, str] = Field(default_factory=dict)
    body_contains: str | None = None
    body_regex: str | None = None
    schema_ref: str | None = Field(default=None, alias="schema")  # "openapi://operationId" or "asyncapi://channelName"

    model_config = {"populate_by_name": True}


# ── Scenario Step (discriminated union) ───────────────────────────────────────

class SpinStep(BaseModel):
    name: str
    # Exactly one of these should be set
    http_request: HttpRequestStep | None = None
    sql_query: SqlQueryStep | None = None
    sql_assert: SqlAssertStep | None = None
    kafka_produce: KafkaProduceStep | None = None
    kafka_consume_assert: KafkaConsumeAssertStep | None = None
    mqtt_publish: MqttPublishStep | None = None
    mqtt_subscribe_assert: MqttSubscribeAssertStep | None = None
    wait_seconds: float | None = None
    assert_: StepAssert | None = Field(default=None, alias="assert")

    model_config = {"populate_by_name": True}


# ── Setup / Teardown actions ──────────────────────────────────────────────────

class DbSnapshotAction(BaseModel):
    connection_string: str
    table: str


class DbExpectChangesAction(BaseModel):
    connection_string: str
    table: str
    delta: int  # e.g. +1 or -1


class SetupTeardownAction(BaseModel):
    db_snapshot: DbSnapshotAction | None = Field(default=None, alias="db.snapshot")
    db_expect_changes: DbExpectChangesAction | None = Field(default=None, alias="db.expect_changes")

    model_config = {"populate_by_name": True}


# ── Full Scenario ─────────────────────────────────────────────────────────────

class SpinScenario(BaseModel):
    name: str = ""
    environment: str | None = None
    setup: list[dict[str, Any]] = Field(default_factory=list)
    steps: list[SpinStep] = Field(default_factory=list)
    teardown: list[dict[str, Any]] = Field(default_factory=list)
    variables: dict[str, Any] = Field(default_factory=dict)  # scenario-level defaults


# ── Results ───────────────────────────────────────────────────────────────────

class AssertionResult(BaseModel):
    name: str
    passed: bool
    expected: Any = None
    actual: Any = None
    error: str | None = None


class StepResult(BaseModel):
    step_name: str
    step_type: str
    status: Literal["passed", "failed", "skipped", "error"]
    duration_ms: float = 0.0
    assertions: list[AssertionResult] = Field(default_factory=list)
    captured_vars: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    response_status: int | None = None
    response_body_snippet: str | None = None


class SpinRunResult(BaseModel):
    scenario_name: str
    status: Literal["passed", "failed", "error"]
    total_steps: int
    passed_steps: int
    failed_steps: int
    duration_ms: float
    steps: list[StepResult] = Field(default_factory=list)
    setup_results: list[StepResult] = Field(default_factory=list)
    teardown_results: list[StepResult] = Field(default_factory=list)
    error: str | None = None


# ── Contract models ───────────────────────────────────────────────────────────

class PactInteractionRequest(BaseModel):
    method: str = "GET"
    path: str = "/"
    query: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None


class PactInteractionResponse(BaseModel):
    status: int = 200
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None


class PactInteraction(BaseModel):
    description: str
    provider_state: str | None = None
    request: PactInteractionRequest
    response: PactInteractionResponse


class PactContract(BaseModel):
    consumer: dict[str, str]  # {"name": "ConsumerName"}
    provider: dict[str, str]  # {"name": "ProviderName"}
    interactions: list[PactInteraction] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContractVerifyResult(BaseModel):
    contract_file: str
    provider_url: str
    total_interactions: int
    passed: int
    failed: int
    results: list[dict[str, Any]] = Field(default_factory=list)
    status: Literal["passed", "failed", "error"]
    error: str | None = None
