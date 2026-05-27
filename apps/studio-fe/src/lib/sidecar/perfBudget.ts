/**
 * Performance Budget sidecar client methods and types.
 */

import { call } from "./client";

// ---- Types ----------------------------------------------------------------

export interface PerfBudget {
  id: string;
  url_pattern: string;
  method: string | null;
  max_time_ms: number;
  max_size_bytes: number | null;
  p95_time_ms: number | null;
  alert_threshold: number;
  name: string;
}

export interface PerfBudgetCreate {
  url_pattern: string;
  method?: string | null;
  max_time_ms: number;
  max_size_bytes?: number | null;
  p95_time_ms?: number | null;
  alert_threshold?: number;
  name?: string;
}

export interface PerfBudgetUpdate {
  url_pattern?: string;
  method?: string | null;
  max_time_ms?: number;
  max_size_bytes?: number | null;
  p95_time_ms?: number | null;
  alert_threshold?: number;
  name?: string;
}

export interface PerfCheckInput {
  url: string;
  method?: string | null;
  elapsed_ms: number;
  body_size?: number | null;
}

export interface PerfViolation {
  budget_id: string;
  budget_name: string;
  metric: string;
  actual: number;
  threshold: number;
  exceeded_by_percent: number;
  url: string;
  method: string | null;
  timestamp: number;
}

export interface PerfCheckOutput {
  violations: PerfViolation[];
  passed: string[];
}

export interface AutoBudgetInput {
  history: Array<{ url: string; method?: string; elapsed_ms: number; body_size?: number }>;
  multiplier?: number;
}

export interface AutoBudgetOutput {
  suggested: PerfBudget[];
}

// ---- Methods --------------------------------------------------------------

export const perfBudgetMethods = {
  listPerfBudgets: () => call<PerfBudget[]>("/api/perf/budgets"),

  createPerfBudget: (data: PerfBudgetCreate) =>
    call<PerfBudget>("/api/perf/budgets", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  updatePerfBudget: (id: string, data: PerfBudgetUpdate) =>
    call<PerfBudget>(`/api/perf/budgets/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  deletePerfBudget: (id: string) =>
    call<void>(`/api/perf/budgets/${id}`, { method: "DELETE" }),

  checkPerfBudget: (data: PerfCheckInput) =>
    call<PerfCheckOutput>("/api/perf/check", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getPerfViolations: () => call<PerfViolation[]>("/api/perf/violations"),

  autoPerfBudget: (data: AutoBudgetInput) =>
    call<AutoBudgetOutput>("/api/perf/auto-budget", {
      method: "POST",
      body: JSON.stringify(data),
    }),
} as const;
