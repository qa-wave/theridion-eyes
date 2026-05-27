import { useEffect, useRef, useState, useCallback } from "react";
import {
  Activity,
  ArrowDown,
  ArrowUp,
  Binary,
  BookTemplate,
  ChevronDown,
  ChevronRight,
  FileUp,
  Loader2,
  Plug,
  PlugZap,
  RefreshCw,
  Save,
  Send,
  Settings2,
  Trash2,
  Type,
  Wifi,
  X,
} from "lucide-react";
import { getSidecarBaseUrl } from "../lib/sidecar";
import type {
  WsAdvancedMetrics,
  WsFrameEntry,
} from "../lib/sidecar/protocols";
import { protocolsMethods } from "../lib/sidecar/protocols";

const BUILT_IN_TEMPLATES: Array<{ label: string; value: string }> = [
  { label: "JSON message", value: '{"type": "ping"}' },
  { label: "Subscribe", value: '{"action": "subscribe", "channel": "events"}' },
  { label: "Unsubscribe", value: '{"action": "unsubscribe", "channel": "events"}' },
  { label: "Auth", value: '{"type": "auth", "token": "{{token}}"}' },
];

const WS_TEMPLATES_KEY = "theridion.ws-templates";
const WS_HISTORY_KEY = "theridion.ws-message-history";

function loadCustomTemplates(): Array<{ label: string; value: string }> {
  try {
    return JSON.parse(localStorage.getItem(WS_TEMPLATES_KEY) ?? "[]");
  } catch {
    return [];
  }
}

function saveCustomTemplates(templates: Array<{ label: string; value: string }>) {
  localStorage.setItem(WS_TEMPLATES_KEY, JSON.stringify(templates));
}

function loadMessageHistory(): string[] {
  try {
    return JSON.parse(localStorage.getItem(WS_HISTORY_KEY) ?? "[]");
  } catch {
    return [];
  }
}

function pushMessageHistory(msg: string) {
  const history = loadMessageHistory().filter((m) => m !== msg);
  history.unshift(msg);
  localStorage.setItem(WS_HISTORY_KEY, JSON.stringify(history.slice(0, 10)));
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
}

interface WsMessage {
  direction: "sent" | "received";
  data: string;
  timestamp: number;
  frameType?: "text" | "binary" | "ping" | "pong" | "close";
}

interface Props {
  open: boolean;
  onClose: () => void;
}

type SendMode = "text" | "binary";
type ViewTab = "messages" | "frames" | "metrics";

export function WebSocketModal({ open, onClose }: Props) {
  const [url, setUrl] = useState("");
  const [headers, setHeaders] = useState("");
  const [status, setStatus] = useState<"disconnected" | "connecting" | "connected" | "reconnecting">("disconnected");
  const [messages, setMessages] = useState<WsMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  // Advanced connection settings
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [autoReconnect, setAutoReconnect] = useState(false);
  const [reconnectInterval, setReconnectInterval] = useState(3000);
  const [maxReconnects, setMaxReconnects] = useState(5);
  const [pingInterval, setPingInterval] = useState<number | null>(null);
  const [subprotocols, setSubprotocols] = useState("");

  // Send mode: text or binary
  const [sendMode, setSendMode] = useState<SendMode>("text");
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Advanced connection (REST-based)
  const [advancedConnectionId, setAdvancedConnectionId] = useState<string | null>(null);

  // Metrics & frames
  const [viewTab, setViewTab] = useState<ViewTab>("messages");
  const [metrics, setMetrics] = useState<WsAdvancedMetrics | null>(null);
  const [frameLog, setFrameLog] = useState<WsFrameEntry[]>([]);
  const metricsIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [messages, frameLog]);

  // Poll metrics when connected via advanced mode.
  useEffect(() => {
    if (advancedConnectionId && status === "connected") {
      const poll = async () => {
        try {
          const m = await protocolsMethods.wsAdvancedMetrics(advancedConnectionId);
          setMetrics(m);
          if (m.status === "reconnecting") setStatus("reconnecting");
          else if (m.status === "disconnected") {
            setStatus("disconnected");
            setAdvancedConnectionId(null);
          }
          const f = await protocolsMethods.wsAdvancedFrames(advancedConnectionId);
          setFrameLog(f);
        } catch {
          // Connection may have been cleaned up.
        }
      };
      void poll();
      metricsIntervalRef.current = setInterval(poll, 2000);
      return () => {
        if (metricsIntervalRef.current) clearInterval(metricsIntervalRef.current);
      };
    }
    return () => {
      if (metricsIntervalRef.current) clearInterval(metricsIntervalRef.current);
    };
  }, [advancedConnectionId, status]);

  // Cleanup on close.
  useEffect(() => {
    if (!open) {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      if (advancedConnectionId) {
        void protocolsMethods.wsAdvancedDisconnect(advancedConnectionId).catch(() => {});
        setAdvancedConnectionId(null);
      }
      setStatus("disconnected");
    }
  }, [open]);

  if (!open) return null;

  function parseHeaders(): Record<string, string> {
    const out: Record<string, string> = {};
    for (const line of headers.split("\n")) {
      const idx = line.indexOf(":");
      if (idx > 0) out[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
    }
    return out;
  }

  const useAdvancedMode = autoReconnect || pingInterval !== null || subprotocols.trim().length > 0;

  async function connect() {
    if (!url.trim()) return;
    setError(null);
    setStatus("connecting");

    if (useAdvancedMode) {
      // Use the REST-based advanced WebSocket API.
      try {
        const result = await protocolsMethods.wsAdvancedConnect({
          url: url.trim(),
          headers: parseHeaders(),
          subprotocols: subprotocols.trim() ? subprotocols.split(",").map((s) => s.trim()) : [],
          auto_reconnect: autoReconnect,
          reconnect_interval_ms: reconnectInterval,
          max_reconnects: maxReconnects,
          ping_interval_ms: pingInterval,
        });
        if (result.status === "connected") {
          setStatus("connected");
          setAdvancedConnectionId(result.connection_id);
        } else {
          setError(result.error ?? "Connection failed");
          setStatus("disconnected");
        }
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : String(e));
        setStatus("disconnected");
      }
      return;
    }

    // Basic mode: use WebSocket proxy.
    const baseUrl = await getSidecarBaseUrl();
    const wsUrl = baseUrl.replace(/^http/, "ws") + "/api/ws/proxy";

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        ws.send(JSON.stringify({ url: url.trim(), headers: parseHeaders() }));
      };

      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.type === "connected") {
          setStatus("connected");
        } else if (msg.type === "message") {
          setMessages((prev) => [...prev, {
            direction: "received",
            data: msg.data,
            timestamp: msg.timestamp,
            frameType: "text",
          }]);
        } else if (msg.type === "disconnected") {
          setStatus("disconnected");
          wsRef.current = null;
        } else if (msg.type === "error") {
          setError(msg.message);
          setStatus("disconnected");
          wsRef.current = null;
        }
      };

      ws.onerror = () => {
        setError("Connection failed");
        setStatus("disconnected");
        wsRef.current = null;
      };

      ws.onclose = () => {
        setStatus("disconnected");
        wsRef.current = null;
      };
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setStatus("disconnected");
    }
  }

  function disconnect() {
    if (advancedConnectionId) {
      void protocolsMethods.wsAdvancedDisconnect(advancedConnectionId).catch(() => {});
      setAdvancedConnectionId(null);
    }
    if (wsRef.current) {
      wsRef.current.send(JSON.stringify({ type: "close" }));
      wsRef.current.close();
      wsRef.current = null;
    }
    setStatus("disconnected");
  }

  const [templateOpen, setTemplateOpen] = useState(false);
  const [customTemplates, setCustomTemplates] = useState(loadCustomTemplates);
  const [historyIndex, setHistoryIndex] = useState(-1);
  const messageHistoryRef = useRef(loadMessageHistory());

  async function sendMessage() {
    if (!draft.trim() || (status !== "connected")) return;

    if (advancedConnectionId) {
      if (sendMode === "binary") {
        // Treat draft as base64.
        try {
          await protocolsMethods.wsAdvancedSendBinary(advancedConnectionId, draft);
          setMessages((prev) => [...prev, { direction: "sent", data: `[binary] ${draft.slice(0, 50)}...`, timestamp: Date.now(), frameType: "binary" }]);
        } catch (e: unknown) {
          setError(e instanceof Error ? e.message : "Send failed");
        }
      } else {
        try {
          await protocolsMethods.wsAdvancedSendText(advancedConnectionId, draft);
          setMessages((prev) => [...prev, { direction: "sent", data: draft, timestamp: Date.now(), frameType: "text" }]);
        } catch (e: unknown) {
          setError(e instanceof Error ? e.message : "Send failed");
        }
      }
    } else if (wsRef.current) {
      wsRef.current.send(JSON.stringify({ type: "send", data: draft }));
      setMessages((prev) => [...prev, { direction: "sent", data: draft, timestamp: Date.now(), frameType: "text" }]);
    }

    pushMessageHistory(draft);
    messageHistoryRef.current = loadMessageHistory();
    setHistoryIndex(-1);
    setDraft("");
  }

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const buffer = await file.arrayBuffer();
    const base64 = btoa(String.fromCharCode(...new Uint8Array(buffer)));
    setDraft(base64);
    setSendMode("binary");
  }

  function applyTemplate(value: string) {
    setDraft(value);
    setTemplateOpen(false);
  }

  function saveAsTemplate() {
    if (!draft.trim()) return;
    const label = prompt("Template name:");
    if (!label) return;
    const updated = [...customTemplates, { label, value: draft }];
    setCustomTemplates(updated);
    saveCustomTemplates(updated);
  }

  function deleteCustomTemplate(index: number) {
    const updated = customTemplates.filter((_, i) => i !== index);
    setCustomTemplates(updated);
    saveCustomTemplates(updated);
  }

  const handleInputKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      void sendMessage();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      const history = messageHistoryRef.current;
      if (history.length > 0) {
        const newIndex = Math.min(historyIndex + 1, history.length - 1);
        setHistoryIndex(newIndex);
        setDraft(history[newIndex]);
      }
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      const history = messageHistoryRef.current;
      if (historyIndex > 0) {
        const newIndex = historyIndex - 1;
        setHistoryIndex(newIndex);
        setDraft(history[newIndex]);
      } else if (historyIndex === 0) {
        setHistoryIndex(-1);
        setDraft("");
      }
    }
  }, [historyIndex, status, advancedConnectionId, sendMode, draft]);

  const statusIndicator = () => {
    if (status === "connected") {
      return <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/20 px-2 py-0.5 text-[10px] font-bold text-emerald-400">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
        CONNECTED
      </span>;
    }
    if (status === "reconnecting") {
      return <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] font-bold text-amber-400">
        <span className="h-1.5 w-1.5 animate-[pulse_0.5s_ease-in-out_infinite] rounded-full bg-amber-400" />
        RECONNECTING
      </span>;
    }
    if (status === "connecting") {
      return <span className="inline-flex items-center gap-1.5 rounded-full bg-cobweb-500/20 px-2 py-0.5 text-[10px] font-bold text-cobweb-400">
        <Loader2 className="h-3 w-3 animate-spin" />
        CONNECTING
      </span>;
    }
    return <span className="rounded-full bg-neutral-800 px-2 py-0.5 text-[10px] font-bold text-neutral-500">
      DISCONNECTED
    </span>;
  };

  const frameTypeBadge = (type: string) => {
    const colors: Record<string, string> = {
      text: "bg-blue-500/20 text-blue-400",
      binary: "bg-purple-500/20 text-purple-400",
      ping: "bg-neutral-700/40 text-neutral-400",
      pong: "bg-neutral-700/40 text-neutral-400",
      close: "bg-rose-500/20 text-rose-400",
    };
    return (
      <span className={`rounded px-1.5 py-0.5 text-[9px] font-bold uppercase ${colors[type] ?? "bg-neutral-800 text-neutral-500"}`}>
        {type}
      </span>
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="glass flex h-[680px] w-[900px] max-h-[90vh] max-w-[95vw] animate-slide-in flex-col overflow-hidden rounded-xl border border-glass-light shadow-2xl shadow-black/60">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-100">
            <Wifi className="h-4 w-4 text-cobweb-400" />
            WebSocket
            {statusIndicator()}
          </div>
          <div className="flex items-center gap-1">
            {/* View tabs */}
            {(status === "connected" || advancedConnectionId) && (
              <div className="flex items-center gap-0.5 rounded-md border border-glass p-0.5 mr-2">
                {(["messages", "frames", "metrics"] as ViewTab[]).map((tab) => (
                  <button
                    key={tab}
                    type="button"
                    onClick={() => setViewTab(tab)}
                    className={`rounded px-2 py-0.5 text-[10px] font-medium transition ${
                      viewTab === tab
                        ? "bg-cobweb-600/20 text-cobweb-300"
                        : "text-neutral-500 hover:text-neutral-300"
                    }`}
                  >
                    {tab.charAt(0).toUpperCase() + tab.slice(1)}
                  </button>
                ))}
              </div>
            )}
            <button type="button" onClick={onClose} className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200">
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* URL bar */}
        <div className="flex items-center gap-2 border-b border-glass px-4 py-2.5">
          <span className="shrink-0 rounded bg-cobweb-600/20 px-2 py-0.5 text-[10px] font-bold text-cobweb-300">
            WS
          </span>
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="wss://echo.websocket.org"
            disabled={status === "connected" || status === "reconnecting"}
            className="flex-1 rounded-md border border-glass bg-neutral-900/50 px-3 py-1.5 font-mono text-xs text-neutral-100 placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none disabled:opacity-50"
            spellCheck={false}
            onKeyDown={(e) => { if (e.key === "Enter" && status === "disconnected") void connect(); }}
          />
          {status === "disconnected" ? (
            <button
              type="button"
              onClick={() => void connect()}
              disabled={!url.trim()}
              className="bg-accent-gradient inline-flex items-center gap-1.5 rounded-md px-4 py-1.5 text-xs font-medium text-white shadow-glow-sm transition disabled:opacity-40 disabled:shadow-none"
            >
              <Plug className="h-3.5 w-3.5" />
              Connect
            </button>
          ) : status === "connecting" ? (
            <button disabled className="inline-flex items-center gap-1.5 rounded-md border border-glass px-4 py-1.5 text-xs text-neutral-400">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Connecting
            </button>
          ) : (
            <button
              type="button"
              onClick={disconnect}
              className="inline-flex items-center gap-1.5 rounded-md border border-rose-800/40 bg-rose-950/20 px-4 py-1.5 text-xs text-rose-400 transition hover:bg-rose-950/40"
            >
              <PlugZap className="h-3.5 w-3.5" />
              Disconnect
            </button>
          )}
        </div>

        {/* Connection Settings (expandable) */}
        {status === "disconnected" && (
          <div className="border-b border-glass">
            {/* Headers */}
            <div className="px-4 py-2">
              <p className="mb-1 text-[10px] uppercase tracking-widest text-neutral-500">Headers</p>
              <textarea
                value={headers}
                onChange={(e) => setHeaders(e.target.value)}
                placeholder="Authorization: Bearer ..."
                rows={2}
                className="w-full rounded-md border border-glass bg-neutral-900/50 px-2 py-1 font-mono text-xs text-neutral-100 placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none"
                spellCheck={false}
              />
            </div>

            {/* Advanced settings toggle */}
            <div className="px-4 pb-2">
              <button
                type="button"
                onClick={() => setSettingsOpen(!settingsOpen)}
                className="inline-flex items-center gap-1.5 text-[11px] text-neutral-500 transition hover:text-neutral-300"
              >
                {settingsOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                <Settings2 className="h-3 w-3" />
                Connection Settings
              </button>

              {settingsOpen && (
                <div className="mt-2 grid grid-cols-2 gap-3 rounded-lg border border-glass bg-neutral-900/30 p-3">
                  {/* Auto-reconnect */}
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={autoReconnect}
                      onChange={(e) => setAutoReconnect(e.target.checked)}
                      className="h-3.5 w-3.5 rounded border-glass bg-neutral-800 text-cobweb-500 focus:ring-cobweb-500/30"
                    />
                    <span className="text-[11px] text-neutral-300">Auto-reconnect</span>
                  </label>

                  {/* Reconnect interval */}
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] text-neutral-500">Interval:</span>
                    <input
                      type="number"
                      value={reconnectInterval}
                      onChange={(e) => setReconnectInterval(Number(e.target.value))}
                      disabled={!autoReconnect}
                      className="w-20 rounded border border-glass bg-neutral-900/50 px-2 py-0.5 text-[11px] text-neutral-200 disabled:opacity-40"
                    />
                    <span className="text-[10px] text-neutral-600">ms</span>
                  </div>

                  {/* Max reconnects */}
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] text-neutral-500">Max retries:</span>
                    <input
                      type="number"
                      value={maxReconnects}
                      onChange={(e) => setMaxReconnects(Number(e.target.value))}
                      disabled={!autoReconnect}
                      className="w-16 rounded border border-glass bg-neutral-900/50 px-2 py-0.5 text-[11px] text-neutral-200 disabled:opacity-40"
                    />
                  </div>

                  {/* Ping interval */}
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] text-neutral-500">Ping every:</span>
                    <input
                      type="number"
                      value={pingInterval ?? ""}
                      onChange={(e) => setPingInterval(e.target.value ? Number(e.target.value) : null)}
                      placeholder="off"
                      className="w-20 rounded border border-glass bg-neutral-900/50 px-2 py-0.5 text-[11px] text-neutral-200 placeholder-neutral-600"
                    />
                    <span className="text-[10px] text-neutral-600">ms</span>
                  </div>

                  {/* Subprotocols */}
                  <div className="col-span-2 flex items-center gap-2">
                    <span className="text-[11px] text-neutral-500">Subprotocols:</span>
                    <input
                      value={subprotocols}
                      onChange={(e) => setSubprotocols(e.target.value)}
                      placeholder="graphql-ws, graphql-transport-ws"
                      className="flex-1 rounded border border-glass bg-neutral-900/50 px-2 py-0.5 font-mono text-[11px] text-neutral-200 placeholder-neutral-600"
                    />
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="border-b border-rose-800/30 bg-rose-950/20 px-4 py-2 text-xs text-rose-400">
            {error}
          </div>
        )}

        {/* Main content area */}
        <div ref={logRef} className="flex-1 overflow-y-auto p-2">
          {viewTab === "messages" && (
            <>
              {messages.length === 0 ? (
                <div className="flex h-full flex-col items-center justify-center text-xs text-neutral-600">
                  <Wifi className="mb-2 h-8 w-8 text-neutral-800" />
                  {status === "connected" ? "Waiting for messages..." : "Connect to start"}
                </div>
              ) : (
                <div className="space-y-1">
                  {messages.map((m, i) => (
                    <div
                      key={i}
                      className={`flex items-start gap-2 rounded-md px-3 py-2 text-xs ${
                        m.direction === "sent"
                          ? "bg-cobweb-950/20 border border-cobweb-800/20"
                          : "bg-neutral-900/40 border border-glass"
                      }`}
                    >
                      {m.direction === "sent" ? (
                        <ArrowUp className="mt-0.5 h-3 w-3 shrink-0 text-cobweb-400" />
                      ) : (
                        <ArrowDown className="mt-0.5 h-3 w-3 shrink-0 text-emerald-400" />
                      )}
                      {m.frameType && frameTypeBadge(m.frameType)}
                      <pre className="flex-1 whitespace-pre-wrap break-all font-mono text-neutral-200">
                        {m.data}
                      </pre>
                      <span className="shrink-0 text-[10px] text-neutral-600">
                        {new Date(m.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          {viewTab === "frames" && (
            <div className="space-y-0.5">
              {frameLog.length === 0 ? (
                <div className="flex h-full flex-col items-center justify-center text-xs text-neutral-600 py-12">
                  <Activity className="mb-2 h-6 w-6 text-neutral-800" />
                  No frames recorded yet
                </div>
              ) : (
                frameLog.map((f, i) => (
                  <div key={i} className="flex items-center gap-2 rounded px-3 py-1.5 text-[11px] border border-glass bg-neutral-900/30">
                    {f.direction === "sent" ? (
                      <ArrowUp className="h-3 w-3 shrink-0 text-cobweb-400" />
                    ) : (
                      <ArrowDown className="h-3 w-3 shrink-0 text-emerald-400" />
                    )}
                    {frameTypeBadge(f.frame_type)}
                    <span className="text-neutral-500">{f.size_bytes}B</span>
                    <span className="flex-1 truncate font-mono text-neutral-300">
                      {f.data_preview ?? ""}
                    </span>
                    <span className="shrink-0 text-[10px] text-neutral-600">
                      {new Date(f.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", fractionalSecondDigits: 3 } as Intl.DateTimeFormatOptions)}
                    </span>
                  </div>
                ))
              )}
            </div>
          )}

          {viewTab === "metrics" && (
            <div className="grid grid-cols-2 gap-3 p-2">
              {metrics ? (
                <>
                  <div className="rounded-lg border border-glass bg-neutral-900/50 p-3">
                    <p className="text-[10px] uppercase tracking-widest text-neutral-500 mb-1">Messages</p>
                    <div className="flex items-baseline gap-3">
                      <div>
                        <span className="text-lg font-bold text-cobweb-300">{metrics.messages_sent}</span>
                        <span className="ml-1 text-[10px] text-neutral-500">sent</span>
                      </div>
                      <div>
                        <span className="text-lg font-bold text-emerald-300">{metrics.messages_received}</span>
                        <span className="ml-1 text-[10px] text-neutral-500">recv</span>
                      </div>
                    </div>
                  </div>

                  <div className="rounded-lg border border-glass bg-neutral-900/50 p-3">
                    <p className="text-[10px] uppercase tracking-widest text-neutral-500 mb-1">Bytes Transferred</p>
                    <div className="flex items-baseline gap-3">
                      <div>
                        <span className="text-lg font-bold text-cobweb-300">{formatBytes(metrics.bytes_sent)}</span>
                        <span className="ml-1 text-[10px] text-neutral-500">up</span>
                      </div>
                      <div>
                        <span className="text-lg font-bold text-emerald-300">{formatBytes(metrics.bytes_received)}</span>
                        <span className="ml-1 text-[10px] text-neutral-500">down</span>
                      </div>
                    </div>
                  </div>

                  <div className="rounded-lg border border-glass bg-neutral-900/50 p-3">
                    <p className="text-[10px] uppercase tracking-widest text-neutral-500 mb-1">Duration</p>
                    <span className="text-lg font-bold text-neutral-200">{formatDuration(metrics.connection_duration_ms)}</span>
                  </div>

                  <div className="rounded-lg border border-glass bg-neutral-900/50 p-3">
                    <p className="text-[10px] uppercase tracking-widest text-neutral-500 mb-1">Reconnects</p>
                    <span className="text-lg font-bold text-neutral-200">{metrics.reconnect_count}</span>
                  </div>

                  <div className="col-span-2 rounded-lg border border-glass bg-neutral-900/50 p-3">
                    <p className="text-[10px] uppercase tracking-widest text-neutral-500 mb-1">Ping/Pong RTT</p>
                    <div className="flex items-baseline gap-4">
                      <div>
                        <span className="text-lg font-bold text-neutral-200">
                          {metrics.last_ping_rtt_ms !== null ? `${metrics.last_ping_rtt_ms.toFixed(1)}ms` : "--"}
                        </span>
                        <span className="ml-1 text-[10px] text-neutral-500">last</span>
                      </div>
                      <div>
                        <span className="text-lg font-bold text-neutral-200">
                          {metrics.avg_ping_rtt_ms !== null ? `${metrics.avg_ping_rtt_ms.toFixed(1)}ms` : "--"}
                        </span>
                        <span className="ml-1 text-[10px] text-neutral-500">avg</span>
                      </div>
                    </div>
                  </div>
                </>
              ) : (
                <div className="col-span-2 flex flex-col items-center justify-center py-12 text-xs text-neutral-600">
                  <RefreshCw className="mb-2 h-6 w-6 text-neutral-800" />
                  {advancedConnectionId ? "Loading metrics..." : "Metrics available in advanced mode (enable auto-reconnect, ping, or subprotocols)"}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Send bar */}
        {(status === "connected" || status === "reconnecting") && (
          <div className="border-t border-glass">
            {/* Mode toggle + file upload */}
            <div className="flex items-center gap-2 border-b border-glass px-4 py-1.5">
              <div className="flex items-center gap-0.5 rounded border border-glass p-0.5">
                <button
                  type="button"
                  onClick={() => setSendMode("text")}
                  className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-medium transition ${
                    sendMode === "text" ? "bg-cobweb-600/20 text-cobweb-300" : "text-neutral-500 hover:text-neutral-300"
                  }`}
                >
                  <Type className="h-3 w-3" />
                  Text
                </button>
                <button
                  type="button"
                  onClick={() => setSendMode("binary")}
                  className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-medium transition ${
                    sendMode === "binary" ? "bg-purple-600/20 text-purple-300" : "text-neutral-500 hover:text-neutral-300"
                  }`}
                >
                  <Binary className="h-3 w-3" />
                  Binary
                </button>
              </div>
              {sendMode === "binary" && (
                <>
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="inline-flex items-center gap-1 rounded-md border border-glass px-2 py-0.5 text-[10px] text-neutral-400 transition hover:bg-white/[0.04] hover:text-neutral-200"
                  >
                    <FileUp className="h-3 w-3" />
                    Upload file
                  </button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    onChange={(e) => void handleFileUpload(e)}
                    className="hidden"
                  />
                  <span className="text-[10px] text-neutral-600">Paste or upload base64 payload</span>
                </>
              )}
            </div>

            <div className="flex items-center gap-2 px-4 py-2.5">
              {/* Templates dropdown */}
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setTemplateOpen(!templateOpen)}
                  className="inline-flex items-center gap-1 rounded-md border border-glass px-2 py-1.5 text-xs text-neutral-400 transition hover:bg-white/[0.04] hover:text-neutral-200"
                  title="Message templates"
                >
                  <BookTemplate className="h-3.5 w-3.5" />
                  <ChevronDown className="h-3 w-3" />
                </button>
                {templateOpen && (
                  <div className="absolute bottom-full left-0 mb-1 w-64 rounded-lg border border-glass bg-neutral-900 shadow-xl z-10">
                    <div className="border-b border-glass px-3 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-neutral-500">
                      Built-in
                    </div>
                    {BUILT_IN_TEMPLATES.map((t, i) => (
                      <button
                        key={`builtin-${i}`}
                        type="button"
                        onClick={() => applyTemplate(t.value)}
                        className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-neutral-300 hover:bg-white/[0.04]"
                      >
                        <span className="truncate">{t.label}</span>
                        <code className="ml-auto truncate text-[10px] text-neutral-600 max-w-[120px]">{t.value}</code>
                      </button>
                    ))}
                    {customTemplates.length > 0 && (
                      <>
                        <div className="border-t border-glass px-3 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-neutral-500">
                          Saved
                        </div>
                        {customTemplates.map((t, i) => (
                          <div key={`custom-${i}`} className="group flex items-center hover:bg-white/[0.04]">
                            <button
                              type="button"
                              onClick={() => applyTemplate(t.value)}
                              className="flex flex-1 items-center gap-2 px-3 py-1.5 text-xs text-neutral-300"
                            >
                              <span className="truncate">{t.label}</span>
                            </button>
                            <button
                              type="button"
                              onClick={() => deleteCustomTemplate(i)}
                              className="mr-2 rounded p-0.5 text-neutral-600 opacity-0 group-hover:opacity-100 hover:text-rose-400"
                            >
                              <Trash2 className="h-3 w-3" />
                            </button>
                          </div>
                        ))}
                      </>
                    )}
                  </div>
                )}
              </div>

              <input
                value={draft}
                onChange={(e) => { setDraft(e.target.value); setHistoryIndex(-1); }}
                placeholder={sendMode === "binary" ? "Base64 encoded payload..." : "Type a message... (Up arrow for history)"}
                className="flex-1 rounded-md border border-glass bg-neutral-900/50 px-3 py-1.5 font-mono text-xs text-neutral-100 placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none"
                spellCheck={false}
                onKeyDown={handleInputKeyDown}
                autoFocus
              />
              <button
                type="button"
                onClick={saveAsTemplate}
                disabled={!draft.trim()}
                className="rounded-md p-1.5 text-neutral-500 transition hover:bg-white/[0.05] hover:text-cobweb-300 disabled:opacity-30"
                title="Save as template"
              >
                <Save className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={() => void sendMessage()}
                disabled={!draft.trim()}
                className="bg-accent-gradient inline-flex items-center gap-1.5 rounded-md px-4 py-1.5 text-xs font-medium text-white shadow-glow-sm transition disabled:opacity-40 disabled:shadow-none"
              >
                <Send className="h-3.5 w-3.5" />
                Send
              </button>
              <button
                type="button"
                onClick={() => setMessages([])}
                className="rounded-md p-1.5 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-300"
                title="Clear messages"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
