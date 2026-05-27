/**
 * Load testing, security, DNS, SSL, waterfall, compression analysis types + sidecar methods.
 */

import { call } from "./client";
import type { ExecuteRequestInput } from "./types";

// ---- Response Trends types --------------------------------------------------

export interface ResponseTrendsResult {
  sizes: number[];
  timestamps: number[];
  trend: "growing" | "stable" | "shrinking";
}

// ---- Security Audit types ---------------------------------------------------

export interface SecurityAuditFinding {
  header: string;
  status: "pass" | "warn" | "fail";
  message: string;
}

export interface SecurityAuditResult {
  score: number;
  findings: SecurityAuditFinding[];
}

// ---- SSL Inspect types ------------------------------------------------------

export interface SslChainEntry {
  subject: string;
  issuer: string;
}

export interface SslInspectResult {
  subject: string;
  issuer: string;
  not_before: string;
  not_after: string;
  serial: string;
  tls_version: string | null;
  cipher: string | null;
  chain: SslChainEntry[];
  days_until_expiry: number;
}

// ---- DNS Inspect types ------------------------------------------------------

export interface DnsAddress {
  ip: string;
  family: string;
}

export interface DnsInspectResult {
  hostname: string;
  addresses: DnsAddress[];
  resolved_in_ms: number;
}

// ---- Compression types ------------------------------------------------------

export interface CompressionResult {
  encoding: string | null;
  wire_size: number;
  decoded_size: number;
  ratio: number;
  compressed: boolean;
}

// ---- Redirect Chain types ---------------------------------------------------

export interface RedirectHop {
  status: number;
  url: string;
  elapsed_ms: number;
  headers: Record<string, string>;
}

export interface RedirectChainResult {
  hops: RedirectHop[];
  total_hops: number;
  total_ms: number;
}

// ---- Content Type Validator types -------------------------------------------

export interface ContentTypeResult {
  declared: string;
  detected: string;
  match: boolean;
  details: string;
}

// ---- Load Test Pattern types ------------------------------------------------

export interface PatternLoadTestInput {
  url: string;
  method?: ExecuteRequestInput["method"];
  headers?: Record<string, string>;
  body?: string | null;
  ramp_pattern?: "linear" | "step" | "spike" | "soak";
  max_concurrency?: number;
  duration_seconds?: number;
}

export interface LoadTestPhase {
  name: string;
  concurrency: number;
  duration_s: number;
  rps: number;
}

export interface PatternLoadTestResult {
  total_requests: number;
  successful: number;
  failed: number;
  error_count: number;
  avg_latency_ms: number;
  min_latency_ms: number;
  max_latency_ms: number;
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
  actual_rps: number;
  duration_seconds: number;
  errors: Record<string, number>;
  pattern: string;
  phases: LoadTestPhase[];
}

// ---- Latency Histogram types ------------------------------------------------

export interface HistogramBucket {
  min: number;
  max: number;
  count: number;
}

export interface LatencyHistogramResult {
  buckets: HistogramBucket[];
  total: number;
  mean: number;
  stddev: number;
}

// ---- Throughput Timeline types ----------------------------------------------

export interface ThroughputWindow {
  timestamp: number;
  rps: number;
  avg_latency: number;
  error_count: number;
}

export interface ThroughputTimelineResult {
  windows: ThroughputWindow[];
}

// ---- Connection Stats types -------------------------------------------------

export interface ConnectionStatsResult {
  total_requests: number;
  connections_opened: number;
  reuse_rate: number;
  avg_latency_ms: number;
}

// ---- User Simulation types --------------------------------------------------

export interface UserSimulationInput {
  url: string;
  method?: ExecuteRequestInput["method"];
  headers?: Record<string, string>;
  body?: string | null;
  num_users?: number;
  duration_s?: number;
  think_time_ms?: number;
}

export interface UserStats {
  user_id: number;
  requests: number;
  avg_latency_ms: number;
  errors: number;
}

export interface UserSimulationResult {
  total_requests: number;
  total_errors: number;
  avg_latency_ms: number;
  duration_seconds: number;
  per_user: UserStats[];
}

// ---- SLA Check types --------------------------------------------------------

export interface SlaRule {
  metric: "p95" | "p99" | "p50" | "avg" | "max" | "error_rate";
  operator: "lt" | "gt" | "lte" | "gte";
  value: number;
}

export interface SlaCheckInput {
  latencies: number[];
  error_count: number;
  total: number;
  rules: SlaRule[];
}

export interface SlaRuleResult {
  rule: SlaRule;
  actual: number;
  passed: boolean;
}

export interface SlaCheckResult {
  passed: boolean;
  results: SlaRuleResult[];
}

// ---- Compare Runs types -----------------------------------------------------

export interface RunStats {
  total_requests: number;
  successful: number;
  failed: number;
  avg_latency_ms: number;
  min_latency_ms: number;
  max_latency_ms: number;
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
  actual_rps: number;
  duration_seconds: number;
}

export interface MetricDelta {
  name: string;
  left: number;
  right: number;
  delta: number;
  delta_pct: number;
  improved: boolean;
}

export interface CompareRunsResult {
  metrics: MetricDelta[];
}

// ---- Waterfall types --------------------------------------------------------

export interface WaterfallPhase {
  name: string;
  start_ms: number;
  duration_ms: number;
}

export interface WaterfallResult {
  phases: WaterfallPhase[];
  total_ms: number;
  url: string;
}

// ---- cURL Log types ---------------------------------------------------------

export interface CurlLogEntry {
  timestamp: string;
  curl: string;
}

export interface CurlLogResult {
  entries: CurlLogEntry[];
}

// ---- Mock Diff types --------------------------------------------------------

export interface MockDiffEntry {
  path: string;
  expected: string | null;
  actual: string | null;
}

export interface MockDiffInput {
  actual_body: string;
  mock_body: string;
  actual_headers?: Record<string, string>;
  mock_headers?: Record<string, string>;
}

export interface MockDiffResult {
  body_diffs: MockDiffEntry[];
  header_diffs: MockDiffEntry[];
  match: boolean;
}

// ---- Error Patterns types ---------------------------------------------------

export interface ErrorPattern {
  type: string;
  count: number;
  urls: string[];
  first_seen: number;
  last_seen: number;
  burst: boolean;
}

export interface ErrorPatternsResult {
  patterns: ErrorPattern[];
  total_errors: number;
  error_rate: number;
}

// ---- Dashboard types --------------------------------------------------------

export interface DashboardMetricFilter {
  status_gte?: number;
  status_lt?: number;
  url_pattern?: string;
}

export interface DashboardMetricDef {
  name: string;
  type: "avg" | "count" | "p95" | "max" | "min" | "sum";
  field: "elapsed_ms" | "status" | "body_size";
  filter?: DashboardMetricFilter;
}

export interface DashboardDataPoint {
  elapsed_ms: number;
  status: number;
  body_size: number;
  url: string;
  timestamp: number;
}

export interface DashboardInput {
  metrics: DashboardMetricDef[];
  data: DashboardDataPoint[];
}

export interface DashboardMetricResult {
  name: string;
  value: number;
}

export interface DashboardResult {
  results: DashboardMetricResult[];
}

// ---- JWT Inspect types ------------------------------------------------------

export interface JwtInspectResult {
  header: Record<string, unknown>;
  payload: Record<string, unknown>;
  expired: boolean;
  expires_at: string | null;
  issued_at: string | null;
}

// ---- Token Refresh types ----------------------------------------------------

export interface TokenRefreshInput {
  url: string;
  method?: string;
  headers?: Record<string, string>;
  body?: string | null;
  refresh_url: string;
  refresh_body?: Record<string, unknown> | null;
  token_field?: string;
  auth_header?: string;
}

export interface TokenRefreshResult {
  original_status: number;
  refreshed: boolean;
  final_status: number;
  final_body: string;
  new_token: string | null;
}

// ---- CORS Test types --------------------------------------------------------

export interface CorsTestResult {
  allowed: boolean;
  allow_origin: string | null;
  allow_methods: string | null;
  allow_headers: string | null;
  allow_credentials: string | null;
  max_age: string | null;
  issues: string[];
}

// ---- Injection Scan types ---------------------------------------------------

export interface InjectionFinding {
  param: string;
  payload: string;
  response_status: number;
  suspicious: boolean;
  evidence: string;
}

export interface InjectionScanResult {
  vulnerable: boolean;
  findings: InjectionFinding[];
}

// ---- Sensitive Data types ---------------------------------------------------

export interface SensitiveFinding {
  type: string;
  value_preview: string;
  location: string;
  line: number;
}

export interface SensitiveDataResult {
  findings: SensitiveFinding[];
  count: number;
  risk_level: "none" | "low" | "medium" | "high";
}

// ---- Full load runner types -------------------------------------------------

export interface LoadRunConfig {
  url: string;
  method?: string;
  headers?: Record<string, string>;
  body?: string | null;
  virtual_users?: number;
  duration_seconds?: number;
  ramp_up_seconds?: number;
  think_time_ms?: number;
  environment_id?: string | null;
}

export interface TimelinePoint {
  second: number;
  rps: number;
  avg_latency_ms: number;
  error_count: number;
  active_users: number;
}

export interface LoadRunResult {
  total_requests: number;
  successful: number;
  failed: number;
  errors: Record<string, number>;
  avg_latency_ms: number;
  min_latency_ms: number;
  max_latency_ms: number;
  p50_ms: number;
  p75_ms: number;
  p90_ms: number;
  p95_ms: number;
  p99_ms: number;
  requests_per_second: number;
  duration_seconds: number;
  timeline: TimelinePoint[];
}

// ---- Load test types --------------------------------------------------------

export interface LoadTestInput {
  url: string;
  method?: ExecuteRequestInput["method"];
  headers?: Record<string, string>;
  body?: string | null;
  concurrency?: number;
  duration_seconds?: number;
  rps_limit?: number | null;
}

export interface LoadTestResult {
  total_requests: number;
  successful: number;
  failed: number;
  error_count: number;
  avg_latency_ms: number;
  min_latency_ms: number;
  max_latency_ms: number;
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
  actual_rps: number;
  duration_seconds: number;
  errors: Record<string, number>;
}

export const analysisMethods = {
  responseTrends: (input: { request_id: string; max_snapshots?: number }) =>
    call<ResponseTrendsResult>("/api/analysis/response-trends", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  securityAudit: (headers: Record<string, string>) =>
    call<SecurityAuditResult>("/api/analysis/security-audit", {
      method: "POST",
      body: JSON.stringify({ headers }),
    }),
  sslInspect: (input: { hostname: string; port?: number }) =>
    call<SslInspectResult>("/api/analysis/ssl-inspect", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  dnsInspect: (hostname: string) =>
    call<DnsInspectResult>("/api/analysis/dns-inspect", {
      method: "POST",
      body: JSON.stringify({ hostname }),
    }),
  compressionStats: (input: { url: string; headers?: Record<string, string> }) =>
    call<CompressionResult>("/api/analysis/compression", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  redirectChain: (input: { url: string; max_hops?: number; headers?: Record<string, string> }) =>
    call<RedirectChainResult>("/api/analysis/redirect-chain", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  contentTypeValidator: (input: { content_type: string; body: string }) =>
    call<ContentTypeResult>("/api/analysis/content-type", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  loadTest: (input: LoadTestInput) =>
    call<LoadTestResult>("/api/loadtest/run", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  loadTestFull: (input: LoadRunConfig) =>
    call<LoadRunResult>("/api/loadtest/run-full", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  loadTestPattern: (input: PatternLoadTestInput) =>
    call<PatternLoadTestResult>("/api/loadtest/run-pattern", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  latencyHistogram: (input: { latency_ms: number[]; buckets?: number }) =>
    call<LatencyHistogramResult>("/api/analysis/latency-histogram", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  throughputTimeline: (entries: Array<{ timestamp: number; latency_ms: number; success: boolean }>) =>
    call<ThroughputTimelineResult>("/api/analysis/throughput-timeline", {
      method: "POST",
      body: JSON.stringify({ entries }),
    }),
  connectionStats: (input: { url: string; num_requests?: number; headers?: Record<string, string> }) =>
    call<ConnectionStatsResult>("/api/analysis/connection-stats", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  simulateUsers: (input: UserSimulationInput) =>
    call<UserSimulationResult>("/api/loadtest/simulate-users", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  slaCheck: (input: SlaCheckInput) =>
    call<SlaCheckResult>("/api/analysis/sla-check", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  compareRuns: (input: { left: RunStats; right: RunStats }) =>
    call<CompareRunsResult>("/api/analysis/compare-runs", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  waterfall: (input: { url: string; method?: string; headers?: Record<string, string>; body?: string | null }) =>
    call<WaterfallResult>("/api/analysis/waterfall", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  logCurl: (input: { method: string; url: string; headers?: Record<string, string>; body?: string | null }) =>
    call<CurlLogEntry>("/api/log/curl", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  getCurlLog: (limit?: number) =>
    call<CurlLogResult>(`/api/log/curl?limit=${limit ?? 50}`),
  mockDiff: (input: MockDiffInput) =>
    call<MockDiffResult>("/api/analysis/mock-diff", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  errorPatterns: (entries: Array<{ timestamp: number; url: string; status: number; error?: string | null }>) =>
    call<ErrorPatternsResult>("/api/analysis/error-patterns", {
      method: "POST",
      body: JSON.stringify({ entries }),
    }),
  computeDashboard: (input: DashboardInput) =>
    call<DashboardResult>("/api/dashboard/compute", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  jwtInspect: (token: string) =>
    call<JwtInspectResult>("/api/security/jwt-inspect", {
      method: "POST",
      body: JSON.stringify({ token }),
    }),
  autoRefreshToken: (input: TokenRefreshInput) =>
    call<TokenRefreshResult>("/api/auth/auto-refresh", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  corsTest: (input: { url: string; origin?: string }) =>
    call<CorsTestResult>("/api/security/cors-test", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  injectionScan: (input: { url: string; method?: string; params: Record<string, string>; headers?: Record<string, string> }) =>
    call<InjectionScanResult>("/api/security/injection-scan", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  sensitiveScan: (input: { body: string; headers?: Record<string, string> }) =>
    call<SensitiveDataResult>("/api/security/sensitive-scan", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  owaspScan: (input: OWASPScanInput) =>
    call<OWASPScanOutput>("/api/security/owasp-scan", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  compareResponses: (input: CompareResponsesInput) =>
    call<CompareResponsesOutput>("/api/compare/responses", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  diffBodies: (input: BodyDiffInput) =>
    call<BodyDiffOutput>("/api/diff/bodies", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  formatBody: (input: BodyFormatInput) =>
    call<BodyFormatOutput>("/api/diff/format", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  mergeBodies: (input: BodyMergeInput) =>
    call<BodyMergeOutput>("/api/diff/merge", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  rateLimitAnalyze: (headers: Record<string, string>) =>
    call<RateLimitAnalyzeOutput>("/api/ratelimit/analyze", {
      method: "POST",
      body: JSON.stringify({ headers }),
    }),
  rateLimitTrack: (input: { url: string; headers: Record<string, string> }) =>
    call<RateLimitTrackOutput>("/api/ratelimit/track", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  rateLimitStatus: () =>
    call<RateLimitStatusOutput>("/api/ratelimit/status"),
  rateLimitHistory: (urlHash: string) =>
    call<RateLimitHistoryOutput>(`/api/ratelimit/history/${urlHash}`),
  diffRequests: (input: RequestDiffInput) =>
    call<RequestDiffOutput>("/api/requests/diff", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  analyzeHeaders: (headers: Record<string, string>) =>
    call<HeaderInsightsOutput>("/api/headers/analyze", {
      method: "POST",
      body: JSON.stringify({ headers }),
    }),
  searchBody: (input: BodySearchInput) =>
    call<BodySearchOutput>("/api/search/body", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  searchJsonPath: (input: { body: string; path: string }) =>
    call<JsonPathOutput>("/api/search/json-path", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  searchXPath: (input: { body: string; xpath: string }) =>
    call<XPathOutput>("/api/search/xpath", {
      method: "POST",
      body: JSON.stringify(input),
    }),
} as const;

// ---- OWASP Scanner types ---------------------------------------------------

export type OWASPSeverity = "critical" | "high" | "medium" | "low" | "info";
export type OWASPScanType = "sql_injection" | "xss" | "auth_bypass" | "rate_limit";

export interface OWASPFinding {
  scan_type: OWASPScanType;
  severity: OWASPSeverity;
  title: string;
  evidence: string;
  description: string;
}

export interface OWASPScanInput {
  url: string;
  method?: string;
  headers?: Record<string, string>;
  params?: Record<string, string>;
  body?: string | null;
  scan_types?: OWASPScanType[];
}

export interface OWASPScanOutput {
  findings: OWASPFinding[];
  score: number;
  scan_types_run: OWASPScanType[];
  elapsed_ms: number;
}

// ---- Response Comparison types -----------------------------------------------

export interface CompareResponsesInput {
  left: string;
  right: string;
  format: "json" | "text";
}

export interface ResponseChangeEntry {
  path: string;
  type: "added" | "removed" | "changed";
  old_value: string | null;
  new_value: string | null;
}

export interface CompareResponsesOutput {
  summary: string;
  changes: ResponseChangeEntry[];
  diff_text: string;
}

// ---- Body Diff types --------------------------------------------------------

export interface BodyDiffInput {
  left: string;
  right: string;
  format?: "json" | "xml" | "text" | "auto";
}

export interface BodyDiffStructuralChange {
  path: string;
  type: "added" | "removed" | "changed";
  old: unknown;
  new: unknown;
}

export interface BodyDiffStats {
  additions: number;
  deletions: number;
  modifications: number;
}

export interface BodyDiffOutput {
  format_detected: string;
  structural_changes: BodyDiffStructuralChange[];
  unified_diff: string;
  stats: BodyDiffStats;
}

export interface BodyFormatInput {
  body: string;
  format?: "json" | "xml" | "auto";
}

export interface BodyFormatOutput {
  formatted: string;
  format_detected: string;
}

export interface BodyMergeInput {
  base: string;
  left: string;
  right: string;
  format?: "json" | "xml" | "text" | "auto";
}

export interface BodyMergeConflict {
  path: string;
  base_value: unknown;
  left_value: unknown;
  right_value: unknown;
}

export interface BodyMergeOutput {
  merged: string;
  conflicts: BodyMergeConflict[];
  format_detected: string;
}

// ---- Rate Limit Detector types -----------------------------------------------

export interface RateLimitAnalyzeOutput {
  detected: boolean;
  limit: number | null;
  remaining: number | null;
  reset_at: string | null;
  reset_seconds: number | null;
  retry_after: number | null;
  policy: string | null;
  provider: string | null;
  percentage_used: number | null;
  headers_found: string[];
}

export interface RateLimitTrackOutput {
  url_hash: string;
  tracked: boolean;
}

export interface RateLimitStatusEntry {
  url_hash: string;
  url: string;
  limit: number | null;
  remaining: number | null;
  reset_seconds: number | null;
  percentage_used: number | null;
  last_seen: number;
}

export interface RateLimitStatusOutput {
  entries: RateLimitStatusEntry[];
}

export interface RateLimitHistoryPoint {
  timestamp: number;
  limit: number | null;
  remaining: number | null;
  percentage_used: number | null;
}

export interface RateLimitHistoryOutput {
  url_hash: string;
  points: RateLimitHistoryPoint[];
}

// ---- Request Diff types -----------------------------------------------------

export interface RequestDiffRef {
  collection_id: string;
  request_id: string;
}

export interface RequestDiffInput {
  left: RequestDiffRef;
  right: RequestDiffRef;
}

export interface RequestDiffUrlDiff {
  left: string;
  right: string;
}

export interface RequestDiffHeaderChange {
  name: string;
  type: "added" | "removed" | "changed";
  left_value: string | null;
  right_value: string | null;
}

export interface RequestDiffBodyDiff {
  format: "json" | "text";
  changes: Array<Record<string, unknown>>;
  unified: string;
}

export interface RequestDiffAuthDiff {
  left_type: string;
  right_type: string;
  details: string;
}

export interface RequestDiffOutput {
  method_changed: boolean;
  url_diff: RequestDiffUrlDiff | null;
  header_changes: RequestDiffHeaderChange[];
  body_diff: RequestDiffBodyDiff | null;
  auth_diff: RequestDiffAuthDiff | null;
  summary: string;
}

// ---- Header Insights types --------------------------------------------------

export interface HeaderFinding {
  category: "security" | "caching" | "performance" | "info_leak" | "compression";
  header: string;
  status: "good" | "warning" | "missing" | "info";
  message: string;
  recommendation: string;
}

export interface HeaderRecommendation {
  header: string;
  severity: "high" | "medium" | "low";
  message: string;
  suggested_value: string;
}

export interface HeaderCachingAnalysis {
  strategy: "none" | "private" | "public" | "aggressive";
  directives: string[];
  effective_ttl: number | null;
  summary: string;
}

export interface HeaderCompressionAnalysis {
  encoding: string | null;
  is_compressed: boolean;
  message: string;
}

export interface HeaderInsightsOutput {
  score: number;
  grade: "A" | "B" | "C" | "D" | "F";
  findings: HeaderFinding[];
  recommendations: HeaderRecommendation[];
  caching: HeaderCachingAnalysis;
  compression: HeaderCompressionAnalysis;
}

// ---- Body Search types ------------------------------------------------------

export interface BodySearchMatch {
  start: number;
  end: number;
  line: number;
  column: number;
  context: string;
}

export interface BodySearchOutput {
  matches: BodySearchMatch[];
  total: number;
  query_valid: boolean;
}

export interface BodySearchInput {
  body: string;
  query: string;
  regex?: boolean;
  case_sensitive?: boolean;
}

export interface JsonPathMatch {
  path: string;
  value: unknown;
  type: string;
}

export interface JsonPathOutput {
  matches: JsonPathMatch[];
  total: number;
}

export interface XPathMatch {
  path: string;
  value: string;
}

export interface XPathOutput {
  matches: XPathMatch[];
  total: number;
}
