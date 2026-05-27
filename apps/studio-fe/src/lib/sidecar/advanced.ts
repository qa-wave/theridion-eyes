/**
 * Advanced/misc types + sidecar methods: secrets, variables, snapshots, proxy,
 * service map, API docs, timeline, schema validation, workspace, projects, etc.
 */

import { call, getSidecarBaseUrl } from "./client";
import type { AuthConfig, ExecuteRequestInput } from "./types";

// ---- Service Map types ---------------------------------------------------

export interface ServiceNode {
  id: string; label: string; url: string; x: number; y: number; color: string;
}
export interface ServiceEdge {
  id: string; source: string; target: string; label: string;
}
export interface ServiceGraph {
  nodes: ServiceNode[]; edges: ServiceEdge[];
}

// ---- API Doc types -------------------------------------------------------

export interface ApiDocEndpoint {
  path: string; method: string; summary: string; description: string;
  parameters: Array<Record<string, unknown>>; tags: string[];
}
export interface ApiDocOutput {
  title: string; version: string; description: string; base_url: string;
  endpoints: ApiDocEndpoint[];
}

// ---- Timeline types ------------------------------------------------------

export interface ResponseSnapshot {
  timestamp: number; status: number; body_hash: string; body_preview: string;
  elapsed_ms: number; body_size: number; changes: string[];
}
export interface TimelineOutput {
  request_id: string; snapshots: ResponseSnapshot[];
}

// ---- Schema Validation types ---------------------------------------------

export interface SchemaValidationError {
  path: string; message: string; schema_path: string;
}

export interface SchemaValidateOutput {
  valid: boolean; errors: SchemaValidationError[];
}

export interface SchemaGenerateOutput {
  schema: Record<string, unknown>;
}

export interface SchemaDiffField {
  path: string; kind: string; detail: string;
}

export interface SchemaDiffOutput {
  added: SchemaDiffField[]; removed: SchemaDiffField[]; changed: SchemaDiffField[];
}

// ---- Request Example types -----------------------------------------------

export interface RequestExample {
  id: string;
  name: string;
  method: ExecuteRequestInput["method"];
  url: string;
  headers: Record<string, string>;
  body?: string | null;
  auth?: AuthConfig | null;
  notes?: string | null;
}

export type RequestExampleInput = Omit<RequestExample, "id"> & { id?: string | null };

// ---- OpenAPI types -------------------------------------------------------

export interface OpenApiImportInput {
  content: string;
  format?: "auto" | "json" | "yaml";
  collection_name?: string | null;
  base_url?: string | null;
}

export interface OpenApiImportOutput {
  collection_id: string;
  collection_name: string;
  request_count: number;
}

export interface OpenApiExportOutput {
  openapi: Record<string, unknown>;
}

// ---- Contract Validation types -------------------------------------------

export interface ContractValidateInput {
  openapi_content: string;
  method: ExecuteRequestInput["method"];
  path: string;
  status?: number;
  headers?: Record<string, string>;
  body?: string;
}

export interface ContractViolation {
  path: string;
  message: string;
}

export interface ContractValidateOutput {
  passed: boolean;
  operation_id?: string | null;
  expected_statuses: string[];
  violations: ContractViolation[];
}

export interface ObservedResponse {
  method: ExecuteRequestInput["method"];
  path: string;
  status: number;
  body?: string;
  headers?: Record<string, string>;
}

export interface ContractDriftInput {
  openapi_content: string;
  collection_id?: string | null;
  observed?: ObservedResponse[];
}

export interface ContractDriftOutput {
  missing_in_collection: string[];
  undocumented_requests: string[];
  failing_observations: ContractValidateOutput[];
  passed_observations: number;
}

// ---- Vault types --------------------------------------------------------

export interface VaultEntrySummary {
  name: string;
  updated_at: string;
}

export interface VaultListOutput {
  entries: VaultEntrySummary[];
}

export interface VaultWriteInput {
  passphrase: string;
  value: string;
}

export interface VaultRevealOutput {
  name: string;
  value: string;
}

// ---- Variable Inspector types -------------------------------------------

export interface VariableInspectInput {
  text: string;
  environment_id?: string | null;
  collection_id?: string | null;
  runtime?: Record<string, string>;
}

export interface VariableResolution {
  name: string;
  source: "runtime" | "environment" | "collection" | "global" | "builtin" | "unresolved";
  value?: string | null;
  resolved: boolean;
}

export interface VariableInspectOutput {
  resolved_text: string;
  variables: VariableResolution[];
}

// ---- Dependency Graph types ---------------------------------------------

export interface DependencyNode {
  id: string;
  name: string;
  produces: string[];
  consumes: string[];
}

export interface DependencyEdge {
  from_id: string;
  to_id: string;
  variable: string;
}

export interface DependencyGraphOutput {
  nodes: DependencyNode[];
  edges: DependencyEdge[];
  unresolved_variables: string[];
}

// ---- JSON Diff types ----------------------------------------------------

export interface JsonDiffInput {
  left: string;
  right: string;
  ignore_paths?: string[];
  unordered_arrays?: boolean;
}

export interface JsonDifference {
  path: string;
  kind: "added" | "removed" | "changed";
  left?: unknown;
  right?: unknown;
}

export interface JsonDiffOutput {
  equal: boolean;
  differences: JsonDifference[];
}

// ---- Snapshot types -----------------------------------------------------

export interface SnapshotWriteInput {
  value: string;
  metadata?: Record<string, string>;
}

export interface SnapshotCompareInput {
  value: string;
  ignore_paths?: string[];
  unordered_arrays?: boolean;
}

export interface SnapshotCompareOutput {
  exists: boolean;
  diff?: JsonDiffOutput | null;
}

// ---- HAR types ----------------------------------------------------------

export interface HarImportInput {
  content: string;
  collection_name?: string;
}

export interface HarImportOutput {
  collection_id: string;
  request_count: number;
}

// ---- TLS Inspect types --------------------------------------------------

export interface TlsInspectInput {
  url: string;
  timeout_seconds?: number;
}

export interface TlsInspectOutput {
  host: string;
  port: number;
  subject: Record<string, string>;
  issuer: Record<string, string>;
  not_before?: string | null;
  not_after?: string | null;
  san: string[];
  tls_version?: string | null;
  cipher?: string | null;
}

// ---- Proxy types --------------------------------------------------------

export interface ProxyStartInput {
  target_base_url: string;
  port?: number | null;
}

export interface ProxyStartOutput {
  session_id: string;
  port: number;
  target_base_url: string;
}

export interface ProxyStatusOutput {
  sessions: ProxyStartOutput[];
}

// ---- Git Review types ---------------------------------------------------

export interface GitReviewChange {
  file: string;
  summary: string;
  details: string[];
}

export interface GitReviewOutput {
  changes: GitReviewChange[];
}

// ---- Terminal types ---------------------------------------------------------

export interface TerminalOutput {
  stdout: string;
  stderr: string;
  exit_code: number;
}

// ---- Catalog types ----------------------------------------------------------

export interface CatalogEntry {
  id?: string;
  name: string;
  version?: string;
  spec_url?: string;
  owner?: string;
  tags?: string[];
  status?: "active" | "deprecated";
}

// ---- Governance types -------------------------------------------------------

export interface GovernanceRule {
  rule: string;
  passed: boolean;
  message: string;
}

export interface GovernanceOutput {
  score: number;
  rules: GovernanceRule[];
}

// ---- Version Diff types -----------------------------------------------------

export interface VersionDiffOutput {
  breaking_changes: string[];
  non_breaking: string[];
  added: string[];
  removed: string[];
  summary: string;
}

// ---- OpenAPI Sync types -----------------------------------------------------

export interface OpenApiSyncOutput {
  in_sync: boolean;
  missing_in_collection: string[];
  extra_in_collection: string[];
  drifted: string[];
}

// ---- NPM Loader types ------------------------------------------------------

export interface NpmInstallOutput {
  installed: boolean;
  path: string;
  error?: string | null;
}

export interface NpmExecuteOutput {
  stdout: string;
  stderr: string;
  exit_code: number;
}

// ---- Cookie Scripting types -------------------------------------------------

export interface CookieScriptOutput {
  cookies_modified: Record<string, string>;
  result: string;
  error?: string | null;
}

// ---- Team Workspace types ---------------------------------------------------

export interface TeamWorkspace {
  id?: string;
  name: string;
  collections?: string[];
  environments?: string[];
  members?: string[];
}

// ---- MCP types --------------------------------------------------------------

export interface McpTool {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

export interface McpManifest {
  name: string;
  version: string;
  tools: McpTool[];
}

export interface McpInvokeOutput {
  result: Record<string, unknown>;
  error?: string | null;
}

// ---- Variable Inspector (resolve) types -------------------------------------

export interface ResolvedVariableItem {
  name: string;
  value: string;
  source: "global" | "collection" | "environment" | "builtin" | "unresolved";
  overridden_by: string | null;
}

export interface VariableResolveOutput {
  variables: ResolvedVariableItem[];
  resolved_text: string;
}

// ---- Semantic Diff types --------------------------------------------------

export interface SemanticDiffChange {
  path: string;
  type: "added" | "removed" | "changed";
  old_value: unknown;
  new_value: unknown;
}

export interface SemanticDiffInput {
  body_a: string;
  body_b: string;
  ignore_keys?: string[];
  ignore_array_order?: boolean;
}

export interface SemanticDiffOutput {
  identical: boolean;
  changes: SemanticDiffChange[];
}

// ---- YAML Project types -----------------------------------------------------

export interface ProjectSummary {
  name: string;
  collection_count: number;
  environment_count: number;
  created_at: string | null;
}

export interface ProjectEnvironment {
  name: string;
  variables: Record<string, string>;
}

export interface ProjectCollection {
  name: string;
  requests: Array<Record<string, unknown>>;
  variables: Record<string, string>;
}

export interface YamlProject {
  name: string;
  created_at: string | null;
  collections: ProjectCollection[];
  environments: ProjectEnvironment[];
}

// ---- HAR Export types -------------------------------------------------------

export interface HarNetworkEntryData {
  method: string;
  url: string;
  status: number;
  request_headers: Record<string, string>;
  response_headers: Record<string, string>;
  request_body: string | null;
  response_body: string;
  elapsed_ms: number;
  timestamp: number;
}

export interface HarExportResult {
  har_json: string;
}

// ---- Postman Export types ---------------------------------------------------

export interface PostmanExportResult {
  postman_json: string;
}

// ---- Failure Notify types ---------------------------------------------------

export interface FailureNotifyInput {
  webhook_url: string;
  collection_name: string;
  failed_requests: Array<{ name: string; status: number; error: string }>;
  total: number;
  passed: number;
  failed: number;
}

export interface FailureNotifyResult {
  ok: boolean;
  status_code: number;
  error: string | null;
}

// ---- Enhanced OpenAPI Import types ------------------------------------------

export interface OpenApiEnhancedPreviewRequest {
  method: string;
  path: string;
  name: string;
}

export interface OpenApiEnhancedPreviewFolder {
  name: string;
  request_count: number;
  requests: OpenApiEnhancedPreviewRequest[];
}

export interface OpenApiEnhancedPreviewOutput {
  title: string;
  version: string;
  base_url: string;
  folder_count: number;
  request_count: number;
  folders: OpenApiEnhancedPreviewFolder[];
  auth_detected: string | null;
  warnings: string[];
}

export interface OpenApiEnhancedImportOutput {
  collection_id: string;
  collection_name: string;
  request_count: number;
  folder_count: number;
  warnings: string[];
}

// ---- Doc Generator types ----------------------------------------------------

export interface DocOptions {
  title?: string;
  description?: string;
  base_url?: string;
  include_examples?: boolean;
  include_headers?: boolean;
  group_by?: "folder" | "method" | "tag";
}

export interface DocGenerateInput {
  collection_id: string;
  format: "html" | "markdown" | "openapi";
  options?: DocOptions;
}

export interface DocGenerateOutput {
  content: string;
  format: string;
  endpoint_count: number;
}

export const advancedMethods = {
  getServiceMap: () => call<ServiceGraph>("/api/servicemap"),
  saveServiceMap: (graph: ServiceGraph) =>
    call<ServiceGraph>("/api/servicemap", { method: "PUT", body: JSON.stringify(graph) }),
  discoverServices: () => call<ServiceGraph>("/api/servicemap/discover", { method: "POST" }),
  addServiceNode: (node: { label: string; url?: string; x?: number; y?: number; color?: string }) =>
    call<ServiceGraph>("/api/servicemap/nodes", { method: "POST", body: JSON.stringify(node) }),
  deleteServiceNode: (nodeId: string) =>
    call<ServiceGraph>(`/api/servicemap/nodes/${nodeId}`, { method: "DELETE" }),
  addServiceEdge: (edge: { source: string; target: string; label?: string }) =>
    call<ServiceGraph>("/api/servicemap/edges", { method: "POST", body: JSON.stringify(edge) }),
  deleteServiceEdge: (edgeId: string) =>
    call<ServiceGraph>(`/api/servicemap/edges/${edgeId}`, { method: "DELETE" }),
  parseApiDoc: (input: { content?: string; url?: string }) =>
    call<ApiDocOutput>("/api/apidocs/parse", { method: "POST", body: JSON.stringify(input) }),
  recordTimeline: (input: { request_id: string; status: number; body: string; headers: Record<string, string>; elapsed_ms: number }) =>
    call<TimelineOutput>("/api/timeline/record", { method: "POST", body: JSON.stringify(input) }),
  getTimeline: (requestId: string) => call<TimelineOutput>(`/api/timeline/${requestId}`),
  exportWorkspace: () => getSidecarBaseUrl().then((base) => `${base}/api/workspace/export`),
  validateSchema: (body: string, schema: string | Record<string, unknown>) =>
    call<SchemaValidateOutput>("/api/schema/validate", {
      method: "POST",
      body: JSON.stringify({ body, schema }),
    }),
  generateSchema: (body: string) =>
    call<SchemaGenerateOutput>("/api/schema/generate", {
      method: "POST",
      body: JSON.stringify({ body }),
    }),
  diffSchemas: (old: Record<string, unknown> | string, newSchema: Record<string, unknown> | string) =>
    call<SchemaDiffOutput>("/api/schema/diff", {
      method: "POST",
      body: JSON.stringify({ old, new: newSchema }),
    }),
  listSecrets: () => call<VaultListOutput>("/api/advanced/secrets"),
  writeSecret: (name: string, input: VaultWriteInput) =>
    call<VaultEntrySummary>(`/api/advanced/secrets/${encodeURIComponent(name)}`, {
      method: "PUT",
      body: JSON.stringify(input),
    }),
  revealSecret: (name: string, passphrase: string) =>
    call<VaultRevealOutput>(`/api/advanced/secrets/${encodeURIComponent(name)}/reveal`, {
      method: "POST",
      body: JSON.stringify({ passphrase }),
    }),
  deleteSecret: async (name: string) => {
    const baseUrl = await getSidecarBaseUrl();
    const r = await fetch(`${baseUrl}/api/advanced/secrets/${encodeURIComponent(name)}`, {
      method: "DELETE",
    });
    if (!r.ok && r.status !== 204) throw new Error(`delete secret ${r.status}`);
  },
  inspectVariables: (input: VariableInspectInput) =>
    call<VariableInspectOutput>("/api/advanced/variables/inspect", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  dependencyGraph: (collectionId: string) =>
    call<DependencyGraphOutput>(`/api/advanced/collections/${collectionId}/dependency-graph`),
  diffJson: (input: JsonDiffInput) =>
    call<JsonDiffOutput>("/api/advanced/diff/json", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  saveSnapshot: (name: string, input: SnapshotWriteInput) =>
    call<{ name: string; status: string }>(`/api/advanced/snapshots/${encodeURIComponent(name)}`, {
      method: "PUT",
      body: JSON.stringify(input),
    }),
  compareSnapshot: (name: string, input: SnapshotCompareInput) =>
    call<SnapshotCompareOutput>(`/api/advanced/snapshots/${encodeURIComponent(name)}/compare`, {
      method: "POST",
      body: JSON.stringify(input),
    }),
  importHar: (input: HarImportInput) =>
    call<HarImportOutput>("/api/advanced/har/import", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  exportHar: (collectionId: string) =>
    call<Record<string, unknown>>(`/api/advanced/har/export/${collectionId}`),
  inspectTls: (input: TlsInspectInput) =>
    call<TlsInspectOutput>("/api/advanced/tls/inspect", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  proxyStart: (input: ProxyStartInput) =>
    call<ProxyStartOutput>("/api/advanced/proxy/start", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  proxyStatus: () => call<ProxyStatusOutput>("/api/advanced/proxy/status"),
  proxyStop: (sessionId: string) =>
    call<{ status: string; session_id: string }>(`/api/advanced/proxy/${sessionId}/stop`, {
      method: "POST",
    }),
  proxyHar: (sessionId: string) =>
    call<Record<string, unknown>>(`/api/advanced/proxy/${sessionId}/har`),
  gitReview: (repoPath: string) =>
    call<GitReviewOutput>("/api/advanced/git/review", {
      method: "POST",
      body: JSON.stringify({ repo_path: repoPath }),
    }),
  openApiImport: (input: OpenApiImportInput) =>
    call<OpenApiImportOutput>("/api/advanced/openapi/import", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  openApiExport: (collectionId: string) =>
    call<OpenApiExportOutput>(`/api/advanced/openapi/export/${collectionId}`),
  validateContract: (input: ContractValidateInput) =>
    call<ContractValidateOutput>("/api/advanced/contracts/validate", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  detectContractDrift: (input: ContractDriftInput) =>
    call<ContractDriftOutput>("/api/advanced/contracts/drift", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  terminalExec: (command: string, cwd?: string) =>
    call<TerminalOutput>("/api/terminal/exec", {
      method: "POST",
      body: JSON.stringify({ command, cwd }),
    }),
  getKeybindings: () => call<{ bindings: Record<string, string> }>("/api/settings/keybindings"),
  putKeybindings: (bindings: Record<string, string>) =>
    call<{ bindings: Record<string, string> }>("/api/settings/keybindings", {
      method: "PUT",
      body: JSON.stringify({ bindings }),
    }),
  generateDocs: (input: DocGenerateInput) =>
    call<DocGenerateOutput>("/api/docs/generate", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  listCatalog: () => call<{ entries: CatalogEntry[] }>("/api/catalog"),
  createCatalogEntry: (entry: CatalogEntry) =>
    call<CatalogEntry>("/api/catalog", {
      method: "POST",
      body: JSON.stringify(entry),
    }),
  updateCatalogEntry: (id: string, entry: CatalogEntry) =>
    call<CatalogEntry>(`/api/catalog/${id}`, {
      method: "PUT",
      body: JSON.stringify(entry),
    }),
  deleteCatalogEntry: async (id: string) => {
    const baseUrl = await getSidecarBaseUrl();
    const r = await fetch(`${baseUrl}/api/catalog/${id}`, { method: "DELETE" });
    if (!r.ok) throw new Error(`delete catalog ${r.status}`);
  },
  lintSpec: (spec: string) =>
    call<GovernanceOutput>("/api/governance/lint", {
      method: "POST",
      body: JSON.stringify({ spec }),
    }),
  compareVersions: (v1_spec: string, v2_spec: string) =>
    call<VersionDiffOutput>("/api/versioning/compare", {
      method: "POST",
      body: JSON.stringify({ v1_spec, v2_spec }),
    }),
  syncOpenapi: (input: { collection_id: string; spec_url: string }) =>
    call<OpenApiSyncOutput>("/api/sync/openapi", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  encryptProject: (passphrase: string) =>
    call<{ status: string; files_encrypted: number }>("/api/security/encrypt-project", {
      method: "POST",
      body: JSON.stringify({ passphrase }),
    }),
  decryptProject: (passphrase: string) =>
    call<{ status: string; files_encrypted: number }>("/api/security/decrypt-project", {
      method: "POST",
      body: JSON.stringify({ passphrase }),
    }),
  encryptSecretValue: (value: string, passphrase: string) =>
    call<{ encrypted: string; decrypted: string }>("/api/security/encrypt-secret", {
      method: "POST",
      body: JSON.stringify({ value, passphrase }),
    }),
  decryptSecretValue: (value: string, passphrase: string) =>
    call<{ encrypted: string; decrypted: string }>("/api/security/decrypt-secret", {
      method: "POST",
      body: JSON.stringify({ value, passphrase }),
    }),
  fetchSecretFromProvider: (provider: string, config: Record<string, string>) =>
    call<{ name: string; value: string; error: string | null }>("/api/secrets/fetch", {
      method: "POST",
      body: JSON.stringify({ provider, config }),
    }),
  pacResolve: (pac_content: string, url: string) =>
    call<{ proxy_url: string | null }>("/api/proxy/pac-resolve", {
      method: "POST",
      body: JSON.stringify({ pac_content, url }),
    }),
  npmInstallModule: (module_name: string) =>
    call<NpmInstallOutput>("/api/scripts/install-module", {
      method: "POST",
      body: JSON.stringify({ module_name }),
    }),
  npmExecuteWithModules: (script: string, modules: string[]) =>
    call<NpmExecuteOutput>("/api/scripts/execute-with-modules", {
      method: "POST",
      body: JSON.stringify({ script, modules }),
    }),
  cookieScript: (script: string, cookies: Record<string, string>) =>
    call<CookieScriptOutput>("/api/scripts/cookie-api", {
      method: "POST",
      body: JSON.stringify({ script, cookies }),
    }),
  groovyExecute: () => call<import("./types").StubOutput>("/api/scripts/groovy", { method: "POST" }),
  listTeamWorkspaces: () => call<{ workspaces: TeamWorkspace[] }>("/api/workspaces"),
  createTeamWorkspace: (workspace: TeamWorkspace) =>
    call<TeamWorkspace>("/api/workspaces", {
      method: "POST",
      body: JSON.stringify(workspace),
    }),
  updateTeamWorkspace: (id: string, workspace: TeamWorkspace) =>
    call<TeamWorkspace>(`/api/workspaces/${id}`, {
      method: "PUT",
      body: JSON.stringify(workspace),
    }),
  deleteTeamWorkspace: async (id: string) => {
    const baseUrl = await getSidecarBaseUrl();
    const r = await fetch(`${baseUrl}/api/workspaces/${id}`, { method: "DELETE" });
    if (!r.ok) throw new Error(`delete workspace ${r.status}`);
  },
  notifyIntegration: (input: { provider: string; url: string; message: string; payload?: Record<string, unknown> }) =>
    call<{ ok: boolean; status_code: number; error: string | null }>("/api/integrations/notify", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  mcpManifest: () => call<McpManifest>("/api/mcp/manifest"),
  mcpInvoke: (tool: string, args: Record<string, unknown>) =>
    call<McpInvokeOutput>("/api/mcp/invoke", {
      method: "POST",
      body: JSON.stringify({ tool, arguments: args }),
    }),
  vscodeStatus: () => call<{ status: string; version: string; uptime_seconds: number }>("/api/vscode/status"),
  vscodeCollections: () =>
    call<{ collections: Array<{ id: string; name: string; request_count: number }> }>("/api/vscode/collections"),
  visualize: (template: string, data: unknown) =>
    call<{ html: string }>("/api/visualize/render", {
      method: "POST",
      body: JSON.stringify({ template, data }),
    }),
  resolveVariables: (input: { text: string; environment_id?: string | null; collection_id?: string | null }) =>
    call<VariableResolveOutput>("/api/variables/resolve", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  semanticDiff: (input: SemanticDiffInput) =>
    call<SemanticDiffOutput>("/api/diff/semantic", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  listProjects: () =>
    call<ProjectSummary[]>("/api/projects"),
  getProject: (name: string) =>
    call<YamlProject>(`/api/projects/${encodeURIComponent(name)}`),
  createProject: (name: string) =>
    call<YamlProject>("/api/projects", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  exportToYaml: (collectionId: string) =>
    call<{ project_name: string }>(
      `/api/projects/_/export-from-collection/${collectionId}`,
      { method: "POST" },
    ),
  deleteProject: async (name: string) => {
    const baseUrl = await getSidecarBaseUrl();
    const r = await fetch(`${baseUrl}/api/projects/${encodeURIComponent(name)}`, {
      method: "DELETE",
    });
    if (!r.ok && r.status !== 204) throw new Error(`delete project ${r.status}`);
  },
  exportHarFromEntries: (entries: HarNetworkEntryData[]) =>
    call<HarExportResult>("/api/export/har", {
      method: "POST",
      body: JSON.stringify({ entries }),
    }),
  exportPostman: (collectionId: string) =>
    call<PostmanExportResult>(`/api/export/postman/${collectionId}`, { method: "POST" }),
  notifyOnFailure: (input: FailureNotifyInput) =>
    call<FailureNotifyResult>("/api/integrations/notify-on-failure", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  openApiImportPreview: (input: { source: string; collection_name?: string; base_url_override?: string }) =>
    call<OpenApiEnhancedPreviewOutput>("/api/import/openapi/preview", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  openApiImportFull: (input: { source: string; collection_name?: string; base_url_override?: string }) =>
    call<OpenApiEnhancedImportOutput>("/api/import/openapi", {
      method: "POST",
      body: JSON.stringify(input),
    }),
} as const;
