import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, ArrowDown, ArrowUp, Bot, CheckCircle2, ChevronDown, Clock, Code2, Copy, Download, FileCode, FolderPlus, GitCompare, Inbox, Minus, RefreshCw, Search, Shield, Star, Terminal, Upload, XCircle, Zap } from "lucide-react";
import type { Assertion } from "../state/types";
import type { AutoCompareOutput, BodySearchMatch, ExecuteResponse, HeaderInsightsOutput, SchemaValidateOutput, TimingBreakdown } from "../lib/sidecar";
import { sidecar } from "../lib/sidecar";
import { CodeEditor } from "./CodeEditor";
import { JsonTreeView } from "./JsonTreeView";
import { RateLimitIndicator } from "./RateLimitIndicator";
import { ResponseBodySearch } from "./ResponseBodySearch";

type BodyViewMode = "editor" | "tree" | "raw";

/** Snapshot of a historical response for per-URL tracking. */
interface ResponseSnapshot {
  timestamp: number;
  status: number;
  elapsed_ms: number;
  body_size: number;
  body_preview: string;
  response: ExecuteResponse;
}

/** Per-URL response history (max 5 per URL, max 50 URLs, persisted to localStorage). */
const HISTORY_KEY = "theridion.response-history";
const MAX_PER_URL = 5;
const MAX_URLS = 50;

const urlHistory = new Map<string, ResponseSnapshot[]>();

// Load persisted history on module init.
try {
  const stored = localStorage.getItem(HISTORY_KEY);
  if (stored) {
    const parsed = JSON.parse(stored) as Record<string, ResponseSnapshot[]>;
    for (const [key, snapshots] of Object.entries(parsed)) {
      if (Array.isArray(snapshots)) {
        urlHistory.set(key, snapshots);
      }
    }
  }
} catch { /* corrupt data — start fresh */ }

function persistUrlHistory() {
  try {
    const obj: Record<string, ResponseSnapshot[]> = {};
    for (const [key, snaps] of urlHistory) {
      // Truncate body_preview for storage and strip the full response object.
      obj[key] = snaps.map((s) => ({
        ...s,
        body_preview: s.body_preview.slice(0, 500),
        response: s.response,
      }));
    }
    localStorage.setItem(HISTORY_KEY, JSON.stringify(obj));
  } catch { /* quota exceeded — non-critical */ }
}

function recordUrlHistory(url: string, res: ExecuteResponse) {
  const key = url.replace(/\?.*/, ""); // strip query params for grouping
  const list = urlHistory.get(key) ?? [];
  list.push({
    timestamp: Date.now(),
    status: res.status,
    elapsed_ms: res.elapsed_ms,
    body_size: res.body_size_bytes,
    body_preview: res.body.slice(0, 500),
    response: res,
  });
  if (list.length > MAX_PER_URL) list.shift();
  urlHistory.set(key, list);
  // Enforce max URLs limit.
  if (urlHistory.size > MAX_URLS) {
    const oldest = urlHistory.keys().next().value;
    if (oldest !== undefined) urlHistory.delete(oldest);
  }
  persistUrlHistory();
}

function getUrlHistory(url: string): ResponseSnapshot[] {
  const key = url.replace(/\?.*/, "");
  return urlHistory.get(key) ?? [];
}

export interface ConsoleEntry {
  timestamp: number;
  level: "info" | "warn" | "error" | "log";
  message: string;
}

type Tab = "body" | "headers" | "cookies" | "timing" | "console" | "schema";

interface Props {
  busy: boolean;
  response: ExecuteResponse | null;
  error: string | null;
  onDiff?: () => void;
  onCodegen?: () => void;
  consoleEntries?: ConsoleEntry[];
  isFirstRun?: boolean;
  onImportCollection?: () => void;
  onOpenSwagger?: () => void;
  onOpenAgentExplorer?: () => void;
  onNewCollection?: () => void;
  onAddAssertion?: (assertion: Assertion) => void;
}

/** Keep last 5 response times for sparkline display. */
const responseTimeHistory: number[] = [];

export function ResponsePanel({ busy, response, error, onDiff, onCodegen, consoleEntries = [], isFirstRun, onImportCollection, onOpenSwagger, onOpenAgentExplorer, onNewCollection, onAddAssertion }: Props) {
  const [tab, setTab] = useState<Tab>("body");
  const panelRef = useRef<HTMLDivElement>(null);
  const [headerSearch, setHeaderSearch] = useState("");
  const [cookieSearch, setCookieSearch] = useState("");
  const headerSearchRef = useRef<HTMLInputElement | null>(null);
  const cookieSearchRef = useRef<HTMLInputElement | null>(null);
  const lastTrackedRef = useRef<string | null>(null);
  const [viewingHistorical, setViewingHistorical] = useState<ExecuteResponse | null>(null);
  const [goldenComparison, setGoldenComparison] = useState<AutoCompareOutput | null>(null);
  const [goldenSaving, setGoldenSaving] = useState(false);

  // Track response time history for sparkline + per-URL history
  useEffect(() => {
    if (response) {
      const key = `${response.status}-${response.elapsed_ms}-${response.body_size_bytes}`;
      if (lastTrackedRef.current !== key) {
        lastTrackedRef.current = key;
        responseTimeHistory.push(response.elapsed_ms);
        if (responseTimeHistory.length > 5) responseTimeHistory.shift();
        recordUrlHistory(response.final_url, response);
      }
    }
    // Clear historical view when new response arrives.
    setViewingHistorical(null);
  }, [response]);

  // Auto-compare against golden file after each new response
  useEffect(() => {
    if (!response) { setGoldenComparison(null); return; }
    let cancelled = false;
    sidecar.autoCompareGolden({
      url: response.final_url,
      method: "GET",
      status: response.status,
      headers: response.headers,
      body: response.body,
    }).then((result) => {
      if (!cancelled) setGoldenComparison(result);
    }).catch(() => {
      if (!cancelled) setGoldenComparison(null);
    });
    return () => { cancelled = true; };
  }, [response]);

  const handleSaveGolden = useCallback(async () => {
    if (!response) return;
    setGoldenSaving(true);
    try {
      await sidecar.saveGolden({
        url: response.final_url,
        method: "GET",
        status: response.status,
        headers: response.headers,
        body: response.body,
      });
      // Re-run auto-compare to refresh the indicator
      const result = await sidecar.autoCompareGolden({
        url: response.final_url,
        method: "GET",
        status: response.status,
        headers: response.headers,
        body: response.body,
      });
      setGoldenComparison(result);
    } catch { /* non-critical */ }
    setGoldenSaving(false);
  }, [response]);

  // Ctrl+F handler to focus search when response panel is active
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "f") {
        if (!panelRef.current?.contains(document.activeElement) && !panelRef.current?.matches(":hover")) return;
        if (tab === "headers") {
          e.preventDefault();
          headerSearchRef.current?.focus();
        } else if (tab === "cookies") {
          e.preventDefault();
          cookieSearchRef.current?.focus();
        }
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [tab]);

  if (busy && !response) return <Loading />;
  if (error && !response) return <ErrorView error={error} />;
  if (!response && isFirstRun) return <WelcomeScreen onImportCollection={onImportCollection} onOpenSwagger={onOpenSwagger} onOpenAgentExplorer={onOpenAgentExplorer} onNewCollection={onNewCollection} />;
  if (!response) return <Empty />;

  const displayResponse = viewingHistorical ?? response;
  const history = getUrlHistory(response.final_url);

  return (
    <div ref={panelRef} className="flex h-full min-h-0 flex-col">
      <StatusRow res={displayResponse} onDiff={onDiff} onCodegen={onCodegen} history={history} onViewHistorical={(snap) => setViewingHistorical(snap.response)} onAddAssertion={onAddAssertion} />
      {viewingHistorical && (
        <div className="flex items-center gap-2 border-b border-amber-800/30 bg-amber-950/20 px-3 py-1 text-[11px] text-amber-400">
          <Clock className="h-3 w-3" />
          Viewing historical response from {new Date(history.find(h => h.response === viewingHistorical)?.timestamp ?? 0).toLocaleTimeString()}
          <button type="button" onClick={() => setViewingHistorical(null)} className="ml-auto text-amber-500 hover:text-amber-300">Show current</button>
        </div>
      )}
      {/* Golden file comparison bar */}
      <GoldenFileBar
        comparison={goldenComparison}
        onSave={handleSaveGolden}
        saving={goldenSaving}
        onUpdate={handleSaveGolden}
      />
      <RateLimitIndicator headers={displayResponse.headers} />
      <div className="flex items-center gap-1 border-b border-neutral-800 px-2 py-0">
        <TabButton active={tab === "body"} onClick={() => setTab("body")}>Body</TabButton>
        <TabButton active={tab === "headers"} onClick={() => setTab("headers")}>
          Headers <span className="ml-1 text-neutral-500">{Object.keys(displayResponse.headers).length}</span>
        </TabButton>
        {displayResponse.cookies && Object.keys(displayResponse.cookies).length > 0 && (
          <TabButton active={tab === "cookies"} onClick={() => setTab("cookies")}>
            Cookies <span className="ml-1 text-neutral-500">{Object.keys(displayResponse.cookies).length}</span>
          </TabButton>
        )}
        <TabButton active={tab === "timing"} onClick={() => setTab("timing")}>
          Timing
        </TabButton>
        <TabButton active={tab === "console"} onClick={() => setTab("console")}>
          Console
          {consoleEntries.length > 0 && (
            <span className="ml-1 text-neutral-500">{consoleEntries.length}</span>
          )}
        </TabButton>
        <TabButton active={tab === "schema"} onClick={() => setTab("schema")}>
          Schema
        </TabButton>
      </div>
      <div className="min-h-0 flex-1 overflow-hidden">
        {tab === "body" && <BodyView res={displayResponse} onAddAssertion={onAddAssertion} />}
        {tab === "headers" && (
          <HeadersView
            res={displayResponse}
            search={headerSearch}
            onSearchChange={setHeaderSearch}
            searchRef={headerSearchRef}
          />
        )}
        {tab === "cookies" && (
          <CookiesView
            res={displayResponse}
            search={cookieSearch}
            onSearchChange={setCookieSearch}
            searchRef={cookieSearchRef}
          />
        )}
        {tab === "timing" && <TimingView res={displayResponse} />}
        {tab === "console" && <ConsoleView entries={consoleEntries} response={displayResponse} />}
        {tab === "schema" && <SchemaView res={displayResponse} />}
      </div>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-3 py-1.5 text-xs font-medium transition-all duration-150 ${
        active
          ? "border-b-2 border-cobweb-500 text-neutral-100 bg-transparent"
          : "border-b-2 border-transparent text-neutral-500 hover:text-neutral-300"
      }`}
    >
      {children}
    </button>
  );
}

function StatusRow({ res, onDiff, onCodegen, history, onViewHistorical, onAddAssertion }: { res: ExecuteResponse; onDiff?: () => void; onCodegen?: () => void; history?: ResponseSnapshot[]; onViewHistorical?: (snap: ResponseSnapshot) => void; onAddAssertion?: (a: Assertion) => void }) {
  const [histDropdownOpen, setHistDropdownOpen] = useState(false);
  const tone = statusTone(res.status);
  const toneGlow = {
    ok: "shadow-[0_0_16px_-4px_rgba(52,211,153,0.35)]",
    info: "shadow-[0_0_16px_-4px_rgba(6,182,212,0.35)]",
    warn: "shadow-[0_0_16px_-4px_rgba(245,158,11,0.35)]",
    bad: "shadow-[0_0_16px_-4px_rgba(244,63,94,0.35)]",
  };
  const toneBorder = {
    ok: "border-emerald-500/20",
    info: "border-cobweb-500/20",
    warn: "border-amber-500/20",
    bad: "border-rose-500/20",
  };
  const toneText = {
    ok: "text-emerald-300",
    info: "text-cobweb-300",
    warn: "text-amber-300",
    bad: "text-rose-300",
  };

  // Track response time history for sparkline
  const prevMs = responseTimeHistory.length >= 2 ? responseTimeHistory[responseTimeHistory.length - 2] : null;
  const timeTrend = prevMs !== null
    ? res.elapsed_ms > prevMs ? "slower" : res.elapsed_ms < prevMs ? "faster" : "same"
    : "same";

  // Per-URL timing comparison: average of past times vs current
  const urlTimingComparison = useMemo(() => {
    if (!history || history.length < 2) return null;
    const pastTimes = history.slice(0, -1).map((h) => h.elapsed_ms);
    const avg = pastTimes.reduce((sum, t) => sum + t, 0) / pastTimes.length;
    if (avg === 0) return null;
    const ratio = res.elapsed_ms / avg;
    if (ratio < 0.85) {
      const pctFaster = Math.round((1 - ratio) * 100);
      return { label: `${pctFaster}% faster`, color: "text-emerald-400" };
    }
    if (ratio > 1.15) {
      if (ratio >= 2) {
        return { label: `${ratio.toFixed(1)}x slower`, color: "text-rose-400" };
      }
      const pctSlower = Math.round((ratio - 1) * 100);
      return { label: `${pctSlower}% slower`, color: "text-rose-400" };
    }
    return { label: "~same", color: "text-neutral-500" };
  }, [history, res.elapsed_ms]);

  // Sparkline bars from history
  const sparkData = responseTimeHistory.slice(-5);
  const sparkMax = Math.max(...sparkData, 1);

  return (
    <div className="grid grid-cols-4 gap-3 border-b border-glass bg-neutral-950/60 px-4 py-2.5">
      {/* Status card — double-click to add status assertion */}
      <div
        className={`stat-card !py-2 !px-4 flex flex-col items-center justify-center cursor-pointer ${toneGlow[tone]} ${toneBorder[tone]}`}
        style={{ animation: "badge-pop 0.3s ease-out" }}
        key={`${res.status}-${res.elapsed_ms}`}
        onDoubleClick={() => onAddAssertion?.({ type: "status", expected: String(res.status), path: "", operator: "eq" })}
        title="Double-click to add status assertion"
      >
        <span className={`metric-value !text-[28px] font-mono ${toneText[tone]}`}>
          {res.status}
        </span>
        <span className="metric-label">
          {res.status_text || statusName(res.status)}
        </span>
      </div>
      {/* Time card with trend + sparkline + timing bar + history badge */}
      <div className="stat-card !py-2 !px-4 flex flex-col items-center justify-center relative" style={{ animation: "badge-pop 0.3s ease-out 0.05s both" }}>
        <div className="flex items-center gap-1">
          <span className="metric-value !text-[28px] font-mono text-neutral-100">
            {formatMs(res.elapsed_ms)}
          </span>
          {timeTrend === "faster" && <ArrowDown className="h-3.5 w-3.5 text-emerald-400" />}
          {timeTrend === "slower" && <ArrowUp className="h-3.5 w-3.5 text-rose-400" />}
          {timeTrend === "same" && prevMs !== null && <Minus className="h-3 w-3 text-neutral-500" />}
        </div>
        <div className="flex items-center gap-1.5">
          <span className="metric-label">Time</span>
          {urlTimingComparison && (
            <span className={`text-[9px] font-medium ${urlTimingComparison.color}`}>
              {urlTimingComparison.label}
            </span>
          )}
          {history && history.length > 1 && (
            <div className="relative">
              <button
                type="button"
                onClick={() => setHistDropdownOpen((o) => !o)}
                className="inline-flex items-center gap-0.5 rounded-full bg-neutral-800/60 px-1.5 py-0.5 text-[9px] text-neutral-400 transition hover:bg-neutral-700/60 hover:text-neutral-200"
              >
                <Clock className="h-2.5 w-2.5" />
                {history.length} runs
              </button>
              {histDropdownOpen && (
                <div className="absolute right-0 top-full z-30 mt-1 w-56 rounded-md border border-neutral-700 bg-neutral-900 py-1 shadow-lg">
                  <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-neutral-500">Response history</p>
                  {[...history].reverse().map((snap, i) => (
                    <button
                      key={i}
                      type="button"
                      onClick={() => { onViewHistorical?.(snap); setHistDropdownOpen(false); }}
                      className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[11px] text-neutral-300 hover:bg-neutral-800"
                    >
                      <span className={`font-mono font-bold ${snap.status < 300 ? "text-emerald-400" : snap.status < 400 ? "text-cobweb-400" : snap.status < 500 ? "text-amber-400" : "text-rose-400"}`}>{snap.status}</span>
                      <span className="text-neutral-500">{formatMs(snap.elapsed_ms)}</span>
                      <span className="ml-auto text-[10px] text-neutral-600">{new Date(snap.timestamp).toLocaleTimeString()}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
        {sparkData.length > 1 && (
          <div className="mt-1.5 flex items-end gap-[2px]" title={`Last ${sparkData.length} responses`}>
            {sparkData.map((v, i) => (
              <div
                key={i}
                className="w-[6px] rounded-sm bg-neutral-600"
                style={{ height: `${Math.max(3, (v / sparkMax) * 16)}px` }}
              />
            ))}
          </div>
        )}
        {/* Timing comparison bar */}
        <TimingBar elapsed_ms={res.elapsed_ms} />
      </div>
      {/* Size card */}
      <div className="stat-card !py-2 !px-4 flex flex-col items-center justify-center" style={{ animation: "badge-pop 0.3s ease-out 0.1s both" }}>
        <span className="metric-value !text-[28px] font-mono text-neutral-100">
          {formatBytes(res.body_size_bytes)}
        </span>
        <span className="metric-label">Size</span>
      </div>
      {/* Action buttons + URL */}
      <div className="stat-card !py-2 !px-4 flex flex-col items-center justify-center gap-1.5 overflow-hidden">
        <div className="flex items-center gap-1.5">
          {onCodegen && (
            <button
              type="button"
              onClick={onCodegen}
              className="inline-flex items-center gap-1 rounded-lg border border-glass px-2.5 py-1 text-[10px] text-neutral-500 transition hover:bg-white/[0.06] hover:text-neutral-300"
              title="Generate code snippet"
            >
              <Code2 className="h-3 w-3" />
              Code
            </button>
          )}
          {onDiff && (
            <button
              type="button"
              onClick={onDiff}
              className="inline-flex items-center gap-1 rounded-lg border border-glass px-2.5 py-1 text-[10px] text-neutral-500 transition hover:bg-white/[0.06] hover:text-neutral-300"
              title="Compare with previous response"
            >
              <GitCompare className="h-3 w-3" />
              Diff
            </button>
          )}
        </div>
        <span className="truncate font-mono text-[10px] text-neutral-600">
          {res.final_url}
        </span>
      </div>
    </div>
  );
}

const SIZE_WARNING_THRESHOLD = 1024 * 1024;       // 1 MB
const SIZE_FORCE_RAW_THRESHOLD = 5 * 1024 * 1024;  // 5 MB

function decodeBase64(s: string): string {
  try { return atob(s.trim()); } catch { return s; }
}

function decodeJwt(s: string): string {
  const parts = s.trim().split(".");
  if (parts.length < 2) return s;
  try {
    const header = JSON.parse(atob(parts[0].replace(/-/g, "+").replace(/_/g, "/")));
    const payload = JSON.parse(atob(parts[1].replace(/-/g, "+").replace(/_/g, "/")));
    return JSON.stringify({ header, payload }, null, 2);
  } catch { return s; }
}

function parseUrlEncoded(s: string): string {
  try {
    const params = new URLSearchParams(s.trim());
    const obj: Record<string, string> = {};
    for (const [k, v] of params) obj[k] = v;
    return JSON.stringify(obj, null, 2);
  } catch { return s; }
}

function minifyJson(s: string): string {
  try { return JSON.stringify(JSON.parse(s)); } catch { return s; }
}

type BodyTransform = "none" | "format" | "minify" | "base64" | "jwt" | "urlencoded";

function BodyView({ res, onAddAssertion }: { res: ExecuteResponse; onAddAssertion?: (assertion: Assertion) => void }) {
  const ct = res.headers["content-type"] ?? "";
  const pretty = useMemo(() => prettify(res.body, ct), [res.body, ct]);
  const [copyDropdownOpen, setCopyDropdownOpen] = useState(false);
  const [forceRaw, setForceRaw] = useState(false);
  const [viewMode, setViewMode] = useState<BodyViewMode>("editor");
  const [transform, setTransform] = useState<BodyTransform>("none");
  const [transformOpen, setTransformOpen] = useState(false);
  const [searchVisible, setSearchVisible] = useState(false);
  const [searchMatches, setSearchMatches] = useState<BodySearchMatch[]>([]);
  const [currentMatchIdx, setCurrentMatchIdx] = useState(0);
  const decorationsRef = useRef<string[]>([]);

  const displayBody = useMemo(() => {
    if (transform === "minify") return minifyJson(res.body);
    if (transform === "base64") return decodeBase64(res.body);
    if (transform === "jwt") return decodeJwt(res.body);
    if (transform === "urlencoded") return parseUrlEncoded(res.body);
    if (transform === "format") return pretty;
    return pretty; // "none" shows pretty by default
  }, [transform, res.body, pretty]);

  const isLarge = res.body_size_bytes >= SIZE_WARNING_THRESHOLD;
  const isForcedRaw = res.body_size_bytes >= SIZE_FORCE_RAW_THRESHOLD || forceRaw;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const editorRef = useRef<any>(null);
  const bodyContainerRef = useRef<HTMLDivElement>(null);
  const lineCount = useMemo(() => pretty.split("\n").length, [pretty]);
  const isXml = ct.includes("xml") || res.body.trimStart().startsWith("<");

  // Ctrl+F to open search in body view
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "f") {
        if (!bodyContainerRef.current?.contains(document.activeElement) && !bodyContainerRef.current?.matches(":hover")) return;
        e.preventDefault();
        setSearchVisible(true);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Apply Monaco decorations when matches change
  useEffect(() => {
    const editor = editorRef.current;
    if (!editor) return;
    if (searchMatches.length === 0) {
      decorationsRef.current = editor.deltaDecorations(decorationsRef.current, []);
      return;
    }
    const model = editor.getModel();
    if (!model) return;
    const newDecorations = searchMatches.map((m, idx) => {
      const startPos = model.getPositionAt(m.start);
      const endPos = model.getPositionAt(m.end);
      return {
        range: {
          startLineNumber: startPos.lineNumber,
          startColumn: startPos.column,
          endLineNumber: endPos.lineNumber,
          endColumn: endPos.column,
        },
        options: {
          className: idx === currentMatchIdx ? "search-match-current" : "search-match",
          overviewRuler: { color: idx === currentMatchIdx ? "#10b981" : "#6b7280", position: 1 },
        },
      };
    });
    decorationsRef.current = editor.deltaDecorations(decorationsRef.current, newDecorations);
  }, [searchMatches, currentMatchIdx]);

  // Scroll to current match in Monaco
  useEffect(() => {
    const editor = editorRef.current;
    if (!editor || searchMatches.length === 0 || currentMatchIdx < 0) return;
    const match = searchMatches[currentMatchIdx];
    if (!match) return;
    const model = editor.getModel();
    if (!model) return;
    const pos = model.getPositionAt(match.start);
    editor.revealLineInCenter(pos.lineNumber);
  }, [currentMatchIdx, searchMatches]);

  function copyAsFormatted() {
    try {
      const formatted = JSON.stringify(JSON.parse(res.body), null, 2);
      void navigator.clipboard?.writeText(formatted);
    } catch {
      void navigator.clipboard?.writeText(res.body);
    }
    setCopyDropdownOpen(false);
  }

  function copyAsRaw() {
    void navigator.clipboard?.writeText(res.body);
    setCopyDropdownOpen(false);
  }

  function copyAsMarkdown() {
    const lang = ct.includes("json") ? "json" : ct.includes("xml") ? "xml" : "";
    void navigator.clipboard?.writeText("```" + lang + "\n" + res.body + "\n```");
    setCopyDropdownOpen(false);
  }

  function copyWithHeaders() {
    const headerStr = Object.entries(res.headers).map(([k, v]) => `${k}: ${v}`).join("\n");
    void navigator.clipboard?.writeText(headerStr + "\n\n" + res.body);
    setCopyDropdownOpen(false);
  }

  function copyAsShareable() {
    const lines: string[] = [];
    lines.push(`${res.status} ${res.final_url}`);
    for (const [k, v] of Object.entries(res.headers)) {
      lines.push(`${k}: ${v}`);
    }
    if (res.body) {
      lines.push("");
      lines.push(res.body.slice(0, 2000));
    }
    void navigator.clipboard?.writeText(lines.join("\n"));
    setCopyDropdownOpen(false);
  }

  function copyAsShareableLink() {
    const data = {
      url: res.final_url,
      status: res.status,
      headers: res.headers,
      body_preview: res.body.slice(0, 500),
    };
    const encoded = btoa(JSON.stringify(data));
    void navigator.clipboard?.writeText(`theridion://response?data=${encoded}`);
    setCopyDropdownOpen(false);
  }

  function downloadAsFile() {
    const ext = ct.includes("json") ? ".json" : ct.includes("xml") ? ".xml" : ".txt";
    const blob = new Blob([res.body], { type: ct || "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `response${ext}`;
    a.click();
    URL.revokeObjectURL(url);
    setCopyDropdownOpen(false);
  }

  return (
    <div ref={bodyContainerRef} className="relative flex h-full flex-col">
      {/* Body search overlay */}
      <ResponseBodySearch
        body={displayBody}
        visible={searchVisible}
        onClose={() => { setSearchVisible(false); setSearchMatches([]); }}
        onMatchesChange={setSearchMatches}
        onCurrentMatchChange={setCurrentMatchIdx}
        isXml={isXml}
      />
      {/* Large response warning */}
      {isLarge && (
        <div className="flex items-center gap-2 border-b border-amber-800/30 bg-amber-950/20 px-3 py-1.5 text-[11px] text-amber-400">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          Large response ({formatBytes(res.body_size_bytes)}) {isForcedRaw && !forceRaw ? "- forced raw mode" : "- rendering may be slow"}
          {!isForcedRaw && (
            <button type="button" onClick={() => setForceRaw(true)} className="ml-2 rounded border border-amber-700/40 px-1.5 py-0.5 text-[10px] hover:bg-amber-900/30">
              Show raw
            </button>
          )}
          <button type="button" onClick={copyAsRaw} className="ml-1 rounded border border-amber-700/40 px-1.5 py-0.5 text-[10px] hover:bg-amber-900/30">
            Copy to clipboard
          </button>
        </div>
      )}
      {/* Quick-add assertion buttons */}
      {onAddAssertion && (
        <div className="flex items-center gap-1.5 border-b border-glass/60 px-3 py-1">
          <span className="text-[10px] text-neutral-600 mr-1">Quick assert:</span>
          <button
            type="button"
            onClick={() => onAddAssertion({ type: "status", expected: String(res.status), path: "", operator: "eq" })}
            className="inline-flex items-center gap-1 rounded border border-glass px-1.5 py-0.5 text-[10px] text-neutral-500 transition hover:bg-white/[0.06] hover:text-neutral-300"
          >
            + Status {res.status}
          </button>
          {res.headers["content-type"] && (
            <button
              type="button"
              onClick={() => onAddAssertion({ type: "header_equals", expected: res.headers["content-type"], path: "content-type", operator: "eq" })}
              className="inline-flex items-center gap-1 rounded border border-glass px-1.5 py-0.5 text-[10px] text-neutral-500 transition hover:bg-white/[0.06] hover:text-neutral-300"
            >
              + Content-Type
            </button>
          )}
          <button
            type="button"
            onClick={() => onAddAssertion({ type: "response_time", expected: String(Math.ceil(res.elapsed_ms * 2)), path: "", operator: "eq" })}
            className="inline-flex items-center gap-1 rounded border border-glass px-1.5 py-0.5 text-[10px] text-neutral-500 transition hover:bg-white/[0.06] hover:text-neutral-300"
          >
            + Time &lt; {Math.ceil(res.elapsed_ms * 2)} ms
          </button>
          {(() => {
            try {
              const parsed = JSON.parse(res.body);
              if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
                const keys = Object.keys(parsed).slice(0, 3);
                return keys.map((key) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => onAddAssertion({ type: "json_path", expected: JSON.stringify(parsed[key]).slice(0, 50), path: key, operator: "eq" })}
                    className="inline-flex items-center gap-1 rounded border border-glass px-1.5 py-0.5 text-[10px] text-neutral-500 transition hover:bg-white/[0.06] hover:text-neutral-300"
                  >
                    + {key}
                  </button>
                ));
              }
            } catch { /* not JSON */ }
            return null;
          })()}
        </div>
      )}
      {/* Fold/unfold bar + line count */}
      {!isForcedRaw && (
        <div className="flex items-center gap-2 border-b border-glass/60 px-3 py-1">
          <button
            type="button"
            onClick={() => editorRef.current?.trigger("fold", "editor.foldAll", {})}
            className="inline-flex items-center gap-1 rounded border border-glass px-1.5 py-0.5 text-[10px] text-neutral-500 transition hover:bg-white/[0.06] hover:text-neutral-300"
          >
            Collapse All
          </button>
          <button
            type="button"
            onClick={() => editorRef.current?.trigger("unfold", "editor.unfoldAll", {})}
            className="inline-flex items-center gap-1 rounded border border-glass px-1.5 py-0.5 text-[10px] text-neutral-500 transition hover:bg-white/[0.06] hover:text-neutral-300"
          >
            Expand All
          </button>
          <span className="text-[10px] text-neutral-600">{lineCount} lines</span>
        </div>
      )}
      {/* View mode + Transform + Copy dropdowns */}
      <div className="absolute right-3 top-2 z-10 flex items-center gap-1.5">
        {/* View mode toggle (only show Tree option for JSON) */}
        {ct.includes("json") || (() => { try { JSON.parse(res.body); return true; } catch { return false; } })() ? (
          <div className="flex items-stretch rounded border border-glass bg-neutral-900/80 backdrop-blur">
            {(["editor", "tree", "raw"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => { setViewMode(m); if (m === "raw") setForceRaw(true); else setForceRaw(false); }}
                className={`px-2 py-0.5 text-[10px] capitalize transition ${viewMode === m ? "bg-white/10 text-neutral-100" : "text-neutral-500 hover:text-neutral-300"}`}
              >
                {m === "editor" ? "Pretty" : m === "tree" ? "Tree" : "Raw"}
              </button>
            ))}
          </div>
        ) : null}
        {/* Transform dropdown */}
        <div className="relative">
          <button
            type="button"
            onClick={() => setTransformOpen((o) => !o)}
            className={`inline-flex items-center gap-1 rounded border border-glass bg-neutral-900/80 px-2 py-0.5 text-[11px] backdrop-blur transition ${transform !== "none" ? "text-cobweb-400" : "text-neutral-400 hover:text-neutral-200"}`}
            title="Transform body view"
          >
            Transform <ChevronDown className="h-3 w-3" />
          </button>
          {transformOpen && (
            <div className="absolute right-0 top-full z-20 mt-1 w-48 rounded-md border border-neutral-700 bg-neutral-900 py-1 shadow-lg">
              {([
                { key: "none" as BodyTransform, label: "Original (pretty)" },
                { key: "format" as BodyTransform, label: "Format JSON/XML" },
                { key: "minify" as BodyTransform, label: "Minify JSON" },
                { key: "base64" as BodyTransform, label: "Decode Base64" },
                { key: "jwt" as BodyTransform, label: "Decode JWT" },
                { key: "urlencoded" as BodyTransform, label: "Parse URL Encoded" },
              ]).map((t) => (
                <button
                  key={t.key}
                  type="button"
                  onClick={() => { setTransform(t.key); setTransformOpen(false); }}
                  className={`flex w-full items-center px-3 py-1.5 text-left text-xs ${transform === t.key ? "text-cobweb-400 bg-cobweb-600/10" : "text-neutral-300 hover:bg-neutral-800"}`}
                >
                  {transform === t.key && <span className="mr-1.5">&#10003;</span>}
                  {t.label}
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="relative">
          <div className="flex items-stretch rounded border border-glass bg-neutral-900/80 backdrop-blur">
            <button
              type="button"
              onClick={copyAsRaw}
              className="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] text-neutral-400 transition hover:text-neutral-200"
              title="Copy body"
            >
              <Copy className="h-3 w-3" /> Copy
            </button>
            <button
              type="button"
              onClick={() => setCopyDropdownOpen((o) => !o)}
              className="border-l border-glass px-1 text-neutral-500 transition hover:text-neutral-300"
              title="Copy options"
            >
              <ChevronDown className="h-3 w-3" />
            </button>
          </div>
          {copyDropdownOpen && (
            <div className="absolute right-0 top-full z-20 mt-1 w-52 rounded-md border border-neutral-700 bg-neutral-900 py-1 shadow-lg">
              <CopyMenuItem label="Copy as JSON (formatted)" onClick={copyAsFormatted} />
              <CopyMenuItem label="Copy as raw text" onClick={copyAsRaw} />
              <CopyMenuItem label="Copy as Markdown code block" onClick={copyAsMarkdown} />
              <CopyMenuItem label="Copy headers + body" onClick={copyWithHeaders} />
              <CopyMenuItem label="Copy as shareable text" onClick={copyAsShareable} />
              <CopyMenuItem label="Copy as shareable link" onClick={copyAsShareableLink} />
              <div className="mx-2 my-1 border-t border-neutral-800" />
              <button
                type="button"
                onClick={downloadAsFile}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-neutral-300 hover:bg-neutral-800"
              >
                <Download className="h-3 w-3 text-neutral-500" />
                Download as file
              </button>
            </div>
          )}
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-hidden">
        {viewMode === "tree" && !isForcedRaw ? (
          <div className="h-full overflow-auto">
            <JsonTreeView data={(() => { try { return JSON.parse(res.body); } catch { return res.body; } })()} />
          </div>
        ) : isForcedRaw || viewMode === "raw" ? (
          <textarea
            readOnly
            value={res.body}
            className="h-full w-full resize-none bg-transparent p-4 font-mono text-xs text-neutral-100 focus:outline-none"
          />
        ) : (
          <CodeEditor
            value={displayBody}
            contentTypeHint={ct}
            readOnly
            onEditorMount={(editor) => { editorRef.current = editor; }}
          />
        )}
      </div>
    </div>
  );
}

function CopyMenuItem({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center px-3 py-1.5 text-left text-xs text-neutral-300 hover:bg-neutral-800"
    >
      {label}
    </button>
  );
}

function TimingBar({ elapsed_ms }: { elapsed_ms: number }) {
  // Scale: 0-1000ms = full bar. Clamp at 100%.
  const maxMs = 1000;
  const pct = Math.min(100, (elapsed_ms / maxMs) * 100);
  const color =
    elapsed_ms <= 200 ? "bg-emerald-500" :
    elapsed_ms <= 1000 ? "bg-amber-500" :
    "bg-rose-500";
  const dotColor =
    elapsed_ms <= 200 ? "bg-emerald-400" :
    elapsed_ms <= 1000 ? "bg-amber-400" :
    "bg-rose-400";

  return (
    <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-neutral-800" title={`${Math.round(elapsed_ms)} ms`}>
      <div className="relative h-full">
        {/* Green zone: 0-20% */}
        <div className="absolute left-0 top-0 h-full bg-emerald-900/30" style={{ width: "20%" }} />
        {/* Yellow zone: 20-100% */}
        <div className="absolute left-[20%] top-0 h-full bg-amber-900/20" style={{ width: "80%" }} />
        {/* Marker dot */}
        <div
          className={`absolute top-0 h-full w-1.5 rounded-full ${color} shadow-[0_0_4px_rgba(0,0,0,0.4)]`}
          style={{ left: `calc(${pct}% - 3px)` }}
        />
        {/* Filled portion */}
        <div className={`h-full rounded-full ${dotColor}/30`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function HeaderRow({ name, value }: { name: string; value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <tr className="border-t border-glass/60 hover:bg-neutral-900/40 group">
      <td className="px-4 py-1.5 font-mono text-neutral-400">{name}</td>
      <td
        className="px-4 py-1.5 font-mono text-neutral-100 break-all cursor-pointer relative"
        title="Click to copy value"
        onClick={() => {
          void navigator.clipboard?.writeText(value);
          setCopied(true);
          setTimeout(() => setCopied(false), 1000);
        }}
      >
        {value}
        {copied && (
          <span className="absolute right-2 top-1/2 -translate-y-1/2 rounded bg-cobweb-600/30 px-1.5 py-0.5 text-[10px] text-cobweb-400 animate-fade-in">
            Copied!
          </span>
        )}
      </td>
    </tr>
  );
}

function HeadersView({
  res,
  search,
  onSearchChange,
  searchRef,
}: {
  res: ExecuteResponse;
  search: string;
  onSearchChange: (s: string) => void;
  searchRef: React.Ref<HTMLInputElement>;
}) {
  const q = search.toLowerCase();
  const filtered = useMemo(
    () =>
      Object.entries(res.headers).filter(
        ([k, v]) => !q || k.toLowerCase().includes(q) || v.toLowerCase().includes(q),
      ),
    [res.headers, q],
  );
  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex items-center gap-2 border-b border-glass/60 px-4 py-1.5">
        <Search className="h-3 w-3 text-neutral-500" />
        <input
          ref={searchRef}
          type="text"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Filter headers..."
          className="flex-1 bg-transparent text-xs text-neutral-100 outline-none placeholder:text-neutral-600"
          spellCheck={false}
        />
        {search && (
          <span className="text-[10px] text-neutral-500">{filtered.length} / {Object.keys(res.headers).length}</span>
        )}
      </div>
      <div className="flex-1 overflow-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-neutral-925/80 text-[11px] uppercase tracking-wider text-neutral-500 backdrop-blur-md [&_tr]:border-b [&_tr]:border-cobweb-500/10">
            <tr>
              <th className="px-4 py-1.5 text-left font-medium">Name</th>
              <th className="px-4 py-1.5 text-left font-medium">Value</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(([k, v]) => (
              <HeaderRow key={k} name={k} value={v} />
            ))}
          </tbody>
        </table>
        <HeaderInsightsPanel headers={res.headers} />
      </div>
    </div>
  );
}

function HeaderInsightsPanel({ headers }: { headers: Record<string, string> }) {
  const [expanded, setExpanded] = useState(false);
  const [insights, setInsights] = useState<HeaderInsightsOutput | null>(null);
  const [loading, setLoading] = useState(false);
  const headersKey = useMemo(() => JSON.stringify(headers), [headers]);

  useEffect(() => {
    if (!expanded) return;
    let cancelled = false;
    setLoading(true);
    sidecar.analyzeHeaders(headers).then((result) => {
      if (!cancelled) setInsights(result);
    }).catch(() => {
      if (!cancelled) setInsights(null);
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expanded, headersKey]);

  // Quick local score for the collapsed badge
  const quickScore = useMemo(() => {
    if (insights) return insights.score;
    const secHeaders = ["strict-transport-security", "content-security-policy", "x-frame-options", "x-content-type-options", "referrer-policy", "permissions-policy"];
    const lower = Object.keys(headers).map((k) => k.toLowerCase());
    const found = secHeaders.filter((h) => lower.includes(h)).length;
    return Math.round((found / secHeaders.length) * 100);
  }, [headers, insights]);

  const gradeColor = (grade: string) => {
    if (grade === "A") return "text-emerald-400 bg-emerald-950/40 border-emerald-700/30";
    if (grade === "B") return "text-emerald-300 bg-emerald-950/30 border-emerald-700/20";
    if (grade === "C") return "text-amber-400 bg-amber-950/40 border-amber-700/30";
    if (grade === "D") return "text-amber-300 bg-amber-950/30 border-amber-700/20";
    return "text-rose-400 bg-rose-950/40 border-rose-700/30";
  };

  const scoreColor = quickScore >= 70 ? "text-emerald-400" : quickScore >= 40 ? "text-amber-400" : "text-rose-400";

  const statusIcon = (status: string) => {
    if (status === "good") return <span className="text-emerald-400">{"\u2713"}</span>;
    if (status === "warning") return <span className="text-amber-400">{"\u26A0"}</span>;
    if (status === "missing") return <span className="text-rose-400">{"\u2717"}</span>;
    return <span className="text-neutral-500">{"\u2139"}</span>;
  };

  const categoryLabel: Record<string, string> = {
    security: "Security",
    caching: "Caching",
    performance: "Performance",
    info_leak: "Info Leak",
    compression: "Compression",
  };

  return (
    <div className="border-t border-glass/60">
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="flex w-full items-center justify-between px-4 py-2 text-left text-[11px] text-neutral-500 transition hover:bg-neutral-900/40"
      >
        <span className="flex items-center gap-1.5 uppercase tracking-wider font-medium">
          <Shield className="h-3 w-3" />
          Header Insights
        </span>
        <span className="flex items-center gap-2">
          <span className={`font-mono font-bold ${scoreColor}`}>{quickScore}%</span>
          {insights && (
            <span className={`rounded border px-1.5 py-0.5 text-[10px] font-bold ${gradeColor(insights.grade)}`}>
              {insights.grade}
            </span>
          )}
          <span className="text-neutral-600">{expanded ? "\u25B2" : "\u25BC"}</span>
        </span>
      </button>
      {expanded && (
        <div className="px-4 pb-4">
          {loading && !insights && (
            <div className="py-3 text-center text-xs text-neutral-500">Analyzing headers...</div>
          )}
          {insights && (
            <div className="space-y-4">
              {/* Score badge */}
              <div className="flex items-center gap-4">
                <div className={`flex items-center justify-center rounded-lg border px-3 py-2 ${gradeColor(insights.grade)}`}>
                  <span className="text-[28px] font-bold font-mono leading-none">{insights.grade}</span>
                </div>
                <div>
                  <div className="text-sm font-medium text-neutral-200">Security Score: {insights.score}/100</div>
                  <div className="text-[11px] text-neutral-500">{insights.findings.filter((f) => f.status === "good").length} checks passed</div>
                </div>
              </div>

              {/* Caching summary */}
              <div className="rounded-md border border-glass bg-neutral-900/40 p-3">
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="text-[11px] uppercase tracking-wider text-neutral-500 font-medium">Caching</span>
                  <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                    insights.caching.strategy === "aggressive" ? "bg-emerald-950/40 text-emerald-400" :
                    insights.caching.strategy === "public" ? "bg-cobweb-950/40 text-cobweb-400" :
                    insights.caching.strategy === "private" ? "bg-amber-950/40 text-amber-400" :
                    "bg-neutral-800 text-neutral-400"
                  }`}>
                    {insights.caching.strategy}
                  </span>
                  {insights.caching.effective_ttl !== null && (
                    <span className="text-[10px] font-mono text-neutral-400">
                      TTL: {insights.caching.effective_ttl}s
                    </span>
                  )}
                </div>
                <div className="text-xs text-neutral-400">{insights.caching.summary}</div>
              </div>

              {/* Findings grouped by category */}
              {(["security", "caching", "performance", "info_leak", "compression"] as const).map((cat) => {
                const catFindings = insights.findings.filter((f) => f.category === cat);
                if (catFindings.length === 0) return null;
                return (
                  <div key={cat}>
                    <div className="text-[11px] uppercase tracking-wider text-neutral-500 font-medium mb-1.5">
                      {categoryLabel[cat]}
                    </div>
                    <div className="space-y-1">
                      {catFindings.map((f, i) => (
                        <div key={i} className="flex items-start gap-2 rounded-md border border-glass/40 bg-neutral-900/30 px-3 py-1.5 text-xs">
                          {statusIcon(f.status)}
                          <div className="flex-1 min-w-0">
                            <span className="font-mono text-neutral-300 mr-1.5">{f.header}</span>
                            <span className="text-neutral-500">{f.message}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}

              {/* Recommendations */}
              {insights.recommendations.length > 0 && (
                <div>
                  <div className="text-[11px] uppercase tracking-wider text-neutral-500 font-medium mb-1.5">
                    Recommendations
                  </div>
                  <div className="space-y-1.5">
                    {insights.recommendations.map((rec, i) => (
                      <div key={i} className="flex items-start gap-2 rounded-md border border-glass/40 bg-neutral-900/30 px-3 py-2 text-xs">
                        <span className={`shrink-0 rounded px-1 py-0.5 text-[9px] font-medium ${
                          rec.severity === "high" ? "bg-rose-950/40 text-rose-400" :
                          rec.severity === "medium" ? "bg-amber-950/40 text-amber-400" :
                          "bg-neutral-800 text-neutral-500"
                        }`}>
                          {rec.severity}
                        </span>
                        <div className="flex-1 min-w-0">
                          <div className="text-neutral-300">{rec.message}</div>
                          {rec.suggested_value && (
                            <div className="mt-1 flex items-center gap-1.5">
                              <code className="rounded bg-neutral-800 px-1.5 py-0.5 font-mono text-[10px] text-neutral-400 break-all">
                                {rec.header}: {rec.suggested_value}
                              </code>
                              <button
                                type="button"
                                onClick={() => void navigator.clipboard?.writeText(`${rec.header}: ${rec.suggested_value}`)}
                                className="shrink-0 rounded p-0.5 text-neutral-600 transition hover:bg-neutral-800 hover:text-neutral-300"
                                title="Copy suggested header"
                              >
                                <Copy className="h-3 w-3" />
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function CookiesView({
  res,
  search,
  onSearchChange,
  searchRef,
}: {
  res: ExecuteResponse;
  search: string;
  onSearchChange: (s: string) => void;
  searchRef: React.Ref<HTMLInputElement>;
}) {
  const allEntries = Object.entries(res.cookies ?? {});
  if (allEntries.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-neutral-500">
        No cookies in this response
      </div>
    );
  }
  const q = search.toLowerCase();
  const filtered = allEntries.filter(
    ([k, v]) => !q || k.toLowerCase().includes(q) || v.toLowerCase().includes(q),
  );
  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex items-center gap-2 border-b border-glass/60 px-4 py-1.5">
        <Search className="h-3 w-3 text-neutral-500" />
        <input
          ref={searchRef}
          type="text"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Filter cookies..."
          className="flex-1 bg-transparent text-xs text-neutral-100 outline-none placeholder:text-neutral-600"
          spellCheck={false}
        />
        {search && (
          <span className="text-[10px] text-neutral-500">{filtered.length} / {allEntries.length}</span>
        )}
      </div>
      <div className="flex-1 overflow-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-neutral-925/80 text-[11px] uppercase tracking-wider text-neutral-500 backdrop-blur-md [&_tr]:border-b [&_tr]:border-cobweb-500/10">
            <tr>
              <th className="px-4 py-1.5 text-left font-medium">Name</th>
              <th className="px-4 py-1.5 text-left font-medium">Value</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(([k, v]) => (
              <tr key={k} className="border-t border-glass/60 hover:bg-neutral-900/40">
                <td className="px-4 py-1.5 font-mono text-neutral-400">{k}</td>
                <td className="px-4 py-1.5 font-mono text-neutral-100 break-all">{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const TIMING_PHASES: { key: keyof TimingBreakdown; label: string; color: string; hex: string }[] = [
  { key: "dns_ms", label: "DNS Lookup", color: "bg-blue-400", hex: "#60a5fa" },
  { key: "connect_ms", label: "TCP Connect", color: "bg-emerald-400", hex: "#34d399" },
  { key: "tls_ms", label: "TLS Handshake", color: "bg-violet-400", hex: "#a78bfa" },
  { key: "server_processing_ms", label: "Server Processing", color: "bg-amber-400", hex: "#fbbf24" },
  { key: "transfer_ms", label: "Content Transfer", color: "bg-cyan-400", hex: "#22d3ee" },
];

function TimingView({ res }: { res: ExecuteResponse }) {
  const t = res.timing;
  if (!t) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-neutral-500">
        No timing data available
      </div>
    );
  }
  const total = t.total_ms || 1;

  // Filter to phases that have a value > 0.
  const activePhases = TIMING_PHASES.filter((p) => t[p.key] > 0);

  return (
    <div className="p-4">
      <p className="mb-3 text-[11px] uppercase tracking-wider text-neutral-500">
        Request timing — {formatMs(t.total_ms)} total
      </p>

      {/* Waterfall bar — all phases as adjacent colored segments */}
      <div className="mb-4 rounded-md bg-neutral-900/80 p-3">
        <div className="flex h-[7px] w-full overflow-hidden rounded-full bg-neutral-800">
          {activePhases.map((phase) => {
            const pct = Math.max(1, (t[phase.key] / total) * 100);
            return (
              <div
                key={phase.key}
                className="relative h-full first:rounded-l-full last:rounded-r-full"
                style={{ width: `${pct}%`, backgroundColor: phase.hex }}
                title={`${phase.label}: ${formatMs(t[phase.key])}`}
              />
            );
          })}
        </div>
        {/* Legend row */}
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
          {activePhases.map((phase) => (
            <div key={phase.key} className="flex items-center gap-1.5 text-[10px] text-neutral-400">
              <span className="inline-block h-2 w-2 rounded-sm" style={{ backgroundColor: phase.hex }} />
              {phase.label}
              <span className="font-mono text-neutral-300">{formatMs(t[phase.key])}</span>
            </div>
          ))}
          <div className="ml-auto text-[10px] font-mono font-bold text-neutral-200">
            {formatMs(t.total_ms)}
          </div>
        </div>
      </div>

      {/* Per-phase breakdown bars */}
      <div className="space-y-2">
        {TIMING_PHASES.map((phase) => {
          const val = t[phase.key];
          if (!val) return null;
          const pct = Math.max(2, (val / total) * 100);
          return (
            <div key={phase.key}>
              <div className="mb-0.5 flex items-baseline justify-between text-xs">
                <span className="flex items-center gap-1.5 text-neutral-400">
                  <span className="inline-block h-2 w-2 rounded-sm" style={{ backgroundColor: phase.hex }} />
                  {phase.label}
                </span>
                <span className="font-mono text-neutral-200">{formatMs(val)}</span>
              </div>
              <div className="h-[6px] w-full overflow-hidden rounded-full bg-neutral-800">
                <div
                  className="h-full rounded-full"
                  style={{ width: `${pct}%`, backgroundColor: phase.hex }}
                />
              </div>
            </div>
          );
        })}
      </div>
      <div className="mt-4 border-t border-glass pt-3">
        <div className="flex items-baseline justify-between text-xs">
          <span className="font-medium text-neutral-300">Total</span>
          <span className="font-mono font-bold text-neutral-100">{formatMs(t.total_ms)}</span>
        </div>
      </div>
    </div>
  );
}

function ConsoleView({ entries, response }: { entries: ConsoleEntry[]; response: ExecuteResponse }) {
  const lifecycle: ConsoleEntry[] = [
    { timestamp: response.elapsed_ms ? Date.now() - response.elapsed_ms : Date.now(), level: "info", message: `Request sent to ${response.final_url}` },
    { timestamp: Date.now(), level: "info", message: `Response received: ${response.status} ${response.status_text || ""} in ${formatMs(response.elapsed_ms)}` },
  ];
  const all = [...lifecycle, ...entries].sort((a, b) => a.timestamp - b.timestamp);
  const levelColor: Record<string, string> = {
    info: "text-cobweb-400",
    log: "text-neutral-300",
    warn: "text-amber-400",
    error: "text-rose-400",
  };
  return (
    <div className="h-full overflow-auto p-4 font-mono text-xs">
      {all.map((e, i) => (
        <div key={i} className="flex gap-3 py-0.5">
          <span className="shrink-0 text-neutral-600">{new Date(e.timestamp).toLocaleTimeString()}</span>
          <Terminal className="mt-0.5 h-3 w-3 shrink-0 text-neutral-600" />
          <span className={levelColor[e.level] ?? "text-neutral-300"}>{e.message}</span>
        </div>
      ))}
      {all.length === 0 && (
        <div className="flex h-full items-center justify-center text-neutral-500">
          No console output
        </div>
      )}
    </div>
  );
}

function SchemaView({ res }: { res: ExecuteResponse }) {
  const [schema, setSchema] = useState("");
  const [result, setResult] = useState<SchemaValidateOutput | null>(null);
  const [validating, setValidating] = useState(false);
  const [schemaError, setSchemaError] = useState<string | null>(null);

  const validate = useCallback(async () => {
    if (!schema.trim()) return;
    setValidating(true);
    setSchemaError(null);
    try {
      const r = await sidecar.validateSchema(res.body, schema);
      setResult(r);
    } catch (e: unknown) {
      setSchemaError(e instanceof Error ? e.message : String(e));
    } finally {
      setValidating(false);
    }
  }, [res.body, schema]);

  return (
    <div className="flex h-full flex-col gap-3 overflow-auto p-4">
      <div className="flex items-center justify-between">
        <p className="text-[11px] uppercase tracking-wider text-neutral-500">
          JSON Schema Validation
        </p>
        <button
          type="button"
          onClick={validate}
          disabled={validating || !schema.trim()}
          className="rounded-md border border-glass bg-cobweb-600/20 px-3 py-1 text-xs font-medium text-cobweb-400 transition hover:bg-cobweb-600/30 disabled:opacity-40"
        >
          {validating ? "Validating..." : "Validate"}
        </button>
      </div>
      <div className="min-h-[120px] flex-1 overflow-hidden rounded border border-glass bg-neutral-900/50">
        <CodeEditor
          value={schema}
          onChange={setSchema}
          language="json"
          placeholder='{"type": "object", "properties": {...}}'
        />
      </div>
      {schemaError && (
        <div className="rounded border border-rose-800/50 bg-rose-950/20 px-3 py-2 text-xs text-rose-400">
          {schemaError}
        </div>
      )}
      {result && (
        <div className={`rounded border px-3 py-2 text-xs ${
          result.valid
            ? "border-emerald-800/50 bg-emerald-950/20"
            : "border-rose-800/50 bg-rose-950/20"
        }`}>
          <div className="flex items-center gap-2 font-medium">
            {result.valid ? (
              <>
                <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                <span className="text-emerald-400">Schema validation passed</span>
              </>
            ) : (
              <>
                <XCircle className="h-4 w-4 text-rose-400" />
                <span className="text-rose-400">{result.errors.length} validation error{result.errors.length !== 1 ? "s" : ""}</span>
              </>
            )}
          </div>
          {result.errors.length > 0 && (
            <ul className="mt-2 space-y-1">
              {result.errors.map((err, i) => (
                <li key={i} className="text-rose-300">
                  <span className="font-mono text-rose-400">{err.path || "$"}</span>: {err.message}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function WelcomeScreen({
  onImportCollection,
  onOpenSwagger,
  onOpenAgentExplorer,
  onNewCollection,
}: {
  onImportCollection?: () => void;
  onOpenSwagger?: () => void;
  onOpenAgentExplorer?: () => void;
  onNewCollection?: () => void;
}) {
  const actions = [
    { label: "Import from Postman/Insomnia", icon: Upload, onClick: onImportCollection },
    { label: "Load OpenAPI/Swagger Spec", icon: FileCode, onClick: onOpenSwagger },
    { label: "AI: Explore an API", icon: Bot, onClick: onOpenAgentExplorer },
    { label: "New Collection", icon: FolderPlus, onClick: onNewCollection },
  ];
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 text-center">
      <div className="mb-5 rounded-full bg-cobweb-950/30 p-5">
        <Zap className="h-10 w-10 text-cobweb-400" />
      </div>
      <h2 className="text-lg font-semibold text-neutral-200">Welcome to Theridion</h2>
      <p className="mt-1.5 text-sm text-neutral-500">The privacy-first API testing tool</p>

      <div className="mt-6 w-full max-w-xs rounded-lg border border-glass bg-neutral-900/40 px-4 py-3 text-left">
        <p className="text-xs text-neutral-400">
          <span className="mr-1.5 text-cobweb-400">1.</span>
          Enter a URL above and hit <kbd className="rounded border border-glass bg-neutral-800 px-1 py-0.5 font-mono text-[10px] text-neutral-300">Send</kbd>
        </p>
      </div>

      <p className="mt-5 text-xs text-neutral-500">Or get started with:</p>

      <div className="mt-3 grid w-full max-w-xs grid-cols-2 gap-3">
        {actions.map((a, i) => (
          <button
            key={a.label}
            type="button"
            onClick={a.onClick}
            disabled={!a.onClick}
            className={`group flex items-center gap-2.5 rounded-lg border border-glass bg-neutral-900/40 px-3 text-xs text-neutral-300 transition hover:bg-white/[0.05] hover:text-neutral-100 hover:-translate-y-0.5 hover:shadow-lg disabled:cursor-not-allowed disabled:opacity-40 ${
              i === 0 ? "col-span-2 py-4 flex-col items-center text-center" : "py-2.5"
            }`}
          >
            <a.icon className={`shrink-0 text-neutral-500 group-hover:text-neutral-300 transition ${i === 0 ? "h-5 w-5" : "h-3.5 w-3.5"}`} />
            <span>{a.label}</span>
            {i === 0 && <span className="text-[10px] text-neutral-600">Import from Postman, Insomnia, or any cURL</span>}
          </button>
        ))}
      </div>

      <div className="mt-6 space-y-1 text-[11px] text-neutral-600">
        <p><kbd className="font-mono">&#x2318;T</kbd> new tab &middot; <kbd className="font-mono">&#x2318;K</kbd> commands</p>
        <p><kbd className="font-mono">&#x2318;,</kbd> settings &middot; <kbd className="font-mono">&#x2318;&#x21E7;N</kbd> network</p>
      </div>
    </div>
  );
}

function Empty() {
  return (
    <div className="relative flex h-full flex-col">
      {/* Ghost skeleton preview of what response will look like */}
      <div className="pointer-events-none opacity-[0.35]">
        {/* Ghost status row */}
        <div className="grid grid-cols-4 gap-3 border-b border-glass bg-neutral-950/60 px-4 py-2.5">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="stat-card !py-3 !px-4 flex flex-col items-center gap-2">
              <div className="h-7 w-16 rounded bg-neutral-800/40" />
              <div className="h-3 w-10 rounded bg-neutral-800/30" />
            </div>
          ))}
        </div>
        {/* Ghost tab bar */}
        <div className="flex items-center gap-1 border-b border-glass px-2 py-1.5">
          {[48, 56, 44, 52].map((w, i) => (
            <div key={i} className="h-7 rounded-lg bg-neutral-800/30" style={{ width: w }} />
          ))}
        </div>
        {/* Ghost code lines */}
        <div className="space-y-2 px-4 py-4">
          {[85, 60, 92, 45, 78, 55].map((pct, i) => (
            <div key={i} className="h-4 rounded bg-neutral-800/25" style={{ width: `${pct}%` }} />
          ))}
        </div>
      </div>
      {/* Overlay CTA */}
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
        <div className="mb-4 rounded-full bg-neutral-900/80 p-4">
          <Inbox className="h-8 w-8 text-neutral-600" />
        </div>
        <p className="text-sm font-medium text-neutral-400">No response yet</p>
        <p className="mt-2 text-xs text-neutral-600">
          Hit{" "}
          <kbd className="rounded-md border border-glass bg-neutral-900/80 px-1.5 py-0.5 font-mono text-[10px] text-neutral-400 shadow-inner-glow">
            Send
          </kbd>{" "}
          or press{" "}
          <kbd className="rounded-md border border-glass bg-neutral-900/80 px-1.5 py-0.5 font-mono text-[10px] text-neutral-400 shadow-inner-glow">
            &#x2318;&#x23CE;
          </kbd>
        </p>
      </div>
    </div>
  );
}

function Loading() {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const start = Date.now();
    const id = setInterval(() => setElapsed(Date.now() - start), 100);
    return () => clearInterval(id);
  }, []);
  const secs = (elapsed / 1000).toFixed(1);

  return (
    <div className="flex h-full flex-col">
      {/* Skeleton status row (4 cards) */}
      <div className="grid grid-cols-4 gap-3 border-b border-glass bg-neutral-950/60 px-4 py-2.5">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="stat-card !py-3 !px-4 flex flex-col items-center gap-2">
            <div className="skeleton h-7 w-16" />
            <div className="skeleton h-3 w-10" />
          </div>
        ))}
      </div>
      {/* Skeleton tab bar */}
      <div className="flex items-center gap-1 border-b border-glass px-2 py-1.5">
        {[48, 56, 44, 52, 48, 44].map((w, i) => (
          <div key={i} className="skeleton h-7" style={{ width: w }} />
        ))}
      </div>
      {/* Skeleton code lines */}
      <div className="flex-1 space-y-2 px-4 py-4">
        {[85, 60, 92, 45, 78, 55, 88, 40].map((pct, i) => (
          <div key={i} className="skeleton h-4" style={{ width: `${pct}%` }} />
        ))}
      </div>
      <div className="flex items-center justify-center gap-3 pb-4">
        <span className="text-xs text-neutral-500 tracking-wide">Sending request...</span>
        <span className="font-mono text-xs text-neutral-400 tabular-nums">{secs}s</span>
      </div>
    </div>
  );
}

function categorizeError(error: string): { icon: React.ReactNode; title: string; hint: string } {
  if (error.includes("ECONNREFUSED") || error.includes("Connection refused"))
    return { icon: <Inbox className="h-8 w-8 text-rose-500" />, title: "Connection refused", hint: "Is the server running? Check the URL and port." };
  if (error.includes("timeout") || error.includes("Timeout"))
    return { icon: <Clock className="h-8 w-8 text-amber-500" />, title: "Request timed out", hint: "The server took too long to respond. Try increasing the timeout in Settings." };
  if (error.includes("ENOTFOUND") || error.includes("getaddrinfo"))
    return { icon: <Upload className="h-8 w-8 text-rose-500" />, title: "DNS resolution failed", hint: "Check the hostname. Is it spelled correctly?" };
  if (error.includes("SSL") || error.includes("certificate"))
    return { icon: <AlertTriangle className="h-8 w-8 text-amber-500" />, title: "SSL/TLS error", hint: "Certificate issue. Try disabling SSL verification in Settings." };
  return { icon: <AlertTriangle className="h-8 w-8 text-rose-500" />, title: "Request failed", hint: error };
}

function ErrorView({ error }: { error: string }) {
  const cat = categorizeError(error);
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 text-center">
      <div className="mb-4 rounded-full bg-rose-950/30 p-4">
        {cat.icon}
      </div>
      <p className="text-sm font-semibold text-rose-300">{cat.title}</p>
      <p className="mt-2 max-w-md break-words text-xs leading-relaxed text-neutral-400">{cat.hint}</p>
      {cat.title !== "Request failed" && (
        <p className="mt-3 max-w-md break-words font-mono text-[10px] leading-relaxed text-neutral-600">{error}</p>
      )}
    </div>
  );
}

function statusTone(s: number): "ok" | "info" | "warn" | "bad" {
  if (s >= 500) return "bad";
  if (s >= 400) return "warn";
  if (s >= 300) return "info";
  return "ok";
}

function statusName(s: number): string {
  const names: Record<number, string> = {
    200: "OK", 201: "Created", 202: "Accepted", 204: "No Content",
    301: "Moved Permanently", 302: "Found", 304: "Not Modified",
    400: "Bad Request", 401: "Unauthorized", 403: "Forbidden", 404: "Not Found",
    422: "Unprocessable", 429: "Too Many Requests",
    500: "Internal Server Error", 502: "Bad Gateway", 503: "Service Unavailable",
  };
  return names[s] ?? "";
}

function formatMs(ms: number): string {
  if (ms < 1) return "<1 ms";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

function prettify(body: string, contentType: string): string {
  if (contentType.includes("application/json") || looksLikeJson(body)) {
    try {
      return JSON.stringify(JSON.parse(body), null, 2);
    } catch {
      // fall through
    }
  }
  if (contentType.includes("xml") || looksLikeXml(body)) {
    try {
      return prettyXml(body);
    } catch {
      // fall through
    }
  }
  return body;
}

function looksLikeJson(s: string): boolean {
  const t = s.trimStart();
  return t.startsWith("{") || t.startsWith("[");
}

function looksLikeXml(s: string): boolean {
  const t = s.trimStart();
  return t.startsWith("<?xml") || t.startsWith("<") && t.includes("</");
}

function prettyXml(xml: string): string {
  let indent = 0;
  const lines: string[] = [];
  // Split on tags
  xml.replace(/>\s*</g, ">\n<").split("\n").forEach((node) => {
    const n = node.trim();
    if (!n) return;
    if (n.startsWith("</")) indent--;
    lines.push("  ".repeat(Math.max(0, indent)) + n);
    if (n.startsWith("<") && !n.startsWith("</") && !n.startsWith("<?") && !n.endsWith("/>") && !/<\/[^>]+>$/.test(n)) indent++;
  });
  return lines.join("\n");
}

function GoldenFileBar({ comparison, onSave, saving, onUpdate }: {
  comparison: AutoCompareOutput | null;
  onSave: () => void;
  saving: boolean;
  onUpdate: () => void;
}) {
  if (!comparison) {
    // No golden file yet — show "Save as Golden" button
    return (
      <div className="flex items-center gap-2 border-b border-neutral-800/50 bg-neutral-950/40 px-3 py-1">
        <button
          type="button"
          onClick={onSave}
          disabled={saving}
          className="inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-[11px] text-neutral-500 transition hover:bg-neutral-800 hover:text-neutral-300 disabled:opacity-50"
          title="Save current response as golden file baseline"
        >
          <Star className="h-3 w-3" />
          {saving ? "Saving..." : "Save as Golden"}
        </button>
      </div>
    );
  }

  if (!comparison.found) {
    // No matching golden found for this URL
    return (
      <div className="flex items-center gap-2 border-b border-neutral-800/50 bg-neutral-950/40 px-3 py-1">
        <button
          type="button"
          onClick={onSave}
          disabled={saving}
          className="inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-[11px] text-neutral-500 transition hover:bg-neutral-800 hover:text-neutral-300 disabled:opacity-50"
          title="Save current response as golden file baseline"
        >
          <Star className="h-3 w-3" />
          {saving ? "Saving..." : "Save as Golden"}
        </button>
      </div>
    );
  }

  // Golden file exists — show comparison result
  const cmp = comparison.comparison!;
  const isMatch = cmp.match;
  const scorePercent = Math.round(cmp.score * 100);

  return (
    <div className={`flex items-center gap-2 border-b px-3 py-1 text-[11px] ${
      isMatch
        ? "border-emerald-800/30 bg-emerald-950/20 text-emerald-400"
        : "border-amber-800/30 bg-amber-950/20 text-amber-400"
    }`}>
      {isMatch ? (
        <>
          <CheckCircle2 className="h-3 w-3 text-emerald-400" />
          <span>Golden match ({scorePercent}%) — {comparison.golden_name}</span>
        </>
      ) : (
        <>
          <AlertTriangle className="h-3 w-3 text-amber-400" />
          <span>
            Drift detected ({scorePercent}% match) — {comparison.golden_name}
            {!cmp.status_match && " | status changed"}
            {!cmp.body_match && ` | body: +${cmp.body_diff.additions}/-${cmp.body_diff.deletions}`}
            {cmp.header_changes.length > 0 && ` | ${cmp.header_changes.length} header changes`}
          </span>
        </>
      )}
      <div className="ml-auto flex items-center gap-1.5">
        {!isMatch && (
          <button
            type="button"
            onClick={onUpdate}
            disabled={saving}
            className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] text-amber-500 transition hover:bg-amber-900/30 hover:text-amber-300 disabled:opacity-50"
            title="Update golden file with current response"
          >
            <RefreshCw className="h-2.5 w-2.5" />
            Update Golden
          </button>
        )}
      </div>
    </div>
  );
}
