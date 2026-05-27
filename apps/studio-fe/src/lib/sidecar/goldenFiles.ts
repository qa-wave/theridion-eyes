/**
 * Golden files — sidecar client methods for response caching / baseline comparison.
 */

import { call } from "./client";

// ---- Types ---------------------------------------------------------------

export interface GoldenFile {
  id: string;
  name: string;
  request_id: string | null;
  collection_id: string | null;
  url: string;
  method: string;
  status: number;
  headers: Record<string, string>;
  body: string;
  body_size: number;
  created_at: number;
  description: string;
}

export interface SaveGoldenInput {
  name?: string;
  request_id?: string | null;
  collection_id?: string | null;
  url: string;
  method?: string;
  status: number;
  headers?: Record<string, string>;
  body?: string;
  description?: string;
}

export interface CompareInput {
  golden_id: string;
  current: {
    status: number;
    headers: Record<string, string>;
    body: string;
  };
}

export interface AutoCompareInput {
  url: string;
  method?: string;
  status: number;
  headers?: Record<string, string>;
  body?: string;
}

export interface HeaderChange {
  key: string;
  type: "added" | "removed" | "changed";
  golden_value: string | null;
  current_value: string | null;
}

export interface BodyDiff {
  additions: number;
  deletions: number;
  changes: string[];
}

export interface CompareOutput {
  match: boolean;
  status_match: boolean;
  body_match: boolean;
  header_changes: HeaderChange[];
  body_diff: BodyDiff;
  score: number;
}

export interface AutoCompareOutput {
  found: boolean;
  golden_id: string | null;
  golden_name: string | null;
  comparison: CompareOutput | null;
}

// ---- Methods -------------------------------------------------------------

export const goldenFilesMethods = {
  saveGolden(input: SaveGoldenInput): Promise<GoldenFile> {
    return call("/api/golden/save", { method: "POST", body: JSON.stringify(input) });
  },

  listGolden(): Promise<GoldenFile[]> {
    return call("/api/golden", { method: "GET" });
  },

  getGolden(id: string): Promise<GoldenFile> {
    return call(`/api/golden/${id}`, { method: "GET" });
  },

  deleteGolden(id: string): Promise<{ status: string; id: string }> {
    return call(`/api/golden/${id}`, { method: "DELETE" });
  },

  compareGolden(input: CompareInput): Promise<CompareOutput> {
    return call("/api/golden/compare", { method: "POST", body: JSON.stringify(input) });
  },

  autoCompareGolden(input: AutoCompareInput): Promise<AutoCompareOutput> {
    return call("/api/golden/auto-compare", { method: "POST", body: JSON.stringify(input) });
  },
} as const;
