/**
 * Request execution, multipart, chaining types + sidecar methods.
 */

import { call } from "./client";
import type {
  AuthConfig, ExecuteRequestInput, ExecuteResponse, TimingBreakdown,
  CertInfo, VerifyChainResponse, SystemCertsResponse,
  RetryConfig, ExecuteWithRetryResponse,
} from "./types";
import type { HealthResponse } from "./client";

// ---- Multipart types ------------------------------------------------------

export interface FormField {
  key: string;
  value: string;
  is_file: boolean;
  filename?: string;
  content_type?: string;
}

export interface ExecuteMultipartInput {
  method: ExecuteRequestInput["method"];
  url: string;
  headers?: Record<string, string>;
  query?: Record<string, string>;
  fields: FormField[];
  auth?: AuthConfig | null;
  timeout_seconds?: number;
  follow_redirects?: boolean;
  environment_id?: string | null;
}

// ---- Request chaining types -----------------------------------------------

export interface CaptureRule {
  name: string;
  source: "body" | "header" | "status";
  path?: string;
}

export interface ExecuteWithCapturesInput {
  method: ExecuteRequestInput["method"];
  url: string;
  headers?: Record<string, string>;
  query?: Record<string, string>;
  body?: string | null;
  auth?: AuthConfig | null;
  timeout_seconds?: number;
  follow_redirects?: boolean;
  environment_id?: string | null;
  captures: CaptureRule[];
}

export interface ExecuteWithCapturesResponse {
  status: number;
  status_text: string;
  headers: Record<string, string>;
  body: string;
  body_size_bytes: number;
  elapsed_ms: number;
  timing?: TimingBreakdown | null;
  final_url: string;
  resolved_url?: string | null;
  captured_values: Record<string, string>;
}

// ---- OAuth2 types ---------------------------------------------------------

export interface OAuth2TokenInput {
  token_url: string;
  client_id: string;
  client_secret?: string;
  code: string;
  redirect_uri?: string;
  scope?: string;
  grant_type?: string;
  code_verifier?: string;
}

export interface OAuth2TokenOutput {
  access_token: string;
  token_type: string;
  expires_in: number | null;
  refresh_token: string | null;
  scope: string | null;
  raw: Record<string, unknown>;
}

// ---- OAuth 1.0 types --------------------------------------------------------

export interface OAuth1Input {
  consumer_key: string;
  consumer_secret: string;
  token?: string;
  token_secret?: string;
  url: string;
  method?: string;
}

export interface OAuth1Output {
  authorization_header: string;
  signed_url: string;
}

// ---- OAuth2 PKCE types ------------------------------------------------------

export interface OAuth2AuthorizeUrlInput {
  auth_url: string;
  client_id: string;
  redirect_uri?: string;
  scope?: string;
  state?: string;
  use_pkce?: boolean;
}

export interface OAuth2AuthorizeUrlOutput {
  url: string;
  state: string;
  code_verifier: string | null;
  code_challenge: string | null;
}

export interface OAuth2CallbackResult {
  status: "waiting" | "received" | "expired" | "not_running";
  code: string | null;
  state: string | null;
  error: string | null;
}

export interface OAuth2RefreshInput {
  token_url: string;
  refresh_token: string;
  client_id: string;
  client_secret?: string;
  scope?: string;
}

// ---- OAuth2 Client Credentials types ----------------------------------------

export interface OAuth2ClientCredentialsInput {
  token_url: string;
  client_id: string;
  client_secret: string;
  scope?: string;
  extra_params?: Record<string, string>;
  use_basic_auth?: boolean;
}

export interface OAuth2ClientCredentialsOutput {
  access_token: string;
  token_type: string;
  expires_in: number | null;
  scope: string | null;
  expires_at: number | null;
  raw: Record<string, unknown>;
}

// ---- OAuth2 token reuse types -----------------------------------------------

export interface OAuth2TokenReuseInput {
  access_token?: string;
  refresh_token?: string;
  expires_at?: number | null;
  token_url?: string;
  client_id?: string;
  client_secret?: string;
  scope?: string;
  expiry_buffer_seconds?: number;
}

export interface OAuth2TokenReuseOutput {
  status: "valid" | "refreshed" | "expired" | "unknown";
  access_token: string;
  refresh_token: string;
  expires_at: number | null;
  message: string;
}

// ---- OAuth2 Password grant types --------------------------------------------

export interface OAuth2PasswordInput {
  token_url: string;
  username: string;
  password: string;
  client_id: string;
  client_secret?: string;
  scope?: string;
}

// ---- Cookie Manager types ---------------------------------------------------

export interface CookieManagerEntry {
  name: string;
  value: string;
  domain: string;
  path?: string;
  env_id?: string | null;
}

export interface CookieManagerList {
  cookies: CookieManagerEntry[];
}

// ---- Cookie Jar types (per-environment, full-featured) ----------------------

export interface CookieJarEntry {
  name: string;
  value: string;
  domain: string;
  path: string;
  expires: string | null;
  httponly: boolean;
  secure: boolean;
  samesite: string | null;
}

export interface CookieJar {
  environment_id: string;
  cookies: CookieJarEntry[];
}

export interface AllCookieJars {
  jars: Record<string, CookieJar>;
}

// ---- Script execution types -------------------------------------------------

export interface ScriptAssertionItem {
  passed: boolean;
  message: string;
}

export interface ScriptSafeOutput {
  variables: Record<string, string>;
  headers: Record<string, string>;
  logs: string[];
  assertions: ScriptAssertionItem[];
  error: string | null;
}

// ---- Console Log types ------------------------------------------------------

export interface ConsoleLogEntry {
  timestamp?: string;
  method?: string;
  url?: string;
  status?: number;
  elapsed_ms?: number;
  request_headers?: Record<string, string>;
  response_headers?: Record<string, string>;
  request_body?: string | null;
  response_body?: string | null;
}

export const requestsMethods = {
  health: () => call<HealthResponse>("/api/health"),
  execute: (input: ExecuteRequestInput) =>
    call<ExecuteResponse>("/api/requests/execute", {
      method: "POST",
      body: JSON.stringify({
        timeout_seconds: 30,
        follow_redirects: true,
        ...input,
      }),
    }),
  executeWithRetry: (input: ExecuteRequestInput, retry: Omit<RetryConfig, "enabled">) =>
    call<ExecuteWithRetryResponse>("/api/requests/execute-with-retry", {
      method: "POST",
      body: JSON.stringify({
        timeout_seconds: 30,
        follow_redirects: true,
        ...input,
        retry: {
          max_retries: retry.max_retries,
          retry_on: retry.retry_on,
          backoff_strategy: retry.backoff_strategy,
          backoff_base_ms: retry.backoff_base_ms,
          backoff_max_ms: retry.backoff_max_ms,
        },
      }),
    }),
  executeMultipart: (input: ExecuteMultipartInput) =>
    call<ExecuteResponse>("/api/requests/execute-multipart", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  executeChain: (input: ExecuteWithCapturesInput) =>
    call<ExecuteWithCapturesResponse>("/api/requests/execute-chain", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  extractVariables: (input: {
    response_body: string;
    response_headers: Record<string, string>;
    response_status: number;
    rules: CaptureRule[];
  }) =>
    call<{ extracted: Record<string, string | null> }>("/api/requests/extract", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  oauth2Token: (input: OAuth2TokenInput) =>
    call<OAuth2TokenOutput>("/api/auth/oauth2/token", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  oauth1Sign: (input: OAuth1Input) =>
    call<OAuth1Output>("/api/auth/oauth1", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  oauth2AuthorizeUrl: (input: OAuth2AuthorizeUrlInput) =>
    call<OAuth2AuthorizeUrlOutput>("/api/auth/oauth2/authorize-url", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  oauth2StartCallback: (port?: number, timeoutSeconds?: number) =>
    call<{ port: number; status: string }>("/api/auth/oauth2/callback-server/start", {
      method: "POST",
      body: JSON.stringify({ port: port ?? 9876, timeout_seconds: timeoutSeconds ?? 300 }),
    }),
  oauth2PollResult: () =>
    call<OAuth2CallbackResult>("/api/auth/oauth2/callback-server/result"),
  oauth2StopCallback: () =>
    call<{ status: string }>("/api/auth/oauth2/callback-server/stop", { method: "POST" }),
  oauth2Refresh: (input: OAuth2RefreshInput) =>
    call<OAuth2TokenOutput>("/api/auth/oauth2/refresh", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  oauth2ClientCredentials: (input: OAuth2ClientCredentialsInput) =>
    call<OAuth2ClientCredentialsOutput>("/api/auth/oauth2/client-credentials", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  oauth2TokenReuse: (input: OAuth2TokenReuseInput) =>
    call<OAuth2TokenReuseOutput>("/api/auth/oauth2/token-reuse", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  oauth2Password: (input: OAuth2PasswordInput) =>
    call<OAuth2TokenOutput>("/api/auth/oauth2/password", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  // executeScript (Node.js subprocess) removed — P0 security: arbitrary code execution.
  // Use executeScriptSafe (safe DSL) or template engine {{$timestamp}} etc. instead.
  // See docs/security/scripts-deprecation.md
  executeScriptSafe: (input: {
    script: string;
    phase: "pre" | "post";
    context: Record<string, unknown>;
  }) =>
    call<ScriptSafeOutput>("/api/scripts/execute-safe", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  encodeForm: (fields: Array<{ key: string; value: string; type: string }>) =>
    call<{ encoded_body: string; content_type: string }>("/api/requests/encode-form", {
      method: "POST",
      body: JSON.stringify({ fields }),
    }),
  getAllCookies: () => call<CookieManagerList>("/api/cookies/all"),
  deleteCookiesByDomain: async (domain: string) => {
    const { getSidecarBaseUrl: getUrl } = await import("./client");
    const baseUrl = await getUrl();
    const r = await fetch(`${baseUrl}/api/cookies/domain/${domain}`, { method: "DELETE" });
    if (!r.ok) throw new Error(`delete cookies ${r.status}`);
  },
  editCookies: (cookies: CookieManagerEntry[]) =>
    call<CookieManagerList>("/api/cookies/edit", {
      method: "PUT",
      body: JSON.stringify({ cookies }),
    }),
  // Cookie jar (per-environment)
  listCookieJars: (envId?: string) =>
    call<AllCookieJars>(`/api/cookies${envId ? `?env_id=${envId}` : ""}`),
  getCookieJar: (envId: string) => call<CookieJar>(`/api/cookies/${envId}`),
  setCookie: (envId: string, cookie: Omit<CookieJarEntry, "expires" | "httponly" | "secure" | "samesite"> & Partial<Pick<CookieJarEntry, "expires" | "httponly" | "secure" | "samesite">>) =>
    call<CookieJar>(`/api/cookies/${envId}`, {
      method: "PUT",
      body: JSON.stringify(cookie),
    }),
  deleteCookie: async (envId: string, cookieName: string) => {
    const { getSidecarBaseUrl: getUrl } = await import("./client");
    const baseUrl = await getUrl();
    const r = await fetch(`${baseUrl}/api/cookies/${envId}/${cookieName}`, { method: "DELETE" });
    if (!r.ok) throw new Error(`delete cookie ${r.status}`);
  },
  clearCookieJar: async (envId?: string) => {
    const { getSidecarBaseUrl: getUrl } = await import("./client");
    const baseUrl = await getUrl();
    const r = await fetch(`${baseUrl}/api/cookies${envId ? `?env_id=${envId}` : ""}`, { method: "DELETE" });
    if (!r.ok) throw new Error(`clear cookies ${r.status}`);
  },
  consoleLog: (entries: ConsoleLogEntry[]) =>
    call<{ stored: number }>("/api/console/log", {
      method: "POST",
      body: JSON.stringify({ entries }),
    }),
  consoleEntries: () => call<{ entries: ConsoleLogEntry[]; total: number }>("/api/console/entries"),
  generateFake: (type: string, count?: number) =>
    call<{ values: string[] }>(`/api/generate/fake?type=${type}&count=${count ?? 1}`),

  // ---- Certificate inspection -----------------------------------------------
  inspectCert: (certPath: string) =>
    call<CertInfo>("/api/certs/inspect", {
      method: "POST",
      body: JSON.stringify({ cert_path: certPath }),
    }),
  verifyChain: (certPath: string, caBundlePath: string) =>
    call<VerifyChainResponse>("/api/certs/verify-chain", {
      method: "POST",
      body: JSON.stringify({ cert_path: certPath, ca_bundle_path: caBundlePath }),
    }),
  listSystemCerts: () => call<SystemCertsResponse>("/api/certs/system"),
} as const;
