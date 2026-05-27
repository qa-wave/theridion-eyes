import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeftRight, Clipboard, GitCompare, X } from "lucide-react";
import { DiffEditor } from "@monaco-editor/react";
import {
  sidecar,
  type BodyDiffOutput,
  type BodyDiffStructuralChange,
  type CollectionItem,
  type StoredCollection,
} from "../lib/sidecar";

interface Props {
  open: boolean;
  onClose: () => void;
  initialLeft?: string;
  initialRight?: string;
}

type DiffFormat = "json" | "xml" | "text" | "auto";

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
      } else if (item.body) {
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

export function BodyDiffModal({ open, onClose, initialLeft, initialRight }: Props) {
  const [left, setLeft] = useState(initialLeft ?? "");
  const [right, setRight] = useState(initialRight ?? "");
  const [format, setFormat] = useState<DiffFormat>("auto");
  const [diffResult, setDiffResult] = useState<BodyDiffOutput | null>(null);
  const [loading, setLoading] = useState(false);
  const [collections, setCollections] = useState<StoredCollection[]>([]);
  const [loadedCollections, setLoadedCollections] = useState(false);

  // Load collections for "import from saved request" dropdowns
  useEffect(() => {
    if (!open) {
      setLoadedCollections(false);
      return;
    }
    if (loadedCollections) return;
    setLoadedCollections(true);
    sidecar
      .listCollections()
      .then(async (summaries) => {
        const full = await Promise.all(summaries.map((s) => sidecar.getCollection(s.id)));
        setCollections(full);
      })
      .catch(() => {});
  }, [open, loadedCollections]);

  // Reset state when opening
  useEffect(() => {
    if (open) {
      setLeft(initialLeft ?? "");
      setRight(initialRight ?? "");
      setDiffResult(null);
    }
  }, [open, initialLeft, initialRight]);

  const flatRequests = useMemo(() => flattenRequests(collections), [collections]);

  const runDiff = useCallback(async () => {
    if (!left.trim() && !right.trim()) return;
    setLoading(true);
    try {
      const result = await sidecar.diffBodies({ left, right, format });
      setDiffResult(result);
    } catch {
      setDiffResult(null);
    } finally {
      setLoading(false);
    }
  }, [left, right, format]);

  // Auto-diff when both sides have content
  useEffect(() => {
    if (open && (left.trim() || right.trim())) {
      const timer = setTimeout(runDiff, 400);
      return () => clearTimeout(timer);
    }
  }, [left, right, format, open, runDiff]);

  const handleSwap = () => {
    setLeft(right);
    setRight(left);
  };

  const handlePasteLeft = async () => {
    try {
      const text = await navigator.clipboard.readText();
      setLeft(text);
    } catch { /* clipboard not available */ }
  };

  const handlePasteRight = async () => {
    try {
      const text = await navigator.clipboard.readText();
      setRight(text);
    } catch { /* clipboard not available */ }
  };

  const handleImportLeft = (key: string) => {
    const req = flatRequests.find((r) => `${r.collectionId}/${r.item.id}` === key);
    if (req?.item.body) setLeft(req.item.body);
  };

  const handleImportRight = (key: string) => {
    const req = flatRequests.find((r) => `${r.collectionId}/${r.item.id}` === key);
    if (req?.item.body) setRight(req.item.body);
  };

  if (!open) return null;

  const stats = diffResult?.stats;
  const changes = diffResult?.structural_changes ?? [];

  const monacoLang =
    diffResult?.format_detected === "json"
      ? "json"
      : diffResult?.format_detected === "xml"
        ? "xml"
        : "plaintext";

  const selectClass =
    "w-full rounded-md border border-glass bg-neutral-900/50 px-2 py-1 text-xs text-neutral-100 focus:border-cobweb-500/40 focus:outline-none";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="glass flex h-[720px] w-[1100px] max-h-[90vh] max-w-[95vw] animate-slide-in flex-col overflow-hidden rounded-xl border border-glass-light shadow-2xl shadow-black/60">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-100">
            <GitCompare className="h-4 w-4 text-cobweb-400" />
            Body Diff
          </div>
          <div className="flex items-center gap-3">
            {/* Format selector */}
            <select
              value={format}
              onChange={(e) => setFormat(e.target.value as DiffFormat)}
              className="rounded-md border border-glass bg-neutral-900/50 px-2 py-1 text-xs text-neutral-300 focus:border-cobweb-500/40 focus:outline-none"
            >
              <option value="auto">Auto-detect</option>
              <option value="json">JSON</option>
              <option value="xml">XML</option>
              <option value="text">Text</option>
            </select>
            <button
              type="button"
              onClick={handleSwap}
              title="Swap left/right"
              className="rounded-md p-1.5 text-neutral-400 transition hover:bg-white/[0.05] hover:text-cobweb-400"
            >
              <ArrowLeftRight className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Stats bar */}
        {stats && (
          <div className="flex items-center gap-4 border-b border-glass px-4 py-2 text-xs">
            <span className="text-emerald-400">+{stats.additions} additions</span>
            <span className="text-red-400">-{stats.deletions} deletions</span>
            <span className="text-amber-400">~{stats.modifications} modifications</span>
            {diffResult?.format_detected && (
              <span className="ml-auto text-neutral-500">
                Detected: {diffResult.format_detected}
              </span>
            )}
            {loading && <span className="text-neutral-500">Comparing...</span>}
          </div>
        )}

        {/* Import controls */}
        <div className="grid grid-cols-2 gap-3 border-b border-glass px-4 py-2">
          <div className="flex items-center gap-2">
            <select
              onChange={(e) => { handleImportLeft(e.target.value); e.target.value = ""; }}
              className={selectClass}
              defaultValue=""
            >
              <option value="" disabled>Import from saved request...</option>
              {flatRequests.map((r) => (
                <option key={`l-${r.collectionId}/${r.item.id}`} value={`${r.collectionId}/${r.item.id}`}>
                  {r.label}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={handlePasteLeft}
              title="Paste from clipboard"
              className="flex-shrink-0 rounded-md p-1.5 text-neutral-400 transition hover:bg-white/[0.05] hover:text-cobweb-400"
            >
              <Clipboard className="h-3.5 w-3.5" />
            </button>
          </div>
          <div className="flex items-center gap-2">
            <select
              onChange={(e) => { handleImportRight(e.target.value); e.target.value = ""; }}
              className={selectClass}
              defaultValue=""
            >
              <option value="" disabled>Import from saved request...</option>
              {flatRequests.map((r) => (
                <option key={`r-${r.collectionId}/${r.item.id}`} value={`${r.collectionId}/${r.item.id}`}>
                  {r.label}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={handlePasteRight}
              title="Paste from clipboard"
              className="flex-shrink-0 rounded-md p-1.5 text-neutral-400 transition hover:bg-white/[0.05] hover:text-cobweb-400"
            >
              <Clipboard className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        {/* Diff editor */}
        <div className="flex-1 min-h-0 overflow-hidden">
          <DiffEditor
            original={left}
            modified={right}
            language={monacoLang}
            theme="vs-dark"
            options={{
              readOnly: false,
              minimap: { enabled: false },
              fontSize: 12,
              lineNumbers: "on",
              scrollBeyondLastLine: false,
              renderSideBySide: true,
              originalEditable: true,
            }}
            onMount={(editor) => {
              const origModel = editor.getModel()?.original;
              const modModel = editor.getModel()?.modified;
              origModel?.onDidChangeContent(() => setLeft(origModel.getValue()));
              modModel?.onDidChangeContent(() => setRight(modModel.getValue()));
            }}
          />
        </div>

        {/* Structural changes list */}
        {changes.length > 0 && (
          <div className="max-h-[140px] overflow-auto border-t border-glass px-4 py-2">
            <p className="mb-1 text-[10px] uppercase tracking-wider text-neutral-500">
              Structural Changes ({changes.length})
            </p>
            <div className="space-y-0.5">
              {changes.slice(0, 50).map((change: BodyDiffStructuralChange, i: number) => (
                <div key={i} className="flex items-center gap-2 text-xs">
                  <span
                    className={
                      change.type === "added"
                        ? "text-emerald-400"
                        : change.type === "removed"
                          ? "text-red-400"
                          : "text-amber-400"
                    }
                  >
                    {change.type === "added" ? "+" : change.type === "removed" ? "-" : "~"}
                  </span>
                  <span className="font-mono text-neutral-300">{change.path}</span>
                  {change.type === "changed" && (
                    <span className="text-neutral-500 truncate max-w-[300px]">
                      {JSON.stringify(change.old)} → {JSON.stringify(change.new)}
                    </span>
                  )}
                </div>
              ))}
              {changes.length > 50 && (
                <p className="text-neutral-500 text-[10px]">...and {changes.length - 50} more</p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
