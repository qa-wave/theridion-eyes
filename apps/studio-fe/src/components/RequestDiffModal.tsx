import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeftRight, GitCompare, X } from "lucide-react";
import { sidecar, type CollectionItem, type StoredCollection, type RequestDiffOutput } from "../lib/sidecar";
import { DiffEditor } from "@monaco-editor/react";

interface Props {
  open: boolean;
  onClose: () => void;
}

interface FlatRequest {
  collectionId: string;
  collectionName: string;
  item: CollectionItem;
  label: string;
}

function flattenRequests(collections: StoredCollection[]): FlatRequest[] {
  const result: FlatRequest[] = [];
  function walk(colId: string, colName: string, items: CollectionItem[]) {
    for (const item of items) {
      if (item.is_folder) {
        if (item.items) walk(colId, colName, item.items);
      } else {
        result.push({
          collectionId: colId,
          collectionName: colName,
          item,
          label: `${item.method ?? "GET"} ${item.name} (${colName})`,
        });
      }
    }
  }
  for (const col of collections) walk(col.id, col.name, col.items);
  return result;
}

function requestToText(item: CollectionItem): string {
  const lines: string[] = [];
  lines.push(`${item.method ?? "GET"} ${item.url ?? ""}`);
  lines.push("");
  lines.push("--- Headers ---");
  if (item.headers && Object.keys(item.headers).length > 0) {
    for (const [k, v] of Object.entries(item.headers)) {
      lines.push(`${k}: ${v}`);
    }
  } else {
    lines.push("(none)");
  }
  lines.push("");
  lines.push("--- Body ---");
  if (item.body) {
    try {
      lines.push(JSON.stringify(JSON.parse(item.body), null, 2));
    } catch {
      lines.push(item.body);
    }
  } else {
    lines.push("(empty)");
  }
  if (item.auth && item.auth.type !== "none") {
    lines.push("");
    lines.push("--- Auth ---");
    lines.push(`Type: ${item.auth.type}`);
  }
  return lines.join("\n");
}

const badgeColors: Record<string, string> = {
  added: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  removed: "bg-red-500/20 text-red-400 border-red-500/30",
  changed: "bg-amber-500/20 text-amber-400 border-amber-500/30",
};

export function RequestDiffModal({ open, onClose }: Props) {
  const [collections, setCollections] = useState<StoredCollection[]>([]);
  const [leftId, setLeftId] = useState("");
  const [rightId, setRightId] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [diffResult, setRequestDiffOutput] = useState<RequestDiffOutput | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);

  useEffect(() => {
    if (!open) { setLoaded(false); setRequestDiffOutput(null); return; }
    if (loaded) return;
    setLoaded(true);
    sidecar.listCollections().then(async (summaries) => {
      const full = await Promise.all(summaries.map((s) => sidecar.getCollection(s.id)));
      setCollections(full);
    }).catch(() => {});
  }, [open, loaded]);

  const flatRequests = useMemo(() => flattenRequests(collections), [collections]);

  const leftItem = useMemo(
    () => flatRequests.find((r) => `${r.collectionId}/${r.item.id}` === leftId)?.item ?? null,
    [flatRequests, leftId],
  );
  const rightItem = useMemo(
    () => flatRequests.find((r) => `${r.collectionId}/${r.item.id}` === rightId)?.item ?? null,
    [flatRequests, rightId],
  );

  // Fetch backend diff when both selections change
  useEffect(() => {
    if (!leftId || !rightId) { setRequestDiffOutput(null); return; }
    const [leftCol, leftReq] = leftId.split("/");
    const [rightCol, rightReq] = rightId.split("/");
    setDiffLoading(true);
    sidecar.diffRequests({
      left: { collection_id: leftCol, request_id: leftReq },
      right: { collection_id: rightCol, request_id: rightReq },
    }).then((res) => {
      setRequestDiffOutput(res);
    }).catch(() => {
      setRequestDiffOutput(null);
    }).finally(() => setDiffLoading(false));
  }, [leftId, rightId]);

  const handleSwap = useCallback(() => {
    const tmp = leftId;
    setLeftId(rightId);
    setRightId(tmp);
  }, [leftId, rightId]);

  const leftText = leftItem ? requestToText(leftItem) : "";
  const rightText = rightItem ? requestToText(rightItem) : "";

  if (!open) return null;

  const selectClass = "w-full rounded-md border border-glass bg-neutral-900/50 px-3 py-1.5 text-xs text-neutral-100 focus:border-cobweb-500/40 focus:outline-none";

  const changeCount = diffResult
    ? (diffResult.method_changed ? 1 : 0) +
      (diffResult.url_diff ? 1 : 0) +
      diffResult.header_changes.length +
      (diffResult.body_diff ? 1 : 0) +
      (diffResult.auth_diff ? 1 : 0)
    : 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="glass flex h-[700px] w-[960px] max-h-[90vh] max-w-[95vw] animate-slide-in flex-col overflow-hidden rounded-xl border border-glass-light shadow-2xl shadow-black/60">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-100">
            <GitCompare className="h-4 w-4 text-cobweb-400" /> Request Diff
            {diffResult && leftId && rightId && (
              <span className={`ml-2 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${changeCount === 0 ? "bg-neutral-800 text-neutral-400 border-neutral-700" : "bg-amber-500/20 text-amber-300 border-amber-500/30"}`}>
                {diffResult.summary}
              </span>
            )}
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Selectors */}
        <div className="flex items-end gap-2 border-b border-glass px-4 py-3">
          <div className="flex-1">
            <p className="mb-1 text-[10px] uppercase tracking-wider text-neutral-500">Left</p>
            <select value={leftId} onChange={(e) => setLeftId(e.target.value)} className={selectClass}>
              <option value="">Select request...</option>
              {flatRequests.map((r) => (
                <option key={`${r.collectionId}/${r.item.id}`} value={`${r.collectionId}/${r.item.id}`}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>
          <button
            type="button"
            onClick={handleSwap}
            disabled={!leftId || !rightId}
            className="mb-0.5 rounded-md border border-glass p-1.5 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200 disabled:opacity-30"
            title="Swap left/right"
          >
            <ArrowLeftRight className="h-3.5 w-3.5" />
          </button>
          <div className="flex-1">
            <p className="mb-1 text-[10px] uppercase tracking-wider text-neutral-500">Right</p>
            <select value={rightId} onChange={(e) => setRightId(e.target.value)} className={selectClass}>
              <option value="">Select request...</option>
              {flatRequests.map((r) => (
                <option key={`${r.collectionId}/${r.item.id}`} value={`${r.collectionId}/${r.item.id}`}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Structured diff sections */}
        {diffResult && !diffLoading && leftItem && rightItem && (
          <div className="shrink-0 overflow-y-auto border-b border-glass px-4 py-2 max-h-[160px]">
            <div className="flex flex-wrap gap-2 text-[11px]">
              {/* Method */}
              {diffResult.method_changed && (
                <div className={`flex items-center gap-1.5 rounded border px-2 py-1 ${badgeColors.changed}`}>
                  <span className="font-medium">Method:</span>
                  <span className="line-through opacity-70">{leftItem.method ?? "GET"}</span>
                  <span>→</span>
                  <span>{rightItem.method ?? "GET"}</span>
                </div>
              )}
              {/* URL */}
              {diffResult.url_diff && (
                <div className={`flex items-center gap-1.5 rounded border px-2 py-1 ${badgeColors.changed}`}>
                  <span className="font-medium">URL changed</span>
                </div>
              )}
              {/* Headers */}
              {diffResult.header_changes.map((h) => (
                <div key={h.name} className={`flex items-center gap-1.5 rounded border px-2 py-1 ${badgeColors[h.type]}`}>
                  <span className="font-medium">{h.name}</span>
                  <span className="opacity-70">{h.type}</span>
                </div>
              ))}
              {/* Body */}
              {diffResult.body_diff && (
                <div className={`flex items-center gap-1.5 rounded border px-2 py-1 ${badgeColors.changed}`}>
                  <span className="font-medium">Body ({diffResult.body_diff.format})</span>
                  <span className="opacity-70">{diffResult.body_diff.changes.length} diff{diffResult.body_diff.changes.length !== 1 ? "s" : ""}</span>
                </div>
              )}
              {/* Auth */}
              {diffResult.auth_diff && (
                <div className={`flex items-center gap-1.5 rounded border px-2 py-1 ${badgeColors.changed}`}>
                  <span className="font-medium">Auth:</span>
                  <span className="opacity-70">{diffResult.auth_diff.details}</span>
                </div>
              )}
              {changeCount === 0 && (
                <span className="text-neutral-500">Requests are identical</span>
              )}
            </div>
          </div>
        )}

        {/* Monaco Diff Editor */}
        <div className="flex-1 min-h-0 overflow-hidden">
          {diffLoading ? (
            <div className="flex h-full items-center justify-center text-xs text-neutral-500">
              Computing diff...
            </div>
          ) : leftItem && rightItem ? (
            <DiffEditor
              original={leftText}
              modified={rightText}
              language="text"
              theme="vs-dark"
              options={{
                readOnly: true,
                minimap: { enabled: false },
                fontSize: 12,
                lineNumbers: "off",
                scrollBeyondLastLine: false,
                renderSideBySide: true,
              }}
            />
          ) : (
            <div className="flex h-full items-center justify-center text-xs text-neutral-500">
              Select two requests to compare
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
