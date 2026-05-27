import { useState } from "react";
import { Activity, Loader2, Play, X } from "lucide-react";
import { sidecar, type LoadTestResult } from "../lib/sidecar";

interface Props {
  open: boolean;
  onClose: () => void;
  method: string;
  url: string;
  headers: Record<string, string>;
  body: string | null;
}

export function LoadTestModal({ open, onClose, method, url, headers, body }: Props) {
  const [concurrency, setConcurrency] = useState(10);
  const [duration, setDuration] = useState(5);
  const [rpsLimit, setRpsLimit] = useState<number | null>(null);
  const [result, setResult] = useState<LoadTestResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  async function run() {
    if (!url) return;
    setBusy(true); setError(null); setResult(null);
    try {
      const res = await sidecar.loadTest({
        url, method: method as "GET", headers, body,
        concurrency, duration_seconds: duration,
        rps_limit: rpsLimit,
      });
      setResult(res);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  const inputClass = "w-full rounded-md border border-glass bg-neutral-900/50 px-3 py-1.5 text-xs text-neutral-100 focus:border-cobweb-500/40 focus:outline-none";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="glass flex h-[560px] w-[700px] max-h-[90vh] max-w-[95vw] animate-slide-in flex-col overflow-hidden rounded-xl border border-glass-light shadow-2xl shadow-black/60">
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-100">
            <Activity className="h-4 w-4 text-cobweb-400" /> Load Test
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200"><X className="h-4 w-4" /></button>
        </div>

        <div className="border-b border-glass px-4 py-2 text-xs">
          <span className="font-mono text-neutral-400">{method} {url}</span>
        </div>

        {error && <div className="border-b border-rose-800/30 bg-rose-950/20 px-4 py-2 text-xs text-rose-400">{error}</div>}

        <div className="flex-1 overflow-y-auto p-4">
          {!result ? (
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="mb-1 block text-[10px] uppercase tracking-widest text-neutral-500">Concurrency</label>
                  <input type="number" value={concurrency} onChange={(e) => setConcurrency(Number(e.target.value))} min={1} max={500} className={inputClass} />
                </div>
                <div>
                  <label className="mb-1 block text-[10px] uppercase tracking-widest text-neutral-500">Duration (s)</label>
                  <input type="number" value={duration} onChange={(e) => setDuration(Number(e.target.value))} min={1} max={300} className={inputClass} />
                </div>
                <div>
                  <label className="mb-1 block text-[10px] uppercase tracking-widest text-neutral-500">RPS limit</label>
                  <input type="number" value={rpsLimit ?? ""} onChange={(e) => setRpsLimit(e.target.value ? Number(e.target.value) : null)} placeholder="unlimited" className={inputClass} />
                </div>
              </div>
              <button type="button" onClick={run} disabled={busy || !url}
                className="bg-accent-gradient inline-flex items-center gap-1.5 rounded-md px-5 py-2 text-xs font-medium text-white shadow-glow-sm transition disabled:opacity-40 disabled:shadow-none">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                {busy ? "Running..." : "Start Load Test"}
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-4 gap-3">
                <StatCard label="Total Requests" value={String(result.total_requests)} />
                <StatCard label="Successful" value={String(result.successful)} color="text-emerald-400" />
                <StatCard label="Failed" value={String(result.failed)} color={result.failed > 0 ? "text-rose-400" : "text-neutral-400"} />
                <StatCard label="RPS" value={result.actual_rps.toFixed(1)} />
              </div>
              <div className="grid grid-cols-4 gap-3">
                <StatCard label="Avg Latency" value={`${result.avg_latency_ms.toFixed(0)}ms`} />
                <StatCard label="p50" value={`${result.p50_ms.toFixed(0)}ms`} />
                <StatCard label="p95" value={`${result.p95_ms.toFixed(0)}ms`} />
                <StatCard label="p99" value={`${result.p99_ms.toFixed(0)}ms`} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <StatCard label="Min Latency" value={`${result.min_latency_ms.toFixed(0)}ms`} />
                <StatCard label="Max Latency" value={`${result.max_latency_ms.toFixed(0)}ms`} />
              </div>
              {Object.keys(result.errors).length > 0 && (
                <div>
                  <p className="mb-1 text-[10px] uppercase tracking-widest text-neutral-500">Errors</p>
                  {Object.entries(result.errors).map(([err, count]) => (
                    <div key={err} className="flex justify-between text-xs">
                      <span className="text-rose-400">{err}</span>
                      <span className="text-neutral-500">{count}x</span>
                    </div>
                  ))}
                </div>
              )}
              <button type="button" onClick={() => setResult(null)} className="text-xs text-cobweb-400 hover:text-cobweb-300">
                Run again
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="rounded-lg border border-glass bg-neutral-900/30 p-3">
      <div className={`text-lg font-bold ${color ?? "text-neutral-100"}`}>{value}</div>
      <div className="mt-0.5 text-[10px] uppercase tracking-widest text-neutral-500">{label}</div>
    </div>
  );
}
