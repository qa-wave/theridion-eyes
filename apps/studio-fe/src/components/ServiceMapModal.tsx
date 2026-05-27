import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, Map, Plus, RefreshCw, Trash2, X } from "lucide-react";
import { sidecar, type ServiceGraph } from "../lib/sidecar";

interface Props { open: boolean; onClose: () => void; }

export function ServiceMapModal({ open, onClose }: Props) {
  const [graph, setGraph] = useState<ServiceGraph>({ nodes: [], edges: [] });
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [addingEdge, setAddingEdge] = useState<string | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (open) sidecar.getServiceMap().then(setGraph).catch(() => {});
  }, [open]);

  useEffect(() => { draw(); }, [graph, selected, addingEdge]);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = canvas.clientWidth * dpr;
    canvas.height = canvas.clientHeight * dpr;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, canvas.clientWidth, canvas.clientHeight);

    // Draw edges
    for (const edge of graph.edges) {
      const src = graph.nodes.find((n) => n.id === edge.source);
      const tgt = graph.nodes.find((n) => n.id === edge.target);
      if (!src || !tgt) continue;
      ctx.strokeStyle = "rgba(255,255,255,0.12)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(src.x + 60, src.y + 25);
      ctx.lineTo(tgt.x + 60, tgt.y + 25);
      ctx.stroke();
      // Arrow
      const angle = Math.atan2(tgt.y - src.y, tgt.x - src.x);
      const ax = tgt.x + 60 - Math.cos(angle) * 30;
      const ay = tgt.y + 25 - Math.sin(angle) * 30;
      ctx.fillStyle = "rgba(255,255,255,0.2)";
      ctx.beginPath();
      ctx.moveTo(ax, ay);
      ctx.lineTo(ax - 8 * Math.cos(angle - 0.4), ay - 8 * Math.sin(angle - 0.4));
      ctx.lineTo(ax - 8 * Math.cos(angle + 0.4), ay - 8 * Math.sin(angle + 0.4));
      ctx.closePath();
      ctx.fill();
      // Label
      if (edge.label) {
        ctx.fillStyle = "rgba(255,255,255,0.3)";
        ctx.font = "10px Inter, sans-serif";
        ctx.fillText(edge.label, (src.x + tgt.x) / 2 + 60, (src.y + tgt.y) / 2 + 20);
      }
    }

    // Draw nodes
    for (const node of graph.nodes) {
      const isSelected = node.id === selected;
      const isEdgeSource = node.id === addingEdge;
      ctx.fillStyle = isSelected ? "rgba(6,182,212,0.15)" : isEdgeSource ? "rgba(16,185,129,0.15)" : "rgba(255,255,255,0.04)";
      ctx.strokeStyle = isSelected ? node.color || "#06b6d4" : isEdgeSource ? "#10b981" : "rgba(255,255,255,0.08)";
      ctx.lineWidth = isSelected || isEdgeSource ? 2 : 1;
      ctx.beginPath();
      ctx.roundRect(node.x, node.y, 120, 50, 8);
      ctx.fill();
      ctx.stroke();
      // Colored dot
      ctx.fillStyle = node.color || "#06b6d4";
      ctx.beginPath();
      ctx.arc(node.x + 15, node.y + 25, 5, 0, Math.PI * 2);
      ctx.fill();
      // Label
      ctx.fillStyle = "#e5e5e5";
      ctx.font = "bold 11px Inter, sans-serif";
      ctx.fillText(node.label, node.x + 26, node.y + 22, 85);
      // URL
      ctx.fillStyle = "rgba(255,255,255,0.3)";
      ctx.font = "9px JetBrains Mono, monospace";
      ctx.fillText(node.url.replace(/^https?:\/\//, ""), node.x + 26, node.y + 36, 85);
    }
  }, [graph, selected, addingEdge]);

  function handleMouseDown(e: React.MouseEvent) {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const node = graph.nodes.find((n) => x >= n.x && x <= n.x + 120 && y >= n.y && y <= n.y + 50);
    if (node) {
      if (addingEdge && addingEdge !== node.id) {
        sidecar.addServiceEdge({ source: addingEdge, target: node.id }).then(setGraph);
        setAddingEdge(null);
        return;
      }
      setSelected(node.id);
      setDragging(node.id);
    } else {
      setSelected(null);
      setAddingEdge(null);
    }
  }

  function handleMouseMove(e: React.MouseEvent) {
    if (!dragging) return;
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    setGraph((g) => ({
      ...g,
      nodes: g.nodes.map((n) =>
        n.id === dragging ? { ...n, x: e.clientX - rect.left - 60, y: e.clientY - rect.top - 25 } : n,
      ),
    }));
  }

  function handleMouseUp() {
    if (dragging) {
      sidecar.saveServiceMap(graph).catch(() => {});
      setDragging(null);
    }
  }

  async function discover() {
    setBusy(true);
    try { const g = await sidecar.discoverServices(); setGraph(g); }
    catch { /* ignore */ }
    finally { setBusy(false); }
  }

  async function addNode() {
    const label = prompt("Service name:", "New Service");
    if (!label) return;
    const url = prompt("Base URL:", "https://");
    const g = await sidecar.addServiceNode({ label, url: url || "" });
    setGraph(g);
  }

  async function deleteSelected() {
    if (!selected) return;
    const g = await sidecar.deleteServiceNode(selected);
    setGraph(g);
    setSelected(null);
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="glass flex h-[700px] w-[1000px] max-h-[90vh] max-w-[95vw] animate-slide-in flex-col overflow-hidden rounded-xl border border-glass-light shadow-2xl shadow-black/60">
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-100">
            <Map className="h-4 w-4 text-cobweb-400" /> Service Map
          </div>
          <div className="flex items-center gap-1">
            <button type="button" onClick={discover} disabled={busy}
              className="inline-flex items-center gap-1 rounded-md border border-glass px-2 py-1 text-[11px] text-neutral-400 hover:bg-white/[0.04] hover:text-neutral-200 disabled:opacity-40">
              {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />} Discover
            </button>
            <button type="button" onClick={addNode}
              className="inline-flex items-center gap-1 rounded-md border border-glass px-2 py-1 text-[11px] text-neutral-400 hover:bg-white/[0.04] hover:text-neutral-200">
              <Plus className="h-3 w-3" /> Add
            </button>
            {selected && (
              <>
                <button type="button" onClick={() => setAddingEdge(selected)}
                  className="inline-flex items-center gap-1 rounded-md border border-emerald-800/40 bg-emerald-950/20 px-2 py-1 text-[11px] text-emerald-400">
                  Connect
                </button>
                <button type="button" onClick={deleteSelected}
                  className="inline-flex items-center gap-1 rounded-md border border-rose-800/40 bg-rose-950/20 px-2 py-1 text-[11px] text-rose-400">
                  <Trash2 className="h-3 w-3" />
                </button>
              </>
            )}
            <button type="button" onClick={onClose} className="ml-2 rounded-md p-1 text-neutral-500 hover:bg-white/[0.05] hover:text-neutral-200">
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {addingEdge && (
          <div className="border-b border-emerald-800/30 bg-emerald-950/10 px-4 py-1.5 text-xs text-emerald-400">
            Click a target node to create a connection. Esc to cancel.
          </div>
        )}

        <canvas
          ref={canvasRef}
          className="min-h-0 flex-1 cursor-crosshair"
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
        />

        <div className="border-t border-glass px-4 py-2 text-[10px] text-neutral-600">
          {graph.nodes.length} services &middot; {graph.edges.length} connections &middot; Drag to move, click to select, "Connect" to add edge
        </div>
      </div>
    </div>
  );
}
