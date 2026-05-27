import { useState } from "react";
import { Bot, Loader2, X, AlertTriangle, AlertCircle, Info, ExternalLink, ChevronDown, ChevronRight } from "lucide-react";
import { sidecar, type ExploreApiResult } from "../lib/sidecar";

interface Props {
  open: boolean;
  onClose: () => void;
  onCollectionCreated?: () => void;
}

const HTTP_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"] as const;

const SEVERITY_STYLES: Record<string, { bg: string; text: string; icon: typeof AlertCircle }> = {
  error: { bg: "bg-red-500/10", text: "text-red-400", icon: AlertCircle },
  warning: { bg: "bg-amber-500/10", text: "text-amber-400", icon: AlertTriangle },
  info: { bg: "bg-blue-500/10", text: "text-blue-400", icon: Info },
};

function statusColor(status: number | null): string {
  if (status === null) return "text-neutral-500";
  if (status < 300) return "text-emerald-400";
  if (status < 400) return "text-amber-400";
  return "text-red-400";
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function AgentExplorerModal({ open, onClose, onCollectionCreated }: Props) {
  const [baseUrl, setBaseUrl] = useState("");
  const [maxRequests, setMaxRequests] = useState(20);
  const [methods, setMethods] = useState<Set<string>>(new Set(HTTP_METHODS));
  const [headersText, setHeadersText] = useState("");
  const [saveAsCollection, setSaveAsCollection] = useState(true);
  const [collectionName, setCollectionName] = useState("");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ExploreApiResult | null>(null);
  const [expandedEndpoint, setExpandedEndpoint] = useState<string | null>(null);

  if (!open) return null;

  function toggleMethod(m: string) {
    setMethods((prev) => {
      const next = new Set(prev);
      if (next.has(m)) {
        if (next.size > 1) next.delete(m);
      } else {
        next.add(m);
      }
      return next;
    });
  }

  function parseHeaders(): Record<string, string> {
    const h: Record<string, string> = {};
    for (const line of headersText.split("\n")) {
      const idx = line.indexOf(":");
      if (idx > 0) {
        h[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
      }
    }
    return h;
  }

  async function explore() {
    if (!baseUrl.trim()) return;
    setBusy(true);
    setError(null);
    setResult(null);
    setExpandedEndpoint(null);
    try {
      const res = await sidecar.exploreApi({
        base_url: baseUrl.trim(),
        max_requests: maxRequests,
        methods: [...methods],
        headers: parseHeaders(),
        save_as_collection: saveAsCollection,
        collection_name: collectionName.trim() || undefined,
      });
      setResult(res);
      if (res.collection_id && onCollectionCreated) {
        onCollectionCreated();
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const inputClass =
    "w-full rounded-md border border-neutral-800 bg-neutral-900/50 px-3 py-1.5 text-xs text-neutral-100 focus:border-emerald-500/40 focus:outline-none";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/60" />
      <div
        className="relative flex max-h-[85vh] w-full max-w-2xl flex-col rounded-lg border border-neutral-800 bg-neutral-950 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-neutral-800 px-5 py-3">
          <div className="flex items-center gap-2">
            <Bot className="h-4 w-4 text-emerald-400" />
            <h2 className="text-sm font-semibold text-neutral-100">API Explorer</h2>
          </div>
          <button onClick={onClose} className="text-neutral-500 hover:text-neutral-300">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-5">
          {!result ? (
            <div className="space-y-4">
              {/* URL input */}
              <div>
                <label className="mb-1 block text-xs font-medium text-neutral-400">Base URL</label>
                <input
                  type="text"
                  className={inputClass}
                  placeholder="http://localhost:4010"
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && explore()}
                />
              </div>

              {/* Max requests slider */}
              <div>
                <label className="mb-1 block text-xs font-medium text-neutral-400">
                  Max requests: {maxRequests}
                </label>
                <input
                  type="range"
                  min={5}
                  max={50}
                  value={maxRequests}
                  onChange={(e) => setMaxRequests(Number(e.target.value))}
                  className="w-full accent-emerald-500"
                />
              </div>

              {/* Methods */}
              <div>
                <label className="mb-1 block text-xs font-medium text-neutral-400">Methods</label>
                <div className="flex gap-2">
                  {HTTP_METHODS.map((m) => (
                    <button
                      key={m}
                      type="button"
                      onClick={() => toggleMethod(m)}
                      className={`rounded px-2.5 py-1 text-[11px] font-medium transition ${
                        methods.has(m)
                          ? "bg-emerald-500/20 text-emerald-400"
                          : "bg-neutral-800/50 text-neutral-500"
                      }`}
                    >
                      {m}
                    </button>
                  ))}
                </div>
              </div>

              {/* Headers */}
              <div>
                <label className="mb-1 block text-xs font-medium text-neutral-400">
                  Headers <span className="text-neutral-600">(optional, one per line: Key: Value)</span>
                </label>
                <textarea
                  className={`${inputClass} h-16 resize-none font-mono`}
                  placeholder={"Authorization: Bearer xxx\nX-Custom: value"}
                  value={headersText}
                  onChange={(e) => setHeadersText(e.target.value)}
                />
              </div>

              {/* Save as collection */}
              <div className="flex items-center gap-4">
                <label className="flex items-center gap-2 text-xs text-neutral-400">
                  <input
                    type="checkbox"
                    checked={saveAsCollection}
                    onChange={(e) => setSaveAsCollection(e.target.checked)}
                    className="accent-emerald-500"
                  />
                  Save as collection
                </label>
                {saveAsCollection && (
                  <input
                    type="text"
                    className={`${inputClass} max-w-[200px]`}
                    placeholder="Collection name (auto)"
                    value={collectionName}
                    onChange={(e) => setCollectionName(e.target.value)}
                  />
                )}
              </div>

              {error && (
                <div className="rounded-md border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">
                  {error}
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-4">
              {/* Summary stats */}
              <div className="grid grid-cols-3 gap-3">
                <div className="rounded-md border border-neutral-800 bg-neutral-900/50 p-3 text-center">
                  <div className="text-lg font-bold text-emerald-400">{result.endpoints_discovered}</div>
                  <div className="text-[10px] text-neutral-500">Endpoints</div>
                </div>
                <div className="rounded-md border border-neutral-800 bg-neutral-900/50 p-3 text-center">
                  <div className="text-lg font-bold text-blue-400">{result.requests_sent}</div>
                  <div className="text-[10px] text-neutral-500">Requests</div>
                </div>
                <div className="rounded-md border border-neutral-800 bg-neutral-900/50 p-3 text-center">
                  <div className="text-lg font-bold text-amber-400">{result.issues.length}</div>
                  <div className="text-[10px] text-neutral-500">Issues</div>
                </div>
              </div>

              <div className="text-[10px] text-neutral-600">Completed in {result.elapsed_ms.toFixed(0)}ms</div>

              {/* Issues */}
              {result.issues.length > 0 && (
                <div>
                  <h3 className="mb-2 text-xs font-medium text-neutral-300">Issues</h3>
                  <div className="space-y-1">
                    {result.issues.map((issue: { severity: string; message: string; endpoint: string }, i: number) => {
                      const style = SEVERITY_STYLES[issue.severity] || SEVERITY_STYLES.info;
                      const Icon = style.icon;
                      return (
                        <div
                          key={i}
                          className={`flex items-center gap-2 rounded px-2.5 py-1.5 ${style.bg}`}
                        >
                          <Icon className={`h-3 w-3 flex-shrink-0 ${style.text}`} />
                          <span className={`text-xs ${style.text}`}>{issue.message}</span>
                          <span className="ml-auto text-[10px] text-neutral-600">{issue.endpoint}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Endpoints table */}
              {result.endpoints.length > 0 && (
                <div>
                  <h3 className="mb-2 text-xs font-medium text-neutral-300">Endpoints</h3>
                  <div className="rounded-md border border-neutral-800">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b border-neutral-800 text-neutral-500">
                          <th className="px-2 py-1.5 text-left font-medium">Method</th>
                          <th className="px-2 py-1.5 text-left font-medium">Path</th>
                          <th className="px-2 py-1.5 text-right font-medium">Status</th>
                          <th className="px-2 py-1.5 text-right font-medium">Time</th>
                          <th className="px-2 py-1.5 text-right font-medium">Size</th>
                          <th className="px-2 py-1.5 text-right font-medium">Issues</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.endpoints.map((ep: { method: string; path: string; status: number | null; elapsed_ms: number; size_bytes: number; issues: string[]; body_preview: string }) => {
                          const key = `${ep.method}-${ep.path}`;
                          const isExpanded = expandedEndpoint === key;
                          return (
                            <>
                              <tr
                                key={key}
                                className="cursor-pointer border-b border-neutral-800/50 hover:bg-neutral-900/50"
                                onClick={() => setExpandedEndpoint(isExpanded ? null : key)}
                              >
                                <td className="px-2 py-1.5">
                                  <div className="flex items-center gap-1">
                                    {isExpanded ? (
                                      <ChevronDown className="h-3 w-3 text-neutral-600" />
                                    ) : (
                                      <ChevronRight className="h-3 w-3 text-neutral-600" />
                                    )}
                                    <span className="font-mono font-medium text-emerald-400">{ep.method}</span>
                                  </div>
                                </td>
                                <td className="px-2 py-1.5 font-mono text-neutral-300">{ep.path}</td>
                                <td className={`px-2 py-1.5 text-right font-mono ${statusColor(ep.status)}`}>
                                  {ep.status ?? "--"}
                                </td>
                                <td className="px-2 py-1.5 text-right text-neutral-400">
                                  {ep.elapsed_ms.toFixed(0)}ms
                                </td>
                                <td className="px-2 py-1.5 text-right text-neutral-400">
                                  {formatBytes(ep.size_bytes)}
                                </td>
                                <td className="px-2 py-1.5 text-right">
                                  {ep.issues.length > 0 && (
                                    <span className="rounded bg-red-500/10 px-1.5 py-0.5 text-[10px] text-red-400">
                                      {ep.issues.length}
                                    </span>
                                  )}
                                </td>
                              </tr>
                              {isExpanded && (
                                <tr key={`${key}-detail`}>
                                  <td colSpan={6} className="border-b border-neutral-800/50 bg-neutral-900/30 px-4 py-2">
                                    <div className="text-[10px] text-neutral-500">Response preview:</div>
                                    <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap rounded bg-neutral-950 p-2 font-mono text-[11px] text-neutral-400">
                                      {ep.body_preview || "(empty)"}
                                    </pre>
                                    {ep.issues.length > 0 && (
                                      <div className="mt-2">
                                        <div className="text-[10px] text-neutral-500">Issues:</div>
                                        <ul className="mt-0.5 list-inside list-disc text-[11px] text-amber-400">
                                          {ep.issues.map((iss: string, j: number) => (
                                            <li key={j}>{iss}</li>
                                          ))}
                                        </ul>
                                      </div>
                                    )}
                                  </td>
                                </tr>
                              )}
                            </>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Collection link */}
              {result.collection_id && (
                <div className="flex items-center gap-2 rounded-md border border-emerald-500/20 bg-emerald-500/10 px-3 py-2">
                  <ExternalLink className="h-3 w-3 text-emerald-400" />
                  <span className="text-xs text-emerald-400">
                    Collection created. Close this dialog to see it in the sidebar.
                  </span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 border-t border-neutral-800 px-5 py-3">
          {result ? (
            <>
              <button
                onClick={() => setResult(null)}
                className="rounded-md border border-neutral-700 px-3 py-1.5 text-xs text-neutral-400 transition hover:bg-neutral-800"
              >
                New Exploration
              </button>
              <button
                onClick={onClose}
                className="rounded-md bg-emerald-600 px-4 py-1.5 text-xs font-medium text-white transition hover:bg-emerald-500"
              >
                Done
              </button>
            </>
          ) : (
            <>
              <button
                onClick={onClose}
                className="rounded-md border border-neutral-700 px-3 py-1.5 text-xs text-neutral-400 transition hover:bg-neutral-800"
              >
                Cancel
              </button>
              <button
                onClick={explore}
                disabled={busy || !baseUrl.trim()}
                className="flex items-center gap-1.5 rounded-md bg-emerald-600 px-4 py-1.5 text-xs font-medium text-white transition hover:bg-emerald-500 disabled:opacity-50"
              >
                {busy ? (
                  <>
                    <Loader2 className="h-3 w-3 animate-spin" />
                    Exploring...
                  </>
                ) : (
                  <>
                    <Bot className="h-3 w-3" />
                    Explore
                  </>
                )}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
