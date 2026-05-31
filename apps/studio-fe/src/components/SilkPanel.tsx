/**
 * SilkPanel — Frontend testing module (Playwright runner panel v2).
 *
 * Layout:
 *   Left sidebar   — run history list (persistent + in-session)
 *   Center         — trace viewer: timeline, browser tabs, stderr
 *   Right sidebar  — spec source / network / screenshots / a11y / console
 *
 * New in v2:
 *   - Run history (loaded from sidecar DB on mount)
 *   - Record new spec (Playwright codegen integration)
 *   - Multi-browser tab switcher
 *   - A11y violations tab with impact badges
 *   - Approve baseline button in screenshot diff view
 *   - Network mocks section in run form
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Download,
  ExternalLink,
  FileCode,
  Globe,
  History,
  Image,
  MonitorPlay,
  Play,
  Plus,
  RefreshCw,
  Square,
  Terminal,
  Video,
  XCircle,
} from "lucide-react";
import { EmptyState } from "./EmptyState";
import { NewTestDialog } from "./NewTestDialog";
import { sidecar } from "../lib/sidecar";
import { getSidecarBaseUrl, getSidecarToken } from "../lib/sidecar/client";
import type {
  SilkA11yViolation,
  SilkBrowserRunResult,
  SilkFramework,
  SilkNetworkEntry,
  SilkRunHistoryEntry,
  SilkRunOutput,
} from "../lib/sidecar/silk";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SessionRun {
  run: SilkRunOutput;
  specLabel: string;
  startedAt: number;
  traceUrl?: string;
}

type ActiveTab = "timeline" | "network" | "screenshots" | "a11y" | "console";

// ---------------------------------------------------------------------------
// Status helpers
// ---------------------------------------------------------------------------

function StatusIcon({
  status,
  size = 12,
}: {
  status: "passed" | "failed" | "error" | "running";
  size?: number;
}) {
  if (status === "passed")
    return <CheckCircle2 size={size} className="text-emerald-400 shrink-0" />;
  if (status === "failed")
    return <XCircle size={size} className="text-red-400 shrink-0" />;
  if (status === "error")
    return <AlertCircle size={size} className="text-amber-400 shrink-0" />;
  return <RefreshCw size={size} className="text-neutral-400 animate-spin shrink-0" />;
}

function ImpactBadge({ impact }: { impact: string }) {
  const colors: Record<string, string> = {
    critical: "bg-red-900/60 text-red-300 border-red-800",
    serious: "bg-orange-900/60 text-orange-300 border-orange-800",
    moderate: "bg-amber-900/60 text-amber-300 border-amber-800",
    minor: "bg-neutral-800 text-neutral-400 border-neutral-700",
  };
  const cls = colors[impact] ?? colors.minor;
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[9px] font-medium uppercase ${cls}`}>
      {impact}
    </span>
  );
}

function durationLabel(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

// ---------------------------------------------------------------------------
// Attachment parsers (mirror Python _parse_network_entries / _parse_screenshot_paths)
// ---------------------------------------------------------------------------

function extractNetworkEntries(report: Record<string, unknown> | null): SilkNetworkEntry[] {
  if (!report) return [];
  const entries: SilkNetworkEntry[] = [];

  function walkSuites(suites: unknown[]): void {
    for (const suite of suites) {
      if (typeof suite !== "object" || !suite) continue;
      const s = suite as Record<string, unknown>;
      for (const spec of (s.specs as unknown[] | undefined) ?? []) {
        if (typeof spec !== "object" || !spec) continue;
        for (const test of ((spec as Record<string, unknown>).tests as unknown[] | undefined) ?? []) {
          if (typeof test !== "object" || !test) continue;
          for (const result of ((test as Record<string, unknown>).results as unknown[] | undefined) ?? []) {
            if (typeof result !== "object" || !result) continue;
            for (const att of ((result as Record<string, unknown>).attachments as unknown[] | undefined) ?? []) {
              if (typeof att !== "object" || !att) continue;
              const a = att as Record<string, unknown>;
              if (a.name !== "network.json" && a.name !== "har.json") continue;
              const body = a.body as string | undefined;
              if (!body) continue;
              try {
                const data = JSON.parse(body) as Record<string, unknown>;
                const ents = (data.log as Record<string, unknown> | undefined)?.entries as SilkNetworkEntry[] | undefined;
                if (Array.isArray(ents)) entries.push(...ents);
              } catch {
                // ignore malformed
              }
            }
          }
        }
      }
      walkSuites((s.suites as unknown[] | undefined) ?? []);
    }
  }

  walkSuites((report.suites as unknown[] | undefined) ?? []);
  return entries;
}

function extractScreenshotPaths(report: Record<string, unknown> | null): string[] {
  if (!report) return [];
  const paths: string[] = [];

  function walkSuites(suites: unknown[]): void {
    for (const suite of suites) {
      if (typeof suite !== "object" || !suite) continue;
      const s = suite as Record<string, unknown>;
      for (const spec of (s.specs as unknown[] | undefined) ?? []) {
        if (typeof spec !== "object" || !spec) continue;
        for (const test of ((spec as Record<string, unknown>).tests as unknown[] | undefined) ?? []) {
          if (typeof test !== "object" || !test) continue;
          for (const result of ((test as Record<string, unknown>).results as unknown[] | undefined) ?? []) {
            if (typeof result !== "object" || !result) continue;
            for (const att of ((result as Record<string, unknown>).attachments as unknown[] | undefined) ?? []) {
              if (typeof att !== "object" || !att) continue;
              const a = att as Record<string, unknown>;
              const ct = String(a.contentType ?? "");
              const name = String(a.name ?? "");
              const path = String(a.path ?? "");
              if (path && (ct.startsWith("image/") || name.toLowerCase().includes("screenshot") || path.endsWith(".png"))) {
                paths.push(path);
              }
            }
          }
        }
      }
      walkSuites((s.suites as unknown[] | undefined) ?? []);
    }
  }

  walkSuites((report.suites as unknown[] | undefined) ?? []);
  return paths;
}

function timeAgo(isoOrMs: string | number): string {
  const ms = typeof isoOrMs === "number" ? isoOrMs : Date.parse(isoOrMs);
  const diff = Date.now() - ms;
  if (diff < 60_000) return "just now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return new Date(ms).toLocaleDateString();
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Browser tab switcher for per_browser_results. */
function BrowserTabBar({
  browsers,
  active,
  onSelect,
  results,
}: {
  browsers: string[];
  active: string;
  onSelect: (b: string) => void;
  results: Record<string, SilkBrowserRunResult>;
}) {
  if (browsers.length <= 1) return null;
  return (
    <div className="flex gap-1 border-b border-neutral-800 px-3 py-1.5">
      {browsers.map((b) => {
        const r = results[b];
        const ok = r?.exit_code === 0;
        return (
          <button
            key={b}
            onClick={() => onSelect(b)}
            className={`flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-medium transition-colors ${
              active === b
                ? "bg-neutral-800 text-neutral-100"
                : "text-neutral-500 hover:text-neutral-300 hover:bg-neutral-900"
            }`}
          >
            {ok ? (
              <CheckCircle2 size={10} className="text-emerald-400" />
            ) : (
              <XCircle size={10} className="text-red-400" />
            )}
            {b}
          </button>
        );
      })}
    </div>
  );
}

/** Step timeline extracted from Playwright JSON report. */
interface PlaywrightSuite {
  title: string;
  specs?: PlaywrightSpec[];
  suites?: PlaywrightSuite[];
}
interface PlaywrightSpec {
  title: string;
  ok: boolean;
  tests?: Array<{
    status: string;
    results?: Array<{ duration: number; error?: { message: string } }>;
  }>;
}

function flattenSpecs(suite: PlaywrightSuite): PlaywrightSpec[] {
  const out: PlaywrightSpec[] = [];
  (suite.specs ?? []).forEach((s) => out.push(s));
  (suite.suites ?? []).forEach((s) => out.push(...flattenSpecs(s)));
  return out;
}

function StepTimeline({ report }: { report: Record<string, unknown> | null }) {
  if (!report)
    return (
      <div className="flex items-center justify-center h-full text-xs text-neutral-600">
        No report data
      </div>
    );

  const suites = (report.suites as PlaywrightSuite[] | undefined) ?? [];
  const allSpecs = suites.flatMap(flattenSpecs);

  if (allSpecs.length === 0)
    return (
      <div className="flex items-center justify-center h-full text-xs text-neutral-600">
        No test steps found
      </div>
    );

  return (
    <div className="flex flex-col gap-1 overflow-y-auto p-2">
      {allSpecs.map((spec, i) => {
        const result = spec.tests?.[0]?.results?.[0];
        const duration = result?.duration ?? 0;
        const errorMsg = result?.error?.message;
        return (
          <div
            key={i}
            className={`flex items-start gap-2 rounded p-2 text-xs ${
              spec.ok
                ? "bg-emerald-950/40 border border-emerald-900/40"
                : "bg-red-950/40 border border-red-900/40"
            }`}
          >
            {spec.ok ? (
              <CheckCircle2 size={12} className="mt-0.5 shrink-0 text-emerald-400" />
            ) : (
              <XCircle size={12} className="mt-0.5 shrink-0 text-red-400" />
            )}
            <div className="flex-1 min-w-0">
              <div className="text-neutral-200 font-medium truncate">{spec.title}</div>
              {errorMsg && (
                <div className="mt-0.5 text-red-400 text-[10px] line-clamp-3 font-mono">
                  {errorMsg}
                </div>
              )}
            </div>
            <div className="shrink-0 flex items-center gap-1 text-neutral-500">
              <Clock size={10} />
              {duration}ms
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** A11y violations list. */
function A11yPanel({ violations }: { violations: SilkA11yViolation[] }) {
  if (violations.length === 0)
    return (
      <div className="flex items-center justify-center h-32 text-xs text-emerald-500 gap-1.5">
        <CheckCircle2 size={14} />
        No accessibility violations
      </div>
    );

  return (
    <div className="flex flex-col gap-2 overflow-y-auto p-2">
      {violations.map((v, i) => (
        <div key={i} className="rounded border border-neutral-800 bg-neutral-900 p-2.5">
          <div className="flex items-center justify-between gap-2 mb-1">
            <span className="text-xs font-medium text-neutral-200 font-mono">{v.rule}</span>
            <ImpactBadge impact={v.impact} />
          </div>
          <p className="text-[10px] text-neutral-400 mb-1.5">{v.description}</p>
          {v.nodes.length > 0 && (
            <details className="text-[10px]">
              <summary className="cursor-pointer text-neutral-500 hover:text-neutral-400">
                {v.nodes.length} affected element(s)
              </summary>
              <ul className="mt-1 space-y-0.5 font-mono">
                {v.nodes.map((n, ni) => (
                  <li key={ni} className="text-neutral-500 truncate">{n}</li>
                ))}
              </ul>
            </details>
          )}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Install dialog
// ---------------------------------------------------------------------------

function InstallDialog({
  onDone,
  onCancel,
}: {
  onDone: () => void;
  onCancel: () => void;
}) {
  const [log, setLog] = useState<string[]>(["Starting download (~150 MB)…"]);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    sidecar
      .silkInstallBrowsersSync()
      .then((res) => {
        if (cancelled) return;
        if (res.ok) {
          setLog((prev) => [...prev, `Done. Path: ${res.browser_path ?? "unknown"}`]);
          setDone(true);
          setTimeout(onDone, 1200);
        } else {
          setError(res.message);
        }
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [onDone]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [log]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-[520px] rounded-lg border border-neutral-800 bg-neutral-925 shadow-2xl p-5 flex flex-col gap-4">
        <div className="flex items-center gap-2 text-neutral-100">
          <Download size={18} className="text-emerald-400" />
          <h2 className="font-semibold text-sm">Install Playwright Chromium</h2>
        </div>
        <div
          ref={logRef}
          className="h-48 overflow-y-auto rounded bg-neutral-950 p-3 font-mono text-xs text-neutral-400 select-text"
        >
          {log.map((line, i) => <div key={i}>{line}</div>)}
          {error && <div className="text-red-400 mt-1">Error: {error}</div>}
          {done && <div className="text-emerald-400 mt-1">Chromium ready.</div>}
        </div>
        <div className="flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="rounded px-3 py-1.5 text-xs bg-neutral-800 hover:bg-neutral-700 text-neutral-300 transition-colors"
          >
            {done || error ? "Close" : "Cancel"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Record dialog
// ---------------------------------------------------------------------------

/**
 * SSE streaming via fetch — works under Tauri where EventSource cannot send
 * the X-Theridion-Token auth header.  We open a streaming fetch, read lines,
 * and accumulate them in state.  The abort controller lets us cancel early
 * when the user hits "Stop recording" or "Cancel".
 */
async function* _fetchSSELines(
  url: string,
  token: string | null,
  signal: AbortSignal,
): AsyncGenerator<string> {
  const headers: Record<string, string> = {};
  if (token) headers["X-Theridion-Token"] = token;
  const res = await fetch(url, { headers, signal });
  if (!res.ok || !res.body) return;
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const parts = buf.split("\n");
    buf = parts.pop() ?? "";
    for (const part of parts) {
      const trimmed = part.trim();
      if (trimmed.startsWith("data:")) {
        yield trimmed.slice(5).trim();
      }
    }
  }
}

function RecordDialog({
  onCapture,
  onRunNow,
  onCancel,
}: {
  /** Called when recording stops and user wants to just keep the spec text. */
  onCapture: (specCode: string, specPath: string | null) => void;
  /** Called when user wants to save + immediately run the recorded spec. */
  onRunNow: (sessionId: string, framework: string) => void;
  onCancel: () => void;
}) {
  const [url, setUrl] = useState("http://localhost:3000");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [liveLines, setLiveLines] = useState<string[]>([]);
  const [stopping, setStopping] = useState(false);
  const [capturedSpec, setCapturedSpec] = useState<{ code: string; path: string | null } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  // Framework selection
  const [frameworks, setFrameworks] = useState<SilkFramework[]>([]);
  const [loadingFrameworks, setLoadingFrameworks] = useState(true);
  const [selectedFrameworkId, setSelectedFrameworkId] = useState<string>("playwright-ts");

  useEffect(() => {
    sidecar
      .silkFrameworks()
      .then(({ frameworks: fws }) => {
        setFrameworks(fws);
        // Pick first recordable framework as default (prefer playwright-ts)
        const defaultFw =
          fws.find((f) => f.id === "playwright-ts") ??
          fws.find((f) => f.recordable) ??
          fws[0];
        if (defaultFw) setSelectedFrameworkId(defaultFw.id);
      })
      .catch(() => {
        // Non-blocking — fall back to playwright-ts
      })
      .finally(() => setLoadingFrameworks(false));
  }, []);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [liveLines]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const selectedFramework = frameworks.find((f) => f.id === selectedFrameworkId) ?? null;
  const canRecord = selectedFramework === null || selectedFramework.recordable;

  /** Start codegen and immediately open the fetch-based SSE stream. */
  const handleStart = async () => {
    setError(null);
    try {
      const res = await sidecar.silkRecordStart({ url, framework: selectedFrameworkId });
      setSessionId(res.session_id);
      setLiveLines([res.message]);

      // Open SSE stream with fetch (compatible with Tauri auth headers).
      const [base, token] = await Promise.all([getSidecarBaseUrl(), getSidecarToken()]);
      const streamUrl = `${base}/api/silk/record/stream/${encodeURIComponent(res.session_id)}`;
      const ctrl = new AbortController();
      abortRef.current = ctrl;

      void (async () => {
        try {
          for await (const line of _fetchSSELines(streamUrl, token, ctrl.signal)) {
            if (line === "DONE") break;
            setLiveLines((prev) => [...prev, line]);
          }
        } catch {
          // AbortError when user clicks cancel — expected.
        }
      })();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const handleStop = async () => {
    if (!sessionId) return;
    setStopping(true);
    abortRef.current?.abort();
    try {
      const res = await sidecar.silkRecordStop(sessionId);
      setCapturedSpec({ code: res.spec_text, path: res.spec_path });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setStopping(false);
    }
  };

  const handleKeep = () => {
    if (capturedSpec) {
      onCapture(capturedSpec.code, capturedSpec.path);
    }
  };

  const handleRunNow = () => {
    if (sessionId) {
      onRunNow(sessionId, selectedFrameworkId);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-[600px] rounded-lg border border-neutral-800 bg-neutral-925 shadow-2xl p-5 flex flex-col gap-4">
        <div className="flex items-center gap-2 text-neutral-100">
          <Video size={16} className="text-emerald-400" />
          <h2 className="font-semibold text-sm">Record new spec</h2>
        </div>

        {/* ── Phase 1: setup ── */}
        {!sessionId && !capturedSpec && (
          <>
            {/* Framework selector */}
            <div className="flex flex-col gap-1">
              <label className="text-xs text-neutral-500">Framework</label>
              {loadingFrameworks ? (
                <div className="flex items-center gap-1.5 text-xs text-neutral-500 h-7">
                  <RefreshCw size={11} className="animate-spin" />
                  Načítám…
                </div>
              ) : (
                <select
                  value={selectedFrameworkId}
                  onChange={(e) => setSelectedFrameworkId(e.target.value)}
                  className="rounded bg-neutral-950 border border-neutral-800 px-3 py-1.5 text-xs text-neutral-200 focus:outline-none focus:border-emerald-600 transition-colors"
                >
                  {frameworks.length === 0 ? (
                    <option value="playwright-ts">Playwright (TypeScript)</option>
                  ) : (
                    frameworks.map((f) => (
                      <option key={f.id} value={f.id}>
                        {f.label}
                      </option>
                    ))
                  )}
                </select>
              )}
              {canRecord && selectedFramework?.recordable_via_transpile && (
                <p className="text-[10px] text-neutral-400 mt-0.5">
                  Nahráno přes Playwright a převedeno do {selectedFramework.label}.
                </p>
              )}
              {!canRecord && selectedFramework && (
                <p className="text-[10px] text-amber-400 mt-0.5">
                  Nahrávání zatím není podporováno pro {selectedFramework.label} — použij{" "}
                  <strong className="text-amber-300">Nový test</strong>.
                </p>
              )}
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs text-neutral-500">Target URL</label>
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                className="rounded bg-neutral-950 border border-neutral-800 px-3 py-1.5 text-xs text-neutral-200 placeholder-neutral-600 focus:outline-none focus:border-emerald-600"
                spellCheck={false}
              />
            </div>
            {error && <div className="text-xs text-red-400">{error}</div>}
            <div className="flex justify-end gap-2">
              <button onClick={onCancel} className="rounded px-3 py-1.5 text-xs bg-neutral-800 hover:bg-neutral-700 text-neutral-300">
                Cancel
              </button>
              <button
                onClick={() => void handleStart()}
                disabled={!url.trim() || !canRecord}
                className="flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium bg-emerald-700 hover:bg-emerald-600 disabled:opacity-40 disabled:cursor-not-allowed text-white"
                title={!canRecord && selectedFramework ? `Nahrávání není podporováno pro ${selectedFramework.label}` : undefined}
              >
                <Play size={11} />
                Start recording
              </button>
            </div>
          </>
        )}

        {/* ── Phase 2: recording in progress ── */}
        {sessionId && !capturedSpec && (
          <>
            <div className="text-xs text-neutral-400">
              Playwright codegen is open in a browser window. Interact with your app,
              then click <strong className="text-neutral-200">Stop recording</strong> to
              capture the generated spec.
            </div>
            <div
              ref={logRef}
              className="h-36 overflow-y-auto rounded bg-neutral-950 p-3 font-mono text-xs text-neutral-400 select-text"
            >
              {liveLines.map((l, i) => <div key={i}>{l}</div>)}
              <div className="animate-pulse text-emerald-500 mt-1">Recording…</div>
            </div>
            {error && <div className="text-xs text-red-400">{error}</div>}
            <div className="flex justify-end gap-2">
              <button onClick={onCancel} className="rounded px-3 py-1.5 text-xs bg-neutral-800 hover:bg-neutral-700 text-neutral-300">
                Cancel
              </button>
              <button
                onClick={() => void handleStop()}
                disabled={stopping}
                className="flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium bg-red-700 hover:bg-red-600 disabled:opacity-40 text-white"
              >
                {stopping ? <RefreshCw size={11} className="animate-spin" /> : <Square size={11} />}
                Stop recording
              </button>
            </div>
          </>
        )}

        {/* ── Phase 3: spec captured — offer Run Now or Keep ── */}
        {capturedSpec && (
          <>
            <div className="text-xs text-neutral-400">
              Spec captured successfully.{" "}
              <strong className="text-neutral-200">Run Now</strong> saves it and immediately
              executes it, or{" "}
              <strong className="text-neutral-200">Keep</strong> saves it for later.
            </div>
            <div className="h-24 overflow-y-auto rounded bg-neutral-950 p-3 font-mono text-[10px] text-neutral-400 select-text">
              {capturedSpec.code.split("\n").slice(0, 12).join("\n")}
              {capturedSpec.code.split("\n").length > 12 && "\n…"}
            </div>
            {error && <div className="text-xs text-red-400">{error}</div>}
            <div className="flex justify-end gap-2">
              <button onClick={onCancel} className="rounded px-3 py-1.5 text-xs bg-neutral-800 hover:bg-neutral-700 text-neutral-300">
                Discard
              </button>
              <button
                onClick={handleKeep}
                className="flex items-center gap-1.5 rounded px-3 py-1.5 text-xs bg-neutral-700 hover:bg-neutral-600 text-neutral-200"
              >
                <FileCode size={11} />
                Keep
              </button>
              <button
                onClick={handleRunNow}
                className="flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium bg-emerald-700 hover:bg-emerald-600 text-white"
              >
                <Play size={11} />
                Run Now
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Run form (with mocks + browser selection)
// ---------------------------------------------------------------------------

function RunForm({
  onRun,
  running,
}: {
  onRun: (specPath: string, workspaceDir: string, browsers: string[]) => void;
  running: boolean;
}) {
  const [specPath, setSpecPath] = useState("");
  const [workspaceDir, setWorkspaceDir] = useState("");
  const [browsers, setBrowsers] = useState<string[]>(["chromium"]);

  const toggleBrowser = (b: string) => {
    setBrowsers((prev) =>
      prev.includes(b) ? (prev.length > 1 ? prev.filter((x) => x !== b) : prev) : [...prev, b],
    );
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (specPath.trim()) onRun(specPath.trim(), workspaceDir.trim(), browsers);
  };

  const BROWSERS = ["chromium", "firefox", "webkit"];

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-3 rounded-lg border border-neutral-800 bg-neutral-900 p-4"
    >
      <h3 className="text-xs font-semibold text-neutral-300 uppercase tracking-wider">
        Run spec
      </h3>

      <div className="flex flex-col gap-1">
        <label className="text-xs text-neutral-500">Spec file path</label>
        <input
          value={specPath}
          onChange={(e) => setSpecPath(e.target.value)}
          placeholder="/path/to/my.spec.ts"
          className="rounded bg-neutral-950 border border-neutral-800 px-3 py-1.5 text-xs text-neutral-200 placeholder-neutral-600 focus:outline-none focus:border-emerald-600 transition-colors"
          spellCheck={false}
        />
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-xs text-neutral-500">Workspace dir (optional)</label>
        <input
          value={workspaceDir}
          onChange={(e) => setWorkspaceDir(e.target.value)}
          placeholder="/path/to/project"
          className="rounded bg-neutral-950 border border-neutral-800 px-3 py-1.5 text-xs text-neutral-200 placeholder-neutral-600 focus:outline-none focus:border-emerald-600 transition-colors"
          spellCheck={false}
        />
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-xs text-neutral-500">Browsers</label>
        <div className="flex gap-1.5">
          {BROWSERS.map((b) => (
            <button
              key={b}
              type="button"
              onClick={() => toggleBrowser(b)}
              className={`rounded border px-2 py-1 text-xs font-medium transition-colors ${
                browsers.includes(b)
                  ? "border-emerald-700 bg-emerald-950/50 text-emerald-300"
                  : "border-neutral-700 bg-neutral-800 text-neutral-500 hover:text-neutral-300"
              }`}
            >
              {b}
            </button>
          ))}
        </div>
      </div>

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={running || !specPath.trim()}
          className="flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium bg-emerald-700 hover:bg-emerald-600 disabled:opacity-40 disabled:cursor-not-allowed text-white transition-colors"
        >
          {running ? <RefreshCw size={12} className="animate-spin" /> : <Play size={12} />}
          {running ? "Running…" : "Run"}
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Main SilkPanel
// ---------------------------------------------------------------------------

interface SilkPanelProps {
  onToast?: (type: "success" | "error" | "info", message: string) => void;
}

export function SilkPanel({ onToast }: SilkPanelProps) {
  const [browsersInstalled, setBrowsersInstalled] = useState<boolean | null>(null);
  const [showInstallDialog, setShowInstallDialog] = useState(false);
  const [showRecordDialog, setShowRecordDialog] = useState(false);
  const [showNewTestDialog, setShowNewTestDialog] = useState(false);
  const [sessionRuns, setSessionRuns] = useState<SessionRun[]>([]);
  const [historyRuns, setHistoryRuns] = useState<SilkRunHistoryEntry[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [checkingBrowsers, setCheckingBrowsers] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [activeTab, setActiveTab] = useState<ActiveTab>("timeline");
  const [activeBrowser, setActiveBrowser] = useState("chromium");

  // Check browser presence on mount.
  const checkBrowsers = useCallback(async () => {
    setCheckingBrowsers(true);
    try {
      const res = await sidecar.silkCheckBrowsers();
      setBrowsersInstalled(res.installed);
    } catch {
      setBrowsersInstalled(false);
    } finally {
      setCheckingBrowsers(false);
    }
  }, []);

  // Load run history on mount.
  const loadHistory = useCallback(async () => {
    setLoadingHistory(true);
    try {
      const runs = await sidecar.silkListRuns(50);
      setHistoryRuns(runs);
    } catch {
      // Non-blocking — history is optional.
    } finally {
      setLoadingHistory(false);
    }
  }, []);

  useEffect(() => {
    void checkBrowsers();
    void loadHistory();
  }, [checkBrowsers, loadHistory]);

  const handleInstallDone = useCallback(() => {
    setShowInstallDialog(false);
    void checkBrowsers();
    onToast?.("success", "Playwright Chromium installed.");
  }, [checkBrowsers, onToast]);

  const handleRun = useCallback(
    async (specPath: string, workspaceDir: string, browsers: string[]) => {
      if (!browsersInstalled) {
        setShowInstallDialog(true);
        return;
      }
      setRunning(true);
      try {
        const result = await sidecar.silkRun({
          spec_path: specPath,
          workspace_dir: workspaceDir || undefined,
          browsers: browsers as ("chromium" | "firefox" | "webkit")[],
        });
        const traceUrl = result.trace_path
          ? await sidecar.silkTraceUrl(result.run_id)
          : undefined;
        const entry: SessionRun = {
          run: result,
          specLabel: specPath.split("/").pop() ?? specPath,
          startedAt: Date.now(),
          traceUrl,
        };
        setSessionRuns((prev) => [entry, ...prev]);
        setSelectedRunId(result.run_id);
        setActiveBrowser(browsers[0] ?? "chromium");
        setActiveTab("timeline");

        if (result.failed > 0 || result.exit_code !== 0) {
          onToast?.("error", `Silk: ${result.failed} failed`);
        } else {
          onToast?.("success", `Silk: ${result.passed} passed`);
        }

        // Refresh history after run.
        void loadHistory();
      } catch (e: unknown) {
        onToast?.(
          "error",
          `Silk run error: ${e instanceof Error ? e.message : String(e)}`,
        );
      } finally {
        setRunning(false);
      }
    },
    [browsersInstalled, onToast, loadHistory],
  );

  const handleCaptureSpec = useCallback(
    (specCode: string, _specPath: string | null) => {
      setShowRecordDialog(false);
      if (specCode.trim()) {
        onToast?.("success", "Spec recorded — paste code into your spec file.");
      }
    },
    [onToast],
  );

  /**
   * "Run Now" bridge: stop the codegen session, save the spec, and immediately
   * run it.  This wires the record->run loop so a recorded spec is never discarded.
   */
  const handleRecordRunNow = useCallback(
    async (sessionId: string, framework: string) => {
      setShowRecordDialog(false);
      if (!browsersInstalled) {
        setShowInstallDialog(true);
        return;
      }
      setRunning(true);
      try {
        const result = await sidecar.silkRecordSaveAndRun({
          session_id: sessionId,
          framework,
          filename: "recorded",
          browsers: ["chromium"],
        });
        const traceUrl = result.run.trace_path
          ? await sidecar.silkTraceUrl(result.run.run_id)
          : undefined;
        const entry: SessionRun = {
          run: result.run,
          specLabel: result.spec_path.split("/").pop() ?? result.spec_path,
          startedAt: Date.now(),
          traceUrl,
        };
        setSessionRuns((prev) => [entry, ...prev]);
        setSelectedRunId(result.run.run_id);
        setActiveBrowser("chromium");
        setActiveTab("timeline");

        if (result.run.failed > 0 || result.run.exit_code !== 0) {
          onToast?.("error", `Silk: ${result.run.failed} failed`);
        } else {
          onToast?.("success", `Silk: ${result.run.passed} passed`);
        }

        void loadHistory();
      } catch (e: unknown) {
        onToast?.(
          "error",
          `Record+run error: ${e instanceof Error ? e.message : String(e)}`,
        );
      } finally {
        setRunning(false);
      }
    },
    [browsersInstalled, onToast, loadHistory],
  );

  const handleNewTestSaved = useCallback(
    (specPath: string) => {
      onToast?.("success", `Test uložen: ${specPath}`);
      // Keep dialog open so user can see the saved path (dialog closes itself via "Zavřít")
    },
    [onToast],
  );

  // Find selected run across session + history.
  const selectedSession = sessionRuns.find((r) => r.run.run_id === selectedRunId);
  const selectedRun = selectedSession?.run ?? null;
  const browsers = selectedRun
    ? Object.keys(selectedRun.per_browser_results)
    : [];
  const browserResult: SilkBrowserRunResult | null =
    selectedRun?.per_browser_results?.[activeBrowser] ?? null;

  const a11yViolations =
    selectedRun?.a11y_violations ??
    browserResult?.a11y_violations ??
    [];

  // Right-panel tab definitions.
  const TABS: { id: ActiveTab; label: string; icon: React.ReactNode }[] = [
    { id: "timeline", label: "Timeline", icon: <Play size={11} /> },
    { id: "network", label: "Network", icon: <Globe size={11} /> },
    { id: "screenshots", label: "Screenshots", icon: <Image size={11} /> },
    {
      id: "a11y",
      label: `A11y${a11yViolations.length > 0 ? ` (${a11yViolations.length})` : ""}`,
      icon: <AlertTriangle size={11} className={a11yViolations.length > 0 ? "text-amber-400" : ""} />,
    },
    { id: "console", label: "Console", icon: <Terminal size={11} /> },
  ];

  return (
    <>
      {showInstallDialog && (
        <InstallDialog
          onDone={handleInstallDone}
          onCancel={() => setShowInstallDialog(false)}
        />
      )}
      {showRecordDialog && (
        <RecordDialog
          onCapture={handleCaptureSpec}
          onRunNow={(sessionId, framework) => void handleRecordRunNow(sessionId, framework)}
          onCancel={() => setShowRecordDialog(false)}
        />
      )}
      {showNewTestDialog && (
        <NewTestDialog
          onSaved={handleNewTestSaved}
          onCancel={() => setShowNewTestDialog(false)}
        />
      )}

      <div className="flex h-full flex-col bg-neutral-950 text-neutral-200">
        {/* Toolbar */}
        <div className="flex items-center justify-between border-b border-neutral-800 px-3 py-2 shrink-0">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowRecordDialog(true)}
              disabled={!browsersInstalled}
              className="flex items-center gap-1.5 rounded px-2.5 py-1.5 text-xs font-medium bg-neutral-800 hover:bg-neutral-700 disabled:opacity-40 text-neutral-200 transition-colors"
              title={browsersInstalled ? "Record new spec via Playwright codegen" : "Install browsers first"}
            >
              <Video size={12} className="text-red-400" />
              Record
            </button>
            <button
              onClick={() => setShowNewTestDialog(true)}
              className="flex items-center gap-1.5 rounded px-2.5 py-1.5 text-xs font-medium bg-neutral-800 hover:bg-neutral-700 text-neutral-200 transition-colors"
              title="Vytvoř nový test ručně v editoru"
            >
              <FileCode size={12} className="text-emerald-400" />
              Nový test
            </button>
          </div>

          <div className="flex items-center gap-2">
            {/* Browser status */}
            {browsersInstalled === false && (
              <button
                onClick={() => setShowInstallDialog(true)}
                className="flex items-center gap-1 text-[10px] text-amber-400 hover:text-amber-300"
              >
                <Download size={10} />
                Install browsers
              </button>
            )}
            <button
              onClick={() => void checkBrowsers()}
              disabled={checkingBrowsers}
              title="Refresh browser check"
              className="text-neutral-500 hover:text-neutral-300 transition-colors"
            >
              <RefreshCw size={12} className={checkingBrowsers ? "animate-spin" : ""} />
            </button>
            <button
              onClick={() => void loadHistory()}
              disabled={loadingHistory}
              title="Refresh run history"
              className="text-neutral-500 hover:text-neutral-300 transition-colors"
            >
              <History size={12} className={loadingHistory ? "animate-spin" : ""} />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex flex-1 min-h-0">
          {/* Left sidebar — history */}
          <div className="flex w-52 shrink-0 flex-col border-r border-neutral-800 bg-neutral-925">
            <div className="flex items-center justify-between border-b border-neutral-800 px-3 py-2">
              <span className="flex items-center gap-1.5 text-xs font-semibold text-neutral-300">
                <MonitorPlay size={12} className="text-emerald-500" />
                History
              </span>
              <button
                onClick={() => handleRun("", "", ["chromium"])}
                disabled={running}
                className="text-neutral-500 hover:text-emerald-400 transition-colors"
                title="New run"
              >
                <Plus size={12} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto py-1">
              {/* Session runs (in-memory, unsaved) */}
              {sessionRuns.length === 0 && historyRuns.length === 0 && (
                <EmptyState
                  icon={History}
                  title="No runs yet"
                  description="Run a spec to see results here"
                />
              )}

              {sessionRuns.map((entry) => {
                const status =
                  entry.run.exit_code === 0 ? "passed" :
                  entry.run.failed > 0 ? "failed" : "error";
                return (
                  <button
                    key={entry.run.run_id}
                    onClick={() => {
                      setSelectedRunId(entry.run.run_id);
                      const firstBrowser = Object.keys(entry.run.per_browser_results)[0] ?? "chromium";
                      setActiveBrowser(firstBrowser);
                    }}
                    className={`w-full text-left px-3 py-2 flex flex-col gap-0.5 transition-colors border-l-2 ${
                      selectedRunId === entry.run.run_id
                        ? "bg-neutral-800 border-emerald-500"
                        : "hover:bg-neutral-900 border-transparent"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-1">
                      <StatusIcon status={status} size={10} />
                      <span className="flex-1 truncate text-xs text-neutral-200 min-w-0">
                        {entry.specLabel}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-[10px] text-neutral-600">
                      <span>{durationLabel(entry.run.duration_ms)}</span>
                      <span>{timeAgo(entry.startedAt)}</span>
                    </div>
                  </button>
                );
              })}

              {historyRuns.length > 0 && (
                <>
                  <div className="px-3 py-1.5 text-[10px] uppercase text-neutral-600 tracking-wider">
                    Previous runs
                  </div>
                  {historyRuns
                    .filter((h) => !sessionRuns.some((s) => s.run.run_id === h.id))
                    .map((h) => (
                      <button
                        key={h.id}
                        onClick={() => setSelectedRunId(h.id)}
                        className={`w-full text-left px-3 py-2 flex flex-col gap-0.5 transition-colors border-l-2 ${
                          selectedRunId === h.id
                            ? "bg-neutral-800 border-emerald-500"
                            : "hover:bg-neutral-900 border-transparent"
                        }`}
                      >
                        <div className="flex items-center gap-1">
                          <StatusIcon status={h.status} size={10} />
                          <span className="flex-1 truncate text-xs text-neutral-200 min-w-0">
                            {h.spec_path.split("/").pop()}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 text-[10px] text-neutral-600">
                          <span>{durationLabel(h.duration_ms)}</span>
                          <span>{timeAgo(h.started_at)}</span>
                          {h.browsers.length > 1 && (
                            <span className="text-neutral-700">{h.browsers.join(", ")}</span>
                          )}
                        </div>
                      </button>
                    ))}
                </>
              )}
            </div>
          </div>

          {/* Center — run form + trace viewer */}
          <div className="flex flex-1 min-w-0 flex-col">
            {/* Run form */}
            <div className="border-b border-neutral-800 p-3">
              <RunForm onRun={handleRun} running={running} />
            </div>

            {/* Browser tab bar */}
            {selectedRun && browsers.length > 1 && (
              <BrowserTabBar
                browsers={browsers}
                active={activeBrowser}
                onSelect={(b) => setActiveBrowser(b)}
                results={selectedRun.per_browser_results}
              />
            )}

            {/* Stats row */}
            {selectedRun && (
              <div className="border-b border-neutral-800 px-4 py-3">
                <div className="flex items-center gap-3 mb-2">
                  <span className="text-xs font-semibold text-neutral-300">
                    Run {selectedRun.run_id.slice(0, 8)}
                  </span>
                  {selectedSession?.traceUrl && (
                    <a
                      href={selectedSession.traceUrl}
                      download={`trace-${selectedRun.run_id}.zip`}
                      className="flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300 transition-colors"
                    >
                      <Download size={11} />
                      Trace
                    </a>
                  )}
                </div>
                <div className="grid grid-cols-4 gap-2">
                  {[
                    {
                      label: "Passed",
                      value: browserResult?.passed ?? selectedRun.passed,
                      color: "text-emerald-400",
                    },
                    {
                      label: "Failed",
                      value: browserResult?.failed ?? selectedRun.failed,
                      color: "text-red-400",
                    },
                    {
                      label: "Errors",
                      value: browserResult?.errors ?? selectedRun.errors,
                      color: "text-amber-400",
                    },
                    {
                      label: "Duration",
                      value: durationLabel(browserResult?.duration_ms ?? selectedRun.duration_ms),
                      color: "text-neutral-300",
                    },
                  ].map(({ label, value, color }) => (
                    <div key={label} className="rounded bg-neutral-900 p-2 flex flex-col items-center">
                      <span className={`text-base font-bold ${color}`}>{value}</span>
                      <span className="text-[10px] text-neutral-500">{label}</span>
                    </div>
                  ))}
                </div>

                {/* Stderr */}
                {(browserResult?.stderr_tail || selectedRun.stderr_tail) && (
                  <div className="mt-3">
                    <span className="text-[10px] uppercase text-neutral-500 tracking-wider">
                      stderr (last 20 lines)
                    </span>
                    <pre className="mt-1 max-h-28 overflow-y-auto rounded bg-neutral-950 p-2 text-[10px] text-neutral-400 font-mono whitespace-pre-wrap">
                      {browserResult?.stderr_tail ?? selectedRun.stderr_tail}
                    </pre>
                  </div>
                )}
              </div>
            )}

            {!selectedRun && (
              <div className="flex flex-1 items-center justify-center text-xs text-neutral-600">
                Select a run from the history to view results
              </div>
            )}
          </div>

          {/* Right sidebar — tabs */}
          <div className="flex w-72 shrink-0 flex-col border-l border-neutral-800">
            {/* Tab headers */}
            <div className="flex border-b border-neutral-800 overflow-x-auto">
              {TABS.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-1 px-2.5 py-2 text-[10px] font-medium whitespace-nowrap transition-colors ${
                    activeTab === tab.id
                      ? "border-b-2 border-emerald-500 text-emerald-300"
                      : "text-neutral-500 hover:text-neutral-300"
                  }`}
                >
                  {tab.icon}
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Tab content */}
            <div className="flex-1 min-h-0 overflow-hidden">
              {activeTab === "timeline" && (
                <StepTimeline
                  report={browserResult?.json_report ?? selectedRun?.json_report ?? null}
                />
              )}

              {activeTab === "a11y" && (
                <A11yPanel violations={a11yViolations} />
              )}

              {activeTab === "console" && (
                <div className="p-2 overflow-y-auto h-full">
                  {(browserResult?.stderr_tail || selectedRun?.stderr_tail) ? (
                    <pre className="text-[10px] font-mono text-neutral-400 whitespace-pre-wrap">
                      {browserResult?.stderr_tail ?? selectedRun?.stderr_tail}
                    </pre>
                  ) : (
                    <div className="flex items-center justify-center h-24 text-xs text-neutral-600">
                      No console output
                    </div>
                  )}
                </div>
              )}

              {activeTab === "network" && (() => {
                const activeReport = browserResult?.json_report ?? selectedRun?.json_report ?? null;
                const networkEntries = extractNetworkEntries(activeReport);
                if (networkEntries.length === 0) {
                  return (
                    <div className="flex items-center justify-center h-full text-xs text-neutral-600 flex-col gap-2">
                      <Globe size={20} className="text-neutral-700" />
                      {activeReport ? "No network entries in report" : "Network log available in Playwright trace"}
                      {selectedSession?.traceUrl && (
                        <a
                          href={selectedSession.traceUrl}
                          download={`trace-${selectedRun?.run_id}.zip`}
                          className="flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300"
                        >
                          <Download size={11} />
                          Download trace
                        </a>
                      )}
                    </div>
                  );
                }
                return (
                  <div className="flex flex-col overflow-y-auto h-full">
                    <div className="px-3 py-1.5 border-b border-neutral-800 text-[10px] text-neutral-500">
                      {networkEntries.length} request(s)
                    </div>
                    {networkEntries.map((entry, i) => {
                      const req = entry.request ?? {};
                      const res = (entry as Record<string, unknown>).response as Record<string, unknown> | undefined;
                      const status = res?.status as number | undefined;
                      const statusColor = !status ? "text-neutral-500"
                        : status < 300 ? "text-emerald-400"
                        : status < 400 ? "text-amber-400"
                        : "text-red-400";
                      return (
                        <div key={i} className="flex items-center gap-2 px-3 py-1.5 border-b border-neutral-900 text-[10px] hover:bg-neutral-900 min-w-0">
                          <span className="shrink-0 w-8 font-mono text-neutral-400">{req.method ?? "?"}</span>
                          <span className={`shrink-0 w-8 font-mono ${statusColor}`}>{status ?? ""}</span>
                          <span className="flex-1 text-neutral-300 truncate font-mono" title={String(req.url ?? "")}>
                            {String(req.url ?? "")}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                );
              })()}

              {activeTab === "screenshots" && (() => {
                const activeReport = browserResult?.json_report ?? selectedRun?.json_report ?? null;
                const screenshotPaths = extractScreenshotPaths(activeReport);
                if (screenshotPaths.length === 0) {
                  return (
                    <div className="flex items-center justify-center h-full text-xs text-neutral-600 flex-col gap-2">
                      <Image size={20} className="text-neutral-700" />
                      {activeReport ? "No screenshots in report" : "Screenshots captured during run"}
                    </div>
                  );
                }
                return (
                  <div className="flex flex-col gap-2 overflow-y-auto p-2 h-full">
                    {screenshotPaths.map((p, i) => (
                      <div key={i} className="rounded border border-neutral-800 bg-neutral-900 p-2">
                        <div className="flex items-center justify-between gap-2 mb-1.5">
                          <span className="text-[10px] text-neutral-400 font-mono truncate flex-1" title={p}>
                            {p.split("/").pop() ?? p}
                          </span>
                          <a
                            href={`file://${p}`}
                            target="_blank"
                            rel="noreferrer"
                            title={p}
                            className="shrink-0 text-neutral-500 hover:text-emerald-400 transition-colors"
                          >
                            <ExternalLink size={11} />
                          </a>
                        </div>
                        <img
                          src={`file://${p}`}
                          alt={`screenshot-${i}`}
                          className="w-full rounded object-contain max-h-48 bg-neutral-950"
                          onError={(e) => {
                            (e.target as HTMLImageElement).style.display = "none";
                          }}
                        />
                      </div>
                    ))}
                  </div>
                );
              })()}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
