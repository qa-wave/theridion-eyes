/**
 * Assertions, runner, batch, healing, test builder types + sidecar methods.
 */

import { call } from "./client";
import type { AuthConfig, ExecuteRequestInput } from "./types";
import type { CaptureRule } from "./requests";

// ---- Assertion types ----------------------------------------------------

export type AssertionType =
  | "status"
  | "response_time"
  | "json_path"
  | "header_exists"
  | "header_equals"
  | "body_contains"
  | "body_regex"
  | "performance_budget";

export interface Assertion {
  type: AssertionType;
  expected: string;
  path: string;
  operator: string;
}

export interface AssertionResult {
  assertion: Assertion;
  passed: boolean;
  message: string;
}

export interface AssertionEvalOutput {
  results: AssertionResult[];
  passed: number;
  failed: number;
  total: number;
}

// ---- Batch Runner types --------------------------------------------------

export interface BatchOutput {
  total_rows: number;
  total_requests: number;
  total_passed: number;
  total_failed: number;
  total_errors: number;
  elapsed_ms: number;
  rows: Array<{
    row_index: number;
    variables: Record<string, string>;
    request_results: Array<Record<string, unknown>>;
    passed: number;
    failed: number;
    errors: number;
  }>;
}

// ---- Self-Healing types -----------------------------------------------------

export interface HealAssertionInput {
  assertion: Assertion;
  response_body: string;
  response_headers?: Record<string, string>;
  response_status?: number;
}

export interface HealCandidate {
  original_path: string;
  suggested_path: string;
  confidence: number;
  reason: string;
}

export interface HealAssertionOutput {
  candidates: HealCandidate[];
  auto_fixable: boolean;
}

// ---- Assertion Suggest types --------------------------------------------

export interface AssertionSuggestInput {
  status: number;
  headers: Record<string, string>;
  body: string;
  elapsed_ms: number;
}

export interface AssertionSuggestion {
  assertion: Assertion;
  confidence: number;
  reason: string;
  category: string;
}

export interface AssertionSuggestOutput {
  suggestions: AssertionSuggestion[];
}

// ---- Flow types ---------------------------------------------------------

export interface FlowStep {
  id?: string | null;
  name?: string;
  method?: ExecuteRequestInput["method"];
  url: string;
  headers?: Record<string, string>;
  body?: string | null;
  auth?: AuthConfig | null;
  assertions?: Assertion[];
  captures?: CaptureRule[];
  timeout_seconds?: number;
}

export interface FlowRunInput {
  environment_id?: string | null;
  dataset?: Record<string, string>[];
  steps: FlowStep[];
  cleanup_steps?: FlowStep[];
}

export interface FlowStepResult {
  step_id: string;
  name: string;
  status?: number | null;
  elapsed_ms: number;
  error?: string | null;
  captured_values: Record<string, string>;
  assertion_results: AssertionResult[];
}

export interface FlowTraceEvent {
  dataset_index: number;
  step_id: string;
  phase: "request" | "assertions" | "capture" | "cleanup";
  started_at: string;
  ended_at: string;
  elapsed_ms: number;
  status?: number | null;
  error?: string | null;
}

export interface FlowDatasetResult {
  index: number;
  runtime: Record<string, string>;
  steps: FlowStepResult[];
  cleanup: FlowStepResult[];
}

export interface FlowRunOutput {
  datasets: FlowDatasetResult[];
  trace: FlowTraceEvent[];
  passed_assertions: number;
  failed_assertions: number;
}

// ---- Visual Test Builder types ----------------------------------------------

export interface TestStep {
  type: "request" | "delay" | "assert" | "loop" | "condition";
  config: Record<string, unknown>;
}

export interface TestBuilderData {
  steps: TestStep[];
  version: number;
}

// ---- Data Loop types --------------------------------------------------------

export interface DataLoopInput {
  collection_id: string;
  datasource: { type: "csv" | "json"; data: string };
  loop_variable?: string;
}

export interface DataLoopRowResult {
  row_index: number;
  variables: Record<string, string>;
  status: string;
  error?: string | null;
}

export interface DataLoopOutput {
  total_rows: number;
  results: DataLoopRowResult[];
}

// ---- Flow Block types -------------------------------------------------------

export interface FlowBlock {
  id: string;
  type: "request" | "transform" | "condition" | "delay";
  config: Record<string, unknown>;
  next?: string[];
}

export interface FlowBlockExecuteInput {
  blocks: FlowBlock[];
}

export interface FlowBlockResult {
  block_id: string;
  output: Record<string, unknown>;
  error?: string | null;
}

export interface FlowBlockExecuteOutput {
  results: FlowBlockResult[];
  elapsed_ms: number;
}

// ---- Retry Tester types -----------------------------------------------------

export interface RetryTestInput {
  url: string;
  method?: string;
  headers?: Record<string, string>;
  body?: string | null;
  attempts?: number;
  delay_ms?: number;
  expected_recovery_after?: number;
}

export interface AttemptResult {
  attempt: number;
  status: number | null;
  elapsed_ms: number;
  error: string | null;
}

export interface RetryTestResult {
  attempts: AttemptResult[];
  recovered: boolean;
  recovered_at: number | null;
}

// ---- Rate Limit types -------------------------------------------------------

export interface RateLimitResult {
  limit: number | null;
  window_seconds: number | null;
  requests_sent: number;
  first_429_at: number | null;
  headers_found: Record<string, string>;
}

// ---- Idempotency types ------------------------------------------------------

export interface IdempotencySnapshot {
  status: number;
  body_hash: string;
}

export interface IdempotencyResult {
  first: IdempotencySnapshot;
  second: IdempotencySnapshot;
  idempotent: boolean;
  differences: string[];
}

// ---- Pagination types -------------------------------------------------------

export interface PaginationInput {
  url: string;
  headers?: Record<string, string>;
  strategy?: "link" | "offset" | "cursor";
  limit_param?: string;
  offset_param?: string;
  cursor_param?: string;
  page_size?: number;
  max_pages?: number;
}

export interface PageResult {
  page: number;
  status: number;
  item_count: number;
  url: string;
}

export interface PaginationResult {
  pages: PageResult[];
  total_items: number;
  total_pages: number;
  consistent: boolean;
}

// ---- Contract Drift Check types ---------------------------------------------

export interface ContractDriftEntry {
  path: string;
  type: "added" | "removed" | "type_changed";
  old_type: string | null;
  new_type: string | null;
}

export interface ContractDriftCheckResult {
  drifts: ContractDriftEntry[];
  breaking: boolean;
  drift_count: number;
}

// ---- Multi Env Runner types -------------------------------------------------

export interface EnvRunResult {
  env_name: string;
  env_id: string;
  passed: number;
  failed: number;
  errors: number;
  elapsed_ms: number;
}

export interface RequestStatusRow {
  request_name: string;
  statuses: Record<string, number>;
}

export interface MultiEnvResult {
  results: EnvRunResult[];
  comparison: RequestStatusRow[];
}

// ---- Multi Env Parallel Runner (new) ----------------------------------------

export interface MultiEnvRequestTemplate {
  method: string;
  url: string;
  headers: Record<string, string>;
  body?: string | null;
}

export interface EnvRequestResult {
  env_id: string;
  env_name: string;
  status: number | null;
  elapsed_ms: number;
  body_preview: string;
  headers: Record<string, string>;
  error: string | null;
  body_size: number;
}

export interface ComparisonSummary {
  all_same_status: boolean;
  fastest_env: string;
  slowest_env: string;
  response_size_diff: boolean;
}

export interface SingleRequestMultiEnvOutput {
  results: EnvRequestResult[];
  comparison: ComparisonSummary;
}

export interface CollectionRequestRow {
  request_name: string;
  results: EnvRequestResult[];
  comparison: ComparisonSummary;
}

export interface CollectionMultiEnvOutput {
  rows: CollectionRequestRow[];
  summary: ComparisonSummary;
}

// ---- Flow Graph types -------------------------------------------------------

export interface FlowVisualNode {
  name: string;
  level: number;
  dependencies: string[];
}

export interface FlowGraphResult {
  nodes: FlowVisualNode[];
  order: string[];
  has_cycle: boolean;
}

// ---- Monitor types ----------------------------------------------------------

export interface MonitorConfig {
  id?: string;
  collection_id: string;
  environment_id?: string | null;
  cron?: string;
  enabled?: boolean;
  last_run?: string | null;
  last_status?: string | null;
}

export interface MonitorListOutput {
  monitors: MonitorConfig[];
}

// ---- Webhook types ----------------------------------------------------------

export interface WebhookConfig {
  id?: string;
  collection_id: string;
  environment_id?: string | null;
  url: string;
  enabled?: boolean;
}

export interface WebhookListOutput {
  webhooks: WebhookConfig[];
}

// ---- Trace Viewer types ---------------------------------------------------

export interface RunRequestResult {
  request_id: string;
  request_name: string;
  method: string;
  url: string;
  status: number | null;
  elapsed_ms: number;
  error: string | null;
  assertion_results: AssertionResult[];
  assertions_passed: number;
  assertions_failed: number;
}

export interface RunCollectionOutput {
  collection_id: string;
  collection_name: string;
  results: RunRequestResult[];
  total_requests: number;
  successful_requests: number;
  failed_requests: number;
  total_assertions: number;
  passed_assertions: number;
  failed_assertions: number;
  total_elapsed_ms: number;
}

export interface RunWithTraceOutput {
  run: RunCollectionOutput;
  trace_html: string;
}

// ---- Contract Guard types -------------------------------------------------

export interface ContractGuardViolation {
  path: string;
  expected: string;
  actual: string;
  message: string;
}

export interface ContractValidateGuardInput {
  response_body: string;
  response_status: number;
  response_headers?: Record<string, string>;
  openapi_spec: string;
  path: string;
  method: string;
}

export interface ContractGuardOutput {
  valid: boolean;
  violations: ContractGuardViolation[];
}

export interface PerRequestValidation {
  request_name: string;
  method: string;
  url: string;
  status: number | null;
  valid: boolean;
  violations: ContractGuardViolation[];
  error: string | null;
}

export interface ContractCollectionOutput {
  results: PerRequestValidation[];
  total: number;
  valid_count: number;
  invalid_count: number;
}

// ---- Report Generation types ------------------------------------------------

export interface ReportAssertionResult {
  assertion: Record<string, unknown>;
  passed: boolean;
  message: string;
}

export interface ReportRequestResult {
  request_id: string;
  request_name: string;
  method: string;
  url: string;
  status: number | null;
  elapsed_ms: number;
  error: string | null;
  assertion_results: ReportAssertionResult[];
  assertions_passed: number;
  assertions_failed: number;
}

export interface ReportGenerationInput {
  collection_id: string;
  collection_name: string;
  results: ReportRequestResult[];
  total_requests: number;
  successful_requests: number;
  failed_requests: number;
  total_assertions: number;
  passed_assertions: number;
  failed_assertions: number;
  total_elapsed_ms: number;
}

export interface HtmlReportOutput {
  html: string;
}

export interface JunitReportOutput {
  xml: string;
}

export interface JsonReportOutput {
  report: Record<string, unknown>;
}

export interface MarkdownReportOutput {
  markdown: string;
}

// ---- JUnit Reporter types ---------------------------------------------------

export interface JunitTestResult {
  name: string;
  status: "passed" | "failed" | "error";
  elapsed_ms?: number;
  error?: string | null;
  assertions?: number;
}

// ---- CLI Reporter types -----------------------------------------------------

export interface ReportResultItem {
  name: string;
  status: string;
  elapsed_ms?: number;
  error?: string | null;
  assertions?: number;
}

// ---- API Changelog types ----------------------------------------------------

export interface FieldChange {
  path: string;
  type: string;
  old_value: string | null;
  new_value: string | null;
}

export interface ChangelogEntry {
  request_name: string;
  changes: FieldChange[];
  breaking: boolean;
}

export interface ChangelogResult {
  collection_name: string;
  entries: ChangelogEntry[];
  breaking_changes: number;
  total_changes: number;
  timestamp: number;
}

// ---- Regression Generator types ---------------------------------------------

export interface GeneratedAssertion {
  type: string;
  expected: string;
  path: string;
  operator: string;
}

export interface RequestAssertions {
  request_id: string;
  request_name: string;
  assertions: GeneratedAssertion[];
}

export interface RegressionOutput {
  collection_name: string;
  total_assertions: number;
  requests_processed: number;
  request_assertions: RequestAssertions[];
}

// ---- Dependency Resolver types ----------------------------------------------

export interface DependencyInfo {
  request_id: string;
  name: string;
  depends_on: string[];
  provides: string[];
  consumes: string[];
}

export interface CycleInfo {
  variable: string;
  involved: string[];
}

export interface DependencyResult {
  order: DependencyInfo[];
  cycles: CycleInfo[];
  unresolved: string[];
}

// ---- Dependency Graph (visual) types -----------------------------------------

export interface DepGraphNode {
  id: string;
  name: string;
  method: string;
  url: string;
  produces: string[];
  consumes: string[];
  folder: string | null;
}

export interface DepGraphEdge {
  from_id: string;
  to_id: string;
  variable: string;
}

export interface DepGraphGroup {
  name: string;
  node_ids: string[];
}

export interface DepGraphResult {
  nodes: DepGraphNode[];
  edges: DepGraphEdge[];
  groups: DepGraphGroup[];
  execution_order: string[];
  has_cycle: boolean;
  cycle_members: string[];
}

export const testingMethods = {
  evaluateAssertions: (input: {
    assertions: Assertion[];
    response: { status: number; headers: Record<string, string>; body: string; elapsed_ms: number };
  }) =>
    call<AssertionEvalOutput>("/api/assertions/evaluate", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  runBatch: (input: { collection_id: string; environment_id?: string; dataset: Array<Record<string, string>>; dataset_csv?: string }) =>
    call<BatchOutput>("/api/batch/run", { method: "POST", body: JSON.stringify(input) }),
  healAssertion: (input: HealAssertionInput) =>
    call<HealAssertionOutput>("/api/assertions/heal", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  runFlow: (input: FlowRunInput) =>
    call<FlowRunOutput>("/api/advanced/flows/run", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  getTestBuilder: (collectionId: string) =>
    call<TestBuilderData>(`/api/test-builder/${collectionId}`),
  putTestBuilder: (collectionId: string, data: TestBuilderData) =>
    call<TestBuilderData>(`/api/test-builder/${collectionId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  dataLoop: (input: DataLoopInput) =>
    call<DataLoopOutput>("/api/test/data-loop", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  executeFlowBlocks: (input: FlowBlockExecuteInput) =>
    call<FlowBlockExecuteOutput>("/api/flows/execute", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  flowVisualize: (nodes: Array<{ name: string; depends_on: string[] }>) =>
    call<FlowGraphResult>("/api/flows/visualize", {
      method: "POST",
      body: JSON.stringify({ nodes }),
    }),
  retryTest: (input: RetryTestInput) =>
    call<RetryTestResult>("/api/test/retry", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  rateLimitDetect: (input: { url: string; method?: string; headers?: Record<string, string>; max_requests?: number }) =>
    call<RateLimitResult>("/api/test/ratelimit", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  idempotencyCheck: (input: { url: string; method?: string; headers?: Record<string, string>; body?: string | null }) =>
    call<IdempotencyResult>("/api/test/idempotency", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  paginationWalker: (input: PaginationInput) =>
    call<PaginationResult>("/api/test/pagination", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  contractDriftCheck: (input: { current_body: string; baseline_body: string }) =>
    call<ContractDriftCheckResult>("/api/test/contract-drift", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  multiEnvRun: (input: { collection_id: string; environment_ids: string[] }) =>
    call<MultiEnvResult>("/api/test/multi-env", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  multiEnvRunSingle: (input: {
    request: MultiEnvRequestTemplate;
    environment_ids: string[];
    collection_id?: string | null;
  }) =>
    call<SingleRequestMultiEnvOutput>("/api/runner/multi-env", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  multiEnvRunCollection: (input: {
    collection_id: string;
    environment_ids: string[];
  }) =>
    call<CollectionMultiEnvOutput>("/api/runner/multi-env/collection", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  listMonitors: () => call<MonitorListOutput>("/api/monitors"),
  createMonitor: (input: MonitorConfig) =>
    call<MonitorConfig>("/api/monitors/create", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  deleteMonitor: async (id: string) => {
    const { getSidecarBaseUrl: getUrl } = await import("./client");
    const baseUrl = await getUrl();
    const r = await fetch(`${baseUrl}/api/monitors/${id}`, { method: "DELETE" });
    if (!r.ok) throw new Error(`delete monitor ${r.status}`);
  },
  listWebhooks: () => call<WebhookListOutput>("/api/webhooks"),
  createWebhook: (input: WebhookConfig) =>
    call<WebhookConfig>("/api/webhooks/create", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  deleteWebhook: async (id: string) => {
    const { getSidecarBaseUrl: getUrl } = await import("./client");
    const baseUrl = await getUrl();
    const r = await fetch(`${baseUrl}/api/webhooks/${id}`, { method: "DELETE" });
    if (!r.ok) throw new Error(`delete webhook ${r.status}`);
  },
  triggerWebhook: (id: string) =>
    call<{ status: string; collection_id: string }>(`/api/webhooks/${id}/trigger`, { method: "POST" }),
  runWithTrace: (collectionId: string, environmentId?: string) =>
    call<RunWithTraceOutput>(`/api/runner/${collectionId}/run-with-trace`, {
      method: "POST",
      body: JSON.stringify({ environment_id: environmentId ?? null }),
    }),
  contractValidate: (input: ContractValidateGuardInput) =>
    call<ContractGuardOutput>("/api/contract/validate", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  contractValidateCollection: (collectionId: string, specContent: string) =>
    call<ContractCollectionOutput>("/api/contract/validate-collection", {
      method: "POST",
      body: JSON.stringify({ collection_id: collectionId, spec_content: specContent }),
    }),
  generateJunit: (results: JunitTestResult[]) =>
    call<{ xml: string }>("/api/reports/junit", {
      method: "POST",
      body: JSON.stringify({ results }),
    }),
  generateReport: (results: ReportResultItem[], format: string) =>
    call<{ content: string; content_type: string }>("/api/reports/generate", {
      method: "POST",
      body: JSON.stringify({ results, format }),
    }),
  generateHtmlReport: (input: ReportGenerationInput) =>
    call<HtmlReportOutput>("/api/reports/generate/html", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  generateJunitReport: (input: ReportGenerationInput) =>
    call<JunitReportOutput>("/api/reports/generate/junit", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  generateJsonReport: (input: ReportGenerationInput) =>
    call<JsonReportOutput>("/api/reports/generate/json", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  generateMarkdownReport: (input: ReportGenerationInput) =>
    call<MarkdownReportOutput>("/api/reports/generate/markdown", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  detectChangelog: (input: { collection_id: string; environment_id?: string }) =>
    call<ChangelogResult>("/api/changelog/detect", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  generateRegression: (collectionId: string, environmentId?: string) =>
    call<RegressionOutput>(`/api/test/generate-regression/${collectionId}`, {
      method: "POST",
      body: JSON.stringify({ environment_id: environmentId ?? null }),
    }),
  resolveDependencies: (collectionId: string) =>
    call<DependencyResult>("/api/test/resolve-dependencies", {
      method: "POST",
      body: JSON.stringify({ collection_id: collectionId }),
    }),
  executePipeline: (input: PipelineInput) =>
    call<PipelineResult>("/api/pipeline/execute", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  validatePipeline: (input: PipelineInput) =>
    call<PipelineValidateOutput>("/api/pipeline/validate", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  getPipelineTemplates: () =>
    call<PipelineTemplate[]>("/api/pipeline/templates"),
  suggestAssertions: (input: AssertionSuggestInput) =>
    call<AssertionSuggestOutput>("/api/assertions/suggest", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  buildDepGraph: (collectionId: string) =>
    call<DepGraphResult>("/api/graph/collection", {
      method: "POST",
      body: JSON.stringify({ collection_id: collectionId }),
    }),
  runCli: (collectionId: string, environmentId?: string) =>
    call<CliRunOutput>(`/api/runner/cli?collection_id=${encodeURIComponent(collectionId)}`, {
      method: "POST",
      body: JSON.stringify({ environment_id: environmentId ?? null }),
    }),
  runCliWithTrace: (collectionId: string, environmentId?: string) =>
    call<CliRunWithTraceOutput>(`/api/runner/cli/trace?collection_id=${encodeURIComponent(collectionId)}`, {
      method: "POST",
      body: JSON.stringify({ environment_id: environmentId ?? null }),
    }),
  downloadTrace: async (traceId: string): Promise<Blob> => {
    const { getSidecarBaseUrl } = await import("./client");
    const baseUrl = await getSidecarBaseUrl();
    const resp = await fetch(`${baseUrl}/api/runner/trace/${encodeURIComponent(traceId)}`);
    if (!resp.ok) throw new Error(`download trace ${resp.status}`);
    return resp.blob();
  },
  traceToHtml: (traceId: string) =>
    call<TraceHtmlOutput>(`/api/runner/trace/html?trace_id=${encodeURIComponent(traceId)}`, {
      method: "POST",
    }),
} as const;

// ---- Pipeline types ----------------------------------------------------------

export interface PipelineExtractor {
  name: string;
  source: "body" | "header" | "status";
  path: string;
}

export interface PipelineStep {
  request_id: string;
  collection_id: string;
  delay_ms?: number;
  condition?: string | null;
  extractors?: PipelineExtractor[];
  on_fail?: "stop" | "continue" | "retry";
  retry_count?: number;
}

export interface PipelineInput {
  name: string;
  steps: PipelineStep[];
  variables?: Record<string, string>;
  environment_id?: string | null;
}

export interface PipelineStepResult {
  step_index: number;
  request_id: string;
  collection_id: string;
  status: number | null;
  elapsed_ms: number;
  passed: boolean;
  error: string | null;
  captured: Record<string, string>;
  attempts: number;
  skipped: boolean;
}

export interface PipelineResult {
  results: PipelineStepResult[];
  total_ms: number;
  passed: number;
  failed: number;
  variables: Record<string, string>;
}

export interface PipelineValidationIssue {
  step_index: number;
  field: string;
  message: string;
}

export interface PipelineValidateOutput {
  valid: boolean;
  issues: PipelineValidationIssue[];
}

export interface PipelineTemplate {
  name: string;
  description: string;
  steps: Record<string, unknown>[];
}

// ---- CLI Runner types -------------------------------------------------------

export interface CliRunOutput {
  output: string;
  passed: number;
  failed: number;
  skipped: number;
  total_ms: number;
}

export interface CliRunWithTraceOutput extends CliRunOutput {
  trace_path: string;
  trace_id: string;
}

export interface TraceHtmlOutput {
  html: string;
}
