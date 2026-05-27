import { useEffect, useRef, useState } from "react";
import { FileText, X, RefreshCw, Plus, Minus, ArrowRight, AlertTriangle } from "lucide-react";
import { sidecar } from "../lib/sidecar";
import type { ChangelogResult, ChangelogEntry, FieldChange } from "../lib/sidecar";
import { useFocusTrap } from "../hooks/useFocusTrap";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function ChangelogModal({ open, onClose }: Props) {
  const [result, setResult] = useState<ChangelogResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const trapRef = useRef<HTMLDivElement>(null);
  useFocusTrap(trapRef, open);

  useEffect(() => {
    if (!open) return;
    detect();
  }, [open]);

  async function detect() {
    setLoading(true);
    setError(null);
    try {
      const r = await sidecar.detectChangelog({ collection_id: "" });
      setResult(r);
    } catch {
      setError("Run requests to the same endpoint multiple times to detect API changes.");
    } finally {
      setLoading(false);
    }
  }

  if (!open) return null;

  const iconFor = (type: string) => {
    if (type === "added" || type === "new_field") return <Plus className="h-3 w-3 text-emerald-400" />;
    if (type === "removed" || type === "removed_field") return <Minus className="h-3 w-3 text-rose-400" />;
    return <ArrowRight className="h-3 w-3 text-amber-400" />;
  };

  const colorFor = (type: string) => {
    if (type === "added" || type === "new_field") return "bg-emerald-950/30 border border-emerald-800/30";
    if (type === "removed" || type === "removed_field") return "bg-rose-950/30 border border-rose-800/30";
    return "bg-amber-950/30 border border-amber-800/30";
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div ref={trapRef} className="glass flex h-[550px] w-[650px] max-h-[90vh] max-w-[95vw] animate-slide-in flex-col overflow-hidden rounded-xl border border-glass-light shadow-2xl shadow-black/60">
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-100">
            <FileText className="h-4 w-4 text-cobweb-400" />
            API Changelog
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={detect}
              disabled={loading}
              className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200"
            >
              <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            </button>
            <button type="button" onClick={onClose} className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200">
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {result && result.breaking_changes > 0 && (
          <div className="flex items-center gap-2 border-b border-rose-800/30 bg-rose-950/20 px-4 py-2 text-[11px] text-rose-400">
            <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
            {result.breaking_changes} breaking change{result.breaking_changes !== 1 ? "s" : ""} detected
          </div>
        )}

        <div className="flex-1 overflow-auto p-4">
          {loading && (
            <div className="flex items-center justify-center h-full text-neutral-500 text-sm">
              Analyzing API changes...
            </div>
          )}
          {error && !loading && (
            <div className="flex items-center justify-center h-full text-neutral-500 text-sm">
              {error}
            </div>
          )}
          {!error && !loading && result && result.entries.length === 0 && (
            <div className="flex items-center justify-center h-full text-neutral-500 text-sm">
              No API changes detected. Send requests to compare responses over time.
            </div>
          )}
          {!loading && result && result.entries.length > 0 && (
            <div className="space-y-4">
              <div className="flex items-center justify-between text-[11px] text-neutral-500">
                <span>{result.collection_name}</span>
                <span>{result.total_changes} change{result.total_changes !== 1 ? "s" : ""}</span>
              </div>
              {result.entries.map((entry: ChangelogEntry, i: number) => (
                <div key={i} className="space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-neutral-200">{entry.request_name}</span>
                    {entry.breaking && (
                      <span className="rounded-full bg-rose-500/20 px-2 py-0.5 text-[10px] font-medium text-rose-400">breaking</span>
                    )}
                  </div>
                  <div className="space-y-1">
                    {entry.changes.map((change: FieldChange, j: number) => (
                      <div
                        key={j}
                        className={`flex items-center gap-2 rounded-md px-3 py-2 text-xs ${colorFor(change.type)}`}
                      >
                        {iconFor(change.type)}
                        <span className="font-mono text-neutral-300">{change.path}</span>
                        {change.old_value != null && change.new_value != null && (
                          <span className="ml-auto text-neutral-500">
                            <span className="text-rose-400 line-through">{change.old_value}</span>
                            {" → "}
                            <span className="text-emerald-400">{change.new_value}</span>
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
