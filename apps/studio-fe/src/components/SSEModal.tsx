import { useEffect, useRef, useState } from "react";
import { Loader2, Radio, X } from "lucide-react";
import { sidecar, type SSEEvent } from "../lib/sidecar";

interface Props {
  open: boolean;
  onClose: () => void;
}

const EVENT_COLORS: Record<string, string> = {
  message: "text-cobweb-400",
  error: "text-rose-400",
  ping: "text-neutral-500",
  open: "text-emerald-400",
};

export function SSEModal({ open, onClose }: Props) {
  const [url, setUrl] = useState("");
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [connectionTime, setConnectionTime] = useState<number | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [events]);

  async function connect() {
    if (!url.trim() || busy) return;
    setBusy(true);
    setError(null);
    setEvents([]);
    setConnectionTime(null);
    try {
      const result = await sidecar.sseConnect({
        url: url.trim(),
        max_events: 100,
        timeout_seconds: 30,
      });
      setEvents(result.events);
      setConnectionTime(result.connection_time_ms);
      if (result.error) setError(result.error);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="glass flex h-[600px] w-[700px] max-h-[90vh] max-w-[95vw] animate-slide-in flex-col overflow-hidden rounded-xl border border-glass-light shadow-2xl shadow-black/60">
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-100">
            <Radio className="h-4 w-4 text-cobweb-400" /> Server-Sent Events
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex items-center gap-2 border-b border-glass px-4 py-2">
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") void connect(); }}
            placeholder="https://api.example.com/events"
            className="flex-1 rounded-md border border-glass bg-neutral-900/50 px-3 py-1.5 font-mono text-xs text-neutral-100 placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none"
            spellCheck={false}
          />
          <button
            type="button"
            onClick={connect}
            disabled={busy || !url.trim()}
            className="inline-flex items-center gap-1.5 rounded-md bg-cobweb-600/20 px-4 py-1.5 text-xs font-medium text-cobweb-400 transition hover:bg-cobweb-600/30 disabled:opacity-50"
          >
            {busy && <Loader2 className="h-3 w-3 animate-spin" />}
            {busy ? "Listening..." : "Connect"}
          </button>
        </div>

        {error && (
          <div className="border-b border-rose-800/30 bg-rose-950/20 px-4 py-2 text-xs text-rose-400">{error}</div>
        )}

        {connectionTime !== null && (
          <div className="border-b border-glass px-4 py-1.5 text-[11px] text-neutral-500">
            Connected for {connectionTime < 1000 ? `${Math.round(connectionTime)} ms` : `${(connectionTime / 1000).toFixed(1)} s`}
            {" "}&middot; {events.length} event{events.length !== 1 ? "s" : ""} received
          </div>
        )}

        <div ref={listRef} className="flex-1 overflow-y-auto p-2 space-y-1">
          {events.length === 0 && !busy && (
            <p className="py-8 text-center text-xs text-neutral-600">
              Enter an SSE endpoint URL and click Connect to start listening for events.
            </p>
          )}
          {events.map((evt, i) => (
            <div key={i} className="rounded border border-glass bg-neutral-900/30 px-3 py-2 font-mono text-xs">
              <div className="flex items-center gap-2 text-[10px]">
                <span className={EVENT_COLORS[evt.event] ?? "text-amber-400"}>
                  {evt.event}
                </span>
                {evt.id && <span className="text-neutral-600">id: {evt.id}</span>}
                <span className="ml-auto text-neutral-600">
                  {new Date(evt.timestamp * 1000).toLocaleTimeString()}
                </span>
              </div>
              <pre className="mt-1 whitespace-pre-wrap break-all text-neutral-300">{evt.data}</pre>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
