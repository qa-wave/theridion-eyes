/**
 * Silk — Frontend testing module sidecar client.
 *
 * Wraps /api/silk/* endpoints (v2: recording, baselines, multi-browser,
 * a11y, history, mocks).
 */

import { call, getSidecarBaseUrl } from "./client";

// ---- Types ----------------------------------------------------------------

export interface SilkBrowserCheckOutput {
  installed: boolean;
  paths: string[];
}

export interface SilkMockRule {
  pattern: string;
  status?: number;
  body?: Record<string, unknown> | unknown[] | string | null;
  content_type?: string;
}

export interface SilkA11yViolation {
  rule: string;
  impact: string;
  description: string;
  nodes: string[];
}

export interface SilkBrowserRunResult {
  browser: string;
  exit_code: number;
  passed: number;
  failed: number;
  errors: number;
  duration_ms: number;
  trace_path: string | null;
  stderr_tail: string;
  json_report: Record<string, unknown> | null;
  a11y_violations: SilkA11yViolation[];
}

export interface SilkRunInput {
  spec_path?: string;
  inline_code?: string;
  env_vars?: Record<string, string>;
  timeout_ms?: number;
  workspace_dir?: string;
  /** Browser engines to target. Default: ["chromium"]. */
  browsers?: ("chromium" | "firefox" | "webkit")[];
  /** Network mock rules injected as page.route() wrappers. */
  mocks?: SilkMockRule[];
  /** Inject axe-core a11y audit after each navigation. */
  run_accessibility_audit?: boolean;
}

export interface SilkRunOutput {
  run_id: string;
  exit_code: number;
  passed: number;
  failed: number;
  errors: number;
  duration_ms: number;
  trace_path: string | null;
  json_report: Record<string, unknown> | null;
  stderr_tail: string;
  per_browser_results: Record<string, SilkBrowserRunResult>;
  a11y_violations: SilkA11yViolation[];
}

export interface SilkInstallBrowsersResponse {
  ok: boolean;
  message: string;
  browser_path: string | null;
}

export interface SilkScreenshotDiffInput {
  baseline_path: string;
  current_path: string;
  threshold?: number;
}

export interface SilkScreenshotDiffOutput {
  diff_path: string;
  pixel_diff_count: number;
  total_pixels: number;
  diff_ratio: number;
  passed: boolean;
}

export interface SilkAutoSpecInput {
  request_id: string;
  method: string;
  url: string;
  headers?: Record<string, string>;
  body?: string;
  status_code?: number;
  workspace_dir?: string;
}

export interface SilkAutoSpecOutput {
  spec_path: string;
  spec_code: string;
}

// ---- Recording ----

export interface SilkRecordStartInput {
  url: string;
  workspace_dir?: string;
}

export interface SilkRecordStartOutput {
  session_id: string;
  message: string;
}

export interface SilkRecordStopOutput {
  session_id: string;
  spec_text: string;
  spec_path: string | null;
}

// ---- Baseline management ----

export interface SilkBaselineSaveInput {
  screenshot_path: string;
  test_id: string;
  browser?: string;
  viewport?: string;
}

export interface SilkBaselineSaveOutput {
  baseline_path: string;
  test_id: string;
  browser: string;
  viewport: string;
}

export interface SilkBaselineCompareInput {
  current_path: string;
  test_id: string;
  browser?: string;
  viewport?: string;
  threshold?: number;
}

export interface SilkBaselineCompareOutput {
  baseline_path: string;
  diff_path: string;
  pixel_diff_count: number;
  total_pixels: number;
  diff_ratio: number;
  passed: boolean;
  approved: boolean;
}

// ---- Run history ----

export interface SilkRunHistoryEntry {
  id: string;
  spec_path: string;
  status: "passed" | "failed" | "error";
  duration_ms: number;
  started_at: string;
  browsers: string[];
  trace_path: string | null;
  screenshot_paths: string[];
  a11y_violations_count: number;
  stderr_tail: string;
  /** Only present in single-run detail endpoint. */
  json_report?: Record<string, unknown> | null;
}

// ---- Methods ----------------------------------------------------------------

export const silkMethods = {
  /** Check whether Playwright Chromium binaries are present locally. */
  silkCheckBrowsers(): Promise<SilkBrowserCheckOutput> {
    return call<SilkBrowserCheckOutput>("/api/silk/browsers/check");
  },

  /** Blocking Chromium install (non-streaming). ~150 MB download. */
  silkInstallBrowsersSync(): Promise<SilkInstallBrowsersResponse> {
    return call<SilkInstallBrowsersResponse>("/api/silk/install-browsers/sync", {
      method: "POST",
    });
  },

  /**
   * Open an SSE stream for Playwright Chromium installation progress.
   *
   * Returns an EventSource you must close when done.
   * Each ``message`` event carries a progress line; look for
   * ``DONE path=`` or ``ERROR `` in ``event.data``.
   */
  silkInstallBrowsersStream(token: string): Promise<EventSource> {
    return getSidecarBaseUrl().then((base) => {
      const url = `${base}/api/silk/install-browsers?token=${encodeURIComponent(token)}`;
      return new EventSource(url);
    });
  },

  /** Run a Playwright spec file and get a structured report. */
  silkRun(input: SilkRunInput): Promise<SilkRunOutput> {
    return call<SilkRunOutput>("/api/silk/run", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  /**
   * URL to download the trace ZIP for a completed run.
   * Pass to an <a href> or window.open().
   */
  silkTraceUrl(runId: string): Promise<string> {
    return getSidecarBaseUrl().then(
      (base) => `${base}/api/silk/trace/${encodeURIComponent(runId)}`,
    );
  },

  /** Pixel-diff two PNG images. Returns diff PNG path + stats. */
  silkScreenshotDiff(
    input: SilkScreenshotDiffInput,
  ): Promise<SilkScreenshotDiffOutput> {
    return call<SilkScreenshotDiffOutput>("/api/silk/screenshot-diff", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  /**
   * Generate a starter Playwright spec from a failed Strand request.
   */
  silkAutoSpec(input: SilkAutoSpecInput): Promise<SilkAutoSpecOutput> {
    return call<SilkAutoSpecOutput>("/api/silk/auto-spec", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  // ---- Recording ----

  /** Start a Playwright codegen session for the given URL. */
  silkRecordStart(input: SilkRecordStartInput): Promise<SilkRecordStartOutput> {
    return call<SilkRecordStartOutput>("/api/silk/record/start", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  /** Open SSE stream to receive live codegen output. */
  silkRecordStream(sessionId: string, token: string): Promise<EventSource> {
    return getSidecarBaseUrl().then((base) => {
      const url = `${base}/api/silk/record/stream/${encodeURIComponent(sessionId)}?token=${encodeURIComponent(token)}`;
      return new EventSource(url);
    });
  },

  /** Stop the codegen session and return the captured spec. */
  silkRecordStop(sessionId: string): Promise<SilkRecordStopOutput> {
    return call<SilkRecordStopOutput>("/api/silk/record/stop", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId }),
    });
  },

  // ---- Visual regression baseline ----

  /** Save a screenshot as the approved visual baseline. */
  silkBaselineSave(input: SilkBaselineSaveInput): Promise<SilkBaselineSaveOutput> {
    return call<SilkBaselineSaveOutput>("/api/silk/baseline/save", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  /** Compare current screenshot against saved baseline. */
  silkBaselineCompare(
    input: SilkBaselineCompareInput,
  ): Promise<SilkBaselineCompareOutput> {
    return call<SilkBaselineCompareOutput>("/api/silk/baseline/compare", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  // ---- Run history ----

  /** Fetch recent run history (newest first). */
  silkListRuns(limit = 50): Promise<SilkRunHistoryEntry[]> {
    return call<SilkRunHistoryEntry[]>(`/api/silk/runs?limit=${limit}`);
  },

  /** Fetch a single run by ID (includes full json_report). */
  silkGetRun(runId: string): Promise<SilkRunHistoryEntry> {
    return call<SilkRunHistoryEntry>(`/api/silk/runs/${encodeURIComponent(runId)}`);
  },
};
