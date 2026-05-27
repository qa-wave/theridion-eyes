import { useEffect, useState } from "react";
import { CheckCircle2, Clock, Loader2, Play, Plus, Trash2, X, XCircle } from "lucide-react";
import { sidecar, type MonitorConfig, type CollectionSummary, type EnvironmentSummary, type RunCollectionOutput } from "../lib/sidecar";

interface Props {
  open: boolean;
  onClose: () => void;
}

interface MonitorRunResult {
  monitorId: string;
  timestamp: number;
  passed: number;
  failed: number;
  total: number;
}

const LAST_RUN_KEY = "theridion.monitor-runs";

function loadRunHistory(): Record<string, MonitorRunResult> {
  try {
    return JSON.parse(localStorage.getItem(LAST_RUN_KEY) ?? "{}");
  } catch { return {}; }
}

function saveRunResult(result: MonitorRunResult) {
  const history = loadRunHistory();
  history[result.monitorId] = result;
  try { localStorage.setItem(LAST_RUN_KEY, JSON.stringify(history)); } catch { /* quota */ }
}

function timeAgo(ts: number): string {
  const diff = Date.now() - ts;
  if (diff < 60000) return "just now";
  if (diff < 3600000) return `${Math.floor(diff / 60000)} min ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
  return `${Math.floor(diff / 86400000)}d ago`;
}

export function MonitorsModal({ open, onClose }: Props) {
  const [monitors, setMonitors] = useState<MonitorConfig[]>([]);
  const [collections, setCollections] = useState<CollectionSummary[]>([]);
  const [environments, setEnvironments] = useState<EnvironmentSummary[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [formCollectionId, setFormCollectionId] = useState("");
  const [formEnvId, setFormEnvId] = useState("");
  const [formCron, setFormCron] = useState("*/5 * * * *");
  const [formEnabled, setFormEnabled] = useState(true);
  const [runningId, setRunningId] = useState<string | null>(null);
  const [runResults, setRunResults] = useState<Record<string, MonitorRunResult>>(loadRunHistory);
  const [lastRunOutput, setLastRunOutput] = useState<RunCollectionOutput | null>(null);

  useEffect(() => {
    if (!open) return;
    loadAll();
    setRunResults(loadRunHistory());
  }, [open]);

  async function loadAll() {
    try {
      const [m, c, e] = await Promise.all([
        sidecar.listMonitors(),
        sidecar.listCollections(),
        sidecar.listEnvironments(),
      ]);
      setMonitors(m.monitors);
      setCollections(c);
      setEnvironments(e);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function create() {
    if (!formCollectionId) return;
    setBusy(true); setError(null);
    try {
      await sidecar.createMonitor({
        collection_id: formCollectionId,
        environment_id: formEnvId || null,
        cron: formCron,
        enabled: formEnabled,
      });
      setShowForm(false);
      await loadAll();
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  async function remove(id: string) {
    if (!confirm("Delete this monitor?")) return;
    try {
      await sidecar.deleteMonitor(id);
      await loadAll();
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
  }

  async function runNow(monitor: MonitorConfig) {
    if (!monitor.id) return;
    setRunningId(monitor.id);
    setError(null);
    setLastRunOutput(null);
    try {
      const traceResult = await sidecar.runWithTrace(monitor.collection_id, monitor.environment_id ?? undefined);
      const result = traceResult.run;
      const passed = result.successful_requests;
      const failed = result.total_requests - passed;
      const runResult: MonitorRunResult = {
        monitorId: monitor.id,
        timestamp: Date.now(),
        passed,
        failed,
        total: result.results.length,
      };
      saveRunResult(runResult);
      setRunResults((prev) => ({ ...prev, [monitor.id!]: runResult }));
      setLastRunOutput(result);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunningId(null);
    }
  }

  if (!open) return null;

  const inputClass = "w-full rounded-md border border-glass bg-neutral-900/50 px-3 py-1.5 text-xs text-neutral-100 focus:border-cobweb-500/40 focus:outline-none";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="glass flex h-[580px] w-[650px] max-h-[90vh] max-w-[95vw] animate-slide-in flex-col overflow-hidden rounded-xl border border-glass-light shadow-2xl shadow-black/60">
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-100">
            <Clock className="h-4 w-4 text-cobweb-400" /> Monitors
          </div>
          <div className="flex items-center gap-1">
            <button type="button" onClick={() => setShowForm(true)} className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200" title="New monitor"><Plus className="h-4 w-4" /></button>
            <button type="button" onClick={onClose} className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200"><X className="h-4 w-4" /></button>
          </div>
        </div>

        {error && <div className="border-b border-rose-800/30 bg-rose-950/20 px-4 py-2 text-xs text-rose-400">{error}</div>}

        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {showForm && (
            <div className="rounded-lg border border-glass p-3 space-y-3 bg-neutral-900/30">
              <p className="text-[11px] uppercase tracking-wider text-neutral-500">New Monitor</p>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-[11px] text-neutral-500">Collection</label>
                  <select value={formCollectionId} onChange={(e) => setFormCollectionId(e.target.value)} className={inputClass}>
                    <option value="">Select...</option>
                    {collections.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-[11px] text-neutral-500">Environment</label>
                  <select value={formEnvId} onChange={(e) => setFormEnvId(e.target.value)} className={inputClass}>
                    <option value="">None</option>
                    {environments.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-[11px] text-neutral-500">Cron expression</label>
                  <input value={formCron} onChange={(e) => setFormCron(e.target.value)} className={inputClass} placeholder="*/5 * * * *" />
                </div>
                <div className="flex items-end gap-2">
                  <label className="flex items-center gap-2 text-xs text-neutral-300">
                    <input type="checkbox" checked={formEnabled} onChange={(e) => setFormEnabled(e.target.checked)} className="rounded" />
                    Enabled
                  </label>
                </div>
              </div>
              <div className="flex gap-2">
                <button type="button" onClick={create} disabled={busy || !formCollectionId} className="inline-flex items-center gap-1 rounded-md bg-cobweb-600/20 px-3 py-1.5 text-xs font-medium text-cobweb-400 transition hover:bg-cobweb-600/30 disabled:opacity-50">
                  {busy && <Loader2 className="h-3 w-3 animate-spin" />} Create
                </button>
                <button type="button" onClick={() => setShowForm(false)} className="rounded-md px-3 py-1.5 text-xs text-neutral-400 hover:text-neutral-200">Cancel</button>
              </div>
            </div>
          )}

          {monitors.length === 0 && !showForm && (
            <p className="py-8 text-center text-xs text-neutral-600">No monitors configured yet.</p>
          )}

          {monitors.map((m) => {
            const coll = collections.find((c) => c.id === m.collection_id);
            const lastRun = m.id ? runResults[m.id] : null;
            const isRunning = runningId === m.id;
            return (
              <div key={m.id} className="rounded-lg border border-glass px-3 py-2 space-y-1.5">
                <div className="flex items-center gap-3">
                  <span className={`h-2 w-2 rounded-full ${m.enabled ? "bg-emerald-500" : "bg-neutral-600"}`} />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-neutral-200 truncate">{coll?.name ?? m.collection_id}</p>
                    <p className="text-[11px] text-neutral-500">cron: {m.cron ?? "not set"}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => runNow(m)}
                    disabled={isRunning}
                    className="inline-flex items-center gap-1 rounded-md border border-glass bg-cobweb-600/10 px-2 py-1 text-[11px] text-cobweb-400 transition hover:bg-cobweb-600/20 disabled:opacity-50"
                  >
                    {isRunning ? <Loader2 className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />}
                    Run Now
                  </button>
                  <button type="button" onClick={() => m.id && remove(m.id)} className="rounded p-1 text-neutral-600 transition hover:bg-neutral-800 hover:text-rose-400">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
                {lastRun && (
                  <div className="flex items-center gap-2 text-[11px] text-neutral-500">
                    <Clock className="h-3 w-3" />
                    Last run: {timeAgo(lastRun.timestamp)}
                    <span className="mx-1">&middot;</span>
                    <span className="flex items-center gap-1">
                      <CheckCircle2 className="h-3 w-3 text-emerald-400" /> {lastRun.passed}
                    </span>
                    {lastRun.failed > 0 && (
                      <span className="flex items-center gap-1">
                        <XCircle className="h-3 w-3 text-rose-400" /> {lastRun.failed}
                      </span>
                    )}
                    <span className="text-neutral-600">/ {lastRun.total} total</span>
                  </div>
                )}
              </div>
            );
          })}

          {lastRunOutput && (
            <div className="mt-3 rounded-lg border border-glass p-3 bg-neutral-900/30">
              <p className="mb-2 text-[11px] uppercase tracking-wider text-neutral-500">Last Run Results</p>
              <div className="flex items-center gap-3 mb-2 text-xs">
                <span className="text-emerald-400">{lastRunOutput.successful_requests} passed</span>
                {lastRunOutput.total_requests - lastRunOutput.successful_requests > 0 && (
                  <span className="text-rose-400">{lastRunOutput.total_requests - lastRunOutput.successful_requests} failed</span>
                )}
                <span className="text-neutral-500">{Math.round(lastRunOutput.total_elapsed_ms)} ms total</span>
              </div>
              <div className="space-y-1">
                {lastRunOutput.results.map((r, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs">
                    <span className={`font-mono font-bold ${(r.status ?? 0) < 400 ? "text-emerald-400" : "text-rose-400"}`}>{r.status ?? "ERR"}</span>
                    <span className="font-mono text-neutral-400">{r.method}</span>
                    <span className="truncate text-neutral-300">{r.url}</span>
                    <span className="ml-auto text-neutral-500">{r.elapsed_ms ? `${Math.round(r.elapsed_ms)} ms` : ""}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
