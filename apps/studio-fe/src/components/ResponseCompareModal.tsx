import { useEffect, useRef, useState } from "react";
import { GitCompare, X } from "lucide-react";
import { DiffEditor } from "@monaco-editor/react";
import { sidecar } from "../lib/sidecar";
import type { ExecuteResponse, ResponseChangeEntry } from "../lib/sidecar";
import { useFocusTrap } from "../hooks/useFocusTrap";

interface Props {
  open: boolean;
  onClose: () => void;
  left: ExecuteResponse;
  right: ExecuteResponse;
}

export function ResponseCompareModal({ open, onClose, left, right }: Props) {
  const trapRef = useRef<HTMLDivElement>(null);
  useFocusTrap(trapRef, open);

  const [changes, setChanges] = useState<ResponseChangeEntry[]>([]);
  const [summary, setSummary] = useState("");
  const [loading, setLoading] = useState(false);
  const [view, setView] = useState<"diff" | "changes">("diff");

  const leftBody = prettifyBody(left.body);
  const rightBody = prettifyBody(right.body);

  // Fetch structured diff from backend for the changes list.
  useEffect(() => {
    if (!open) return;
    setLoading(true);
    const format = looksLikeJson(left.body) && looksLikeJson(right.body) ? "json" : "text";
    sidecar
      .compareResponses({ left: left.body, right: right.body, format })
      .then((r) => {
        setChanges(r.changes);
        setSummary(r.summary);
      })
      .catch(() => {
        setSummary("Could not compute diff");
        setChanges([]);
      })
      .finally(() => setLoading(false));
  }, [open, left.body, right.body]);

  if (!open) return null;

  const added = changes.filter((c) => c.type === "added").length;
  const removed = changes.filter((c) => c.type === "removed").length;
  const changed = changes.filter((c) => c.type === "changed").length;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div
        ref={trapRef}
        className="glass flex h-[80vh] w-[90vw] max-h-[800px] max-w-[1200px] animate-slide-in flex-col overflow-hidden rounded-xl border border-glass-light shadow-2xl shadow-black/60"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-100">
            <GitCompare className="h-4 w-4 text-cobweb-400" />
            Response Comparison
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Summary bar */}
        <div className="flex items-center gap-3 border-b border-glass px-4 py-2">
          <span className="text-[11px] text-neutral-400">
            {loading ? "Computing diff..." : summary}
          </span>
          {!loading && changes.length > 0 && (
            <div className="flex items-center gap-2 text-[11px]">
              {added > 0 && (
                <span className="rounded bg-emerald-950/40 px-1.5 py-0.5 text-emerald-400">
                  +{added} added
                </span>
              )}
              {removed > 0 && (
                <span className="rounded bg-rose-950/40 px-1.5 py-0.5 text-rose-400">
                  -{removed} removed
                </span>
              )}
              {changed > 0 && (
                <span className="rounded bg-amber-950/40 px-1.5 py-0.5 text-amber-400">
                  ~{changed} changed
                </span>
              )}
            </div>
          )}
          <div className="ml-auto flex items-stretch rounded border border-glass bg-neutral-900/80">
            <button
              type="button"
              onClick={() => setView("diff")}
              className={`px-2.5 py-0.5 text-[11px] transition ${view === "diff" ? "bg-white/10 text-neutral-100" : "text-neutral-500 hover:text-neutral-300"}`}
            >
              Diff
            </button>
            <button
              type="button"
              onClick={() => setView("changes")}
              className={`px-2.5 py-0.5 text-[11px] transition ${view === "changes" ? "bg-white/10 text-neutral-100" : "text-neutral-500 hover:text-neutral-300"}`}
            >
              Changes ({changes.length})
            </button>
          </div>
        </div>

        {/* Status comparison row */}
        <div className="grid grid-cols-2 gap-px border-b border-glass bg-neutral-800/30">
          <StatusLabel label="Left" res={left} />
          <StatusLabel label="Right" res={right} />
        </div>

        {/* Content area */}
        <div className="min-h-0 flex-1 overflow-hidden">
          {view === "diff" ? (
            <DiffEditor
              original={leftBody}
              modified={rightBody}
              language={detectLanguage(left)}
              theme="vs-dark"
              options={{
                readOnly: true,
                minimap: { enabled: false },
                fontSize: 12,
                lineNumbers: "on",
                scrollBeyondLastLine: false,
                renderSideBySide: true,
                wordWrap: "on",
              }}
            />
          ) : (
            <ChangesListView changes={changes} loading={loading} />
          )}
        </div>
      </div>
    </div>
  );
}

function StatusLabel({ label, res }: { label: string; res: ExecuteResponse }) {
  const tone = res.status < 300 ? "text-emerald-400" : res.status < 400 ? "text-cobweb-400" : res.status < 500 ? "text-amber-400" : "text-rose-400";
  return (
    <div className="flex items-center gap-3 px-4 py-1.5 bg-neutral-950/60">
      <span className="text-[11px] font-medium uppercase tracking-wider text-neutral-500">{label}</span>
      <span className={`font-mono text-xs font-bold ${tone}`}>{res.status}</span>
      <span className="text-[11px] text-neutral-500">{formatMs(res.elapsed_ms)}</span>
      <span className="truncate text-[10px] font-mono text-neutral-600">{res.final_url}</span>
    </div>
  );
}

function ChangesListView({ changes, loading }: { changes: ResponseChangeEntry[]; loading: boolean }) {
  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-neutral-500">
        Loading changes...
      </div>
    );
  }
  if (changes.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-neutral-500">
        No differences found
      </div>
    );
  }
  return (
    <div className="h-full overflow-auto">
      <table className="w-full text-xs">
        <thead className="sticky top-0 bg-neutral-925/80 text-[11px] uppercase tracking-wider text-neutral-500 backdrop-blur-md">
          <tr className="border-b border-cobweb-500/10">
            <th className="px-4 py-1.5 text-left font-medium">Path</th>
            <th className="px-4 py-1.5 text-left font-medium">Type</th>
            <th className="px-4 py-1.5 text-left font-medium">Old Value</th>
            <th className="px-4 py-1.5 text-left font-medium">New Value</th>
          </tr>
        </thead>
        <tbody>
          {changes.map((c, i) => (
            <tr
              key={i}
              className={`border-t border-glass/60 ${
                c.type === "added"
                  ? "bg-emerald-950/10"
                  : c.type === "removed"
                    ? "bg-rose-950/10"
                    : "bg-amber-950/10"
              }`}
            >
              <td className="px-4 py-1.5 font-mono text-neutral-300">{c.path}</td>
              <td className="px-4 py-1.5">
                <span
                  className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                    c.type === "added"
                      ? "bg-emerald-950/40 text-emerald-400"
                      : c.type === "removed"
                        ? "bg-rose-950/40 text-rose-400"
                        : "bg-amber-950/40 text-amber-400"
                  }`}
                >
                  {c.type}
                </span>
              </td>
              <td className="max-w-[200px] truncate px-4 py-1.5 font-mono text-neutral-400">
                {c.old_value ?? "-"}
              </td>
              <td className="max-w-[200px] truncate px-4 py-1.5 font-mono text-neutral-100">
                {c.new_value ?? "-"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function prettifyBody(body: string): string {
  try {
    return JSON.stringify(JSON.parse(body), null, 2);
  } catch {
    return body;
  }
}

function looksLikeJson(s: string): boolean {
  const t = s.trimStart();
  return t.startsWith("{") || t.startsWith("[");
}

function detectLanguage(res: ExecuteResponse): string {
  const ct = res.headers["content-type"] ?? "";
  if (ct.includes("json") || looksLikeJson(res.body)) return "json";
  if (ct.includes("xml") || ct.includes("html")) return "xml";
  return "plaintext";
}

function formatMs(ms: number): string {
  if (ms < 1) return "<1 ms";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}
