import { useState } from "react";
import { Key, Loader2, X } from "lucide-react";
import { sidecar, type JwtInspectResult } from "../lib/sidecar";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function JwtInspectorModal({ open, onClose }: Props) {
  const [token, setToken] = useState("");
  const [result, setResult] = useState<JwtInspectResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  async function inspect() {
    if (!token.trim()) return;
    setBusy(true); setError(null); setResult(null);
    try {
      const res = await sidecar.jwtInspect(token.trim());
      setResult(res);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="glass flex h-[560px] w-[600px] max-h-[90vh] max-w-[95vw] animate-slide-in flex-col overflow-hidden rounded-xl border border-glass-light shadow-2xl shadow-black/60">
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-100">
            <Key className="h-4 w-4 text-cobweb-400" /> JWT Inspector
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200"><X className="h-4 w-4" /></button>
        </div>

        {error && <div className="border-b border-rose-800/30 bg-rose-950/20 px-4 py-2 text-xs text-rose-400">{error}</div>}

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          <div>
            <p className="mb-2 text-[11px] uppercase tracking-wider text-neutral-500">Paste JWT Token</p>
            <textarea
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="eyJhbGciOiJIUzI1NiIs..."
              rows={3}
              className="w-full resize-none rounded-md border border-glass bg-neutral-900/50 px-3 py-2 font-mono text-xs text-neutral-100 placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none"
              spellCheck={false}
            />
            <button
              type="button"
              onClick={inspect}
              disabled={busy || !token.trim()}
              className="mt-2 inline-flex items-center gap-2 rounded-md bg-cobweb-600/20 px-3 py-1.5 text-xs font-medium text-cobweb-400 transition hover:bg-cobweb-600/30 disabled:opacity-50"
            >
              {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              Inspect
            </button>
          </div>

          {result && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <span className={`rounded px-2 py-0.5 text-[11px] font-bold ${result.expired ? "bg-rose-950/40 text-rose-400" : "bg-emerald-950/40 text-emerald-400"}`}>
                  {result.expired ? "EXPIRED" : "VALID"}
                </span>
                {result.expires_at && <span className="text-[11px] text-neutral-500">Expires: {result.expires_at}</span>}
                {result.issued_at && <span className="text-[11px] text-neutral-500">Issued: {result.issued_at}</span>}
              </div>

              <div>
                <p className="mb-1 text-[11px] uppercase tracking-wider text-neutral-500">Header</p>
                <pre className="rounded-md border border-glass bg-neutral-900/50 p-3 text-xs">
                  <code className="text-cyan-400">{JSON.stringify(result.header, null, 2)}</code>
                </pre>
              </div>

              <div>
                <p className="mb-1 text-[11px] uppercase tracking-wider text-neutral-500">Payload</p>
                <pre className="rounded-md border border-glass bg-neutral-900/50 p-3 text-xs">
                  <code className="text-emerald-400">{JSON.stringify(result.payload, null, 2)}</code>
                </pre>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
