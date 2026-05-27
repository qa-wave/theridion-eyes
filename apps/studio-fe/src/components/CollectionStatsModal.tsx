import { useEffect, useMemo, useState } from "react";
import {
  BarChart3,
  Clock,
  Code2,
  FolderTree,
  Globe,
  Hash,
  Key,
  ShieldCheck,
  TrendingUp,
  X,
  Zap,
} from "lucide-react";
import type { StoredCollection, CollectionStats } from "../lib/sidecar";
import { sidecar } from "../lib/sidecar";

interface Props {
  open: boolean;
  onClose: () => void;
  collection: StoredCollection | null;
}

interface LastResponse {
  status: number;
  elapsed_ms: number;
  preview: string;
  timestamp: number;
}

interface FlatRequest {
  id: string;
  name: string;
  method: string;
  url: string;
  hasAssertions: boolean;
  lastResponse: LastResponse | null;
}

function flattenRequests(
  items: StoredCollection["items"],
  responses: Record<string, LastResponse>,
): FlatRequest[] {
  const result: FlatRequest[] = [];
  for (const item of items) {
    if (item.is_folder) {
      result.push(...flattenRequests(item.items ?? [], responses));
    } else {
      result.push({
        id: item.id,
        name: item.name,
        method: item.method ?? "GET",
        url: item.url ?? "",
        hasAssertions: (item.assertions?.length ?? 0) > 0,
        lastResponse: responses[item.id] ?? null,
      });
    }
  }
  return result;
}

function MethodBar({ method, count, total }: { method: string; count: number; total: number }) {
  const pct = total > 0 ? (count / total) * 100 : 0;
  const colors: Record<string, string> = {
    GET: "bg-emerald-500",
    POST: "bg-cobweb-500",
    PUT: "bg-amber-500",
    PATCH: "bg-violet-500",
    DELETE: "bg-rose-500",
    HEAD: "bg-neutral-500",
    OPTIONS: "bg-cyan-500",
  };
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-14 font-mono text-neutral-400">{method}</span>
      <div className="flex-1 h-3 rounded-full bg-neutral-800 overflow-hidden">
        <div
          className={`h-full rounded-full ${colors[method] ?? "bg-neutral-600"}`}
          style={{ width: `${Math.max(pct, 2)}%` }}
        />
      </div>
      <span className="w-8 text-right text-neutral-500">{count}</span>
    </div>
  );
}

function CoverageDonut({
  covered,
  total,
  label,
  color,
}: {
  covered: number;
  total: number;
  label: string;
  color: string;
}) {
  const pct = total > 0 ? Math.round((covered / total) * 100) : 0;
  const circumference = 2 * Math.PI * 32;
  const offset = circumference - (pct / 100) * circumference;
  return (
    <div className="flex flex-col items-center gap-1.5">
      <svg width="72" height="72" className="-rotate-90">
        <circle cx="36" cy="36" r="32" fill="none" stroke="currentColor" strokeWidth="6" className="text-neutral-800" />
        <circle
          cx="36" cy="36" r="32" fill="none" strokeWidth="6"
          className={color}
          stroke="currentColor"
          strokeDasharray={`${circumference}`}
          strokeDashoffset={`${offset}`}
          strokeLinecap="round"
        />
      </svg>
      <div className="text-center">
        <div className="text-sm font-bold text-neutral-100">{pct}%</div>
        <div className="text-[10px] text-neutral-500">{label}</div>
        <div className="text-[10px] text-neutral-600">{covered}/{total}</div>
      </div>
    </div>
  );
}

export function CollectionStatsModal({ open, onClose, collection }: Props) {
  const [responses, setResponses] = useState<Record<string, LastResponse>>({});
  const [backendStats, setBackendStats] = useState<CollectionStats | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    try {
      const stored = JSON.parse(
        localStorage.getItem("theridion.last-responses") ?? "{}",
      ) as Record<string, LastResponse>;
      setResponses(stored);
    } catch {
      setResponses({});
    }
  }, [open]);

  useEffect(() => {
    if (!open || !collection) {
      setBackendStats(null);
      return;
    }
    setLoading(true);
    sidecar.getCollectionStats(collection.id)
      .then(setBackendStats)
      .catch(() => setBackendStats(null))
      .finally(() => setLoading(false));
  }, [open, collection]);

  const localStats = useMemo(() => {
    if (!collection) return null;

    const flat = flattenRequests(collection.items, responses);
    const total = flat.length;

    // Response stats from localStorage
    const withResponses = flat.filter((r) => r.lastResponse !== null);
    const avgTime =
      withResponses.length > 0
        ? withResponses.reduce((s, r) => s + (r.lastResponse?.elapsed_ms ?? 0), 0) /
          withResponses.length
        : 0;

    // Status code breakdown
    const statusCounts: Record<number, number> = {};
    for (const r of withResponses) {
      const st = r.lastResponse!.status;
      statusCounts[st] = (statusCounts[st] ?? 0) + 1;
    }

    // Pass/fail
    const passed = withResponses.filter((r) => r.lastResponse!.status < 400).length;
    const failed = withResponses.length - passed;

    // Slowest endpoints
    const slowest = [...withResponses]
      .sort((a, b) => (b.lastResponse?.elapsed_ms ?? 0) - (a.lastResponse?.elapsed_ms ?? 0))
      .slice(0, 5);

    return {
      total,
      avgTime,
      statusCounts,
      passed,
      failed,
      testedCount: withResponses.length,
      slowest,
    };
  }, [collection, responses]);

  if (!open || !collection || !localStats) return null;

  const bs = backendStats;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="w-full max-w-2xl rounded-xl border border-glass bg-neutral-900/95 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-glass px-5 py-3">
          <div className="flex items-center gap-2">
            <BarChart3 className="h-4 w-4 text-cobweb-400" />
            <h2 className="text-sm font-semibold text-neutral-100">
              Collection Statistics: {collection.name}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-neutral-500 hover:bg-neutral-800 hover:text-neutral-300"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="max-h-[70vh] overflow-y-auto p-5 space-y-5">
          {loading && (
            <div className="text-center text-xs text-neutral-500 animate-pulse">Loading stats...</div>
          )}

          {/* Summary cards */}
          <div className="grid grid-cols-4 gap-3">
            <div className="rounded-lg border border-glass bg-neutral-800/50 p-3 text-center">
              <Hash className="mx-auto h-4 w-4 text-cobweb-400 mb-1" />
              <div className="text-lg font-bold text-neutral-100">
                {bs?.request_breakdown.total ?? localStats.total}
              </div>
              <div className="text-[10px] text-neutral-500">Total Requests</div>
            </div>
            <div className="rounded-lg border border-glass bg-neutral-800/50 p-3 text-center">
              <Clock className="mx-auto h-4 w-4 text-amber-400 mb-1" />
              <div className="text-lg font-bold text-neutral-100">
                {localStats.avgTime > 0 ? `${Math.round(localStats.avgTime)}ms` : "--"}
              </div>
              <div className="text-[10px] text-neutral-500">Avg Response</div>
            </div>
            <div className="rounded-lg border border-glass bg-neutral-800/50 p-3 text-center">
              <ShieldCheck className="mx-auto h-4 w-4 text-violet-400 mb-1" />
              <div className="text-lg font-bold text-neutral-100">
                {bs ? `${bs.coverage.assertion_coverage_pct}%` : "--"}
              </div>
              <div className="text-[10px] text-neutral-500">Assertion Coverage</div>
            </div>
            <div className="rounded-lg border border-glass bg-neutral-800/50 p-3 text-center">
              <Key className="mx-auto h-4 w-4 text-emerald-400 mb-1" />
              <div className="text-lg font-bold text-neutral-100">
                {bs ? `${bs.auth_usage.auth_coverage_pct}%` : "--"}
              </div>
              <div className="text-[10px] text-neutral-500">Auth Coverage</div>
            </div>
          </div>

          {/* Coverage donuts */}
          {bs && bs.request_breakdown.total > 0 && (
            <div className="flex justify-around">
              <CoverageDonut
                covered={bs.coverage.with_assertions}
                total={bs.request_breakdown.total}
                label="Assertions"
                color="text-violet-500"
              />
              <CoverageDonut
                covered={bs.auth_usage.with_auth}
                total={bs.request_breakdown.total}
                label="Auth"
                color="text-emerald-500"
              />
              <CoverageDonut
                covered={bs.body_analysis.with_body}
                total={bs.request_breakdown.total}
                label="Has Body"
                color="text-cobweb-500"
              />
            </div>
          )}

          {/* Method breakdown */}
          {bs && Object.keys(bs.request_breakdown.by_method).length > 0 && (
            <div>
              <h3 className="mb-2 text-xs font-semibold text-neutral-400">Method Distribution</h3>
              <div className="space-y-1.5">
                {Object.entries(bs.request_breakdown.by_method)
                  .sort((a, b) => b[1] - a[1])
                  .map(([method, count]) => (
                    <MethodBar key={method} method={method} count={count} total={bs.request_breakdown.total} />
                  ))}
              </div>
            </div>
          )}

          {/* Folder breakdown */}
          {bs && bs.request_breakdown.by_folder.length > 0 && (
            <div>
              <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-neutral-400">
                <FolderTree className="h-3 w-3" />
                Folder Breakdown
              </h3>
              <div className="space-y-1">
                {bs.request_breakdown.by_folder.map((f) => (
                  <div
                    key={f.name}
                    className="flex items-center justify-between rounded-md border border-glass bg-neutral-800/30 px-3 py-1.5 text-xs"
                  >
                    <span className="text-neutral-300 truncate">{f.name}</span>
                    <span className="shrink-0 font-mono text-cobweb-400">{f.request_count}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Assertion type distribution */}
          {bs && Object.keys(bs.coverage.assertion_type_distribution).length > 0 && (
            <div>
              <h3 className="mb-2 text-xs font-semibold text-neutral-400">Assertion Types</h3>
              <div className="flex flex-wrap gap-2">
                {Object.entries(bs.coverage.assertion_type_distribution)
                  .sort((a, b) => b[1] - a[1])
                  .map(([type, count]) => (
                    <span
                      key={type}
                      className="rounded-md border border-violet-700/40 bg-violet-500/10 px-2 py-0.5 text-xs font-mono text-violet-400"
                    >
                      {type} x{count}
                    </span>
                  ))}
              </div>
            </div>
          )}

          {/* URL analysis */}
          {bs && bs.url_analysis.unique_base_urls.length > 0 && (
            <div>
              <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-neutral-400">
                <Globe className="h-3 w-3" />
                URL Patterns
              </h3>
              <div className="space-y-1.5">
                <div className="flex gap-3 text-xs text-neutral-500">
                  <span>{bs.url_analysis.unique_base_urls.length} unique base URL{bs.url_analysis.unique_base_urls.length !== 1 ? "s" : ""}</span>
                  <span>{bs.url_analysis.parameterized_urls} parameterized</span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {bs.url_analysis.unique_base_urls.map((url) => (
                    <span
                      key={url}
                      className="rounded border border-neutral-700 bg-neutral-800/50 px-2 py-0.5 text-[10px] font-mono text-neutral-400"
                    >
                      {url}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Complexity metrics */}
          {bs && (bs.complexity.total_headers > 0 || bs.complexity.total_variables_used > 0 || bs.complexity.scripts_attached > 0) && (
            <div>
              <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-neutral-400">
                <Code2 className="h-3 w-3" />
                Complexity
              </h3>
              <div className="grid grid-cols-3 gap-3">
                <div className="rounded-md border border-glass bg-neutral-800/30 p-2 text-center">
                  <div className="text-sm font-bold text-neutral-200">{bs.complexity.total_headers}</div>
                  <div className="text-[10px] text-neutral-500">Headers</div>
                </div>
                <div className="rounded-md border border-glass bg-neutral-800/30 p-2 text-center">
                  <div className="text-sm font-bold text-neutral-200">{bs.complexity.total_variables_used}</div>
                  <div className="text-[10px] text-neutral-500">Variables Used</div>
                </div>
                <div className="rounded-md border border-glass bg-neutral-800/30 p-2 text-center">
                  <div className="text-sm font-bold text-neutral-200">{bs.complexity.scripts_attached}</div>
                  <div className="text-[10px] text-neutral-500">Scripts</div>
                </div>
              </div>
            </div>
          )}

          {/* Status codes */}
          {Object.keys(localStats.statusCounts).length > 0 && (
            <div>
              <h3 className="mb-2 text-xs font-semibold text-neutral-400">Status Codes (session)</h3>
              <div className="flex flex-wrap gap-2">
                {Object.entries(localStats.statusCounts)
                  .sort((a, b) => b[1] - a[1])
                  .map(([status, count]) => {
                    const s = Number(status);
                    const color =
                      s >= 500
                        ? "border-rose-700/40 bg-rose-500/10 text-rose-400"
                        : s >= 400
                          ? "border-amber-700/40 bg-amber-500/10 text-amber-400"
                          : s >= 300
                            ? "border-cobweb-700/40 bg-cobweb-500/10 text-cobweb-400"
                            : "border-emerald-700/40 bg-emerald-500/10 text-emerald-400";
                    return (
                      <span
                        key={status}
                        className={`rounded-md border px-2 py-0.5 text-xs font-mono ${color}`}
                      >
                        {status} x{count}
                      </span>
                    );
                  })}
              </div>
            </div>
          )}

          {/* Slowest endpoints */}
          {localStats.slowest.length > 0 && (
            <div>
              <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-neutral-400">
                <Zap className="h-3 w-3" />
                Slowest Endpoints (session)
              </h3>
              <div className="space-y-1">
                {localStats.slowest.map((r) => (
                  <div
                    key={r.id}
                    className="flex items-center justify-between rounded-md border border-glass bg-neutral-800/30 px-3 py-1.5 text-xs"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="font-mono text-cobweb-400">{r.method}</span>
                      <span className="truncate text-neutral-300">{r.name}</span>
                    </div>
                    <span className="shrink-0 font-mono text-amber-400">
                      {Math.round(r.lastResponse?.elapsed_ms ?? 0)}ms
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Pass / Fail */}
          {localStats.testedCount > 0 && (
            <div>
              <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-neutral-400">
                <TrendingUp className="h-3 w-3" />
                Health (session)
              </h3>
              <div className="flex h-4 overflow-hidden rounded-full bg-neutral-800">
                <div
                  className="bg-emerald-500"
                  style={{ width: `${(localStats.passed / localStats.testedCount) * 100}%` }}
                />
                <div
                  className="bg-rose-500"
                  style={{ width: `${(localStats.failed / localStats.testedCount) * 100}%` }}
                />
              </div>
              <div className="mt-1 flex justify-between text-[10px] text-neutral-500">
                <span className="text-emerald-400">{localStats.passed} passed</span>
                <span className="text-rose-400">{localStats.failed} failed</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
