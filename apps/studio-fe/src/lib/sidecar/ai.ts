/**
 * AI settings, test generation, smart suggest types + sidecar methods.
 */

import { call } from "./client";
import type { Assertion } from "./testing";

// ---- Testgen types -------------------------------------------------------

export type TestgenCategory = "is_alive" | "smoke" | "regression";

export interface TestgenOperationSummary {
  method: string;
  path: string;
  summary: string;
  has_path_params: boolean;
  has_request_body: boolean;
}

export interface TestgenParseOutput {
  kind: "openapi" | "wsdl" | "unknown";
  service_name: string;
  base_url: string;
  operations: TestgenOperationSummary[];
  expected_counts: Record<string, number>;
}

export interface TestgenGenerateOutput {
  collection_id: string;
  collection_name: string;
  counts: Record<string, number>;
}

// ---- AI Chat types ----------------------------------------------------------

export interface AiChatContext {
  collections?: string[];
  environment?: string;
  recent_responses?: string[];
}

export interface AiSuggestion {
  action: string;
  label: string;
}

export interface AiChatOutput {
  response: string;
  suggestions: AiSuggestion[];
  error?: string | null;
}

// ---- Smart Assert types ---------------------------------------------------

export interface SmartSuggestInput {
  method: string;
  url: string;
  status: number;
  response_body: string;
  response_headers?: Record<string, string>;
  response_time_ms?: number | null;
}

export interface SmartSuggestOutput {
  assertions: Assertion[];
}

// ---- Agent Explorer types ---------------------------------------------------

export interface ExploreIssue {
  severity: "error" | "warning" | "info";
  message: string;
  endpoint: string;
}

export interface ExploredEndpoint {
  method: string;
  path: string;
  status: number | null;
  elapsed_ms: number;
  size_bytes: number;
  content_type: string;
  issues: string[];
  body_preview: string;
}

export interface ExploreApiResult {
  endpoints_discovered: number;
  requests_sent: number;
  issues: ExploreIssue[];
  endpoints: ExploredEndpoint[];
  collection_id: string | null;
  elapsed_ms: number;
}

export const aiMethods = {
  aiSettings: () =>
    call<{ provider: string; ollama_base_url: string; ollama_model: string }>("/api/ai/settings"),
  updateAiSettings: (settings: { provider: string; ollama_base_url: string; ollama_model: string }) =>
    call<{ provider: string; ollama_base_url: string; ollama_model: string }>("/api/ai/settings", {
      method: "PUT",
      body: JSON.stringify(settings),
    }),
  aiPing: () => call<{ ok: boolean; version?: string; error?: string }>("/api/ai/ping"),
  aiModels: () => call<{ models: Array<{ name: string; size: number }> }>("/api/ai/models"),
  aiTestGen: (input: {
    method: string; url: string; headers: Record<string, string>;
    request_body: string | null; response_status: number;
    response_headers: Record<string, string>; response_body: string;
    category: string;
  }) =>
    call<{ assertions: Array<{ type: string; expected: string; path: string; operator: string }>; explanation: string }>(
      "/api/ai/testgen",
      { method: "POST", body: JSON.stringify(input) },
    ),
  testgenParse: (input: { content: string; base_url?: string | null }) =>
    call<TestgenParseOutput>("/api/testgen/parse", {
      method: "POST",
      body: JSON.stringify({ content: input.content, base_url: input.base_url ?? null }),
    }),
  testgenGenerate: (input: {
    content: string;
    base_url?: string | null;
    collection_name?: string | null;
    categories: TestgenCategory[];
  }) =>
    call<TestgenGenerateOutput>("/api/testgen/generate", {
      method: "POST",
      body: JSON.stringify({
        content: input.content,
        base_url: input.base_url ?? null,
        collection_name: input.collection_name ?? null,
        categories: input.categories,
      }),
    }),
  aiChat: (message: string, context?: AiChatContext) =>
    call<AiChatOutput>("/api/ai/chat", {
      method: "POST",
      body: JSON.stringify({ message, context }),
    }),
  smartSuggest: (input: SmartSuggestInput) =>
    call<SmartSuggestOutput>("/api/ai/suggest-from-response", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  exploreApi: (input: {
    base_url: string;
    max_requests?: number;
    methods?: string[];
    headers?: Record<string, string>;
    save_as_collection?: boolean;
    collection_name?: string;
  }) =>
    call<ExploreApiResult>("/api/agent/explore", {
      method: "POST",
      body: JSON.stringify(input),
    }),
} as const;
