/**
 * Spin — Automated backend testing module sidecar client.
 *
 * Wraps /api/spin/* endpoints.
 */

import { call } from "./client";

// ---- Types ----------------------------------------------------------------

export interface SpinStepAssert {
  status?: number;
  status_in?: number[];
  response_time_lt?: number;
  json_path?: Record<string, unknown>;
  header_exists?: string[];
  header_equals?: Record<string, string>;
  body_contains?: string;
  body_regex?: string;
  schema?: string;
}

export interface SpinHttpRequestStep {
  method: string;
  url: string;
  headers?: Record<string, string>;
  body?: unknown;
  timeout_seconds?: number;
  capture?: Record<string, string>;
}

export interface SpinSqlAssertStep {
  connection_string: string;
  query: string;
  params?: unknown[];
  expect?: Record<string, unknown>;
}

export interface SpinKafkaProduceStep {
  bootstrap_servers: string;
  topic: string;
  key?: string;
  value?: unknown;
  headers?: Record<string, string>;
}

export interface SpinKafkaConsumeAssertStep {
  bootstrap_servers: string;
  topic: string;
  timeout_seconds?: number;
  max_messages?: number;
  payload_contains?: Record<string, unknown>;
  capture?: Record<string, string>;
}

export interface SpinStep {
  name: string;
  http_request?: SpinHttpRequestStep;
  sql_assert?: SpinSqlAssertStep;
  kafka_produce?: SpinKafkaProduceStep;
  kafka_consume_assert?: SpinKafkaConsumeAssertStep;
  wait_seconds?: number;
  assert?: SpinStepAssert;
}

export interface SpinScenario {
  name: string;
  environment?: string;
  setup?: Record<string, unknown>[];
  steps: SpinStep[];
  teardown?: Record<string, unknown>[];
  variables?: Record<string, unknown>;
}

export interface SpinAssertionResult {
  name: string;
  passed: boolean;
  expected: unknown;
  actual: unknown;
  error?: string;
}

export interface SpinStepResult {
  step_name: string;
  step_type: string;
  status: "passed" | "failed" | "skipped" | "error";
  duration_ms: number;
  assertions: SpinAssertionResult[];
  captured_vars: Record<string, unknown>;
  error?: string;
  response_status?: number;
  response_body_snippet?: string;
}

export interface SpinRunResult {
  scenario_name: string;
  status: "passed" | "failed" | "error";
  total_steps: number;
  passed_steps: number;
  failed_steps: number;
  duration_ms: number;
  steps: SpinStepResult[];
  setup_results: SpinStepResult[];
  teardown_results: SpinStepResult[];
  error?: string;
}

export interface SpinScenarioInfo {
  path: string;
  relative_path: string;
  name: string | null;
  step_count: number;
  environment: string | null;
  valid: boolean;
  errors: string[];
}

export interface SpinScenarioListOutput {
  scenarios: SpinScenarioInfo[];
  workspace_dir: string;
}

export interface SpinDryRunOutput {
  valid: boolean;
  errors: string[];
  step_count: number;
  scenario_name: string | null;
}

export interface SpinContractVerifyInput {
  contract_path: string;
  provider_url: string;
  provider_state_handler_url?: string;
}

export interface SpinContractVerifyResult {
  contract_file: string;
  provider_url: string;
  total_interactions: number;
  passed: number;
  failed: number;
  results: Array<{
    description: string;
    passed: boolean;
    failures: string[];
    actual_status?: number;
    duration_ms?: number;
    error?: string;
  }>;
  status: "passed" | "failed" | "error";
  error?: string;
}

export interface SpinSchemaValidateInput {
  payload: unknown;
  schema_ref: string;
  spec_path?: string;
  raw_schema?: Record<string, unknown>;
}

export interface SpinSchemaValidateOutput {
  valid: boolean;
  errors: string[];
}

export interface SpinDbSnapshotInput {
  connection_string: string;
  table: string;
}

export interface SpinDbSnapshotOutput {
  table: string;
  row_count: number;
  sample_rows: Record<string, unknown>[];
  snapshot: Record<string, unknown>;
}

export interface SpinDbCompareInput {
  connection_string: string;
  table: string;
  snapshot_before: Record<string, unknown>;
  expected_delta: number;
}

export interface SpinDbCompareOutput {
  passed: boolean;
  expected_delta: number;
  actual_delta: number;
  rows_before: number;
  rows_after: number;
  diff: Record<string, unknown>;
}

export interface SpinPerfProbeInput {
  url: string;
  method?: string;
  headers?: Record<string, string>;
  body?: unknown;
  target_rps?: number;
  duration_seconds?: number;
  expected_status?: number;
  p95_threshold_ms?: number;
  error_rate_threshold?: number;
}

export interface SpinPerfProbeOutput {
  target_rps: number;
  actual_rps: number;
  duration_seconds: number;
  total_requests: number;
  errors: number;
  error_rate_pct: number;
  latency_p50_ms: number;
  latency_p95_ms: number;
  latency_p99_ms: number;
  latency_min_ms: number;
  latency_max_ms: number;
  checks: Array<{ name: string; passed: boolean; expected: string; actual: string }>;
  passed: boolean;
}

// ---- API methods ----------------------------------------------------------

function post<T>(path: string, body: unknown): Promise<T> {
  return call<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export const spinMethods = {
  runScenario: (scenario_path: string, env_vars: Record<string, unknown> = {}): Promise<SpinRunResult> =>
    post("/api/spin/scenarios/run", { scenario_path, env_vars }),

  listScenarios: (workspace_dir?: string): Promise<SpinScenarioListOutput> =>
    call<SpinScenarioListOutput>(
      `/api/spin/scenarios${workspace_dir ? `?workspace_dir=${encodeURIComponent(workspace_dir)}` : ""}`
    ),

  dryRunWorkflow: (content: string): Promise<SpinDryRunOutput> =>
    post("/api/spin/workflow/dry-run", { content }),

  verifyContract: (input: SpinContractVerifyInput): Promise<SpinContractVerifyResult> =>
    post("/api/spin/contract/verify", input),

  recordContract: (input: {
    consumer: string;
    provider: string;
    base_url: string;
    interactions: Record<string, unknown>[];
    output_path: string;
  }) => post("/api/spin/contract/record", input),

  spinValidateSchema: (input: SpinSchemaValidateInput): Promise<SpinSchemaValidateOutput> =>
    post("/api/spin/schemas/validate", input),

  dbSnapshot: (input: SpinDbSnapshotInput): Promise<SpinDbSnapshotOutput> =>
    post("/api/spin/database/snapshot", input),

  dbCompare: (input: SpinDbCompareInput): Promise<SpinDbCompareOutput> =>
    post("/api/spin/database/compare", input),

  performanceProbe: (input: SpinPerfProbeInput): Promise<SpinPerfProbeOutput> =>
    post("/api/spin/performance/probe", input),
} as const;
