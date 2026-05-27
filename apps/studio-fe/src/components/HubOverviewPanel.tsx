import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  ExternalLink,
  RefreshCw,
  Server,
  Settings2,
  ShieldAlert,
  XCircle,
} from "lucide-react";
import {
  getGates,
  getIncidents,
  getRuns,
  type HubConfig,
  type IncidentSummary,
  type QualityGateStatus,
  type RunSummary,
} from "../lib/sidecar/hub";

const POLL_INTERVAL_MS = 30_000;
const HUB_CONFIG_KEY = "theridion.hubConfig";

type ConnectionState = "connected" | "stale" | "error" | "idle";

interface HubData {
  runs: RunSummary[];
  incidents: IncidentSummary[];
  gates: QualityGateStatus[];
  loadedAt: number;
}

function useHubData() {
  const [config, setConfig] = useState<HubConfig | null>(null);
  const [data, setData] = useState<HubData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [connState, setConnState] = useState<ConnectionState>("idle");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load Hub config from localStorage (persisted by SettingsModal)
  const loadConfig = useCallback(() => {
    try {
      const raw = window.localStorage.getItem(HUB_CONFIG_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as { url?: string; token?: string };
        if (parsed.url && parsed.token) {
          setConfig({ url: parsed.url, token: parsed.token });
          return;
        }
      }
    } catch {
      /* ignore parse errors */
    }
    setConfig(null);
  }, []);

  const fetchData = useCallback(async (cfg: HubConfig) => {
    setLoading(true);
    setError(null);
    try {
      const [runsRes, incidentsRes, gatesRes] = await Promise.all([
        getRuns(cfg),
        getIncidents(cfg),
        getGates(cfg),
      ]);
      setData({
        runs: runsRes.runs,
        incidents: incidentsRes.incidents,
        gates: gatesRes.gates,
        loadedAt: Date.now(),
      });
      setConnState("connected");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      setConnState("error");
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial config load
  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  // Start polling when config is available
  useEffect(() => {
    if (!config) {
      setConnState("idle");
      return;
    }

    void fetchData(config);

    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(() => {
      // Mark stale after two missed cycles (if fetchData sets error, connState = error)
      setConnState((prev) => (prev === "connected" ? "stale" : prev));
      void fetchData(config);
    }, POLL_INTERVAL_MS);

    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [config, fetchData]);

  const refresh = useCallback(() => {
    if (config) void fetchData(config);
  }, [config, fetchData]);

  return { config, data, loading, error, connState, refresh, reload: loadConfig };
}

interface IncidentDetailModalProps {
  incident: IncidentSummary;
  hubUrl: string;
  onClose: () => void;
}

function IncidentDetailModal({ incident, hubUrl, onClose }: IncidentDetailModalProps) {
  const severityColor: Record<string, string> = {
    critical: "text-rose-400",
    high: "text-orange-400",
    medium: "text-amber-400",
    low: "text-sky-400",
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="glass w-[480px] max-w-[95vw] animate-slide-in overflow-hidden rounded-xl border border-glass-light shadow-2xl shadow-black/60"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-2">
            <ShieldAlert className="h-4 w-4 text-rose-400" />
            <span className="text-sm font-semibold text-neutral-100">Incident</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200"
          >
            <XCircle className="h-4 w-4" />
          </button>
        </div>

        <div className="p-4 space-y-3">
          <p className="text-sm font-medium text-neutral-100">{incident.title}</p>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div>
              <span className="text-neutral-500">Severity</span>
              <p className={`mt-0.5 font-medium capitalize ${severityColor[incident.severity] ?? "text-neutral-300"}`}>
                {incident.severity}
              </p>
            </div>
            <div>
              <span className="text-neutral-500">Status</span>
              <p className={`mt-0.5 font-medium capitalize ${incident.status === "open" ? "text-amber-400" : "text-emerald-400"}`}>
                {incident.status}
              </p>
            </div>
            <div>
              <span className="text-neutral-500">Collection</span>
              <p className="mt-0.5 text-neutral-200">{incident.collection_name}</p>
            </div>
            <div>
              <span className="text-neutral-500">Opened</span>
              <p className="mt-0.5 text-neutral-200">{formatTime(incident.opened_at)}</p>
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-2 border-t border-glass px-4 py-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-glass px-3 py-1.5 text-xs text-neutral-400 hover:bg-white/[0.04] hover:text-neutral-200"
          >
            Close
          </button>
          <a
            href={`${hubUrl}/incidents/${incident.id}`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 rounded-md border border-glass px-3 py-1.5 text-xs text-cobweb-400 hover:bg-white/[0.04] hover:text-cobweb-300"
          >
            Open in Hub <ExternalLink className="h-3 w-3" />
          </a>
        </div>
      </div>
    </div>
  );
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60_000).toFixed(1)}m`;
}

interface Props {
  onOpenCollection?: (collectionId: string) => void;
  onOpenSettings?: () => void;
}

export function HubOverviewPanel({ onOpenCollection, onOpenSettings }: Props) {
  const { config, data, loading, error, connState, refresh, reload } = useHubData();
  const [category, setCategory] = useState<"runs" | "incidents" | "gates">("runs");
  const [selectedIncident, setSelectedIncident] = useState<IncidentSummary | null>(null);

  // Reload config whenever the panel gains visibility (e.g. user just saved settings)
  useEffect(() => {
    reload();
  }, [reload]);

  // Keyboard shortcut: Ctrl+R refreshes the panel
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key === "r" && !e.shiftKey) {
        // Only intercept when no input is focused
        if (document.activeElement?.tagName === "INPUT") return;
        e.preventDefault();
        refresh();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [refresh]);

  const connDot: Record<ConnectionState, string> = {
    connected: "bg-emerald-500",
    stale: "bg-neutral-400",
    error: "bg-rose-500",
    idle: "bg-neutral-600",
  };

  // Empty state — Hub not configured
  if (!config) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 p-8 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-neutral-900 border border-glass">
          <Server className="h-6 w-6 text-neutral-500" />
        </div>
        <div>
          <p className="text-sm font-medium text-neutral-300">Hub not configured</p>
          <p className="mt-1 text-xs text-neutral-500 max-w-xs">
            Connect to a Theridion Hub to see run trends, incidents, and quality gate statuses without leaving Studio.
          </p>
        </div>
        {onOpenSettings && (
          <button
            type="button"
            onClick={onOpenSettings}
            className="inline-flex items-center gap-1.5 rounded-md border border-glass px-3 py-1.5 text-xs text-cobweb-400 hover:bg-white/[0.04] hover:text-cobweb-300 transition"
          >
            <Settings2 className="h-3.5 w-3.5" /> Open Settings
          </button>
        )}
      </div>
    );
  }

  const categories: { id: "runs" | "incidents" | "gates"; label: string; count?: number }[] = [
    { id: "runs", label: "Runs", count: data?.runs.length },
    {
      id: "incidents",
      label: "Incidents",
      count: data?.incidents.filter((i) => i.status === "open").length,
    },
    { id: "gates", label: "Quality Gates", count: data?.gates.length },
  ];

  // KPI summary numbers
  const totalRuns = data?.runs.length ?? 0;
  const avgPassRate =
    totalRuns > 0
      ? Math.round(data!.runs.reduce((s, r) => s + r.pass_rate, 0) / totalRuns)
      : 0;
  const openIncidents = data?.incidents.filter((i) => i.status === "open").length ?? 0;
  const gatesFailing = data?.gates.filter((g) => g.status === "fail").length ?? 0;

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between border-b border-glass px-4 py-2">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-cobweb-400" />
          <span className="text-xs font-semibold uppercase tracking-widest text-neutral-300">
            Hub Overview
          </span>
          <span
            className={`inline-block h-1.5 w-1.5 rounded-full ${connDot[connState]}`}
            title={connState}
          />
        </div>
        <div className="flex items-center gap-1">
          {data && (
            <span className="text-[10px] text-neutral-600">
              {new Date(data.loadedAt).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
            </span>
          )}
          <button
            type="button"
            onClick={refresh}
            title="Refresh (Ctrl+R)"
            disabled={loading}
            className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200 disabled:opacity-40"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="shrink-0 flex items-center gap-2 bg-rose-950/40 border-b border-rose-800/30 px-4 py-2 text-xs text-rose-300">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          <span className="truncate">{error}</span>
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        {/* Sidebar — categories */}
        <div className="flex w-36 shrink-0 flex-col border-r border-glass bg-neutral-950/30">
          {/* KPI mini-cards */}
          <div className="border-b border-glass p-3 space-y-2">
            <KpiCard label="Avg pass rate" value={`${avgPassRate}%`} color={avgPassRate >= 80 ? "text-emerald-400" : "text-rose-400"} />
            <KpiCard label="Open incidents" value={String(openIncidents)} color={openIncidents > 0 ? "text-amber-400" : "text-neutral-400"} />
            <KpiCard label="Gates failing" value={String(gatesFailing)} color={gatesFailing > 0 ? "text-rose-400" : "text-neutral-400"} />
          </div>

          <div className="py-1">
            {categories.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => setCategory(c.id)}
                className={`flex w-full items-center justify-between px-3 py-2 text-left text-xs transition ${
                  category === c.id
                    ? "bg-white/[0.05] text-neutral-100"
                    : "text-neutral-400 hover:bg-white/[0.03] hover:text-neutral-200"
                }`}
              >
                <span>{c.label}</span>
                {c.count !== undefined && (
                  <span className="rounded-full bg-neutral-800 px-1.5 py-0.5 text-[10px] text-neutral-400">
                    {c.count}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Center — main content */}
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          {/* Loading skeleton */}
          {loading && !data && (
            <div className="flex flex-1 flex-col gap-3 p-4">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-10 rounded-md bg-neutral-900/60 animate-pulse" />
              ))}
            </div>
          )}

          {/* Runs list */}
          {!loading || data ? (
            <>
              {category === "runs" && (
                <RunsList
                  runs={data?.runs ?? []}
                  onOpenCollection={onOpenCollection}
                  hubUrl={config.url}
                />
              )}
              {category === "incidents" && (
                <IncidentsList
                  incidents={data?.incidents ?? []}
                  onSelect={setSelectedIncident}
                />
              )}
              {category === "gates" && (
                <GatesList gates={data?.gates ?? []} />
              )}
            </>
          ) : null}
        </div>
      </div>

      {/* Incident detail modal */}
      {selectedIncident && (
        <IncidentDetailModal
          incident={selectedIncident}
          hubUrl={config.url}
          onClose={() => setSelectedIncident(null)}
        />
      )}
    </div>
  );
}

function KpiCard({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div>
      <p className="text-[9px] uppercase tracking-widest text-neutral-600">{label}</p>
      <p className={`text-sm font-semibold ${color}`}>{value}</p>
    </div>
  );
}

function PassRateBar({ rate }: { rate: number }) {
  const color = rate >= 90 ? "bg-emerald-500" : rate >= 70 ? "bg-amber-500" : "bg-rose-500";
  return (
    <div className="flex items-center gap-2 text-xs">
      <div className="h-1.5 flex-1 rounded-full bg-neutral-800">
        <div className={`h-1.5 rounded-full ${color} transition-all`} style={{ width: `${rate}%` }} />
      </div>
      <span className={`w-8 text-right ${color.replace("bg-", "text-")}`}>{rate}%</span>
    </div>
  );
}

function RunsList({
  runs,
  onOpenCollection,
  hubUrl,
}: {
  runs: RunSummary[];
  onOpenCollection?: (id: string) => void;
  hubUrl: string;
}) {
  if (runs.length === 0) {
    return <EmptyState label="No runs recorded yet" />;
  }

  return (
    <div className="overflow-y-auto">
      <table className="w-full text-xs">
        <thead className="sticky top-0 bg-neutral-950/80 backdrop-blur-sm">
          <tr className="border-b border-glass text-neutral-500">
            <th className="px-3 py-2 text-left font-medium">Collection</th>
            <th className="px-3 py-2 text-left font-medium w-32">Pass rate</th>
            <th className="px-3 py-2 text-right font-medium w-20">Duration</th>
            <th className="px-3 py-2 text-right font-medium w-24">Started</th>
            <th className="w-8" />
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr
              key={r.id}
              className={`border-b border-glass/50 hover:bg-white/[0.02] ${r.status === "fail" ? "cursor-pointer" : ""}`}
              onClick={() => r.status === "fail" && onOpenCollection?.(r.collection_id)}
              title={r.status === "fail" ? "Click to open collection" : undefined}
            >
              <td className="px-3 py-2">
                <div className="flex items-center gap-1.5">
                  {r.status === "fail" ? (
                    <XCircle className="h-3 w-3 shrink-0 text-rose-400" />
                  ) : r.status === "running" ? (
                    <RefreshCw className="h-3 w-3 shrink-0 animate-spin text-sky-400" />
                  ) : (
                    <CheckCircle2 className="h-3 w-3 shrink-0 text-emerald-400" />
                  )}
                  <span className="truncate max-w-[140px] text-neutral-200">{r.collection_name}</span>
                </div>
              </td>
              <td className="px-3 py-2 w-32">
                <PassRateBar rate={r.pass_rate} />
              </td>
              <td className="px-3 py-2 text-right text-neutral-400">
                {formatDuration(r.duration_ms)}
              </td>
              <td className="px-3 py-2 text-right text-neutral-500">
                {formatTime(r.started_at)}
              </td>
              <td className="px-2 py-2">
                <a
                  href={`${hubUrl}/runs/${r.id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="text-neutral-600 hover:text-cobweb-400 transition"
                  title="Open in Hub"
                >
                  <ExternalLink className="h-3 w-3" />
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function IncidentsList({
  incidents,
  onSelect,
}: {
  incidents: IncidentSummary[];
  onSelect: (i: IncidentSummary) => void;
}) {
  if (incidents.length === 0) {
    return <EmptyState label="No incidents" sublabel="All clear." icon="shield" />;
  }

  const severityColor: Record<string, string> = {
    critical: "text-rose-400 bg-rose-950/30 border-rose-800/30",
    high: "text-orange-400 bg-orange-950/30 border-orange-800/30",
    medium: "text-amber-400 bg-amber-950/30 border-amber-800/30",
    low: "text-sky-400 bg-sky-950/30 border-sky-800/30",
  };

  return (
    <div className="overflow-y-auto divide-y divide-glass/50">
      {incidents.map((inc) => (
        <button
          key={inc.id}
          type="button"
          onClick={() => onSelect(inc)}
          className="flex w-full items-start gap-3 px-3 py-2.5 text-left text-xs hover:bg-white/[0.02] transition"
        >
          <span
            className={`mt-0.5 shrink-0 rounded border px-1.5 py-0.5 text-[10px] font-medium capitalize ${
              severityColor[inc.severity] ?? "text-neutral-400"
            }`}
          >
            {inc.severity}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-neutral-200">{inc.title}</p>
            <p className="mt-0.5 text-neutral-500">
              {inc.collection_name} · {formatTime(inc.opened_at)}
            </p>
          </div>
          <span
            className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] capitalize ${
              inc.status === "open" ? "text-amber-400 bg-amber-950/20" : "text-emerald-400 bg-emerald-950/20"
            }`}
          >
            {inc.status}
          </span>
          <ChevronRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-neutral-600" />
        </button>
      ))}
    </div>
  );
}

function GatesList({ gates }: { gates: QualityGateStatus[] }) {
  if (gates.length === 0) {
    return <EmptyState label="No quality gates defined" />;
  }

  return (
    <div className="overflow-y-auto divide-y divide-glass/50">
      {gates.map((g) => (
        <div key={g.name} className="flex items-center gap-3 px-3 py-2.5 text-xs">
          {g.status === "pass" ? (
            <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
          ) : g.status === "fail" ? (
            <XCircle className="h-4 w-4 shrink-0 text-rose-400" />
          ) : (
            <div className="h-4 w-4 shrink-0 rounded-full border-2 border-neutral-600" />
          )}
          <div className="min-w-0 flex-1">
            <p className="truncate text-neutral-200">{g.name}</p>
            <p className="mt-0.5 text-neutral-500">
              Threshold: {g.threshold}
              {g.unit} · Current: {g.current}
              {g.unit}
            </p>
          </div>
          <span
            className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] capitalize font-medium ${
              g.status === "pass"
                ? "text-emerald-400 bg-emerald-950/20"
                : g.status === "fail"
                  ? "text-rose-400 bg-rose-950/20"
                  : "text-neutral-400 bg-neutral-900/40"
            }`}
          >
            {g.status}
          </span>
        </div>
      ))}
    </div>
  );
}

function EmptyState({
  label,
  sublabel,
  icon,
}: {
  label: string;
  sublabel?: string;
  icon?: "shield";
}) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-2 p-8 text-center">
      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-neutral-900 border border-glass">
        {icon === "shield" ? (
          <CheckCircle2 className="h-5 w-5 text-emerald-500/60" />
        ) : (
          <Activity className="h-5 w-5 text-neutral-600" />
        )}
      </div>
      <p className="text-xs text-neutral-400">{label}</p>
      {sublabel && <p className="text-[11px] text-neutral-600">{sublabel}</p>}
    </div>
  );
}
