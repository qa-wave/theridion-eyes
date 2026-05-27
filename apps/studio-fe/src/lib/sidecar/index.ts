/**
 * Sidecar client — re-exports all domain modules and composes the unified `sidecar` object.
 */

// Re-export everything from each module so consumers can import types directly.
export { getSidecarBaseUrl, isTauri } from "./client";
export type { HealthResponse } from "./client";

export type {
  AuthType, AuthConfig, TimingBreakdown, ExecuteRequestInput, ExecuteResponse,
  EnvVariable, Environment, EnvironmentSummary, CollectionVariable, StubOutput,
  CertConfig, CertInfo, VerifyChainResponse, SystemCertEntry, SystemCertsResponse,
  BackoffStrategy, RetryConfig, RetryAttemptInfo, ExecuteWithRetryResponse,
} from "./types";
export { DEFAULT_RETRY_CONFIG } from "./types";

export type {
  CollectionItem, SavedRequest, StoredCollection, CollectionSummary,
  SaveRequestInput, CreateFolderInput, FavoriteItem, ForkOutput, MergeOutput,
  CollectionStats,
} from "./collections";

export type { EnvDiffOutput, StructuredDiffOutput, DiffVarPair, DiffVarDifferent } from "./environments";

export type {
  FormField, ExecuteMultipartInput, CaptureRule, ExecuteWithCapturesInput,
  ExecuteWithCapturesResponse, OAuth2TokenInput, OAuth2TokenOutput,
  OAuth2RefreshInput,
  OAuth2ClientCredentialsInput, OAuth2ClientCredentialsOutput,
  OAuth2TokenReuseInput, OAuth2TokenReuseOutput,
  OAuth2PasswordInput,
  OAuth1Input, OAuth1Output, OAuth2AuthorizeUrlInput, OAuth2AuthorizeUrlOutput,
  OAuth2CallbackResult, CookieManagerEntry, CookieManagerList,
  CookieJarEntry, CookieJar, AllCookieJars,
  ConsoleLogEntry, ScriptAssertionItem, ScriptSafeOutput,
} from "./requests";

export type {
  GraphQLExecuteInput, GraphQLResponse, GraphQLType, IntrospectOutput,
  SoapOperation, SoapPort, SoapService, WsdlSummary, SoapExecuteInput, SoapExecuteOutput,
  WsSecurityConfig, WsSecurityInput, WsSecurityOutput,
  MtomAttachment, MtomInput, MtomOutput, WsdlDiffOutput, SoapCoverageOutput,
  XsdValidateOutput, WsdlMockGenOutput,
  GrpcTlsConfig, GrpcMethodInfo, GrpcService, GrpcReflectOutput,
  GrpcLoadProtoInput,
  GrpcFieldDescriptor, GrpcDescribeInput, GrpcDescribeOutput,
  GrpcInvokeInput, GrpcInvokeOutput,
  MockRoute, MockStartInput, MockStartOutput, MockServerInfo, MockStatusOutput,
  RecordedInteraction, RecordStartInput, RecordStartOutput, RecordStopOutput,
  InteractionsOutput, ReplayStartInput, ReplayStartOutput, ReplayStatusOutput,
  JdbcInput, JdbcOutput,
  SSEConnectInput, SSEEvent, SSEResult,
} from "./protocols";

export type {
  AssertionType, Assertion, AssertionResult, AssertionEvalOutput,
  AssertionSuggestInput, AssertionSuggestion, AssertionSuggestOutput,
  BatchOutput, HealAssertionInput, HealCandidate, HealAssertionOutput,
  FlowStep, FlowRunInput, FlowStepResult, FlowTraceEvent, FlowDatasetResult, FlowRunOutput,
  TestStep, TestBuilderData, DataLoopInput, DataLoopRowResult, DataLoopOutput,
  FlowBlock, FlowBlockExecuteInput, FlowBlockResult, FlowBlockExecuteOutput,
  RetryTestInput, AttemptResult, RetryTestResult, RateLimitResult,
  IdempotencySnapshot, IdempotencyResult, PaginationInput, PageResult, PaginationResult,
  ContractDriftEntry, ContractDriftCheckResult,
  EnvRunResult, RequestStatusRow, MultiEnvResult,
  MultiEnvRequestTemplate, EnvRequestResult, ComparisonSummary,
  SingleRequestMultiEnvOutput, CollectionRequestRow, CollectionMultiEnvOutput,
  FlowVisualNode, FlowGraphResult,
  MonitorConfig, MonitorListOutput, WebhookConfig, WebhookListOutput,
  RunRequestResult, RunCollectionOutput, RunWithTraceOutput,
  ContractGuardViolation, ContractValidateGuardInput, ContractGuardOutput,
  PerRequestValidation, ContractCollectionOutput,
  JunitTestResult, ReportResultItem,
  ReportAssertionResult, ReportRequestResult, ReportGenerationInput,
  HtmlReportOutput, JunitReportOutput, JsonReportOutput, MarkdownReportOutput,
  FieldChange, ChangelogEntry, ChangelogResult,
  GeneratedAssertion, RequestAssertions, RegressionOutput,
  DependencyInfo, CycleInfo, DependencyResult,
  DepGraphNode, DepGraphEdge, DepGraphGroup, DepGraphResult,
  PipelineExtractor, PipelineStep, PipelineInput, PipelineStepResult,
  PipelineResult, PipelineValidationIssue, PipelineValidateOutput, PipelineTemplate,
  CliRunOutput, CliRunWithTraceOutput, TraceHtmlOutput,
} from "./testing";

export type {
  ResponseTrendsResult, SecurityAuditFinding, SecurityAuditResult,
  SslChainEntry, SslInspectResult, DnsAddress, DnsInspectResult,
  CompressionResult, RedirectHop, RedirectChainResult, ContentTypeResult,
  PatternLoadTestInput, LoadTestPhase, PatternLoadTestResult,
  HistogramBucket, LatencyHistogramResult, ThroughputWindow, ThroughputTimelineResult,
  ConnectionStatsResult, UserSimulationInput, UserStats, UserSimulationResult,
  SlaRule, SlaCheckInput, SlaRuleResult, SlaCheckResult,
  RunStats, MetricDelta, CompareRunsResult,
  WaterfallPhase, WaterfallResult, CurlLogEntry, CurlLogResult,
  MockDiffEntry, MockDiffInput, MockDiffResult,
  ErrorPattern, ErrorPatternsResult,
  DashboardMetricFilter, DashboardMetricDef, DashboardDataPoint, DashboardInput,
  DashboardMetricResult, DashboardResult,
  JwtInspectResult, TokenRefreshInput, TokenRefreshResult,
  CorsTestResult, InjectionFinding, InjectionScanResult,
  SensitiveFinding, SensitiveDataResult,
  LoadTestInput, LoadTestResult,
  LoadRunConfig, TimelinePoint, LoadRunResult,
  OWASPSeverity, OWASPScanType, OWASPFinding, OWASPScanInput, OWASPScanOutput,
  CompareResponsesInput, ResponseChangeEntry, CompareResponsesOutput,
  BodyDiffInput, BodyDiffStructuralChange, BodyDiffStats, BodyDiffOutput,
  BodyFormatInput, BodyFormatOutput,
  BodyMergeInput, BodyMergeConflict, BodyMergeOutput,
  RateLimitAnalyzeOutput, RateLimitTrackOutput,
  RateLimitStatusEntry, RateLimitStatusOutput,
  RateLimitHistoryPoint, RateLimitHistoryOutput,
  RequestDiffRef, RequestDiffInput, RequestDiffUrlDiff,
  RequestDiffHeaderChange, RequestDiffBodyDiff, RequestDiffAuthDiff, RequestDiffOutput,
  HeaderFinding, HeaderRecommendation, HeaderCachingAnalysis, HeaderCompressionAnalysis,
  HeaderInsightsOutput,
  BodySearchMatch, BodySearchOutput, BodySearchInput,
  JsonPathMatch, JsonPathOutput, XPathMatch, XPathOutput,
} from "./analysis";

export type { ParsedCurl, UniversalImportResult, ReplayDiff, ReplayOutput } from "./codegen";

export type {
  Snippet, SnippetCreate, SnippetUpdate, SnippetList, SnippetExport,
} from "./snippets";

export type {
  PerfBudget, PerfBudgetCreate, PerfBudgetUpdate, PerfCheckInput,
  PerfViolation, PerfCheckOutput, AutoBudgetInput, AutoBudgetOutput,
} from "./perfBudget";

export type {
  GoldenFile, SaveGoldenInput, CompareInput, AutoCompareInput,
  HeaderChange, BodyDiff, CompareOutput, AutoCompareOutput,
} from "./goldenFiles";

export type {
  HistoryEntryCreate, HistoryEntry as SidecarHistoryEntry, HistoryEntrySummary,
  HistoryListResponse, HistoryStats,
} from "./history";

export type {
  TestgenCategory, TestgenOperationSummary, TestgenParseOutput, TestgenGenerateOutput,
  AiChatContext, AiSuggestion, AiChatOutput,
  SmartSuggestInput, SmartSuggestOutput,
  ExploreIssue, ExploredEndpoint, ExploreApiResult,
} from "./ai";

export type {
  ServiceNode, ServiceEdge, ServiceGraph,
  ApiDocEndpoint, ApiDocOutput, ResponseSnapshot, TimelineOutput,
  SchemaValidationError, SchemaValidateOutput, SchemaGenerateOutput,
  SchemaDiffField, SchemaDiffOutput,
  RequestExample, RequestExampleInput,
  OpenApiImportInput, OpenApiImportOutput, OpenApiExportOutput,
  ContractValidateInput, ContractViolation, ContractValidateOutput,
  ObservedResponse, ContractDriftInput, ContractDriftOutput,
  VaultEntrySummary, VaultListOutput, VaultWriteInput, VaultRevealOutput,
  VariableInspectInput, VariableResolution, VariableInspectOutput,
  DependencyNode, DependencyEdge, DependencyGraphOutput,
  JsonDiffInput, JsonDifference, JsonDiffOutput,
  SnapshotWriteInput, SnapshotCompareInput, SnapshotCompareOutput,
  HarImportInput, HarImportOutput, TlsInspectInput, TlsInspectOutput,
  ProxyStartInput, ProxyStartOutput, ProxyStatusOutput,
  GitReviewChange, GitReviewOutput,
  TerminalOutput, CatalogEntry, GovernanceRule, GovernanceOutput,
  VersionDiffOutput, OpenApiSyncOutput,
  NpmInstallOutput, NpmExecuteOutput, CookieScriptOutput,
  TeamWorkspace, McpTool, McpManifest, McpInvokeOutput,
  ResolvedVariableItem, VariableResolveOutput,
  SemanticDiffChange, SemanticDiffInput, SemanticDiffOutput,
  ProjectSummary, ProjectEnvironment, ProjectCollection, YamlProject,
  HarNetworkEntryData, HarExportResult, PostmanExportResult,
  FailureNotifyInput, FailureNotifyResult,
  OpenApiEnhancedPreviewRequest, OpenApiEnhancedPreviewFolder, OpenApiEnhancedPreviewOutput,
  OpenApiEnhancedImportOutput,
  DocOptions, DocGenerateInput, DocGenerateOutput,
} from "./advanced";

export type {
  TagCount, TagListResponse, AssignTagsInput, RemoveTagInput,
  BulkAssignInput, TagSearchResult, TagSearchResponse,
} from "./tags";

export type {
  RenderOptions, TemplateRenderInput, TemplateRenderOutput,
  TemplateValidateInput, TemplateValidateOutput,
  TemplateExtractInput, TemplateExtractOutput,
} from "./templateEngine";

export type {
  FeatureArea, FeatureStatus, FeatureEntry, FeatureRegistryOutput,
  ReadinessCheck, ReadinessOutput, CollectionHealthIssue,
  CollectionHealthOutput, SampleWorkspaceOutput, RedactionPreviewOutput,
} from "./product";

export type {
  SilkBrowserCheckOutput, SilkRunInput, SilkRunOutput,
  SilkInstallBrowsersResponse, SilkScreenshotDiffInput, SilkScreenshotDiffOutput,
  SilkAutoSpecInput, SilkAutoSpecOutput,
  SilkMockRule, SilkA11yViolation, SilkBrowserRunResult,
  SilkRecordStartInput, SilkRecordStartOutput, SilkRecordStopOutput,
  SilkBaselineSaveInput, SilkBaselineSaveOutput,
  SilkBaselineCompareInput, SilkBaselineCompareOutput,
  SilkRunHistoryEntry,
} from "./silk";

export type {
  SpinScenario, SpinStep, SpinStepResult, SpinRunResult,
  SpinScenarioInfo, SpinScenarioListOutput, SpinDryRunOutput,
  SpinContractVerifyInput, SpinContractVerifyResult,
  SpinSchemaValidateInput, SpinSchemaValidateOutput,
  SpinDbSnapshotInput, SpinDbSnapshotOutput,
  SpinDbCompareInput, SpinDbCompareOutput,
  SpinPerfProbeInput, SpinPerfProbeOutput,
  SpinAssertionResult, SpinStepAssert,
} from "./spin";

// ---- Compose the unified sidecar object from all sub-modules ----

import { collectionsMethods } from "./collections";
import { environmentsMethods } from "./environments";
import { requestsMethods } from "./requests";
import { protocolsMethods } from "./protocols";
import { testingMethods } from "./testing";
import { analysisMethods } from "./analysis";
import { codegenMethods } from "./codegen";
import { aiMethods } from "./ai";
import { advancedMethods } from "./advanced";
import { historyMethods } from "./history";
import { snippetsMethods } from "./snippets";
import { perfBudgetMethods } from "./perfBudget";
import { goldenFilesMethods } from "./goldenFiles";
import { tagsMethods } from "./tags";
import { templateEngineMethods } from "./templateEngine";
import { productMethods } from "./product";
import { silkMethods } from "./silk";
import { spinMethods } from "./spin";

export const sidecar = {
  ...requestsMethods,
  ...collectionsMethods,
  ...environmentsMethods,
  ...protocolsMethods,
  ...testingMethods,
  ...analysisMethods,
  ...codegenMethods,
  ...aiMethods,
  ...advancedMethods,
  ...historyMethods,
  ...snippetsMethods,
  ...perfBudgetMethods,
  ...goldenFilesMethods,
  ...tagsMethods,
  ...templateEngineMethods,
  ...productMethods,
  ...silkMethods,
  ...spinMethods,
} as const;
