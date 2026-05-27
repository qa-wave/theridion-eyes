import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle,
  Clock,
  Plus,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import {
  sidecar,
  type PerfBudget,
  type PerfViolation,
} from "../lib/sidecar";

interface Props {
  onClose?: () => void;
}

type Tab = "budgets" | "violations";

export function PerfBudgetPanel({ onClose }: Props) {
  const [tab, setTab] = useState<Tab>("budgets");
  const [budgets, setBudgets] = useState<PerfBudget[]>([]);
  const [violations, setViolations] = useState<PerfViolation[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(false);

  // Form state
  const [formPattern, setFormPattern] = useState("");
  const [formMethod, setFormMethod] = useState("");
  const [formMaxTime, setFormMaxTime] = useState("500");
  const [formMaxSize, setFormMaxSize] = useState("");
  const [formName, setFormName] = useState("");

  const loadBudgets = useCallback(async () => {
    try {
      const data = await sidecar.listPerfBudgets();
      setBudgets(data);
    } catch {
      /* ignore */
    }
  }, []);

  const loadViolations = useCallback(async () => {
    try {
      const data = await sidecar.getPerfViolations();
      setViolations(data);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    loadBudgets();
    loadViolations();
  }, [loadBudgets, loadViolations]);

  const handleCreate = async () => {
    if (!formPattern || !formMaxTime) return;
    try {
      await sidecar.createPerfBudget({
        url_pattern: formPattern,
        method: formMethod || null,
        max_time_ms: parseInt(formMaxTime, 10),
        max_size_bytes: formMaxSize ? parseInt(formMaxSize, 10) : null,
        name: formName || formPattern,
      });
      setShowForm(false);
      setFormPattern("");
      setFormMethod("");
      setFormMaxTime("500");
      setFormMaxSize("");
      setFormName("");
      loadBudgets();
    } catch {
      /* ignore */
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await sidecar.deletePerfBudget(id);
      loadBudgets();
    } catch {
      /* ignore */
    }
  };

  const handleAutoGenerate = async () => {
    setLoading(true);
    try {
      const result = await sidecar.autoPerfBudget({ history: [], multiplier: 1.5 });
      if (result.suggested.length > 0) {
        // Create all suggested budgets
        for (const s of result.suggested) {
          await sidecar.createPerfBudget({
            url_pattern: s.url_pattern,
            method: s.method,
            max_time_ms: s.max_time_ms,
            max_size_bytes: s.max_size_bytes,
            p95_time_ms: s.p95_time_ms,
            name: s.name,
          });
        }
        loadBudgets();
      }
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  };

  const violatedBudgetIds = new Set(violations.map((v) => v.budget_id));

  return (
    <div className="flex flex-col h-full bg-neutral-950 text-neutral-200">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-neutral-800">
        <div className="flex items-center gap-2">
          <Clock className="w-4 h-4 text-emerald-400" />
          <span className="text-sm font-medium">Performance Budgets</span>
        </div>
        <div className="flex items-center gap-2">
          {/* Tabs */}
          <button
            className={`text-xs px-2 py-1 rounded ${
              tab === "budgets"
                ? "bg-neutral-800 text-white"
                : "text-neutral-400 hover:text-white"
            }`}
            onClick={() => setTab("budgets")}
          >
            Budgets ({budgets.length})
          </button>
          <button
            className={`text-xs px-2 py-1 rounded ${
              tab === "violations"
                ? "bg-neutral-800 text-white"
                : "text-neutral-400 hover:text-white"
            }`}
            onClick={() => {
              setTab("violations");
              loadViolations();
            }}
          >
            Violations ({violations.length})
          </button>
          {onClose && (
            <button
              onClick={onClose}
              className="text-neutral-500 hover:text-white"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-3">
        {tab === "budgets" && (
          <div className="space-y-3">
            {/* Actions */}
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowForm(true)}
                className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white"
              >
                <Plus className="w-3 h-3" /> Add Budget
              </button>
              <button
                onClick={handleAutoGenerate}
                disabled={loading}
                className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-neutral-800 hover:bg-neutral-700 text-neutral-300 disabled:opacity-50"
              >
                <Sparkles className="w-3 h-3" /> Auto-Generate
              </button>
            </div>

            {/* Add Budget Form */}
            {showForm && (
              <div className="bg-neutral-900 border border-neutral-800 rounded p-3 space-y-2">
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="text"
                    placeholder="Name"
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    className="col-span-2 bg-neutral-800 border border-neutral-700 rounded px-2 py-1 text-xs text-white placeholder-neutral-500"
                  />
                  <input
                    type="text"
                    placeholder="URL pattern (glob or regex)"
                    value={formPattern}
                    onChange={(e) => setFormPattern(e.target.value)}
                    className="col-span-2 bg-neutral-800 border border-neutral-700 rounded px-2 py-1 text-xs text-white placeholder-neutral-500"
                  />
                  <input
                    type="text"
                    placeholder="Method (optional)"
                    value={formMethod}
                    onChange={(e) => setFormMethod(e.target.value)}
                    className="bg-neutral-800 border border-neutral-700 rounded px-2 py-1 text-xs text-white placeholder-neutral-500"
                  />
                  <input
                    type="number"
                    placeholder="Max time (ms)"
                    value={formMaxTime}
                    onChange={(e) => setFormMaxTime(e.target.value)}
                    className="bg-neutral-800 border border-neutral-700 rounded px-2 py-1 text-xs text-white placeholder-neutral-500"
                  />
                  <input
                    type="number"
                    placeholder="Max size (bytes, optional)"
                    value={formMaxSize}
                    onChange={(e) => setFormMaxSize(e.target.value)}
                    className="bg-neutral-800 border border-neutral-700 rounded px-2 py-1 text-xs text-white placeholder-neutral-500"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleCreate}
                    className="text-xs px-2 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white"
                  >
                    Create
                  </button>
                  <button
                    onClick={() => setShowForm(false)}
                    className="text-xs px-2 py-1 rounded bg-neutral-800 hover:bg-neutral-700 text-neutral-400"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {/* Budget Table */}
            {budgets.length === 0 && !showForm && (
              <div className="text-center text-neutral-500 text-sm py-8">
                No performance budgets defined yet.
              </div>
            )}
            {budgets.length > 0 && (
              <div className="space-y-1">
                {budgets.map((b) => {
                  const isViolated = violatedBudgetIds.has(b.id);
                  return (
                    <div
                      key={b.id}
                      className={`flex items-center justify-between px-3 py-2 rounded border ${
                        isViolated
                          ? "border-red-500/40 bg-red-950/20"
                          : "border-neutral-800 bg-neutral-900"
                      }`}
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        {isViolated ? (
                          <AlertTriangle className="w-3.5 h-3.5 text-red-400 shrink-0" />
                        ) : (
                          <CheckCircle className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                        )}
                        <div className="min-w-0">
                          <div className="text-xs font-medium truncate">
                            {b.name || b.url_pattern}
                          </div>
                          <div className="text-[10px] text-neutral-500 truncate">
                            {b.method ? `${b.method} ` : ""}
                            {b.url_pattern} | {b.max_time_ms}ms
                            {b.max_size_bytes
                              ? ` | ${(b.max_size_bytes / 1024).toFixed(1)}KB`
                              : ""}
                          </div>
                        </div>
                      </div>
                      <button
                        onClick={() => handleDelete(b.id)}
                        className="text-neutral-600 hover:text-red-400 shrink-0"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {tab === "violations" && (
          <div className="space-y-1">
            {violations.length === 0 && (
              <div className="text-center text-neutral-500 text-sm py-8">
                No violations recorded.
              </div>
            )}
            {violations
              .slice()
              .reverse()
              .map((v, i) => (
                <div
                  key={`${v.budget_id}-${v.timestamp}-${i}`}
                  className="px-3 py-2 rounded border border-red-500/30 bg-red-950/10"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-red-300">
                      {v.budget_name}
                    </span>
                    <span className="text-[10px] text-neutral-500">
                      {new Date(v.timestamp * 1000).toLocaleTimeString()}
                    </span>
                  </div>
                  <div className="text-[10px] text-neutral-400 mt-0.5">
                    {v.metric}: {v.actual.toFixed(0)} &gt; {v.threshold.toFixed(0)}{" "}
                    (+{v.exceeded_by_percent}%)
                  </div>
                  <div className="text-[10px] text-neutral-500 truncate mt-0.5">
                    {v.method ? `${v.method} ` : ""}
                    {v.url}
                  </div>
                </div>
              ))}
          </div>
        )}
      </div>
    </div>
  );
}
