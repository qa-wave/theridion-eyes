/**
 * Request history persistence types + sidecar methods.
 */

import { call } from "./client";

// ---- Types ---------------------------------------------------------------

export interface HistoryEntryCreate {
  method: string;
  url: string;
  status: number;
  elapsed_ms: number;
  timestamp: number;
  request_body?: string | null;
  response_body?: string | null;
  request_headers?: Record<string, string>;
  response_headers?: Record<string, string>;
}

export interface HistoryEntry {
  id: string;
  method: string;
  url: string;
  status: number;
  elapsed_ms: number;
  timestamp: number;
  request_body?: string | null;
  response_body?: string | null;
  request_headers?: Record<string, string>;
  response_headers?: Record<string, string>;
}

export interface HistoryEntrySummary {
  id: string;
  method: string;
  url: string;
  status: number;
  elapsed_ms: number;
  timestamp: number;
}

export interface HistoryListResponse {
  entries: HistoryEntrySummary[];
  total: number;
}

export interface HistoryStats {
  total: number;
  avg_response_time_ms: number;
  status_distribution: Record<string, number>;
  top_endpoints: Array<{ endpoint: string; count: number }>;
}

// ---- Methods -------------------------------------------------------------

export const historyMethods = {
  recordHistory: (entry: HistoryEntryCreate) =>
    call<HistoryEntry>("/api/history", {
      method: "POST",
      body: JSON.stringify(entry),
    }),

  listHistory: (params?: {
    method?: string;
    status?: number;
    search?: string;
    limit?: number;
    offset?: number;
  }) => {
    const sp = new URLSearchParams();
    if (params?.method) sp.set("method", params.method);
    if (params?.status !== undefined) sp.set("status", String(params.status));
    if (params?.search) sp.set("search", params.search);
    if (params?.limit !== undefined) sp.set("limit", String(params.limit));
    if (params?.offset !== undefined) sp.set("offset", String(params.offset));
    const qs = sp.toString();
    return call<HistoryListResponse>(`/api/history${qs ? `?${qs}` : ""}`);
  },

  getHistoryEntry: (id: string) =>
    call<HistoryEntry>(`/api/history/${id}`),

  getHistoryStats: () =>
    call<HistoryStats>("/api/history/stats"),

  clearHistory: () =>
    call<void>("/api/history", { method: "DELETE" }),

  deleteHistoryEntry: (id: string) =>
    call<void>(`/api/history/${id}`, { method: "DELETE" }),
} as const;
