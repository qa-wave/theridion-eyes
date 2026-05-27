import { useState } from "react";
import { Loader2, Shield, X } from "lucide-react";
import { sidecar, type CorsTestResult, type InjectionScanResult, type SensitiveDataResult, type JwtInspectResult, type OWASPScanOutput } from "../lib/sidecar";

interface Props {
  open: boolean;
  onClose: () => void;
}

type ScanTab = "cors" | "injection" | "sensitive" | "jwt" | "owasp";

export function SecurityScannerModal({ open, onClose }: Props) {
  const [tab, setTab] = useState<ScanTab>("cors");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // CORS
  const [corsUrl, setCorsUrl] = useState("");
  const [corsOrigin, setCorsOrigin] = useState("");
  const [corsResult, setCorsResult] = useState<CorsTestResult | null>(null);

  // Injection
  const [injUrl, setInjUrl] = useState("");
  const [injParams, setInjParams] = useState("");
  const [injResult, setInjResult] = useState<InjectionScanResult | null>(null);

  // Sensitive
  const [sensBody, setSensBody] = useState("");
  const [sensResult, setSensResult] = useState<SensitiveDataResult | null>(null);

  // JWT
  const [jwtToken, setJwtToken] = useState("");
  const [jwtResult, setJwtResult] = useState<JwtInspectResult | null>(null);

  // OWASP
  const [owaspUrl, setOwaspUrl] = useState("");
  const [owaspParams, setOwaspParams] = useState("");
  const [owaspResult, setOwaspResult] = useState<OWASPScanOutput | null>(null);

  if (!open) return null;

  async function runCors() {
    if (!corsUrl) return;
    setBusy(true); setError(null);
    try {
      setCorsResult(await sidecar.corsTest({ url: corsUrl, origin: corsOrigin || undefined }));
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  async function runInjection() {
    if (!injUrl) return;
    setBusy(true); setError(null);
    try {
      let params: Record<string, string> = {};
      try { params = JSON.parse(injParams); } catch { /* ignore */ }
      setInjResult(await sidecar.injectionScan({ url: injUrl, params }));
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  async function runSensitive() {
    if (!sensBody) return;
    setBusy(true); setError(null);
    try {
      setSensResult(await sidecar.sensitiveScan({ body: sensBody }));
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  async function runJwt() {
    if (!jwtToken) return;
    setBusy(true); setError(null);
    try {
      setJwtResult(await sidecar.jwtInspect(jwtToken.trim()));
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  const inputClass = "w-full rounded-md border border-glass bg-neutral-900/50 px-3 py-1.5 text-xs text-neutral-100 placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none";
  const btnClass = "inline-flex items-center gap-2 rounded-md bg-cobweb-600/20 px-3 py-1.5 text-xs font-medium text-cobweb-400 transition hover:bg-cobweb-600/30 disabled:opacity-50";

  const TABS: { id: ScanTab; label: string }[] = [
    { id: "cors", label: "CORS Test" },
    { id: "injection", label: "Injection Scan" },
    { id: "sensitive", label: "Sensitive Data" },
    { id: "jwt", label: "JWT" },
    { id: "owasp", label: "OWASP Scan" },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="glass flex h-[560px] w-[700px] max-h-[90vh] max-w-[95vw] animate-slide-in flex-col overflow-hidden rounded-xl border border-glass-light shadow-2xl shadow-black/60">
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-100">
            <Shield className="h-4 w-4 text-cobweb-400" /> Security Scanner
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200"><X className="h-4 w-4" /></button>
        </div>

        <div className="flex border-b border-glass">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => { setTab(t.id); setError(null); }}
              className={`px-4 py-2 text-xs font-medium transition ${tab === t.id ? "text-neutral-100 border-b-2 border-cobweb-400" : "text-neutral-400 hover:text-neutral-200"}`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {error && <div className="border-b border-rose-800/30 bg-rose-950/20 px-4 py-2 text-xs text-rose-400">{error}</div>}

        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {tab === "cors" && (
            <>
              <input value={corsUrl} onChange={(e) => setCorsUrl(e.target.value)} placeholder="https://api.example.com" className={inputClass} />
              <input value={corsOrigin} onChange={(e) => setCorsOrigin(e.target.value)} placeholder="Origin (optional)" className={inputClass} />
              <button type="button" onClick={runCors} disabled={busy} className={btnClass}>
                {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Test CORS
              </button>
              {corsResult && (
                <div className="rounded-lg border border-glass p-3 space-y-1 text-xs">
                  <p className={corsResult.allowed ? "text-emerald-400" : "text-rose-400"}>{corsResult.allowed ? "CORS Allowed" : "CORS Blocked"}</p>
                  {corsResult.allow_origin && <p className="text-neutral-400">Allow-Origin: {corsResult.allow_origin}</p>}
                  {corsResult.allow_methods && <p className="text-neutral-400">Allow-Methods: {corsResult.allow_methods}</p>}
                  {corsResult.issues.length > 0 && corsResult.issues.map((i, idx) => <p key={idx} className="text-amber-400">{i}</p>)}
                </div>
              )}
            </>
          )}

          {tab === "injection" && (
            <>
              <input value={injUrl} onChange={(e) => setInjUrl(e.target.value)} placeholder="https://api.example.com/search" className={inputClass} />
              <textarea value={injParams} onChange={(e) => setInjParams(e.target.value)} placeholder='{"q":"test"}' rows={3} className={`${inputClass} font-mono resize-none`} />
              <button type="button" onClick={runInjection} disabled={busy} className={btnClass}>
                {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Scan
              </button>
              {injResult && (
                <div className="space-y-2">
                  <p className={`text-xs font-medium ${injResult.vulnerable ? "text-rose-400" : "text-emerald-400"}`}>
                    {injResult.vulnerable ? "Potential vulnerabilities found" : "No issues detected"}
                  </p>
                  {injResult.findings.map((f, idx) => (
                    <div key={idx} className="rounded border border-glass p-2 text-xs">
                      <p className={f.suspicious ? "text-rose-400" : "text-neutral-400"}>Param: {f.param} | Status: {f.response_status}</p>
                      <p className="text-neutral-500 font-mono text-[11px] mt-1">{f.evidence}</p>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          {tab === "sensitive" && (
            <>
              <textarea value={sensBody} onChange={(e) => setSensBody(e.target.value)} placeholder="Paste response body to scan..." rows={6} className={`${inputClass} font-mono resize-y`} />
              <button type="button" onClick={runSensitive} disabled={busy} className={btnClass}>
                {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Scan
              </button>
              {sensResult && (
                <div className="space-y-2">
                  <p className="text-xs">
                    Risk: <span className={`font-medium ${sensResult.risk_level === "high" ? "text-rose-400" : sensResult.risk_level === "medium" ? "text-amber-400" : sensResult.risk_level === "low" ? "text-amber-300" : "text-emerald-400"}`}>{sensResult.risk_level}</span>
                    <span className="ml-2 text-neutral-400">{sensResult.count} finding(s)</span>
                  </p>
                  {sensResult.findings.map((f, idx) => (
                    <div key={idx} className="rounded border border-glass p-2 text-xs">
                      <p className="text-neutral-300">{f.type} at {f.location} (line {f.line})</p>
                      <p className="text-neutral-500 font-mono">{f.value_preview}</p>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          {tab === "owasp" && (
            <>
              <input value={owaspUrl} onChange={(e) => setOwaspUrl(e.target.value)} placeholder="https://api.example.com/endpoint" className={inputClass} />
              <textarea value={owaspParams} onChange={(e) => setOwaspParams(e.target.value)} placeholder='{"q":"test"}' rows={2} className={`${inputClass} font-mono resize-none`} />
              <button type="button" onClick={async () => {
                if (!owaspUrl) return;
                setBusy(true); setError(null);
                try {
                  let params: Record<string, string> = {};
                  try { params = JSON.parse(owaspParams); } catch { /* ignore */ }
                  setOwaspResult(await sidecar.owaspScan({ url: owaspUrl, params }));
                } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
                finally { setBusy(false); }
              }} disabled={busy} className={btnClass}>
                {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Run OWASP Scan
              </button>
              {owaspResult && (
                <div className="space-y-2">
                  <div className="flex items-center gap-3">
                    <span className={`text-2xl font-bold ${owaspResult.score >= 80 ? "text-emerald-400" : owaspResult.score >= 60 ? "text-amber-400" : "text-rose-400"}`}>{owaspResult.score}</span>
                    <span className="text-xs text-neutral-400">{owaspResult.findings.length} finding(s) in {owaspResult.elapsed_ms.toFixed(0)}ms</span>
                  </div>
                  {owaspResult.findings.map((f, idx) => (
                    <div key={idx} className="rounded border border-glass p-2 text-xs">
                      <span className={`mr-2 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${f.severity === "critical" ? "bg-rose-600 text-white" : f.severity === "high" ? "bg-orange-600 text-white" : f.severity === "medium" ? "bg-amber-600 text-black" : "bg-sky-600 text-white"}`}>{f.severity}</span>
                      <span className="text-neutral-200">{f.title}</span>
                      <p className="mt-1 text-neutral-500 text-[11px]">{f.description}</p>
                      <p className="font-mono text-[10px] text-neutral-600 mt-0.5">{f.evidence}</p>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          {tab === "jwt" && (
            <>
              <textarea value={jwtToken} onChange={(e) => setJwtToken(e.target.value)} placeholder="eyJhbGci..." rows={3} className={`${inputClass} font-mono resize-none`} />
              <button type="button" onClick={runJwt} disabled={busy} className={btnClass}>
                {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Inspect
              </button>
              {jwtResult && (
                <div className="space-y-2">
                  <span className={`rounded px-2 py-0.5 text-[11px] font-bold ${jwtResult.expired ? "bg-rose-950/40 text-rose-400" : "bg-emerald-950/40 text-emerald-400"}`}>
                    {jwtResult.expired ? "EXPIRED" : "VALID"}
                  </span>
                  <pre className="rounded border border-glass bg-neutral-900/50 p-2 text-xs text-cyan-400">{JSON.stringify(jwtResult.header, null, 2)}</pre>
                  <pre className="rounded border border-glass bg-neutral-900/50 p-2 text-xs text-emerald-400">{JSON.stringify(jwtResult.payload, null, 2)}</pre>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
