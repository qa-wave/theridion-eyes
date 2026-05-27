import { useState } from "react";
import { AlertTriangle, Loader2, Shield, X } from "lucide-react";
import { sidecar, type OWASPFinding, type OWASPScanOutput, type OWASPScanType } from "../lib/sidecar";

interface Props {
  open: boolean;
  onClose: () => void;
}

const SCAN_TYPES: { id: OWASPScanType; label: string; description: string }[] = [
  { id: "sql_injection", label: "SQL Injection", description: "Test with 5 common SQLi payloads" },
  { id: "xss", label: "XSS", description: "Test with 3 cross-site scripting payloads" },
  { id: "auth_bypass", label: "Auth Bypass", description: "Remove auth headers and compare" },
  { id: "rate_limit", label: "Rate Limit", description: "Send 20 rapid requests" },
];

const SEVERITY_COLORS: Record<string, string> = {
  critical: "bg-rose-950/50 border-rose-700/50 text-rose-300",
  high: "bg-orange-950/50 border-orange-700/50 text-orange-300",
  medium: "bg-amber-950/50 border-amber-700/50 text-amber-300",
  low: "bg-yellow-950/50 border-yellow-700/50 text-yellow-300",
  info: "bg-sky-950/50 border-sky-700/50 text-sky-300",
};

const SEVERITY_BADGE: Record<string, string> = {
  critical: "bg-rose-600 text-white",
  high: "bg-orange-600 text-white",
  medium: "bg-amber-600 text-black",
  low: "bg-yellow-600 text-black",
  info: "bg-sky-600 text-white",
};

function scoreColor(score: number): string {
  if (score >= 80) return "text-emerald-400";
  if (score >= 60) return "text-amber-400";
  return "text-rose-400";
}

export function OWASPScannerModal({ open, onClose }: Props) {
  const [url, setUrl] = useState("");
  const [method, setMethod] = useState("GET");
  const [paramsText, setParamsText] = useState("");
  const [headersText, setHeadersText] = useState("");
  const [selectedTypes, setSelectedTypes] = useState<Set<OWASPScanType>>(
    new Set(["sql_injection", "xss", "auth_bypass", "rate_limit"]),
  );
  const [result, setResult] = useState<OWASPScanOutput | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  function toggleType(t: OWASPScanType) {
    setSelectedTypes((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });
  }

  async function runScan() {
    if (!url) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      let params: Record<string, string> = {};
      if (paramsText.trim()) {
        try { params = JSON.parse(paramsText); } catch { /* ignore */ }
      }
      let headers: Record<string, string> = {};
      if (headersText.trim()) {
        for (const line of headersText.split("\n")) {
          const idx = line.indexOf(":");
          if (idx > 0) headers[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
        }
      }
      const res = await sidecar.owaspScan({
        url,
        method,
        params,
        headers,
        scan_types: Array.from(selectedTypes),
      });
      setResult(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const inputClass = "w-full rounded-md border border-glass bg-neutral-900/50 px-3 py-1.5 text-xs text-neutral-100 placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="glass flex h-[640px] w-[780px] max-h-[90vh] max-w-[95vw] animate-slide-in flex-col overflow-hidden rounded-xl border border-glass-light shadow-2xl shadow-black/60">
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-100">
            <Shield className="h-4 w-4 text-cobweb-400" /> OWASP Security Scanner
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200">
            <X className="h-4 w-4" />
          </button>
        </div>

        {error && <div className="border-b border-rose-800/30 bg-rose-950/20 px-4 py-2 text-xs text-rose-400">{error}</div>}

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {!result ? (
            <>
              <div className="grid grid-cols-[1fr_auto] gap-3">
                <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://api.example.com/endpoint" className={inputClass} />
                <select value={method} onChange={(e) => setMethod(e.target.value)} className={`${inputClass} w-24`}>
                  {["GET", "POST", "PUT", "PATCH", "DELETE"].map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              </div>

              <div>
                <p className="mb-1 text-[11px] uppercase tracking-wider text-neutral-500">Params (JSON)</p>
                <textarea
                  value={paramsText}
                  onChange={(e) => setParamsText(e.target.value)}
                  placeholder='{"q": "test", "page": "1"}'
                  rows={2}
                  className={`${inputClass} font-mono resize-none`}
                />
              </div>

              <div>
                <p className="mb-1 text-[11px] uppercase tracking-wider text-neutral-500">Headers</p>
                <textarea
                  value={headersText}
                  onChange={(e) => setHeadersText(e.target.value)}
                  placeholder="Authorization: Bearer token123"
                  rows={2}
                  className={`${inputClass} font-mono resize-none`}
                />
              </div>

              <div>
                <p className="mb-2 text-[11px] uppercase tracking-wider text-neutral-500">Scan Types</p>
                <div className="grid grid-cols-2 gap-2">
                  {SCAN_TYPES.map((st) => (
                    <label key={st.id} className="flex items-start gap-2 rounded-lg border border-glass p-2 cursor-pointer hover:bg-white/[0.02]">
                      <input
                        type="checkbox"
                        checked={selectedTypes.has(st.id)}
                        onChange={() => toggleType(st.id)}
                        className="mt-0.5 h-3.5 w-3.5 accent-cobweb-500"
                      />
                      <div>
                        <p className="text-xs font-medium text-neutral-200">{st.label}</p>
                        <p className="text-[10px] text-neutral-500">{st.description}</p>
                      </div>
                    </label>
                  ))}
                </div>
              </div>

              <button
                type="button"
                onClick={runScan}
                disabled={busy || !url || selectedTypes.size === 0}
                className="inline-flex items-center gap-2 rounded-md bg-accent-gradient px-4 py-2 text-xs font-medium text-white shadow-glow-sm transition disabled:opacity-50 disabled:shadow-none"
              >
                {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Shield className="h-3.5 w-3.5" />}
                Run OWASP Scan
              </button>
            </>
          ) : (
            <div className="space-y-4">
              {/* Score badge */}
              <div className="flex items-center gap-4">
                <div className={`text-4xl font-bold ${scoreColor(result.score)}`}>
                  {result.score}
                </div>
                <div>
                  <p className="text-xs text-neutral-400">Security Score (0-100)</p>
                  <p className="text-[10px] text-neutral-500">
                    {result.findings.length} finding{result.findings.length !== 1 ? "s" : ""} in {result.elapsed_ms.toFixed(0)}ms
                  </p>
                  <p className="text-[10px] text-neutral-600">
                    Scanned: {result.scan_types_run.join(", ")}
                  </p>
                </div>
              </div>

              {result.findings.length === 0 ? (
                <div className="rounded-lg border border-emerald-800/50 bg-emerald-950/20 p-4 text-center">
                  <p className="text-sm text-emerald-400">No vulnerabilities detected</p>
                  <p className="text-[11px] text-emerald-600 mt-1">All scans passed without findings</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {result.findings.map((f: OWASPFinding, idx: number) => (
                    <div key={idx} className={`rounded-lg border p-3 ${SEVERITY_COLORS[f.severity] ?? SEVERITY_COLORS.info}`}>
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${SEVERITY_BADGE[f.severity] ?? SEVERITY_BADGE.info}`}>
                          {f.severity}
                        </span>
                        <AlertTriangle className="h-3 w-3" />
                        <span className="text-xs font-medium">{f.title}</span>
                      </div>
                      <p className="text-[11px] opacity-80 mb-1">{f.description}</p>
                      <p className="text-[10px] font-mono opacity-60">{f.evidence}</p>
                    </div>
                  ))}
                </div>
              )}

              <button
                type="button"
                onClick={() => setResult(null)}
                className="text-xs text-cobweb-400 hover:text-cobweb-300"
              >
                Scan again
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
