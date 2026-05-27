import { useEffect, useState } from "react";
import {
  Circle,
  Download,
  Loader2,
  Play,
  Plus,
  Radio,
  RefreshCw,
  Server,
  Square,
  Trash2,
  X,
} from "lucide-react";
import {
  sidecar,
  type MockRoute,
  type RecordedInteraction,
  type ReplayStatusOutput,
} from "../lib/sidecar";

interface Props {
  open: boolean;
  onClose: () => void;
}

type Tab = "manual" | "record";

export function MockServerModal({ open, onClose }: Props) {
  const [tab, setTab] = useState<Tab>("manual");

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="glass flex h-[640px] w-[860px] max-h-[90vh] max-w-[95vw] animate-slide-in flex-col overflow-hidden rounded-xl border border-glass-light shadow-2xl shadow-black/60">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-3">
            <Server className="h-4 w-4 text-cobweb-400" />
            <span className="text-sm font-medium text-neutral-100">Mock Server</span>
            <div className="flex rounded-md border border-glass bg-neutral-900/60">
              <TabBtn active={tab === "manual"} onClick={() => setTab("manual")}>
                Manual Mocks
              </TabBtn>
              <TabBtn active={tab === "record"} onClick={() => setTab("record")}>
                Record &amp; Replay
              </TabBtn>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {tab === "manual" ? <ManualMocksTab /> : <RecordReplayTab />}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Tab button                                                          */
/* ------------------------------------------------------------------ */

function TabBtn({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-3 py-1 text-[11px] font-medium transition ${
        active
          ? "bg-cobweb-500/20 text-cobweb-300"
          : "text-neutral-500 hover:text-neutral-300"
      }`}
    >
      {children}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/* Manual Mocks tab (original)                                         */
/* ------------------------------------------------------------------ */

function ManualMocksTab() {
  const [routes, setRoutes] = useState<MockRoute[]>([
    {
      path: "/health",
      method: "GET",
      status: 200,
      body: '{"status":"ok"}',
      content_type: "application/json",
    },
  ]);
  const [servers, setServers] = useState<Array<{ port: number; route_count: number }>>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    refreshStatus();
  }, []);

  async function refreshStatus() {
    try {
      const s = await sidecar.mockStatus();
      setServers(s.servers);
    } catch {
      /* ignore */
    }
  }

  async function start() {
    setBusy(true);
    setError(null);
    try {
      await sidecar.mockStart({ routes });
      await refreshStatus();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function stop(port: number) {
    try {
      await sidecar.mockStop(port);
      await refreshStatus();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function addRoute() {
    setRoutes((r) => [
      ...r,
      { path: "/new", method: "GET", status: 200, body: "", content_type: "application/json" },
    ]);
  }
  function updateRoute(i: number, patch: Partial<MockRoute>) {
    setRoutes((r) => r.map((rt, j) => (j === i ? { ...rt, ...patch } : rt)));
  }
  function removeRoute(i: number) {
    setRoutes((r) => r.filter((_, j) => j !== i));
  }

  const inputClass =
    "w-full rounded-md border border-glass bg-neutral-900/50 px-2 py-1 font-mono text-xs text-neutral-100 placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none";

  return (
    <>
      {/* Running servers */}
      {servers.length > 0 && (
        <div className="flex items-center gap-2 border-b border-glass px-4 py-2 text-xs">
          <span className="text-neutral-500">Running:</span>
          {servers.map((s) => (
            <span
              key={s.port}
              className="inline-flex items-center gap-1 rounded-md border border-emerald-800/30 bg-emerald-950/20 px-2 py-0.5 text-emerald-400"
            >
              :{s.port} ({s.route_count} routes)
              <button
                type="button"
                onClick={() => stop(s.port)}
                className="ml-1 text-rose-400 hover:text-rose-300"
              >
                <Square className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      )}

      {error && (
        <div className="border-b border-rose-800/30 bg-rose-950/20 px-4 py-2 text-xs text-rose-400">
          {error}
        </div>
      )}

      {/* Routes editor */}
      <div className="flex-1 overflow-y-auto p-4">
        <div className="mb-3 flex items-center justify-between">
          <p className="text-[10px] uppercase tracking-widest text-neutral-500">Routes</p>
          <button
            type="button"
            onClick={addRoute}
            className="inline-flex items-center gap-1 text-xs text-cobweb-400 hover:text-cobweb-300"
          >
            <Plus className="h-3 w-3" /> Add route
          </button>
        </div>
        <div className="space-y-2">
          {routes.map((r, i) => (
            <div key={i} className="rounded-lg border border-glass p-3">
              <div className="flex items-center gap-2">
                <select
                  value={r.method ?? "GET"}
                  onChange={(e) => updateRoute(i, { method: e.target.value })}
                  className="shrink-0 rounded-md border border-glass bg-neutral-900/50 px-2 py-1 text-xs text-neutral-100 focus:outline-none"
                >
                  {["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"].map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
                <input
                  value={r.path}
                  onChange={(e) => updateRoute(i, { path: e.target.value })}
                  placeholder="/api/resource"
                  className={inputClass}
                />
                <input
                  type="number"
                  value={r.status ?? 200}
                  onChange={(e) => updateRoute(i, { status: Number(e.target.value) })}
                  className="w-16 shrink-0 rounded-md border border-glass bg-neutral-900/50 px-2 py-1 text-xs text-neutral-100 focus:outline-none"
                />
                <button
                  type="button"
                  onClick={() => removeRoute(i)}
                  className="shrink-0 rounded-md p-1 text-neutral-500 hover:bg-white/[0.05] hover:text-rose-400"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
              <textarea
                value={r.body ?? ""}
                onChange={(e) => updateRoute(i, { body: e.target.value })}
                placeholder='{"message": "mocked"}'
                rows={2}
                className="mt-2 w-full rounded-md border border-glass bg-neutral-900/50 px-2 py-1 font-mono text-xs text-neutral-100 placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none"
                spellCheck={false}
              />
            </div>
          ))}
        </div>
      </div>

      <div className="flex justify-end gap-2 border-t border-glass px-4 py-3">
        <button
          type="button"
          onClick={start}
          disabled={busy || routes.length === 0}
          className="bg-accent-gradient inline-flex items-center gap-1.5 rounded-md px-4 py-1.5 text-xs font-medium text-white shadow-glow-sm transition disabled:opacity-40 disabled:shadow-none"
        >
          {busy ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Play className="h-3.5 w-3.5" />
          )}{" "}
          Start Server
        </button>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ */
/* Record & Replay tab                                                 */
/* ------------------------------------------------------------------ */

type RecordState = "idle" | "recording" | "replaying";

function RecordReplayTab() {
  const [state, setState] = useState<RecordState>("idle");
  const [targetUrl, setTargetUrl] = useState("http://localhost:3000");
  const [recordPort, setRecordPort] = useState(9000);
  const [replayPort, setReplayPort] = useState(9001);
  const [, setSessionId] = useState<string | null>(null);
  const [interactions, setInteractions] = useState<RecordedInteraction[]>([]);
  const [recordings, setRecordings] = useState<string[]>([]);
  const [selectedRecording, setSelectedRecording] = useState<string | null>(null);
  const [fuzzyQuery, setFuzzyQuery] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [replayStatus, setReplayStatus] = useState<ReplayStatusOutput | null>(null);

  useEffect(() => {
    refreshAll();
  }, []);

  // Poll interactions while recording
  useEffect(() => {
    if (state !== "recording") return;
    const interval = setInterval(async () => {
      try {
        const res = await sidecar.mockRecordInteractions();
        setInteractions(res.interactions);
      } catch {
        /* ignore */
      }
    }, 1500);
    return () => clearInterval(interval);
  }, [state]);

  async function refreshAll() {
    try {
      const ixResp = await sidecar.mockRecordInteractions();
      setRecordings(ixResp.recordings);
      if (ixResp.session_id) {
        setState("recording");
        setSessionId(ixResp.session_id);
        setInteractions(ixResp.interactions);
      }
    } catch {
      /* ignore */
    }
    try {
      const rs = await sidecar.mockReplayStatus();
      setReplayStatus(rs);
      if (rs.running) setState("replaying");
    } catch {
      /* ignore */
    }
  }

  async function startRecording() {
    setBusy(true);
    setError(null);
    try {
      const res = await sidecar.mockRecordStart({
        target_url: targetUrl,
        port: recordPort || undefined,
      });
      setSessionId(res.session_id);
      setRecordPort(res.port);
      setInteractions([]);
      setState("recording");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function stopRecording() {
    setBusy(true);
    setError(null);
    try {
      const res = await sidecar.mockRecordStop();
      setInteractions([]);
      setState("idle");
      setSessionId(null);
      setSelectedRecording(res.session_id);
      // Refresh recordings list
      const ixResp = await sidecar.mockRecordInteractions();
      setRecordings(ixResp.recordings);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function loadRecording(id: string) {
    setSelectedRecording(id);
    try {
      const res = await sidecar.mockRecordInteractions(id);
      setInteractions(res.interactions);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function startReplay() {
    setBusy(true);
    setError(null);
    try {
      const res = await sidecar.mockReplayStart({
        recording_id: selectedRecording,
        interactions: selectedRecording ? undefined : interactions,
        port: replayPort || undefined,
        fuzzy_query: fuzzyQuery,
      });
      setReplayPort(res.port);
      setState("replaying");
      setReplayStatus({ running: true, port: res.port, route_count: res.route_count });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function stopReplay() {
    setBusy(true);
    setError(null);
    try {
      await sidecar.mockReplayStop();
      setState("idle");
      setReplayStatus(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const inputClass =
    "w-full rounded-md border border-glass bg-neutral-900/50 px-2 py-1 font-mono text-xs text-neutral-100 placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none";

  return (
    <>
      {/* Status bar */}
      <div className="flex items-center gap-3 border-b border-glass px-4 py-2">
        <StatusPill state={state} />
        {state === "recording" && (
          <span className="text-[11px] text-neutral-400">
            {interactions.length} interaction{interactions.length !== 1 ? "s" : ""} recorded
          </span>
        )}
        {state === "replaying" && replayStatus && (
          <span className="text-[11px] text-neutral-400">
            Replaying {replayStatus.route_count} routes on :{replayStatus.port}
          </span>
        )}
      </div>

      {error && (
        <div className="border-b border-rose-800/30 bg-rose-950/20 px-4 py-2 text-xs text-rose-400">
          {error}
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-4">
        {/* Record controls */}
        {state === "idle" && (
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-[11px] uppercase tracking-widest text-neutral-500">
                Record from target
              </label>
              <div className="flex gap-2">
                <input
                  value={targetUrl}
                  onChange={(e) => setTargetUrl(e.target.value)}
                  placeholder="http://localhost:3000"
                  className={inputClass}
                />
                <input
                  type="number"
                  value={recordPort}
                  onChange={(e) => setRecordPort(Number(e.target.value))}
                  className="w-20 shrink-0 rounded-md border border-glass bg-neutral-900/50 px-2 py-1 text-xs text-neutral-100 focus:outline-none"
                  placeholder="Port"
                />
                <button
                  type="button"
                  onClick={startRecording}
                  disabled={busy || !targetUrl}
                  className="bg-accent-gradient inline-flex shrink-0 items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium text-white shadow-glow-sm transition disabled:opacity-40 disabled:shadow-none"
                >
                  {busy ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Radio className="h-3.5 w-3.5" />
                  )}{" "}
                  Record
                </button>
              </div>
            </div>

            {/* Saved recordings */}
            {recordings.length > 0 && (
              <div>
                <label className="mb-1 block text-[11px] uppercase tracking-widest text-neutral-500">
                  Saved recordings
                </label>
                <div className="space-y-1">
                  {recordings.map((r) => (
                    <button
                      key={r}
                      type="button"
                      onClick={() => loadRecording(r)}
                      className={`flex w-full items-center gap-2 rounded-md border px-3 py-1.5 text-left text-xs transition ${
                        selectedRecording === r
                          ? "border-cobweb-500/40 bg-cobweb-500/10 text-cobweb-300"
                          : "border-glass text-neutral-400 hover:border-glass-light hover:text-neutral-200"
                      }`}
                    >
                      <Download className="h-3 w-3 shrink-0" />
                      <span className="truncate font-mono">{r}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Replay controls */}
            {(selectedRecording || interactions.length > 0) && (
              <div>
                <label className="mb-1 block text-[11px] uppercase tracking-widest text-neutral-500">
                  Replay
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    value={replayPort}
                    onChange={(e) => setReplayPort(Number(e.target.value))}
                    className="w-20 shrink-0 rounded-md border border-glass bg-neutral-900/50 px-2 py-1 text-xs text-neutral-100 focus:outline-none"
                    placeholder="Port"
                  />
                  <label className="flex items-center gap-1.5 text-[11px] text-neutral-400">
                    <input
                      type="checkbox"
                      checked={fuzzyQuery}
                      onChange={(e) => setFuzzyQuery(e.target.checked)}
                      className="rounded border-glass accent-cobweb-500"
                    />
                    Fuzzy query
                  </label>
                  <button
                    type="button"
                    onClick={startReplay}
                    disabled={busy}
                    className="bg-accent-gradient inline-flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium text-white shadow-glow-sm transition disabled:opacity-40 disabled:shadow-none"
                  >
                    {busy ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <RefreshCw className="h-3.5 w-3.5" />
                    )}{" "}
                    Start Replay
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Recording active */}
        {state === "recording" && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-[11px] text-neutral-400">
                Proxying to <span className="font-mono text-cobweb-400">{targetUrl}</span> on port{" "}
                <span className="font-mono text-cobweb-400">{recordPort}</span>
              </p>
              <button
                type="button"
                onClick={stopRecording}
                disabled={busy}
                className="inline-flex items-center gap-1.5 rounded-md border border-rose-800/40 bg-rose-950/20 px-3 py-1 text-xs font-medium text-rose-400 transition hover:bg-rose-950/40 disabled:opacity-40"
              >
                {busy ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Square className="h-3.5 w-3.5" />
                )}{" "}
                Stop Recording
              </button>
            </div>
            <InteractionsTable interactions={interactions} />
          </div>
        )}

        {/* Replaying active */}
        {state === "replaying" && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-[11px] text-neutral-400">
                Replay server on port{" "}
                <span className="font-mono text-cobweb-400">{replayStatus?.port}</span> with{" "}
                {replayStatus?.route_count} routes
              </p>
              <button
                type="button"
                onClick={stopReplay}
                disabled={busy}
                className="inline-flex items-center gap-1.5 rounded-md border border-rose-800/40 bg-rose-950/20 px-3 py-1 text-xs font-medium text-rose-400 transition hover:bg-rose-950/40 disabled:opacity-40"
              >
                {busy ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Square className="h-3.5 w-3.5" />
                )}{" "}
                Stop Replay
              </button>
            </div>
            {interactions.length > 0 && <InteractionsTable interactions={interactions} />}
          </div>
        )}

        {/* Interactions table for idle state with selected recording */}
        {state === "idle" && interactions.length > 0 && (
          <div className="mt-4">
            <p className="mb-2 text-[10px] uppercase tracking-widest text-neutral-500">
              Interactions ({interactions.length})
            </p>
            <InteractionsTable interactions={interactions} />
          </div>
        )}
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ */
/* Status pill                                                         */
/* ------------------------------------------------------------------ */

function StatusPill({ state }: { state: RecordState }) {
  if (state === "recording") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-rose-800/30 bg-rose-950/20 px-2.5 py-0.5 text-[11px] font-medium text-rose-400">
        <Circle className="h-2 w-2 animate-pulse fill-rose-400 text-rose-400" />
        Recording
      </span>
    );
  }
  if (state === "replaying") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-800/30 bg-emerald-950/20 px-2.5 py-0.5 text-[11px] font-medium text-emerald-400">
        <RefreshCw className="h-2.5 w-2.5 animate-spin" />
        Replaying
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-glass px-2.5 py-0.5 text-[11px] font-medium text-neutral-500">
      <Circle className="h-2 w-2 fill-neutral-600 text-neutral-600" />
      Idle
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* Interactions table                                                   */
/* ------------------------------------------------------------------ */

const METHOD_COLORS: Record<string, string> = {
  GET: "text-emerald-400",
  POST: "text-amber-400",
  PUT: "text-blue-400",
  PATCH: "text-violet-400",
  DELETE: "text-rose-400",
};

function InteractionsTable({ interactions }: { interactions: RecordedInteraction[] }) {
  if (interactions.length === 0) {
    return (
      <p className="py-6 text-center text-xs text-neutral-600">
        No interactions yet. Send requests through the proxy to record them.
      </p>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-glass">
      <table className="w-full text-left text-xs">
        <thead>
          <tr className="border-b border-glass bg-neutral-900/40">
            <th className="px-3 py-1.5 text-[10px] font-medium uppercase tracking-widest text-neutral-500">
              Method
            </th>
            <th className="px-3 py-1.5 text-[10px] font-medium uppercase tracking-widest text-neutral-500">
              Path
            </th>
            <th className="px-3 py-1.5 text-[10px] font-medium uppercase tracking-widest text-neutral-500">
              Status
            </th>
            <th className="px-3 py-1.5 text-right text-[10px] font-medium uppercase tracking-widest text-neutral-500">
              Time
            </th>
          </tr>
        </thead>
        <tbody>
          {interactions.map((ix, i) => (
            <tr
              key={i}
              className="border-b border-glass/50 last:border-b-0 hover:bg-white/[0.02]"
            >
              <td className="px-3 py-1.5">
                <span
                  className={`font-mono font-medium ${METHOD_COLORS[ix.method] ?? "text-neutral-300"}`}
                >
                  {ix.method}
                </span>
              </td>
              <td className="max-w-[300px] truncate px-3 py-1.5 font-mono text-neutral-300">
                {ix.path}
                {ix.query ? (
                  <span className="text-neutral-600">?{ix.query}</span>
                ) : null}
              </td>
              <td className="px-3 py-1.5">
                <span
                  className={`font-mono ${
                    ix.status < 300
                      ? "text-emerald-400"
                      : ix.status < 400
                        ? "text-amber-400"
                        : "text-rose-400"
                  }`}
                >
                  {ix.status}
                </span>
              </td>
              <td className="px-3 py-1.5 text-right font-mono text-neutral-500">
                {ix.elapsed_ms.toFixed(0)}ms
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
