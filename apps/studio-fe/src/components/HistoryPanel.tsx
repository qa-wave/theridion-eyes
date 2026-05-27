import { useCallback, useEffect, useState } from "react";
import { Clock, Play, Search, Trash2, X } from "lucide-react";
import { sidecar, type HistoryEntrySummary, type HistoryStats } from "../lib/sidecar";
import { HTTP_METHOD_COLOR } from "../state/types";
import type { Method } from "../state/types";

export interface HistoryEntry {
  id: string;
  method: Method;
  url: string;
  status: number;
  elapsed_ms: number;
  timestamp: number;
}

interface Props {
  entries: HistoryEntry[];
  onSelect: (entry: HistoryEntry) => void;
  onReplay: (entry: HistoryEntry) => void;
  onClear: () => void;
}

const METHOD_CHIPS: Method[] = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"];
const STATUS_FILTERS = [
  { label: "2xx", value: 2, color: "text-emerald-400 border-emerald-500/40" },
  { label: "3xx", value: 3, color: "text-sky-400 border-sky-500/40" },
  { label: "4xx", value: 4, color: "text-amber-400 border-amber-500/40" },
  { label: "5xx", value: 5, color: "text-rose-400 border-rose-500/40" },
];

export function HistoryPanel({ entries, onSelect, onReplay, onClear }: Props) {
  const [search, setSearch] = useState("");
  const [methodFilter, setMethodFilter] = useState<Method | null>(null);
  const [statusFilter, setStatusFilter] = useState<number | null>(null);
  const [stats, setStats] = useState<HistoryStats | null>(null);
  const [backendEntries, setBackendEntries] = useState<HistoryEntrySummary[]>([]);
  const [backendTotal, setBackendTotal] = useState(0);
  const [useBackend, setUseBackend] = useState(false);

  // Try loading from backend on mount
  const loadFromBackend = useCallback(async () => {
    try {
      const params: { method?: string; status?: number; search?: string; limit?: number } = { limit: 100 };
      if (methodFilter) params.method = methodFilter;
      if (statusFilter) params.status = statusFilter;
      if (search) params.search = search;
      const result = await sidecar.listHistory(params);
      setBackendEntries(result.entries);
      setBackendTotal(result.total);
      setUseBackend(true);
    } catch {
      // Backend not available, fall back to in-memory entries
      setUseBackend(false);
    }
  }, [methodFilter, statusFilter, search]);

  const loadStats = useCallback(async () => {
    try {
      const s = await sidecar.getHistoryStats();
      setStats(s);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    void loadFromBackend();
    void loadStats();
  }, [loadFromBackend, loadStats]);

  // Re-fetch when in-memory entries change (new request executed)
  useEffect(() => {
    if (entries.length > 0) {
      void loadFromBackend();
      void loadStats();
    }
  }, [entries.length, loadFromBackend, loadStats]);

  // Apply local filtering for in-memory fallback
  const displayEntries: Array<HistoryEntry | HistoryEntrySummary> = useBackend
    ? backendEntries
    : (() => {
        let filtered = entries;
        if (search) {
          const q = search.toLowerCase();
          filtered = filtered.filter(
            (e) =>
              e.url.toLowerCase().includes(q) ||
              e.method.toLowerCase().includes(q),
          );
        }
        if (methodFilter) {
          filtered = filtered.filter((e) => e.method === methodFilter);
        }
        if (statusFilter) {
          filtered = filtered.filter(
            (e) => Math.floor(e.status / 100) === statusFilter,
          );
        }
        return filtered;
      })();

  const totalCount = useBackend ? backendTotal : entries.length;
  const successRate =
    stats && stats.total > 0
      ? Math.round(
          ((stats.status_distribution["2xx"] ?? 0) / stats.total) * 100,
        )
      : null;

  const handleClear = async () => {
    try {
      await sidecar.clearHistory();
    } catch {
      // ignore
    }
    onClear();
    setBackendEntries([]);
    setBackendTotal(0);
    setStats(null);
  };

  const handleDeleteEntry = async (id: string) => {
    try {
      await sidecar.deleteHistoryEntry(id);
      void loadFromBackend();
      void loadStats();
    } catch {
      // ignore
    }
  };

  const toggleMethod = (m: Method) => {
    setMethodFilter((prev) => (prev === m ? null : m));
  };

  const toggleStatus = (s: number) => {
    setStatusFilter((prev) => (prev === s ? null : s));
  };

  const hasActiveFilters = methodFilter !== null || statusFilter !== null || search.length > 0;

  return (
    <div className="flex h-full flex-col" style={{ width: 320 }}>
      {/* Header */}
      <div className="flex items-center gap-1 border-b border-glass px-3 py-2">
        <Clock className="h-3.5 w-3.5 text-neutral-500" />
        <span className="text-[11px] font-semibold uppercase tracking-wider text-neutral-500">
          History
        </span>
        <span className="ml-1 rounded bg-neutral-800 px-1.5 py-0.5 text-[10px] text-neutral-400">
          {totalCount}
        </span>
        {totalCount > 0 && (
          <button
            type="button"
            onClick={() => void handleClear()}
            className="ml-auto rounded p-1 text-neutral-600 transition hover:bg-neutral-800 hover:text-rose-400"
            title="Clear history"
          >
            <Trash2 className="h-3 w-3" />
          </button>
        )}
      </div>

      {/* Stats summary */}
      {stats && stats.total > 0 && (
        <div className="flex gap-3 border-b border-glass px-3 py-1.5 text-[10px] text-neutral-500">
          <span>
            <span className="text-neutral-400">{stats.total}</span> total
          </span>
          <span>
            avg{" "}
            <span className="text-neutral-400">
              {Math.round(stats.avg_response_time_ms)}ms
            </span>
          </span>
          {successRate !== null && (
            <span>
              <span className={successRate >= 90 ? "text-emerald-400" : successRate >= 70 ? "text-amber-400" : "text-rose-400"}>
                {successRate}%
              </span>{" "}
              ok
            </span>
          )}
        </div>
      )}

      {/* Search */}
      <div className="px-3 py-1.5">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-neutral-600" />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search URL, method..."
            className="w-full rounded-md border border-glass bg-neutral-900/50 py-1 pl-7 pr-2 text-xs placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none"
          />
          {search && (
            <button
              type="button"
              onClick={() => setSearch("")}
              className="absolute right-1.5 top-1/2 -translate-y-1/2 text-neutral-600 hover:text-neutral-400"
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </div>
      </div>

      {/* Method filter chips */}
      <div className="flex flex-wrap gap-1 px-3 pb-1">
        {METHOD_CHIPS.map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => toggleMethod(m)}
            className={`rounded px-1.5 py-0.5 text-[10px] font-mono font-bold transition ${
              methodFilter === m
                ? `${HTTP_METHOD_COLOR[m]} bg-neutral-800 border border-neutral-700`
                : "text-neutral-600 hover:text-neutral-400 border border-transparent"
            }`}
          >
            {m}
          </button>
        ))}
      </div>

      {/* Status filter chips */}
      <div className="flex gap-1 border-b border-glass px-3 pb-1.5">
        {STATUS_FILTERS.map((sf) => (
          <button
            key={sf.value}
            type="button"
            onClick={() => toggleStatus(sf.value)}
            className={`rounded px-1.5 py-0.5 text-[10px] font-mono font-bold transition ${
              statusFilter === sf.value
                ? `${sf.color} bg-neutral-800 border`
                : "text-neutral-600 hover:text-neutral-400 border border-transparent"
            }`}
          >
            {sf.label}
          </button>
        ))}
        {hasActiveFilters && (
          <button
            type="button"
            onClick={() => {
              setSearch("");
              setMethodFilter(null);
              setStatusFilter(null);
            }}
            className="ml-auto text-[10px] text-neutral-600 hover:text-neutral-400"
          >
            clear filters
          </button>
        )}
      </div>

      {/* Entry list */}
      <div className="flex-1 overflow-y-auto">
        {displayEntries.length === 0 ? (
          <p className="px-3 py-6 text-center text-xs text-neutral-600">
            {totalCount === 0 ? "No history yet" : "No matches"}
          </p>
        ) : (
          displayEntries.map((entry) => (
            <div
              key={entry.id}
              className="group flex w-full items-center gap-2 px-3 py-1.5 text-xs hover:bg-neutral-800/60"
            >
              <button
                type="button"
                onClick={() =>
                  onSelect({
                    id: entry.id,
                    method: entry.method as Method,
                    url: entry.url,
                    status: entry.status,
                    elapsed_ms: entry.elapsed_ms,
                    timestamp: entry.timestamp,
                  })
                }
                className="flex flex-1 items-center gap-2 text-left"
              >
                <span
                  className={`w-9 shrink-0 font-mono text-[10px] font-bold ${
                    HTTP_METHOD_COLOR[entry.method as Method] ?? "text-neutral-400"
                  }`}
                >
                  {entry.method}
                </span>
                <span className="flex-1 truncate font-mono text-neutral-300">
                  {shortenUrl(entry.url)}
                </span>
                <StatusBadge status={entry.status} />
                <span className="shrink-0 text-[10px] text-neutral-600">
                  {Math.round(entry.elapsed_ms)}ms
                </span>
              </button>
              {/* Action buttons visible on hover */}
              <div className="flex shrink-0 gap-0.5 opacity-0 transition group-hover:opacity-100">
                <button
                  type="button"
                  onClick={() =>
                    onReplay({
                      id: entry.id,
                      method: entry.method as Method,
                      url: entry.url,
                      status: entry.status,
                      elapsed_ms: entry.elapsed_ms,
                      timestamp: entry.timestamp,
                    })
                  }
                  className="rounded p-1 text-neutral-600 hover:bg-neutral-700 hover:text-emerald-400"
                  title="Replay in new tab"
                >
                  <Play className="h-3 w-3" />
                </button>
                <button
                  type="button"
                  onClick={() => void handleDeleteEntry(entry.id)}
                  className="rounded p-1 text-neutral-600 hover:bg-neutral-700 hover:text-rose-400"
                  title="Delete entry"
                >
                  <Trash2 className="h-2.5 w-2.5" />
                </button>
              </div>
              <span className="shrink-0 text-[10px] text-neutral-600 group-hover:hidden">
                {formatTime(entry.timestamp)}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: number }) {
  const color =
    status >= 500
      ? "text-rose-400"
      : status >= 400
        ? "text-amber-400"
        : status >= 300
          ? "text-sky-400"
          : "text-emerald-400";
  return (
    <span className={`shrink-0 font-mono text-[10px] font-bold ${color}`}>
      {status}
    </span>
  );
}

function shortenUrl(url: string): string {
  try {
    const u = new URL(url);
    return u.pathname + u.search;
  } catch {
    return url;
  }
}

function formatTime(ts: number): string {
  const d = new Date(ts);
  return d.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}
