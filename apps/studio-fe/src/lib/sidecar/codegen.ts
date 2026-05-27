/**
 * Code generation, cURL, import/export types + sidecar methods.
 */

import { call } from "./client";
import type { AuthConfig, ExecuteRequestInput } from "./types";

// ---- cURL types ---------------------------------------------------------

export interface ParsedCurl {
  method: ExecuteRequestInput["method"];
  url: string;
  headers: Record<string, string>;
  body: string | null;
  auth: AuthConfig | null;
}

// ---- Universal Import types -------------------------------------------------

export interface UniversalImportResult {
  format_detected: string;
  collection_id: string;
  collection_name: string;
  request_count: number;
  warnings: string[];
}

// ---- Traffic Replay types ---------------------------------------------------

export interface ReplayDiff {
  request_name: string;
  method: string;
  url: string;
  original_status: number;
  replay_status: number;
  status_match: boolean;
  body_match: boolean;
  body_diffs: Array<{ path: string; original: unknown; replayed: unknown }>;
  header_diffs: Array<{ path: string; original: unknown; replayed: unknown }>;
  original_elapsed_ms: number;
  replay_elapsed_ms: number;
}

export interface ReplayOutput {
  total_requests: number;
  replayed: number;
  matches: number;
  diffs: number;
  errors: number;
  results: ReplayDiff[];
  collection_id: string | null;
  elapsed_ms: number;
}

export const codegenMethods = {
  parseCurl: (curl: string) =>
    call<ParsedCurl>("/api/curl/parse", {
      method: "POST",
      body: JSON.stringify({ curl }),
    }),
  generateCurl: (input: {
    method: string;
    url: string;
    headers?: Record<string, string>;
    body?: string | null;
    auth?: AuthConfig | null;
  }) =>
    call<{ curl: string }>("/api/curl/generate", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  exportCurl: (collectionId: string) =>
    call<{ commands: string[]; count: number }>(
      `/api/collections/${collectionId}/export-curl`,
      { method: "POST" },
    ),
  generateCode: (input: {
    method: string; url: string; headers: Record<string, string>;
    body: string | null; language: string;
  }) =>
    call<{ language: string; code: string }>("/api/codegen/generate", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  importCollection: (content: string, format?: string) =>
    call<{ collection_id: string; collection_name: string; request_count: number }>(
      "/api/import",
      { method: "POST", body: JSON.stringify({ content, format: format ?? "auto" }) },
    ),
  universalImport: (content: string, filename?: string, format?: string) =>
    call<UniversalImportResult>("/api/import/universal", {
      method: "POST",
      body: JSON.stringify({ content, filename, format: format ?? "auto" }),
    }),
  replayHar: (input: { har_content: string; environment_id?: string; collection_name?: string; ignore_paths?: string[] }) =>
    call<ReplayOutput>("/api/replay/from-har", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  replayCollection: (input: { collection_id: string; environment_id?: string }) =>
    call<ReplayOutput>("/api/replay/run-collection", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  toBru: (collection: Record<string, unknown>) =>
    call<{ content: string }>("/api/format/to-bru", {
      method: "POST",
      body: JSON.stringify({ collection }),
    }),
  fromBru: (content: string) =>
    call<{ collection: Record<string, unknown> }>("/api/format/from-bru", {
      method: "POST",
      body: JSON.stringify({ content }),
    }),
  toYaml: (collection: Record<string, unknown>) =>
    call<{ content: string }>("/api/format/to-yaml", {
      method: "POST",
      body: JSON.stringify({ collection }),
    }),
  fromYaml: (content: string) =>
    call<{ collection: Record<string, unknown> }>("/api/format/from-yaml", {
      method: "POST",
      body: JSON.stringify({ content }),
    }),
  explodeCollection: (collectionId: string) =>
    call<{ files_created: number; directory: string }>(`/api/format/explode/${collectionId}`, { method: "POST" }),
  implodeCollection: (directory: string) =>
    call<{ collection_id: string; items_loaded: number }>("/api/format/implode", {
      method: "POST",
      body: JSON.stringify({ directory }),
    }),
} as const;
