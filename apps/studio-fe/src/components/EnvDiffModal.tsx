import { useEffect, useState } from "react";
import { ArrowRight, GitCompareArrows, X } from "lucide-react";
import {
  sidecar,
  type EnvironmentSummary,
  type StructuredDiffOutput,
} from "../lib/sidecar";

interface Props {
  open: boolean;
  onClose: () => void;
  summaries: EnvironmentSummary[];
  initialLeftId?: string | null;
}

export function EnvDiffModal({ open, onClose, summaries, initialLeftId }: Props) {
  const [leftId, setLeftId] = useState<string>("");
  const [rightId, setRightId] = useState<string>("");
  const [diff, setDiff] = useState<StructuredDiffOutput | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset state when modal opens
  useEffect(() => {
    if (!open) return;
    setDiff(null);
    setError(null);
    setLeftId(initialLeftId ?? (summaries[0]?.id ?? ""));
    setRightId(summaries[1]?.id ?? summaries[0]?.id ?? "");
  }, [open, summaries, initialLeftId]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  async function runDiff() {
    if (!leftId || !rightId) return;
    setLoading(true);
    setError(null);
    try {
      const result = await sidecar.diffEnvironments(leftId, rightId);
      setDiff(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  if (!open) return null;

  const leftName = summaries.find((s) => s.id === leftId)?.name ?? "?";
  const rightName = summaries.find((s) => s.id === rightId)?.name ?? "?";

  const totalVars =
    diff
      ? diff.only_left.length + diff.only_right.length + diff.different.length + diff.same.length
      : 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div
        role="dialog"
        aria-label="Compare environments"
        className="glass flex h-[600px] w-[780px] max-w-[95vw] animate-slide-in flex-col overflow-hidden rounded-xl border border-glass-light shadow-2xl shadow-black/60"
      >
        {/* Header */}
        <header className="flex items-center justify-between border-b border-glass px-4 py-3">
          <h2 className="inline-flex items-center gap-2 text-sm font-semibold text-neutral-100">
            <GitCompareArrows className="h-4 w-4 text-cobweb-400" /> Compare Environments
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        {/* Selectors */}
        <div className="flex items-center gap-3 border-b border-glass px-4 py-3">
          <select
            value={leftId}
            onChange={(e) => setLeftId(e.target.value)}
            className="flex-1 rounded-md border border-glass bg-neutral-900/60 px-3 py-1.5 text-xs text-neutral-100 focus:border-cobweb-500/40 focus:outline-none"
          >
            <option value="" disabled>
              Select left...
            </option>
            {summaries.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name} ({s.variable_count} vars)
              </option>
            ))}
          </select>

          <ArrowRight className="h-4 w-4 shrink-0 text-neutral-500" />

          <select
            value={rightId}
            onChange={(e) => setRightId(e.target.value)}
            className="flex-1 rounded-md border border-glass bg-neutral-900/60 px-3 py-1.5 text-xs text-neutral-100 focus:border-cobweb-500/40 focus:outline-none"
          >
            <option value="" disabled>
              Select right...
            </option>
            {summaries.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name} ({s.variable_count} vars)
              </option>
            ))}
          </select>

          <button
            type="button"
            onClick={runDiff}
            disabled={!leftId || !rightId || leftId === rightId || loading}
            className="inline-flex items-center gap-1.5 rounded-md bg-accent-gradient px-3 py-1.5 text-[11px] font-medium text-white shadow-glow-sm transition disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
          >
            {loading ? "Comparing..." : "Compare"}
          </button>
        </div>

        {/* Error */}
        {error && (
          <p className="border-b border-rose-800/30 bg-rose-950/20 px-4 py-2 text-xs text-rose-300">
            {error}
          </p>
        )}

        {/* Results */}
        <div className="flex-1 overflow-y-auto p-4">
          {!diff && !loading && (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-xs text-neutral-500">
              <GitCompareArrows className="h-8 w-8 text-neutral-700" />
              <span>Select two environments and click Compare</span>
            </div>
          )}

          {loading && (
            <div className="flex h-full items-center justify-center text-xs text-neutral-500">
              Loading...
            </div>
          )}

          {diff && !loading && (
            <div className="space-y-4">
              {/* Summary badges */}
              <div className="flex items-center gap-2 text-[11px]">
                <span className="text-neutral-400">
                  {leftName} vs {rightName} -- {totalVars} variable{totalVars !== 1 ? "s" : ""} compared
                </span>
              </div>

              {/* Only Left (red) */}
              {diff.only_left.length > 0 && (
                <DiffSection
                  title={`Only in ${leftName}`}
                  count={diff.only_left.length}
                  color="rose"
                >
                  {diff.only_left.map((v) => (
                    <DiffRow key={v.name} name={v.name}>
                      <span className="font-mono text-rose-300">{v.value}</span>
                    </DiffRow>
                  ))}
                </DiffSection>
              )}

              {/* Only Right (green) */}
              {diff.only_right.length > 0 && (
                <DiffSection
                  title={`Only in ${rightName}`}
                  count={diff.only_right.length}
                  color="emerald"
                >
                  {diff.only_right.map((v) => (
                    <DiffRow key={v.name} name={v.name}>
                      <span className="font-mono text-emerald-300">{v.value}</span>
                    </DiffRow>
                  ))}
                </DiffSection>
              )}

              {/* Different (amber) */}
              {diff.different.length > 0 && (
                <DiffSection
                  title="Different values"
                  count={diff.different.length}
                  color="amber"
                >
                  {diff.different.map((v) => (
                    <DiffRow key={v.name} name={v.name}>
                      <span className="font-mono text-rose-300 line-through decoration-rose-500/50">
                        {v.left_value}
                      </span>
                      <ArrowRight className="mx-1 inline h-3 w-3 text-neutral-500" />
                      <span className="font-mono text-emerald-300">{v.right_value}</span>
                    </DiffRow>
                  ))}
                </DiffSection>
              )}

              {/* Same (muted) */}
              {diff.same.length > 0 && (
                <DiffSection
                  title="Identical"
                  count={diff.same.length}
                  color="neutral"
                >
                  {diff.same.map((v) => (
                    <DiffRow key={v.name} name={v.name}>
                      <span className="font-mono text-neutral-500">{v.value}</span>
                    </DiffRow>
                  ))}
                </DiffSection>
              )}

              {/* All empty */}
              {totalVars === 0 && (
                <p className="text-center text-xs text-neutral-500">
                  Both environments have no enabled variables.
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ---- Helpers ---------------------------------------------------------------

const colorMap = {
  rose: {
    border: "border-rose-800/40",
    bg: "bg-rose-950/20",
    badge: "bg-rose-900/40 text-rose-300",
    text: "text-rose-300",
  },
  emerald: {
    border: "border-emerald-800/40",
    bg: "bg-emerald-950/20",
    badge: "bg-emerald-900/40 text-emerald-300",
    text: "text-emerald-300",
  },
  amber: {
    border: "border-amber-800/40",
    bg: "bg-amber-950/20",
    badge: "bg-amber-900/40 text-amber-300",
    text: "text-amber-300",
  },
  neutral: {
    border: "border-neutral-800/40",
    bg: "bg-neutral-900/20",
    badge: "bg-neutral-800/40 text-neutral-400",
    text: "text-neutral-400",
  },
} as const;

function DiffSection({
  title,
  count,
  color,
  children,
}: {
  title: string;
  count: number;
  color: keyof typeof colorMap;
  children: React.ReactNode;
}) {
  const c = colorMap[color];
  return (
    <div className={`overflow-hidden rounded-lg border ${c.border}`}>
      <div className={`flex items-center gap-2 px-3 py-2 ${c.bg}`}>
        <span className={`text-[11px] font-medium ${c.text}`}>{title}</span>
        <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${c.badge}`}>
          {count}
        </span>
      </div>
      <div className="divide-y divide-glass">{children}</div>
    </div>
  );
}

function DiffRow({ name, children }: { name: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3 px-3 py-1.5 text-xs hover:bg-white/[0.02]">
      <span className="w-40 shrink-0 truncate font-mono font-medium text-neutral-200">{name}</span>
      <div className="min-w-0 flex-1 truncate">{children}</div>
    </div>
  );
}
