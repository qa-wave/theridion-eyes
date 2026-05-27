import { useEffect, useState } from "react";
import { Download, Loader2, Play, Radio, Square, X } from "lucide-react";
import { sidecar } from "../lib/sidecar";

interface ProxySession {
  session_id: string;
  port: number;
  target_base_url: string;
}

interface Props {
  open: boolean;
  onClose: () => void;
}

export function ProxyRecorderModal({ open, onClose }: Props) {
  const [targetUrl, setTargetUrl] = useState("https://api.example.com");
  const [port, setPort] = useState(9999);
  const [sessions, setSessions] = useState<ProxySession[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) refreshStatus();
  }, [open]);

  async function refreshStatus() {
    try {
      const res = await sidecar.proxyStatus();
      setSessions(res.sessions || []);
    } catch { /* ignore */ }
  }

  async function start() {
    setBusy(true);
    setError(null);
    try {
      await sidecar.proxyStart({ target_base_url: targetUrl, port });
      await refreshStatus();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function stop(sessionId: string) {
    try {
      await sidecar.proxyStop(sessionId);
      await refreshStatus();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function downloadHar(sessionId: string) {
    try {
      const har = await sidecar.proxyHar(sessionId);
      const blob = new Blob([JSON.stringify(har, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `theridion-proxy-${sessionId.slice(0, 8)}.har`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  if (!open) return null;

  const inputClass = "w-full rounded-md border border-glass bg-neutral-900/50 px-3 py-1.5 font-mono text-xs text-neutral-100 placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="glass w-[600px] max-w-[95vw] animate-slide-in rounded-xl border border-glass-light shadow-2xl shadow-black/60">
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-100">
            <Radio className="h-4 w-4 text-cobweb-400" /> Proxy Recorder
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4 p-4">
          {/* Active sessions */}
          {sessions.length > 0 && (
            <div>
              <p className="mb-2 text-[10px] uppercase tracking-widest text-neutral-500">Active sessions</p>
              <div className="space-y-1.5">
                {sessions.map((s) => (
                  <div key={s.session_id} className="flex items-center gap-2 rounded-lg border border-emerald-800/30 bg-emerald-950/10 px-3 py-2 text-xs">
                    <span className="relative flex h-2 w-2">
                      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-40" />
                      <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
                    </span>
                    <span className="font-mono text-neutral-200">:{s.port}</span>
                    <span className="text-neutral-500">&rarr;</span>
                    <span className="flex-1 truncate font-mono text-neutral-400">{s.target_base_url}</span>
                    <button type="button" onClick={() => downloadHar(s.session_id)}
                      className="inline-flex items-center gap-1 rounded-md border border-glass px-2 py-0.5 text-neutral-400 hover:bg-white/[0.04] hover:text-neutral-200"
                      title="Download HAR">
                      <Download className="h-3 w-3" /> HAR
                    </button>
                    <button type="button" onClick={() => stop(s.session_id)}
                      className="inline-flex items-center gap-1 rounded-md border border-rose-800/40 bg-rose-950/20 px-2 py-0.5 text-rose-400 hover:bg-rose-950/40">
                      <Square className="h-3 w-3" /> Stop
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* New session */}
          <div>
            <p className="mb-2 text-[10px] uppercase tracking-widest text-neutral-500">Start new proxy</p>
            <div className="space-y-2">
              <div>
                <label className="mb-1 block text-[10px] uppercase tracking-widest text-neutral-500">Target base URL</label>
                <input value={targetUrl} onChange={(e) => setTargetUrl(e.target.value)} placeholder="https://api.example.com" className={inputClass} spellCheck={false} />
              </div>
              <div>
                <label className="mb-1 block text-[10px] uppercase tracking-widest text-neutral-500">Proxy port</label>
                <input type="number" value={port} onChange={(e) => setPort(Number(e.target.value))} min={1024} max={65535}
                  className="w-24 rounded-md border border-glass bg-neutral-900/50 px-3 py-1.5 text-xs text-neutral-100 focus:border-cobweb-500/40 focus:outline-none" />
              </div>
            </div>
          </div>

          <p className="rounded-md border border-glass bg-neutral-900/20 px-3 py-2 text-[11px] text-neutral-500">
            Point your HTTP client at <span className="font-mono text-cobweb-400">http://localhost:{port}</span> &mdash;
            all requests will be forwarded to {targetUrl || "the target"} and recorded. Download as HAR when done.
          </p>

          {error && (
            <p className="rounded-md border border-rose-800/30 bg-rose-950/20 px-2 py-1 text-xs text-rose-400">{error}</p>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-glass px-4 py-3">
          <button type="button" onClick={onClose} className="rounded-md border border-glass px-3 py-1.5 text-xs text-neutral-400 hover:bg-white/[0.04] hover:text-neutral-200">
            Close
          </button>
          <button type="button" onClick={start} disabled={busy || !targetUrl.trim()}
            className="bg-accent-gradient inline-flex items-center gap-1.5 rounded-md px-4 py-1.5 text-xs font-medium text-white shadow-glow-sm transition disabled:opacity-40 disabled:shadow-none">
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
            Start Recording
          </button>
        </div>
      </div>
    </div>
  );
}
