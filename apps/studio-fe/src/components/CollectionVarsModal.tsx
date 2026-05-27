import { useEffect, useState } from "react";
import { Layers, Loader2, Save, X } from "lucide-react";
import { sidecar, type CollectionVariable, type CollectionSummary } from "../lib/sidecar";

interface Props {
  open: boolean;
  onClose: () => void;
}

interface DraftRow extends CollectionVariable {
  _key: string;
}

export function CollectionVarsModal({ open, onClose }: Props) {
  const [collections, setCollections] = useState<CollectionSummary[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [rows, setRows] = useState<DraftRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!open) return;
    sidecar.listCollections().then((c) => {
      setCollections(c);
      if (c.length > 0 && !selectedId) setSelectedId(c[0].id);
    }).catch(() => {});
  }, [open, selectedId]);

  useEffect(() => {
    if (!selectedId) return;
    sidecar.getCollection(selectedId).then((c) => {
      setRows(
        (c.variables ?? []).map((v) => ({ ...v, _key: crypto.randomUUID() })),
      );
    }).catch(() => {});
  }, [selectedId]);

  function addRow() {
    setRows((r) => [...r, { name: "", value: "", enabled: true, _key: crypto.randomUUID() }]);
  }

  function updateRow(idx: number, patch: Partial<DraftRow>) {
    setRows((r) => r.map((row, i) => (i === idx ? { ...row, ...patch } : row)));
    setSaved(false);
  }

  function removeRow(idx: number) {
    setRows((r) => r.filter((_, i) => i !== idx));
    setSaved(false);
  }

  async function save() {
    if (!selectedId) return;
    setBusy(true); setError(null);
    try {
      const vars: CollectionVariable[] = rows
        .filter((r) => r.name.trim())
        .map((r) => ({ name: r.name, value: r.value, enabled: r.enabled }));
      await sidecar.updateCollectionVariables(selectedId, vars);
      setSaved(true);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  if (!open) return null;

  const inputClass = "w-full bg-transparent px-3 py-1.5 font-mono text-xs focus:outline-none";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="glass flex h-[500px] w-[600px] max-h-[90vh] max-w-[95vw] animate-slide-in flex-col overflow-hidden rounded-xl border border-glass-light shadow-2xl shadow-black/60">
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-100">
            <Layers className="h-4 w-4 text-cobweb-400" /> Collection Variables
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200"><X className="h-4 w-4" /></button>
        </div>

        <div className="border-b border-glass px-4 py-2">
          <select
            value={selectedId}
            onChange={(e) => setSelectedId(e.target.value)}
            className="rounded-md border border-glass bg-neutral-900/50 px-3 py-1.5 text-xs text-neutral-100 focus:border-cobweb-500/40 focus:outline-none"
          >
            {collections.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>

        {error && <div className="border-b border-rose-800/30 bg-rose-950/20 px-4 py-2 text-xs text-rose-400">{error}</div>}

        <div className="flex-1 overflow-y-auto p-4">
          <div className="overflow-hidden rounded border border-glass">
            <table className="w-full text-xs">
              <thead className="bg-neutral-900/60 text-neutral-500">
                <tr>
                  <th className="w-8 px-2 py-1.5" />
                  <th className="px-3 py-1.5 text-left font-medium">Name</th>
                  <th className="px-3 py-1.5 text-left font-medium">Value</th>
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody>
                {rows.map((r, idx) => (
                  <tr key={r._key} className="border-t border-glass">
                    <td className="px-2 text-center">
                      <input type="checkbox" checked={r.enabled} onChange={(e) => updateRow(idx, { enabled: e.target.checked })} />
                    </td>
                    <td><input value={r.name} onChange={(e) => updateRow(idx, { name: e.target.value })} placeholder="VAR_NAME" className={inputClass} spellCheck={false} /></td>
                    <td><input value={r.value} onChange={(e) => updateRow(idx, { value: e.target.value })} placeholder="value" className={inputClass} spellCheck={false} /></td>
                    <td className="text-center">
                      <button type="button" onClick={() => removeRow(idx)} className="rounded p-1 text-neutral-600 transition hover:bg-neutral-800 hover:text-rose-400">x</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button type="button" onClick={addRow} className="mt-2 text-xs text-cobweb-400 hover:text-cobweb-300">+ Add variable</button>
        </div>

        <div className="flex items-center justify-between border-t border-glass px-4 py-3">
          {saved && <span className="text-[11px] text-emerald-400">Saved</span>}
          {!saved && <span />}
          <button type="button" onClick={save} disabled={busy} className="inline-flex items-center gap-2 rounded-md bg-cobweb-600/20 px-4 py-1.5 text-xs font-medium text-cobweb-400 transition hover:bg-cobweb-600/30 disabled:opacity-50">
            {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />} Save
          </button>
        </div>
      </div>
    </div>
  );
}
