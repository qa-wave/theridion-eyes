import type {
  Assertion,
  AssertionResult,
  AuthConfig,
  CertConfig,
  ExecuteResponse,
  ExecuteRequestInput,
  RetryConfig,
  RetryAttemptInfo,
  SavedRequest,
} from "../lib/sidecar";
import { DEFAULT_RETRY_CONFIG } from "../lib/sidecar";

export type { Assertion, AssertionResult, AuthConfig, CertConfig, RetryConfig, RetryAttemptInfo };
export type Method = ExecuteRequestInput["method"];

export const METHODS: Method[] = [
  "GET",
  "POST",
  "PUT",
  "PATCH",
  "DELETE",
  "HEAD",
  "OPTIONS",
];

export interface Extractor {
  name: string;       // variable name to set (e.g., "auth_token")
  source: "body" | "header" | "status";
  path: string;       // JSONPath for body, header name for header
}

export interface RequestTab {
  id: string;
  /** When set, points to a saved request — Save updates in place. */
  savedAs: { collectionId: string; requestId: string } | null;
  name: string;
  method: Method;
  url: string;
  headersRaw: string;
  body: string;
  auth: AuthConfig;
  /** mTLS / client certificate configuration. */
  certConfig: CertConfig;
  assertions: Assertion[];
  assertionResults: AssertionResult[] | null;
  preRequestScript: string;
  postResponseScript: string;
  /** Free-form notes / description for this request (Markdown-compatible). */
  notes: string;
  /** Extractors for request chaining — pull values from responses into variables. */
  extractors: Extractor[];
  /** Retry configuration for transient errors. */
  retryConfig: RetryConfig;
  /** Attempt timeline from the last retry-enabled execution. */
  retryAttempts: RetryAttemptInfo[] | null;
  response: ExecuteResponse | null;
  error: string | null;
  busy: boolean;
  /** Snapshot of saved-on-disk state — used to compute the dirty bit. */
  cleanSignature: string;
  lastRunAt: number | null;
  pinned: boolean;
}

export const HTTP_METHOD_COLOR: Record<Method, string> = {
  GET: "text-sky-400",
  POST: "text-emerald-400",
  PUT: "text-amber-400",
  PATCH: "text-violet-400",
  DELETE: "text-rose-400",
  HEAD: "text-neutral-400",
  OPTIONS: "text-neutral-400",
};

export function newRequestTab(partial?: Partial<RequestTab>): RequestTab {
  const base: RequestTab = {
    id: crypto.randomUUID(),
    savedAs: null,
    name: "Untitled",
    method: "GET",
    url: "",
    headersRaw: "",
    body: "",
    auth: { type: "none" },
    certConfig: { client_cert_path: "", client_key_path: "", ca_bundle_path: "", verify_ssl: true },
    assertions: [],
    assertionResults: null,
    preRequestScript: "",
    postResponseScript: "",
    notes: "",
    extractors: [],
    retryConfig: { ...DEFAULT_RETRY_CONFIG },
    retryAttempts: null,
    response: null,
    error: null,
    busy: false,
    cleanSignature: "",
    lastRunAt: null,
    pinned: false,
  };
  const merged = { ...base, ...partial };
  return { ...merged, cleanSignature: signatureOf(merged) };
}

/** Compact, stable signature of the editable fields — used for dirty state. */
export function signatureOf(t: Partial<RequestTab>): string {
  return JSON.stringify({
    n: t.name,
    m: t.method,
    u: t.url,
    h: t.headersRaw,
    b: t.body,
    a: t.auth,
    cc: t.certConfig,
    t: t.assertions,
    s: t.preRequestScript,
    ps: t.postResponseScript,
    nt: t.notes,
    rc: t.retryConfig,
    ex: t.extractors,
  });
}

export function isDirty(t: RequestTab): boolean {
  // A never-saved tab is dirty as soon as the user puts anything in the URL —
  // but a fresh empty tab shouldn't show the unsaved indicator.
  if (t.savedAs === null) {
    return Boolean(t.url || t.headersRaw || t.body || t.auth.type !== "none");
  }
  return signatureOf(t) !== t.cleanSignature;
}

/** Parse multi-line "Name: value" header text to a record. Skips blanks/`#`. */
export function parseHeadersText(raw: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const idx = trimmed.indexOf(":");
    if (idx === -1) continue;
    const name = trimmed.slice(0, idx).trim();
    const value = trimmed.slice(idx + 1).trim();
    if (name) out[name] = value;
  }
  return out;
}

/** Inverse of parseHeadersText for round-tripping saved → editor state. */
export function headersToText(headers: Record<string, string>): string {
  return Object.entries(headers)
    .map(([k, v]) => `${k}: ${v}`)
    .join("\n");
}

export function tabFromSaved(
  collectionId: string,
  saved: SavedRequest,
): RequestTab {
  // tabFromSaved is only called with leaf request items (is_folder=false),
  // so request fields are populated — but the API type is permissive and
  // we fall back defensively to keep TS happy.
  return newRequestTab({
    savedAs: { collectionId, requestId: saved.id },
    name: saved.name,
    method: saved.method ?? "GET",
    url: saved.url ?? "",
    headersRaw: headersToText(saved.headers ?? {}),
    body: saved.body ?? "",
    auth: saved.auth ?? { type: "none" },
    assertions: saved.assertions ?? [],
    preRequestScript: saved.pre_request_script ?? "",
    postResponseScript: saved.post_response_script ?? "",
    notes: saved.notes ?? "",
    extractors: (saved.captures ?? []).map((c) => ({
      name: c.name,
      source: c.source ?? "body",
      path: c.path ?? "",
    })),
  });
}
