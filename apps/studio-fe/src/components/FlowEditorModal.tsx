import { useState } from "react";
import { GitBranch, Loader2, Play, Plus, Trash2, X } from "lucide-react";
import { sidecar, type FlowBlock, type FlowBlockExecuteOutput } from "../lib/sidecar";

interface Props {
  open: boolean;
  onClose: () => void;
}

interface DraftBlock {
  id: string;
  type: FlowBlock["type"];
  label: string;
  config: Record<string, unknown>;
}

export function FlowEditorModal({ open, onClose }: Props) {
  const [blocks, setBlocks] = useState<DraftBlock[]>([]);
  const [result, setResult] = useState<FlowBlockExecuteOutput | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  function addBlock(type: FlowBlock["type"]) {
    const id = crypto.randomUUID();
    let label = "Request";
    const config: Record<string, unknown> = {};
    if (type === "request") {
      label = "Request";
      config.method = "GET";
      config.url = "";
    } else if (type === "delay") {
      label = "Delay";
      config.ms = 1000;
    } else if (type === "condition") {
      label = "Condition";
      config.expression = "";
    } else if (type === "transform") {
      label = "Transform";
      config.script = "";
    }
    setBlocks((b) => [...b, { id, type, label, config }]);
  }

  function updateBlock(id: string, patch: Partial<DraftBlock>) {
    setBlocks((b) => b.map((bl) => (bl.id === id ? { ...bl, ...patch } : bl)));
  }

  function updateConfig(id: string, key: string, value: unknown) {
    setBlocks((b) =>
      b.map((bl) =>
        bl.id === id ? { ...bl, config: { ...bl.config, [key]: value } } : bl,
      ),
    );
  }

  function removeBlock(id: string) {
    setBlocks((b) => b.filter((bl) => bl.id !== id));
  }

  async function execute() {
    if (blocks.length === 0) return;
    setBusy(true); setError(null); setResult(null);
    try {
      const flowBlocks: FlowBlock[] = blocks.map((b, idx) => ({
        id: b.id,
        type: b.type,
        config: b.config,
        next: idx < blocks.length - 1 ? [blocks[idx + 1].id] : undefined,
      }));
      const res = await sidecar.executeFlowBlocks({ blocks: flowBlocks });
      setResult(res);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  const inputClass = "w-full rounded-md border border-glass bg-neutral-900/50 px-3 py-1.5 text-xs text-neutral-100 placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="glass flex h-[600px] w-[700px] max-h-[90vh] max-w-[95vw] animate-slide-in flex-col overflow-hidden rounded-xl border border-glass-light shadow-2xl shadow-black/60">
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-100">
            <GitBranch className="h-4 w-4 text-cobweb-400" /> Flow Editor
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200"><X className="h-4 w-4" /></button>
        </div>

        {error && <div className="border-b border-rose-800/30 bg-rose-950/20 px-4 py-2 text-xs text-rose-400">{error}</div>}

        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {blocks.map((block, idx) => {
            const blockResult = result?.results.find((r) => r.block_id === block.id);
            return (
              <div key={block.id} className={`rounded-lg border p-3 space-y-2 ${blockResult?.error ? "border-rose-800/50" : blockResult ? "border-emerald-800/50" : "border-glass"}`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-[10px] font-mono text-neutral-400">{idx + 1}</span>
                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${
                      block.type === "request" ? "bg-cobweb-600/20 text-cobweb-400"
                        : block.type === "delay" ? "bg-amber-600/20 text-amber-400"
                        : block.type === "condition" ? "bg-purple-600/20 text-purple-400"
                        : "bg-blue-600/20 text-blue-400"
                    }`}>{block.type}</span>
                    <input
                      value={block.label}
                      onChange={(e) => updateBlock(block.id, { label: e.target.value })}
                      className="bg-transparent text-xs text-neutral-200 focus:outline-none"
                      placeholder="Label"
                    />
                  </div>
                  <button type="button" onClick={() => removeBlock(block.id)} className="rounded p-1 text-neutral-600 hover:text-rose-400 hover:bg-neutral-800">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>

                {block.type === "request" && (
                  <div className="grid grid-cols-[80px_1fr] gap-2">
                    <select
                      value={(block.config.method as string) || "GET"}
                      onChange={(e) => updateConfig(block.id, "method", e.target.value)}
                      className="rounded-md border border-glass bg-neutral-900/50 px-2 py-1.5 text-xs text-neutral-100 focus:outline-none"
                    >
                      {["GET", "POST", "PUT", "PATCH", "DELETE"].map((m) => <option key={m}>{m}</option>)}
                    </select>
                    <input
                      value={(block.config.url as string) || ""}
                      onChange={(e) => updateConfig(block.id, "url", e.target.value)}
                      placeholder="https://api.example.com"
                      className={inputClass}
                    />
                  </div>
                )}

                {block.type === "delay" && (
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      value={(block.config.ms as number) ?? 1000}
                      onChange={(e) => updateConfig(block.id, "ms", parseInt(e.target.value) || 0)}
                      className={`w-24 ${inputClass}`}
                    />
                    <span className="text-xs text-neutral-500">ms</span>
                  </div>
                )}

                {block.type === "condition" && (
                  <input
                    value={(block.config.expression as string) || ""}
                    onChange={(e) => updateConfig(block.id, "expression", e.target.value)}
                    placeholder="status == 200"
                    className={inputClass}
                  />
                )}

                {block.type === "transform" && (
                  <input
                    value={(block.config.script as string) || ""}
                    onChange={(e) => updateConfig(block.id, "script", e.target.value)}
                    placeholder="response.data.id"
                    className={inputClass}
                  />
                )}

                {blockResult && (
                  <div className={`rounded border p-2 text-[11px] font-mono ${blockResult.error ? "border-rose-800/30 text-rose-400" : "border-emerald-800/30 text-emerald-400"}`}>
                    {blockResult.error ?? JSON.stringify(blockResult.output, null, 2)}
                  </div>
                )}
              </div>
            );
          })}

          <div className="flex gap-2 pt-2">
            <button type="button" onClick={() => addBlock("request")} className="inline-flex items-center gap-1 rounded-md border border-glass px-2 py-1.5 text-xs text-neutral-400 hover:bg-neutral-800/40 hover:text-neutral-200">
              <Plus className="h-3 w-3" /> Request
            </button>
            <button type="button" onClick={() => addBlock("delay")} className="inline-flex items-center gap-1 rounded-md border border-glass px-2 py-1.5 text-xs text-neutral-400 hover:bg-neutral-800/40 hover:text-neutral-200">
              <Plus className="h-3 w-3" /> Delay
            </button>
            <button type="button" onClick={() => addBlock("condition")} className="inline-flex items-center gap-1 rounded-md border border-glass px-2 py-1.5 text-xs text-neutral-400 hover:bg-neutral-800/40 hover:text-neutral-200">
              <Plus className="h-3 w-3" /> Condition
            </button>
            <button type="button" onClick={() => addBlock("transform")} className="inline-flex items-center gap-1 rounded-md border border-glass px-2 py-1.5 text-xs text-neutral-400 hover:bg-neutral-800/40 hover:text-neutral-200">
              <Plus className="h-3 w-3" /> Transform
            </button>
          </div>
        </div>

        <div className="border-t border-glass px-4 py-3">
          <button
            type="button"
            onClick={execute}
            disabled={busy || blocks.length === 0}
            className="inline-flex items-center gap-2 rounded-md bg-cobweb-600/20 px-4 py-2 text-xs font-medium text-cobweb-400 transition hover:bg-cobweb-600/30 disabled:opacity-50"
          >
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
            Execute Flow
            {result && <span className="text-neutral-500 ml-1">{result.elapsed_ms}ms</span>}
          </button>
        </div>
      </div>
    </div>
  );
}
