/**
 * Shared types used across multiple sidecar domain modules.
 */

export type AuthType =
  | "none"
  | "bearer"
  | "basic"
  | "apikey"
  | "oauth2_code"        // Authorization Code + PKCE (interactive browser flow)
  | "oauth2_cc"          // Client Credentials (server-to-server)
  | "oauth2_password";   // Resource Owner Password (deprecated, legacy only)

export interface AuthConfig {
  type: AuthType;
  // Bearer
  token?: string;
  // Basic
  username?: string;
  password?: string;
  // API Key
  key?: string;
  value?: string;
  add_to?: "header" | "query";
  // OAuth2 — fields shared across all OAuth2 flows
  oauth2_token_url?: string;
  oauth2_client_id?: string;
  oauth2_client_secret?: string;
  oauth2_scope?: string;
  // OAuth2 Authorization Code + PKCE only
  oauth2_auth_url?: string;
  oauth2_use_pkce?: boolean;
  // OAuth2 cached token (populated after "Get Token" succeeds)
  oauth2_access_token?: string;
  oauth2_refresh_token?: string;
  oauth2_expires_at?: number;   // Unix timestamp
  // OAuth2 Client Credentials extra params (e.g. audience)
  oauth2_extra_params?: Record<string, string>;
  oauth2_use_basic_auth?: boolean;
  // OAuth2 Resource Owner Password
  oauth2_username?: string;
  oauth2_password?: string;
}

export interface TimingBreakdown {
  dns_ms: number;
  connect_ms: number;
  tls_ms: number;
  server_processing_ms: number;
  transfer_ms: number;
  total_ms: number;
}

export interface ExecuteRequestInput {
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE" | "HEAD" | "OPTIONS";
  url: string;
  headers?: Record<string, string>;
  query?: Record<string, string>;
  body?: string | null;
  auth?: AuthConfig | null;
  timeout_seconds?: number;
  follow_redirects?: boolean;
  environment_id?: string | null;
  collection_id?: string | null;
  client_cert?: string | null;
  client_key?: string | null;
  ca_bundle_path?: string | null;
  verify_ssl?: boolean;
}

/** mTLS / client certificate configuration for a request. */
export interface CertConfig {
  client_cert_path: string;
  client_key_path: string;
  ca_bundle_path: string;
  verify_ssl: boolean;
}

/** Certificate inspection result from /api/certs/inspect. */
export interface CertInfo {
  subject: Record<string, string>;
  issuer: Record<string, string>;
  not_before: string;
  not_after: string;
  serial: string;
  fingerprint_sha256: string;
  is_expired: boolean;
  extensions: string[];
}

export interface VerifyChainResponse {
  valid: boolean;
  error: string | null;
}

export interface SystemCertEntry {
  subject: string;
  fingerprint_sha256: string;
}

export interface SystemCertsResponse {
  certificates: SystemCertEntry[];
  count: number;
}

export interface ExecuteResponse {
  status: number;
  status_text: string;
  headers: Record<string, string>;
  body: string;
  body_size_bytes: number;
  elapsed_ms: number;
  timing?: TimingBreakdown | null;
  final_url: string;
  resolved_url?: string | null;
  cookies?: Record<string, string>;
}

// ---- Retry types -----------------------------------------------------------

export type BackoffStrategy = "fixed" | "linear" | "exponential" | "jitter";

export interface RetryConfig {
  enabled: boolean;
  max_retries: number;
  retry_on: number[];
  backoff_strategy: BackoffStrategy;
  backoff_base_ms: number;
  backoff_max_ms: number;
}

export const DEFAULT_RETRY_CONFIG: RetryConfig = {
  enabled: false,
  max_retries: 3,
  retry_on: [429, 500, 502, 503, 504],
  backoff_strategy: "exponential",
  backoff_base_ms: 1000,
  backoff_max_ms: 30000,
};

export interface RetryAttemptInfo {
  attempt: number;
  status: number;
  elapsed_ms: number;
  waited_ms: number;
}

export interface ExecuteWithRetryResponse {
  final_response: ExecuteResponse;
  attempts: RetryAttemptInfo[];
  total_elapsed_ms: number;
  retried: boolean;
}

export interface EnvVariable {
  name: string;
  value: string;
  enabled: boolean;
}

export interface Environment {
  id: string;
  name: string;
  variables: EnvVariable[];
}

export interface EnvironmentSummary {
  id: string;
  name: string;
  variable_count: number;
}

export interface CollectionVariable {
  name: string;
  value: string;
  enabled: boolean;
}

// ---- Stub output (JMS, MQTT, Groovy, AMF) -----------------------------------

export interface StubOutput {
  status: string;
  message: string;
}
