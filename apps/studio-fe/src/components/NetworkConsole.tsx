import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  Cookie,
  FileText,
  Filter,
  Pause,
  Play,
  Search,
  Timer,
  Trash2,
  X,
} from "lucide-react";
import { CodeEditor } from "./CodeEditor";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type NetworkEntryType = "xhr" | "ws" | "soap" | "graphql" | "grpc" | "other";

export interface NetworkEntry {
  id: string;
  timestamp: number;
  method: string;
  url: string;
  status: number;
  statusText: string;
  type: NetworkEntryType;
  requestHeaders: Record<string, string>;
  responseHeaders: Record<string, string>;
  requestBody: string | null;
  responseBody: string;
  cookies: Record<string, string>;
  size: number;
  elapsed_ms: number;
  timing?: {
    dns_ms: number;
    connect_ms: number;
    tls_ms: number;
    ttfb_ms: number;
    download_ms: number;
  };
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface Props {
  entries: NetworkEntry[];
  recording: boolean;
  onToggleRecording: () => void;
  onClear: () => void;
  preserveLog: boolean;
  onTogglePreserveLog: () => void;
  onExportHar?: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type SortField = "status" | "method" | "url" | "type" | "size" | "elapsed_ms";
type SortDir = "asc" | "desc";

const TYPE_FILTERS: { label: string; value: NetworkEntryType | "all" }[] = [
  { label: "All", value: "all" },
  { label: "XHR", value: "xhr" },
  { label: "WS", value: "ws" },
  { label: "SOAP", value: "soap" },
  { label: "GraphQL", value: "graphql" },
  { label: "gRPC", value: "grpc" },
  { label: "Other", value: "other" },
];

function statusColor(s: number): string {
  if (s >= 500) return "text-rose-400";
  if (s >= 400) return "text-amber-400";
  if (s >= 300) return "text-cobweb-400";
  return "text-emerald-400";
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

function formatMs(ms: number): string {
  if (ms < 1) return "<1 ms";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

function typeLabel(t: NetworkEntryType): string {
  return t.toUpperCase();
}

function typeBadgeClass(t: NetworkEntryType): string {
  switch (t) {
    case "xhr": return "border-cobweb-700/40 bg-cobweb-500/10 text-cobweb-400";
    case "soap": return "border-violet-700/40 bg-violet-500/10 text-violet-400";
    case "graphql": return "border-pink-700/40 bg-pink-500/10 text-pink-400";
    case "grpc": return "border-amber-700/40 bg-amber-500/10 text-amber-400";
    case "ws": return "border-emerald-700/40 bg-emerald-500/10 text-emerald-400";
    default: return "border-neutral-700/40 bg-neutral-500/10 text-neutral-400";
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

type DetailTab = "headers" | "payload" | "response" | "timing" | "cookies";

export function NetworkConsole({
  entries,
  recording,
  onToggleRecording,
  onClear,
  preserveLog,
  onTogglePreserveLog,
  onExportHar,
}: Props) {
  const [filter, setFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState<NetworkEntryType | "all">("all");
  const [sortField, setSortField] = useState<SortField | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detailTab, setDetailTab] = useState<DetailTab>("headers");
  const [detailHeaderSearch, setDetailHeaderSearch] = useState("");
  const tableRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new entries arrive and recording.
  useEffect(() => {
    if (recording && tableRef.current) {
      tableRef.current.scrollTop = tableRef.current.scrollHeight;
    }
  }, [entries.length, recording]);

  const toggleSort = useCallback((field: SortField) => {
    setSortField((prev) => {
      if (prev === field) {
        setSortDir((d) => (d === "asc" ? "desc" : "asc"));
        return field;
      }
      setSortDir("asc");
      return field;
    });
  }, []);

  const filtered = useMemo(() => {
    const q = filter.toLowerCase();
    let result = entries;
    if (typeFilter !== "all") {
      result = result.filter((e) => e.type === typeFilter);
    }
    if (q) {
      result = result.filter(
        (e) =>
          e.url.toLowerCase().includes(q) ||
          e.method.toLowerCase().includes(q) ||
          String(e.status).includes(q) ||
          e.statusText.toLowerCase().includes(q),
      );
    }
    if (sortField) {
      const dir = sortDir === "asc" ? 1 : -1;
      result = [...result].sort((a, b) => {
        const av = a[sortField];
        const bv = b[sortField];
        if (typeof av === "number" && typeof bv === "number") return (av - bv) * dir;
        return String(av).localeCompare(String(bv)) * dir;
      });
    }
    return result;
  }, [entries, filter, typeFilter, sortField, sortDir]);

  const selected = selectedId ? entries.find((e) => e.id === selectedId) ?? null : null;

  // Max elapsed for waterfall scaling.
  const maxElapsed = useMemo(
    () => Math.max(1, ...entries.map((e) => e.elapsed_ms)),
    [entries],
  );

  return (
    <div className="flex h-full flex-col overflow-hidden border-t border-glass bg-neutral-950/95 backdrop-blur">
      {/* Top toolbar */}
      <div className="flex shrink-0 items-center gap-2 border-b border-glass px-3 py-1.5">
        <button
          type="button"
          onClick={onToggleRecording}
          className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium transition ${
            recording
              ? "bg-rose-500/20 text-rose-400 hover:bg-rose-500/30"
              : "bg-neutral-800/50 text-neutral-500 hover:bg-neutral-800 hover:text-neutral-300"
          }`}
          title={recording ? "Pause recording" : "Resume recording"}
        >
          {recording ? (
            <>
              <Pause className="h-3 w-3" />
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-rose-400 opacity-40" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-rose-400" />
              </span>
            </>
          ) : (
            <Play className="h-3 w-3" />
          )}
        </button>

        <button
          type="button"
          onClick={onClear}
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-neutral-500 transition hover:bg-neutral-800/50 hover:text-neutral-300"
          title="Clear network log"
        >
          <Trash2 className="h-3 w-3" />
        </button>

        <div className="mx-1 h-4 w-px bg-glass" />

        <div className="flex items-center gap-1.5 rounded-md border border-glass bg-neutral-900/50 px-2 py-1">
          <Filter className="h-3 w-3 text-neutral-500" />
          <input
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter..."
            className="w-32 bg-transparent text-xs text-neutral-100 outline-none placeholder:text-neutral-600"
            spellCheck={false}
          />
          {filter && (
            <button type="button" onClick={() => setFilter("")} className="text-neutral-500 hover:text-neutral-300">
              <X className="h-3 w-3" />
            </button>
          )}
        </div>

        <div className="flex items-center gap-px">
          {TYPE_FILTERS.map((tf) => (
            <button
              key={tf.value}
              type="button"
              onClick={() => setTypeFilter(tf.value)}
              className={`rounded-md px-2 py-1 text-[10px] font-medium transition ${
                typeFilter === tf.value
                  ? "bg-cobweb-500/20 text-cobweb-300"
                  : "text-neutral-500 hover:bg-neutral-800/50 hover:text-neutral-300"
              }`}
            >
              {tf.label}
            </button>
          ))}
        </div>

        <div className="mx-1 h-4 w-px bg-glass" />

        <label className="inline-flex cursor-pointer items-center gap-1.5 text-[10px] text-neutral-500">
          <input
            type="checkbox"
            checked={preserveLog}
            onChange={onTogglePreserveLog}
            className="h-3 w-3 rounded border-glass bg-neutral-900 accent-cobweb-500"
          />
          Preserve log
        </label>

        {onExportHar && entries.length > 0 && (
          <>
            <div className="mx-1 h-4 w-px bg-glass" />
            <button
              type="button"
              onClick={onExportHar}
              className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-neutral-500 transition hover:bg-neutral-800/50 hover:text-neutral-300"
              title="Export as HAR"
            >
              <FileText className="h-3 w-3" />
              Export HAR
            </button>
          </>
        )}

        <span className="ml-auto text-[10px] font-mono text-neutral-600">
          {filtered.length} / {entries.length} requests
        </span>
      </div>

      {/* Main area: table + optional detail panel */}
      <div className="flex min-h-0 flex-1">
        {/* Request table */}
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          {/* Table header */}
          <div className="flex shrink-0 items-center border-b border-glass bg-neutral-925 text-[10px] uppercase tracking-wider text-neutral-500">
            <SortableHeader field="status" label="Status" width="w-16" sortField={sortField} sortDir={sortDir} onSort={toggleSort} />
            <SortableHeader field="method" label="Method" width="w-16" sortField={sortField} sortDir={sortDir} onSort={toggleSort} />
            <SortableHeader field="url" label="URL" width="flex-1 min-w-0" sortField={sortField} sortDir={sortDir} onSort={toggleSort} />
            <SortableHeader field="type" label="Type" width="w-16" sortField={sortField} sortDir={sortDir} onSort={toggleSort} />
            <SortableHeader field="size" label="Size" width="w-20" sortField={sortField} sortDir={sortDir} onSort={toggleSort} />
            <SortableHeader field="elapsed_ms" label="Time" width="w-20" sortField={sortField} sortDir={sortDir} onSort={toggleSort} />
            <div className="w-24 px-2 py-1.5 font-medium">Waterfall</div>
          </div>

          {/* Table body */}
          <div ref={tableRef} className="flex-1 overflow-auto">
            {filtered.length === 0 ? (
              <div className="flex h-full items-center justify-center text-xs text-neutral-600">
                {entries.length === 0
                  ? "No network activity recorded"
                  : "No requests match the current filter"}
              </div>
            ) : (
              filtered.map((entry) => (
                <button
                  key={entry.id}
                  type="button"
                  onClick={() => setSelectedId(entry.id === selectedId ? null : entry.id)}
                  className={`flex w-full items-center text-left text-[11px] transition ${
                    entry.id === selectedId
                      ? "bg-cobweb-500/10 border-l-2 border-cobweb-500"
                      : "border-l-2 border-transparent hover:bg-neutral-900/60"
                  } border-b border-b-glass/40`}
                >
                  <span className={`w-16 shrink-0 px-2 py-2.5 font-mono font-bold ${statusColor(entry.status)}`}>
                    {entry.status}
                  </span>
                  <span className="w-16 shrink-0 px-2 py-2.5 font-mono text-neutral-300">
                    {entry.method}
                  </span>
                  <span
                    className="min-w-0 flex-1 truncate px-2 py-2.5 font-mono text-neutral-400 cursor-pointer"
                    title={`${entry.url} (double-click to copy)`}
                    onDoubleClick={(e) => {
                      e.stopPropagation();
                      void navigator.clipboard?.writeText(entry.url);
                    }}
                  >
                    {entry.url}
                  </span>
                  <span className="w-16 shrink-0 px-2 py-2.5">
                    <span className={`inline-flex rounded border px-1 py-0.5 text-[9px] font-bold ${typeBadgeClass(entry.type)}`}>
                      {typeLabel(entry.type)}
                    </span>
                  </span>
                  <span className="w-20 shrink-0 px-2 py-2.5 text-right font-mono text-neutral-400">
                    {formatBytes(entry.size)}
                  </span>
                  <span className="w-20 shrink-0 px-2 py-2.5 text-right font-mono text-neutral-300">
                    {formatMs(entry.elapsed_ms)}
                  </span>
                  <span className="w-24 shrink-0 px-2 py-2.5">
                    <WaterfallBar entry={entry} maxElapsed={maxElapsed} />
                  </span>
                </button>
              ))
            )}
          </div>
        </div>

        {/* Detail panel */}
        {selected && (
          <div className="flex w-[400px] shrink-0 flex-col overflow-hidden border-l border-glass bg-neutral-925">
            <DetailPanel
              entry={selected}
              tab={detailTab}
              onTabChange={setDetailTab}
              onClose={() => setSelectedId(null)}
              headerSearch={detailHeaderSearch}
              onHeaderSearchChange={setDetailHeaderSearch}
            />
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sortable table header
// ---------------------------------------------------------------------------

function SortableHeader({
  field,
  label,
  width,
  sortField,
  sortDir,
  onSort,
}: {
  field: SortField;
  label: string;
  width: string;
  sortField: SortField | null;
  sortDir: SortDir;
  onSort: (f: SortField) => void;
}) {
  const active = sortField === field;
  return (
    <button
      type="button"
      onClick={() => onSort(field)}
      className={`${width} inline-flex items-center gap-1 px-2 py-1.5 text-left font-medium transition hover:text-neutral-300 ${
        active ? "text-neutral-300" : ""
      }`}
    >
      {label}
      {active && (sortDir === "asc" ? <ArrowUp className="h-2.5 w-2.5" /> : <ArrowDown className="h-2.5 w-2.5" />)}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Waterfall bar
// ---------------------------------------------------------------------------

const WATERFALL_PHASES = [
  { key: "dns_ms", label: "DNS", gradient: "from-cyan-400 to-cyan-500" },
  { key: "connect_ms", label: "Connect", gradient: "from-emerald-400 to-green-500" },
  { key: "tls_ms", label: "TLS", gradient: "from-amber-400 to-orange-500" },
  { key: "ttfb_ms", label: "TTFB", gradient: "from-purple-400 to-violet-500" },
  { key: "download_ms", label: "Download", gradient: "from-blue-400 to-cobweb-500" },
] as const;

function WaterfallBar({ entry, maxElapsed }: { entry: NetworkEntry; maxElapsed: number }) {
  const pct = Math.max(3, (entry.elapsed_ms / maxElapsed) * 100);

  if (entry.timing) {
    const total = entry.timing.dns_ms + entry.timing.connect_ms + entry.timing.tls_ms + entry.timing.ttfb_ms + entry.timing.download_ms || 1;
    const tooltipParts = WATERFALL_PHASES
      .filter((p) => (entry.timing?.[p.key as keyof typeof entry.timing] ?? 0) > 0)
      .map((p) => `${p.label}: ${formatMs(entry.timing![p.key as keyof typeof entry.timing] as number)}`)
      .join(" | ");
    return (
      <div
        className="group relative flex h-2.5 w-full overflow-hidden rounded-full bg-neutral-800"
        style={{ width: `${pct}%` }}
        title={tooltipParts}
      >
        {WATERFALL_PHASES.map((phase, i) => {
          const val = entry.timing![phase.key as keyof typeof entry.timing] as number ?? 0;
          if (val <= 0) return null;
          return (
            <div
              key={i}
              className={`h-full bg-gradient-to-r ${phase.gradient} transition-all duration-200 group-hover:brightness-110`}
              style={{ width: `${(val / total) * 100}%` }}
            />
          );
        })}
      </div>
    );
  }

  const barGradient = entry.status >= 400
    ? "from-rose-500/70 to-rose-400/50"
    : "from-cobweb-500/70 to-cobweb-400/50";
  return (
    <div className="h-2.5 w-full overflow-hidden rounded-full bg-neutral-800" title={formatMs(entry.elapsed_ms)}>
      <div className={`h-full rounded-full bg-gradient-to-r ${barGradient}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Detail panel
// ---------------------------------------------------------------------------

function DetailPanel({
  entry,
  tab,
  onTabChange,
  onClose,
  headerSearch,
  onHeaderSearchChange,
}: {
  entry: NetworkEntry;
  tab: DetailTab;
  onTabChange: (t: DetailTab) => void;
  onClose: () => void;
  headerSearch: string;
  onHeaderSearchChange: (s: string) => void;
}) {
  const tabs: { key: DetailTab; label: string; icon: React.ReactNode }[] = [
    { key: "headers", label: "Headers", icon: <FileText className="h-3 w-3" /> },
    { key: "payload", label: "Payload", icon: <ArrowUp className="h-3 w-3" /> },
    { key: "response", label: "Response", icon: <ArrowDown className="h-3 w-3" /> },
    { key: "timing", label: "Timing", icon: <Timer className="h-3 w-3" /> },
    { key: "cookies", label: "Cookies", icon: <Cookie className="h-3 w-3" /> },
  ];

  return (
    <>
      <div className="flex shrink-0 items-center border-b border-glass">
        <div className="flex flex-1 items-center gap-px px-1">
          {tabs.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => onTabChange(t.key)}
              className={`relative inline-flex items-center gap-1 px-2.5 py-2 text-[10px] font-medium transition ${
                tab === t.key ? "text-neutral-100" : "text-neutral-500 hover:text-neutral-300"
              }`}
            >
              {t.icon}
              {t.label}
              {tab === t.key && (
                <span className="absolute inset-x-1 bottom-0 h-0.5 rounded-full bg-accent-gradient-bar" aria-hidden />
              )}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="px-2 py-1 text-neutral-500 hover:text-neutral-300"
          title="Close detail"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {tab === "headers" && (
          <DetailHeaders entry={entry} search={headerSearch} onSearchChange={onHeaderSearchChange} />
        )}
        {tab === "payload" && <DetailPayload entry={entry} />}
        {tab === "response" && <DetailResponse entry={entry} />}
        {tab === "timing" && <DetailTiming entry={entry} />}
        {tab === "cookies" && <DetailCookies entry={entry} />}
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Detail: Headers
// ---------------------------------------------------------------------------

function DetailHeaders({
  entry,
  search,
  onSearchChange,
}: {
  entry: NetworkEntry;
  search: string;
  onSearchChange: (s: string) => void;
}) {
  const q = search.toLowerCase();

  const reqHeaders = useMemo(
    () => Object.entries(entry.requestHeaders).filter(
      ([k, v]) => !q || k.toLowerCase().includes(q) || v.toLowerCase().includes(q),
    ),
    [entry.requestHeaders, q],
  );
  const resHeaders = useMemo(
    () => Object.entries(entry.responseHeaders).filter(
      ([k, v]) => !q || k.toLowerCase().includes(q) || v.toLowerCase().includes(q),
    ),
    [entry.responseHeaders, q],
  );

  return (
    <div className="space-y-3 p-3">
      {/* General */}
      <section>
        <h4 className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-neutral-500">General</h4>
        <div className="space-y-1 text-[11px]">
          <KV label="Request URL" value={entry.url} mono />
          <KV label="Request Method" value={entry.method} />
          <KV
            label="Status Code"
            value={`${entry.status} ${entry.statusText}`}
            valueClass={statusColor(entry.status)}
          />
        </div>
      </section>

      {/* Search */}
      <div className="flex items-center gap-1.5 rounded border border-glass bg-neutral-900/50 px-2 py-1">
        <Search className="h-3 w-3 text-neutral-500" />
        <input
          type="text"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Filter headers..."
          className="flex-1 bg-transparent text-xs text-neutral-100 outline-none placeholder:text-neutral-600"
          spellCheck={false}
        />
        {search && (
          <button type="button" onClick={() => onSearchChange("")} className="text-neutral-500 hover:text-neutral-300">
            <X className="h-3 w-3" />
          </button>
        )}
      </div>

      {/* Response Headers */}
      <section>
        <h4 className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-neutral-500">
          Response Headers
          <span className="ml-1 font-normal text-neutral-600">{resHeaders.length}</span>
        </h4>
        <HeaderTable headers={resHeaders} />
      </section>

      {/* Request Headers */}
      <section>
        <h4 className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-neutral-500">
          Request Headers
          <span className="ml-1 font-normal text-neutral-600">{reqHeaders.length}</span>
        </h4>
        <HeaderTable headers={reqHeaders} />
      </section>
    </div>
  );
}

function KV({ label, value, mono, valueClass }: { label: string; value: string; mono?: boolean; valueClass?: string }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="shrink-0 text-neutral-500">{label}:</span>
      <span className={`break-all ${mono ? "font-mono" : ""} ${valueClass ?? "text-neutral-200"}`}>{value}</span>
    </div>
  );
}

function HeaderTable({ headers }: { headers: [string, string][] }) {
  if (headers.length === 0) {
    return <p className="text-[10px] text-neutral-600">No headers</p>;
  }
  return (
    <table className="w-full text-[11px]">
      <tbody>
        {headers.map(([k, v]) => (
          <tr key={k} className="border-b border-glass/40 hover:bg-neutral-900/40">
            <td className="py-1 pr-2 font-mono text-neutral-400">{k}</td>
            <td className="break-all py-1 font-mono text-neutral-100">{v}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ---------------------------------------------------------------------------
// Detail: Payload
// ---------------------------------------------------------------------------

function DetailPayload({ entry }: { entry: NetworkEntry }) {
  if (!entry.requestBody) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-neutral-600">
        No request body
      </div>
    );
  }

  // Parse query params from URL.
  let queryParams: [string, string][] = [];
  try {
    const u = new URL(entry.url);
    queryParams = Array.from(u.searchParams.entries());
  } catch {
    // ignore
  }

  return (
    <div className="flex h-full flex-col">
      {queryParams.length > 0 && (
        <div className="border-b border-glass p-3">
          <h4 className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-neutral-500">
            Query Parameters
          </h4>
          <table className="w-full text-[11px]">
            <tbody>
              {queryParams.map(([k, v], i) => (
                <tr key={`${k}-${i}`} className="border-b border-glass/40">
                  <td className="py-1 pr-2 font-mono text-neutral-400">{k}</td>
                  <td className="break-all py-1 font-mono text-neutral-100">{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="min-h-0 flex-1 overflow-hidden">
        <CodeEditor value={prettifyBody(entry.requestBody)} readOnly />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Detail: Response
// ---------------------------------------------------------------------------

function DetailResponse({ entry }: { entry: NetworkEntry }) {
  if (!entry.responseBody) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-neutral-600">
        No response body
      </div>
    );
  }
  return (
    <div className="h-full overflow-hidden">
      <CodeEditor value={prettifyBody(entry.responseBody)} readOnly />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Detail: Timing
// ---------------------------------------------------------------------------

const TIMING_PHASES: { key: string; label: string; color: string }[] = [
  { key: "dns_ms", label: "DNS Lookup", color: "bg-cyan-400" },
  { key: "connect_ms", label: "Initial Connection", color: "bg-orange-400" },
  { key: "tls_ms", label: "SSL/TLS", color: "bg-violet-400" },
  { key: "ttfb_ms", label: "Waiting (TTFB)", color: "bg-emerald-400" },
  { key: "download_ms", label: "Content Download", color: "bg-cobweb-400" },
];

function DetailTiming({ entry }: { entry: NetworkEntry }) {
  const t = entry.timing;

  return (
    <div className="p-3">
      <h4 className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-neutral-500">
        Request Timing -- {formatMs(entry.elapsed_ms)} total
      </h4>

      {t ? (
        <div className="space-y-2.5">
          {TIMING_PHASES.map((phase) => {
            const val = t[phase.key as keyof typeof t] ?? 0;
            const total = entry.elapsed_ms || 1;
            const pct = Math.max(2, (val / total) * 100);
            return (
              <div key={phase.key}>
                <div className="mb-0.5 flex items-center justify-between text-[11px]">
                  <span className="flex items-center gap-1.5 text-neutral-400">
                    <span className={`inline-block h-2 w-2 rounded-sm ${phase.color}`} />
                    {phase.label}
                  </span>
                  <span className="font-mono text-neutral-200">{formatMs(val)}</span>
                </div>
                <div className="h-3 w-full overflow-hidden rounded bg-neutral-800">
                  <div className={`h-full rounded ${phase.color}/80`} style={{ width: `${pct}%` }} />
                </div>
              </div>
            );
          })}
          <div className="mt-3 border-t border-glass pt-2">
            <div className="flex items-baseline justify-between text-xs">
              <span className="font-medium text-neutral-300">Total</span>
              <span className="font-mono font-bold text-neutral-100">{formatMs(entry.elapsed_ms)}</span>
            </div>
          </div>
        </div>
      ) : (
        <div className="space-y-2.5">
          <div className="flex items-baseline justify-between text-[11px]">
            <span className="text-neutral-400">Total elapsed</span>
            <span className="font-mono text-neutral-200">{formatMs(entry.elapsed_ms)}</span>
          </div>
          <div className="h-3 w-full overflow-hidden rounded bg-neutral-800">
            <div className="h-full rounded bg-cobweb-500/60" style={{ width: "100%" }} />
          </div>
          <p className="text-[10px] text-neutral-600">Detailed timing breakdown not available for this request</p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Detail: Cookies
// ---------------------------------------------------------------------------

function DetailCookies({ entry }: { entry: NetworkEntry }) {
  const cookies = Object.entries(entry.cookies ?? {});

  // Parse Set-Cookie from response headers.
  const setCookieHeader = entry.responseHeaders["set-cookie"] ?? entry.responseHeaders["Set-Cookie"] ?? "";
  const responseCookies: [string, string][] = setCookieHeader
    ? setCookieHeader.split(/,(?=\s*\w+=)/).map((c) => {
        const eq = c.indexOf("=");
        return eq > 0 ? [c.slice(0, eq).trim(), c.slice(eq + 1).trim()] : [c.trim(), ""];
      })
    : [];

  if (cookies.length === 0 && responseCookies.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-neutral-600">
        No cookies
      </div>
    );
  }

  return (
    <div className="space-y-3 p-3">
      {cookies.length > 0 && (
        <section>
          <h4 className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-neutral-500">
            Request Cookies
          </h4>
          <table className="w-full text-[11px]">
            <thead className="text-[10px] uppercase tracking-wider text-neutral-600">
              <tr>
                <th className="py-1 text-left font-medium">Name</th>
                <th className="py-1 text-left font-medium">Value</th>
              </tr>
            </thead>
            <tbody>
              {cookies.map(([k, v]) => (
                <tr key={k} className="border-t border-glass/40">
                  <td className="py-1 pr-2 font-mono text-neutral-400">{k}</td>
                  <td className="break-all py-1 font-mono text-neutral-100">{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      {responseCookies.length > 0 && (
        <section>
          <h4 className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-neutral-500">
            Response Cookies (Set-Cookie)
          </h4>
          <table className="w-full text-[11px]">
            <thead className="text-[10px] uppercase tracking-wider text-neutral-600">
              <tr>
                <th className="py-1 text-left font-medium">Name</th>
                <th className="py-1 text-left font-medium">Value</th>
              </tr>
            </thead>
            <tbody>
              {responseCookies.map(([k, v], i) => (
                <tr key={`${k}-${i}`} className="border-t border-glass/40">
                  <td className="py-1 pr-2 font-mono text-neutral-400">{k}</td>
                  <td className="break-all py-1 font-mono text-neutral-100">{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function prettifyBody(body: string): string {
  const trimmed = body.trimStart();
  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    try {
      return JSON.stringify(JSON.parse(body), null, 2);
    } catch {
      // fall through
    }
  }
  return body;
}
