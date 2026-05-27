import { useState } from "react";
import { BarChart3, Loader2, X } from "lucide-react";
import { sidecar, type LatencyHistogramResult, type ThroughputTimelineResult, type SlaCheckResult, type SlaRule } from "../lib/sidecar";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function PerformanceDashboardModal({ open, onClose }: Props) {
  const [latencies, setLatencies] = useState("");
  const [histogram, setHistogram] = useState<LatencyHistogramResult | null>(null);
  const [throughput, setThroughput] = useState<ThroughputTimelineResult | null>(null);
  const [slaResult, setSlaResult] = useState<SlaCheckResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // SLA form
  const [slaMetric, setSlaMetric] = useState<SlaRule["metric"]>("p95");
  const [slaOp, setSlaOp] = useState<SlaRule["operator"]>("lt");
  const [slaValue, setSlaValue] = useState(500);

  if (!open) return null;

  async function analyze() {
    const nums = latencies
      .split(/[,\s\n]+/)
      .map(Number)
      .filter((n) => !isNaN(n) && n >= 0);
    if (nums.length === 0) return;
    setBusy(true); setError(null);
    try {
      const [h, t, s] = await Promise.all([
        sidecar.latencyHistogram({ latency_ms: nums }),
        sidecar.throughputTimeline(
          nums.map((lat, i) => ({
            timestamp: Date.now() - (nums.length - i) * 100,
            latency_ms: lat,
            success: true,
          })),
        ),
        sidecar.slaCheck({
          latencies: nums,
          error_count: 0,
          total: nums.length,
          rules: [{ metric: slaMetric, operator: slaOp, value: slaValue }],
        }),
      ]);
      setHistogram(h);
      setThroughput(t);
      setSlaResult(s);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const inputClass = "w-full rounded-md border border-glass bg-neutral-900/50 px-3 py-1.5 text-xs text-neutral-100 placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="glass flex h-[600px] w-[750px] max-h-[90vh] max-w-[95vw] animate-slide-in flex-col overflow-hidden rounded-xl border border-glass-light shadow-2xl shadow-black/60">
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-100">
            <BarChart3 className="h-4 w-4 text-cobweb-400" /> Performance Dashboard
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200"><X className="h-4 w-4" /></button>
        </div>

        {error && <div className="border-b border-rose-800/30 bg-rose-950/20 px-4 py-2 text-xs text-rose-400">{error}</div>}

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          <div>
            <p className="mb-1 text-[11px] uppercase tracking-wider text-neutral-500">Latency data (ms, comma or newline separated)</p>
            <textarea
              value={latencies}
              onChange={(e) => setLatencies(e.target.value)}
              placeholder="12, 45, 23, 67, 98, 34, 55, 120, 15, 78"
              rows={3}
              className={`${inputClass} font-mono resize-y`}
            />
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="mb-1 block text-[11px] text-neutral-500">SLA metric</label>
              <select value={slaMetric} onChange={(e) => setSlaMetric(e.target.value as SlaRule["metric"])} className={inputClass}>
                <option value="p95">p95</option>
                <option value="p99">p99</option>
                <option value="p50">p50</option>
                <option value="avg">avg</option>
                <option value="max">max</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-[11px] text-neutral-500">Operator</label>
              <select value={slaOp} onChange={(e) => setSlaOp(e.target.value as SlaRule["operator"])} className={inputClass}>
                <option value="lt">&lt;</option>
                <option value="lte">&lt;=</option>
                <option value="gt">&gt;</option>
                <option value="gte">&gt;=</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-[11px] text-neutral-500">Threshold (ms)</label>
              <input type="number" value={slaValue} onChange={(e) => setSlaValue(parseInt(e.target.value) || 0)} className={inputClass} />
            </div>
          </div>

          <button
            type="button"
            onClick={analyze}
            disabled={busy}
            className="inline-flex items-center gap-2 rounded-md bg-cobweb-600/20 px-4 py-2 text-xs font-medium text-cobweb-400 transition hover:bg-cobweb-600/30 disabled:opacity-50"
          >
            {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Analyze
          </button>

          {histogram && (
            <div>
              <p className="mb-2 text-[11px] uppercase tracking-wider text-neutral-500">
                Latency Histogram
                <span className="ml-2 normal-case text-neutral-600">mean={histogram.mean.toFixed(1)}ms stddev={histogram.stddev.toFixed(1)}ms n={histogram.total}</span>
              </p>
              <div className="flex items-end gap-[2px] h-24">
                {histogram.buckets.map((b, idx) => {
                  const maxCount = Math.max(...histogram.buckets.map((x) => x.count), 1);
                  const pct = (b.count / maxCount) * 100;
                  return (
                    <div
                      key={idx}
                      className="flex-1 rounded-t bg-cobweb-500/60 transition-all"
                      style={{ height: `${pct}%` }}
                      title={`${b.min.toFixed(0)}-${b.max.toFixed(0)}ms: ${b.count}`}
                    />
                  );
                })}
              </div>
              <div className="flex justify-between text-[10px] text-neutral-600 mt-1">
                <span>{histogram.buckets[0]?.min.toFixed(0)}ms</span>
                <span>{histogram.buckets[histogram.buckets.length - 1]?.max.toFixed(0)}ms</span>
              </div>
            </div>
          )}

          {throughput && throughput.windows.length > 0 && (
            <div>
              <p className="mb-2 text-[11px] uppercase tracking-wider text-neutral-500">Throughput Timeline</p>
              <div className="flex items-end gap-[2px] h-16">
                {throughput.windows.map((w, idx) => {
                  const maxRps = Math.max(...throughput.windows.map((x) => x.rps), 1);
                  const pct = (w.rps / maxRps) * 100;
                  return (
                    <div
                      key={idx}
                      className={`flex-1 rounded-t transition-all ${w.error_count > 0 ? "bg-rose-500/60" : "bg-emerald-500/60"}`}
                      style={{ height: `${pct}%` }}
                      title={`RPS: ${w.rps.toFixed(1)} Latency: ${w.avg_latency.toFixed(0)}ms Errors: ${w.error_count}`}
                    />
                  );
                })}
              </div>
            </div>
          )}

          {slaResult && (
            <div>
              <p className="mb-2 text-[11px] uppercase tracking-wider text-neutral-500">SLA Check</p>
              <div className={`rounded-lg border p-3 ${slaResult.passed ? "border-emerald-800/50 bg-emerald-950/20" : "border-rose-800/50 bg-rose-950/20"}`}>
                <p className={`text-xs font-medium ${slaResult.passed ? "text-emerald-400" : "text-rose-400"}`}>
                  {slaResult.passed ? "SLA PASSED" : "SLA FAILED"}
                </p>
                {slaResult.results.map((r, idx) => (
                  <p key={idx} className="text-[11px] text-neutral-400 mt-1">
                    {r.rule.metric} {r.rule.operator} {r.rule.value}ms: actual={r.actual.toFixed(1)}ms
                    <span className={`ml-1 ${r.passed ? "text-emerald-400" : "text-rose-400"}`}>{r.passed ? "PASS" : "FAIL"}</span>
                  </p>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
