import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, X, GitBranch } from "lucide-react";
import { sidecar, type DepGraphNode, type DepGraphResult } from "../lib/sidecar";

interface Props {
  open: boolean;
  onClose: () => void;
  collectionId: string | null;
  onOpenRequest?: (requestId: string) => void;
}

// Method color mapping
const METHOD_COLORS: Record<string, string> = {
  GET: "#10b981",
  POST: "#f59e0b",
  PUT: "#3b82f6",
  PATCH: "#8b5cf6",
  DELETE: "#ef4444",
  HEAD: "#6b7280",
  OPTIONS: "#6b7280",
};

interface LayoutNode {
  node: DepGraphNode;
  x: number;
  y: number;
  width: number;
  height: number;
  order: number;
}

function layoutGraph(
  result: DepGraphResult,
): { layoutNodes: LayoutNode[]; width: number; height: number } {
  const NODE_W = 220;
  const NODE_H = 56;
  const H_GAP = 80;
  const V_GAP = 32;

  if (result.nodes.length === 0) {
    return { layoutNodes: [], width: 0, height: 0 };
  }

  // Build columns by topological order (execution_order)
  // Group nodes into columns: col 0 = producers (no deps), col 1 = first level consumers, etc.
  const orderIndex = new Map<string, number>();
  result.execution_order.forEach((id, idx) => orderIndex.set(id, idx));

  // Find depth for each node using BFS from roots
  const incomingEdges = new Map<string, Set<string>>();
  for (const node of result.nodes) {
    incomingEdges.set(node.id, new Set());
  }
  for (const edge of result.edges) {
    incomingEdges.get(edge.to_id)?.add(edge.from_id);
  }

  const depth = new Map<string, number>();
  // BFS to compute depths
  const queue: string[] = [];
  for (const node of result.nodes) {
    if ((incomingEdges.get(node.id)?.size ?? 0) === 0) {
      depth.set(node.id, 0);
      queue.push(node.id);
    }
  }

  const outEdges = new Map<string, string[]>();
  for (const edge of result.edges) {
    const existing = outEdges.get(edge.from_id) ?? [];
    existing.push(edge.to_id);
    outEdges.set(edge.from_id, existing);
  }

  while (queue.length > 0) {
    const current = queue.shift()!;
    const currentDepth = depth.get(current) ?? 0;
    for (const neighbor of outEdges.get(current) ?? []) {
      const existingDepth = depth.get(neighbor) ?? -1;
      if (currentDepth + 1 > existingDepth) {
        depth.set(neighbor, currentDepth + 1);
        queue.push(neighbor);
      }
    }
  }

  // Assign depth 0 to any nodes not yet assigned (cycle members / orphans)
  for (const node of result.nodes) {
    if (!depth.has(node.id)) {
      depth.set(node.id, 0);
    }
  }

  // Group by column (depth)
  const columns = new Map<number, DepGraphNode[]>();
  for (const node of result.nodes) {
    const d = depth.get(node.id) ?? 0;
    const col = columns.get(d) ?? [];
    col.push(node);
    columns.set(d, col);
  }

  // Sort within each column by execution order
  for (const [, col] of columns) {
    col.sort((a, b) => (orderIndex.get(a.id) ?? 0) - (orderIndex.get(b.id) ?? 0));
  }

  const maxCol = Math.max(...Array.from(columns.keys()), 0);
  const layoutNodes: LayoutNode[] = [];

  for (let col = 0; col <= maxCol; col++) {
    const nodesInCol = columns.get(col) ?? [];
    const x = 40 + col * (NODE_W + H_GAP);
    for (let row = 0; row < nodesInCol.length; row++) {
      const y = 40 + row * (NODE_H + V_GAP);
      const order = result.execution_order.indexOf(nodesInCol[row].id) + 1;
      layoutNodes.push({
        node: nodesInCol[row],
        x,
        y,
        width: NODE_W,
        height: NODE_H,
        order,
      });
    }
  }

  const totalWidth = 80 + (maxCol + 1) * (NODE_W + H_GAP);
  const maxRows = Math.max(...Array.from(columns.values()).map((c) => c.length), 1);
  const totalHeight = 80 + maxRows * (NODE_H + V_GAP);

  return { layoutNodes, width: totalWidth, height: totalHeight };
}

function getNodeStatus(
  node: DepGraphNode,
  result: DepGraphResult,
): "ready" | "unresolved" | "orphan" {
  if (node.consumes.length === 0 && node.produces.length === 0) return "orphan";
  // Check if all consumed vars have a producer
  const producedVars = new Set<string>();
  for (const n of result.nodes) {
    for (const v of n.produces) producedVars.add(v);
  }
  for (const v of node.consumes) {
    if (!producedVars.has(v)) return "unresolved";
  }
  return "ready";
}

const STATUS_RING: Record<string, string> = {
  ready: "rgba(16, 185, 129, 0.6)",
  unresolved: "rgba(245, 158, 11, 0.6)",
  orphan: "rgba(107, 114, 128, 0.4)",
};

export function DependencyGraphModal({ open, onClose, collectionId, onOpenRequest }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DepGraphResult | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const fetchGraph = useCallback(async () => {
    if (!collectionId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await sidecar.buildDepGraph(collectionId);
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [collectionId]);

  useEffect(() => {
    if (open && collectionId) {
      fetchGraph();
    }
  }, [open, collectionId, fetchGraph]);

  if (!open) return null;

  const { layoutNodes, width, height } = result
    ? layoutGraph(result)
    : { layoutNodes: [], width: 600, height: 400 };

  // Build a lookup for node positions
  const posMap = new Map<string, LayoutNode>();
  for (const ln of layoutNodes) {
    posMap.set(ln.node.id, ln);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="relative flex flex-col w-[90vw] max-w-[1200px] h-[80vh] bg-neutral-900 border border-neutral-700/50 rounded-xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-neutral-800">
          <div className="flex items-center gap-2">
            <GitBranch className="w-4 h-4 text-emerald-400" />
            <h2 className="text-sm font-semibold text-neutral-100">
              Request Dependency Graph
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-neutral-800 text-neutral-400 hover:text-neutral-200 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-auto p-4">
          {loading && (
            <div className="flex items-center justify-center h-full gap-2 text-neutral-400">
              <Loader2 className="w-5 h-5 animate-spin" />
              <span className="text-sm">Analyzing dependencies...</span>
            </div>
          )}

          {error && (
            <div className="flex items-center justify-center h-full">
              <p className="text-sm text-red-400">{error}</p>
            </div>
          )}

          {!loading && !error && result && result.nodes.length === 0 && (
            <div className="flex items-center justify-center h-full">
              <p className="text-sm text-neutral-500">
                No dependencies detected in this collection.
              </p>
            </div>
          )}

          {!loading && !error && result && result.nodes.length > 0 && (
            <div className="w-full h-full overflow-auto">
              {result.has_cycle && (
                <div className="mb-3 px-3 py-2 bg-amber-900/30 border border-amber-700/50 rounded-lg text-xs text-amber-300">
                  Circular dependency detected between {result.cycle_members.length} requests.
                  Execution order may not be fully deterministic.
                </div>
              )}
              <svg
                ref={svgRef}
                width={Math.max(width, 600)}
                height={Math.max(height, 300)}
                className="select-none"
              >
                {/* Edges */}
                {result.edges.map((edge, i) => {
                  const from = posMap.get(edge.from_id);
                  const to = posMap.get(edge.to_id);
                  if (!from || !to) return null;
                  const x1 = from.x + from.width;
                  const y1 = from.y + from.height / 2;
                  const x2 = to.x;
                  const y2 = to.y + to.height / 2;
                  const mx = (x1 + x2) / 2;
                  return (
                    <g key={`edge-${i}`}>
                      <path
                        d={`M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`}
                        fill="none"
                        stroke="#525252"
                        strokeWidth={1.5}
                        markerEnd="url(#arrowhead)"
                      />
                      <text
                        x={mx}
                        y={(y1 + y2) / 2 - 6}
                        textAnchor="middle"
                        className="text-[9px] fill-neutral-500"
                      >
                        {`{{${edge.variable}}}`}
                      </text>
                    </g>
                  );
                })}

                {/* Arrow marker definition */}
                <defs>
                  <marker
                    id="arrowhead"
                    markerWidth="8"
                    markerHeight="6"
                    refX="7"
                    refY="3"
                    orient="auto"
                  >
                    <polygon points="0 0, 8 3, 0 6" fill="#525252" />
                  </marker>
                </defs>

                {/* Nodes */}
                {layoutNodes.map((ln) => {
                  const status = getNodeStatus(ln.node, result);
                  const methodColor = METHOD_COLORS[ln.node.method] ?? "#6b7280";
                  return (
                    <g
                      key={ln.node.id}
                      className="cursor-pointer"
                      onClick={() => onOpenRequest?.(ln.node.id)}
                    >
                      {/* Node background */}
                      <rect
                        x={ln.x}
                        y={ln.y}
                        width={ln.width}
                        height={ln.height}
                        rx={8}
                        fill="#171717"
                        stroke={STATUS_RING[status]}
                        strokeWidth={1.5}
                      />
                      {/* Method color left border */}
                      <rect
                        x={ln.x}
                        y={ln.y}
                        width={4}
                        height={ln.height}
                        rx={2}
                        fill={methodColor}
                      />
                      {/* Method badge */}
                      <text
                        x={ln.x + 14}
                        y={ln.y + 22}
                        className="text-[9px] font-bold"
                        fill={methodColor}
                      >
                        {ln.node.method}
                      </text>
                      {/* Name */}
                      <text
                        x={ln.x + 14}
                        y={ln.y + 40}
                        className="text-[11px] fill-neutral-200"
                      >
                        {ln.node.name.length > 24
                          ? ln.node.name.slice(0, 22) + "..."
                          : ln.node.name}
                      </text>
                      {/* Order badge */}
                      <circle
                        cx={ln.x + ln.width - 16}
                        cy={ln.y + 16}
                        r={10}
                        fill="#262626"
                        stroke="#404040"
                        strokeWidth={1}
                      />
                      <text
                        x={ln.x + ln.width - 16}
                        y={ln.y + 20}
                        textAnchor="middle"
                        className="text-[9px] font-semibold fill-emerald-400"
                      >
                        {ln.order}
                      </text>
                    </g>
                  );
                })}
              </svg>

              {/* Legend */}
              <div className="flex items-center gap-4 mt-4 px-2 text-[10px] text-neutral-500">
                <span className="flex items-center gap-1">
                  <span className="inline-block w-2 h-2 rounded-full bg-emerald-500/60" />
                  Ready
                </span>
                <span className="flex items-center gap-1">
                  <span className="inline-block w-2 h-2 rounded-full bg-amber-500/60" />
                  Unresolved deps
                </span>
                <span className="flex items-center gap-1">
                  <span className="inline-block w-2 h-2 rounded-full bg-neutral-500/60" />
                  No dependencies
                </span>
                <span className="ml-auto">Click a node to open the request</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
