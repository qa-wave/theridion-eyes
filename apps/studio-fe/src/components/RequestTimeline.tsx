/**
 * Horizontal bar chart showing collection run results.
 * Each request = row with bar width proportional to elapsed_ms, colored by status.
 */

interface TimelineEntry {
  name: string;
  method: string;
  url: string;
  status: number;
  elapsed_ms: number;
  error?: string | null;
}

interface Props {
  entries: TimelineEntry[];
}

function statusColor(status: number): string {
  if (status >= 200 && status < 300) return "bg-emerald-500";
  if (status >= 300 && status < 400) return "bg-sky-500";
  if (status >= 400 && status < 500) return "bg-amber-500";
  if (status >= 500) return "bg-rose-500";
  return "bg-neutral-500";
}

function statusTextColor(status: number): string {
  if (status >= 200 && status < 300) return "text-emerald-400";
  if (status >= 300 && status < 400) return "text-sky-400";
  if (status >= 400 && status < 500) return "text-amber-400";
  if (status >= 500) return "text-rose-400";
  return "text-neutral-400";
}

const METHOD_COLORS: Record<string, string> = {
  GET: "text-sky-400",
  POST: "text-emerald-400",
  PUT: "text-amber-400",
  PATCH: "text-violet-400",
  DELETE: "text-rose-400",
};

export function RequestTimeline({ entries }: Props) {
  if (entries.length === 0) {
    return <p className="text-xs text-neutral-500">No results to display</p>;
  }

  const maxMs = Math.max(...entries.map((e) => e.elapsed_ms), 1);

  return (
    <div className="space-y-1">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-[10px] uppercase tracking-wider text-neutral-500">Request Timeline</p>
        <p className="text-[10px] text-neutral-600">max {maxMs.toFixed(0)}ms</p>
      </div>
      {entries.map((entry, idx) => {
        const widthPct = Math.max((entry.elapsed_ms / maxMs) * 100, 2);
        return (
          <div key={idx} className="group flex items-center gap-2 rounded px-1 py-0.5 hover:bg-white/[0.02]">
            <div className="w-16 shrink-0 text-right">
              <span className={`text-[10px] font-bold ${METHOD_COLORS[entry.method] ?? "text-neutral-400"}`}>
                {entry.method}
              </span>
            </div>
            <div className="w-32 shrink-0 truncate text-[11px] text-neutral-300" title={entry.name}>
              {entry.name}
            </div>
            <div className="flex-1 min-w-0">
              <div className="relative h-5 w-full rounded bg-neutral-800/50">
                <div
                  className={`h-full rounded ${statusColor(entry.status)} transition-all duration-300`}
                  style={{ width: `${widthPct}%` }}
                />
                <span className="absolute inset-y-0 left-2 flex items-center text-[10px] font-mono text-white/80">
                  {entry.elapsed_ms.toFixed(0)}ms
                </span>
              </div>
            </div>
            <div className="w-12 shrink-0 text-right">
              <span className={`text-[11px] font-mono font-bold ${statusTextColor(entry.status)}`}>
                {entry.status}
              </span>
            </div>
            {entry.error && (
              <span className="text-[10px] text-rose-400 truncate max-w-[120px]" title={entry.error}>
                {entry.error}
              </span>
            )}
          </div>
        );
      })}
      {/* Summary bar */}
      <div className="mt-3 flex items-center gap-4 rounded-lg border border-glass bg-neutral-900/30 px-3 py-2 text-[10px]">
        <span className="text-neutral-500">
          Total: <span className="text-neutral-300">{entries.length} requests</span>
        </span>
        <span className="text-neutral-500">
          Avg: <span className="text-neutral-300">{(entries.reduce((s, e) => s + e.elapsed_ms, 0) / entries.length).toFixed(0)}ms</span>
        </span>
        <span className="text-emerald-500">
          2xx: {entries.filter((e) => e.status >= 200 && e.status < 300).length}
        </span>
        <span className="text-amber-500">
          4xx: {entries.filter((e) => e.status >= 400 && e.status < 500).length}
        </span>
        <span className="text-rose-500">
          5xx: {entries.filter((e) => e.status >= 500).length}
        </span>
      </div>
    </div>
  );
}
