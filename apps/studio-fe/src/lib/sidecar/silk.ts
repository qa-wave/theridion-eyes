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
  /**
   * Optional ranked-candidate locator map from a previous recording.
   * When provided the spec is wrapped with a self-healing helper that falls
   * back through candidates when the primary locator fails.
   */
  locator_map?: Record<string, SilkElementLocators>;
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
  /** Self-healing locator substitutions that occurred during this run. */
  healed_locators: SilkHealedLocatorEvent[];
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
  /** Rectangular areas to exclude from the pixel diff (timestamps, ads, etc.). */
  ignore_regions?: SilkIgnoreRegion[];
  /**
   * Anti-aliasing tolerance [0–1].  Pixels whose 3×3 neighbourhood max-channel
   * variance is below this fraction are treated as AA edge pixels and ignored.
   * 0 = strict (default), 0.1 = light suppression.
   */
  anti_alias_tolerance?: number;
}

export interface SilkScreenshotDiffOutput {
  diff_path: string;
  pixel_diff_count: number;
  total_pixels: number;
  diff_ratio: number;
  passed: boolean;
  /** Number of pixels excluded from the diff (ignore_regions + AA suppression). */
  ignored_pixels: number;
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

// ---- Frameworks ----

export interface SilkFramework {
  id: string;
  label: string;
  kind: "web" | "mobile";
  file_extension: string;
  codegen_target: string | null;
  recordable: boolean;
  /** True when the framework records via Playwright codegen + transpile (e.g. Cypress, Selenium). */
  recordable_via_transpile: boolean;
  runnable: boolean;
  template: string;
}

// ---- Recording ----

export interface SilkRecordStartInput {
  url: string;
  workspace_dir?: string;
  /** Framework to use for codegen. Default: "playwright-ts". */
  framework?: string;
}

// ---- Spec save ----

export interface SilkSpecSaveInput {
  framework: string;
  filename: string;
  code: string;
  workspace_dir?: string;
}

export interface SilkSpecSaveOutput {
  spec_path: string;
}

export interface SilkRecordStartOutput {
  session_id: string;
  message: string;
}

export interface SilkRecordStopOutput {
  session_id: string;
  spec_text: string;
  spec_path: string | null;
  /** Ranked locator candidates extracted from the recorded spec (per primary selector). */
  locators: Record<string, SilkElementLocators>;
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
  /** Rectangular areas to exclude from the pixel diff. */
  ignore_regions?: SilkIgnoreRegion[];
  /** Anti-aliasing tolerance [0–1]. 0 = strict (default). */
  anti_alias_tolerance?: number;
}

export interface SilkBaselineCompareOutput {
  baseline_path: string;
  diff_path: string;
  pixel_diff_count: number;
  total_pixels: number;
  diff_ratio: number;
  passed: boolean;
  approved: boolean;
  /** Number of pixels excluded from the diff (ignore_regions + AA suppression). */
  ignored_pixels: number;
}

export interface SilkBaselineApproveInput {
  test_id: string;
  candidate_path: string;
  browser?: string;
  viewport?: string;
  approved_by?: string;
  diff_ratio?: number;
}

export interface SilkBaselineApproveOutput {
  baseline_path: string;
  test_id: string;
  browser: string;
  viewport: string;
  approved: boolean;
  approved_by: string;
  approved_at: string;
  diff_ratio: number;
}

// ---- Record save-and-run bridge ----

export interface SilkRecordSaveAndRunInput {
  session_id: string;
  framework?: string;
  filename?: string;
  workspace_dir?: string;
  browsers?: ("chromium" | "firefox" | "webkit")[];
  timeout_ms?: number;
}

export interface SilkRecordSaveAndRunOutput {
  spec_path: string;
  run: SilkRunOutput;
}

// ---- Self-healing locators ----

export interface SilkLocatorCandidate {
  priority: number;
  strategy: string;
  selector: string;
}

export interface SilkElementLocators {
  primary: SilkLocatorCandidate;
  candidates: SilkLocatorCandidate[];
}

/** One self-healing substitution event emitted during a run. */
export interface SilkHealedLocatorEvent {
  /** Original primary selector that failed. */
  primary: string;
  /** Fallback selector that succeeded. */
  healed: string;
  /** Strategy of the healed selector (e.g. "text", "css"). */
  strategy: string;
}

// ---- Ignore regions for visual diff ----

export interface SilkIgnoreRegion {
  x: number;
  y: number;
  width: number;
  height: number;
}

// ---- Attachment data (parsed from json_report) ----

export interface SilkNetworkEntry {
  request?: { method?: string; url?: string };
  response?: { status?: number; content?: { mimeType?: string } };
  [key: string]: unknown;
}

export interface SilkScreenshotInfo {
  path: string;
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

// ---- Publish config ----

/** Response from GET /api/silk/publish-config.  Tokens are never returned. */
export interface SilkPublishConfigOut {
  weave_url: string;
  /** True when a Weave token is stored (value is masked). */
  weave_token_set: boolean;
  hub_url: string;
  /** True when a Hub token is stored (value is masked). */
  hub_token_set: boolean;
  enabled: boolean;
}

/** Body for PUT /api/silk/publish-config. */
export interface SilkPublishConfigIn {
  weave_url?: string;
  /** Pass the real token to update it; pass empty string to keep existing. */
  weave_token?: string;
  hub_url?: string;
  /** Pass the real token to update it; pass empty string to keep existing. */
  hub_token?: string;
  enabled?: boolean;
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

  /** Fetch the list of supported test frameworks. */
  silkFrameworks(): Promise<{ frameworks: SilkFramework[] }> {
    return call<{ frameworks: SilkFramework[] }>("/api/silk/frameworks");
  },

  /** Save a manually authored spec to disk. */
  silkSpecSave(input: SilkSpecSaveInput): Promise<SilkSpecSaveOutput> {
    return call<SilkSpecSaveOutput>("/api/silk/spec/save", {
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

  /** Approve a candidate screenshot, promoting it to the stored baseline. */
  silkBaselineApprove(
    input: SilkBaselineApproveInput,
  ): Promise<SilkBaselineApproveOutput> {
    return call<SilkBaselineApproveOutput>("/api/silk/baseline/approve", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  /** Stop recording session, save the spec, and immediately run it. */
  silkRecordSaveAndRun(
    input: SilkRecordSaveAndRunInput,
  ): Promise<SilkRecordSaveAndRunOutput> {
    return call<SilkRecordSaveAndRunOutput>("/api/silk/record/save-and-run", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  // ---- Publish config ----

  /** Fetch the current publish config (tokens are masked — not returned). */
  silkGetPublishConfig(): Promise<SilkPublishConfigOut> {
    return call<SilkPublishConfigOut>("/api/silk/publish-config");
  },

  /** Save publish config.  Pass empty weave_token / hub_token to keep existing. */
  silkPutPublishConfig(input: SilkPublishConfigIn): Promise<SilkPublishConfigOut> {
    return call<SilkPublishConfigOut>("/api/silk/publish-config", {
      method: "PUT",
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
