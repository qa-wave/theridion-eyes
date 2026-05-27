import { useMemo, useState } from "react";
import { GitCompare, X } from "lucide-react";

/**
 * Inline diff indicator for response body changes between runs.
 * Computes a simple line-level diff and shows a summary toggle button.
 */

interface Props {
  currentBody: string;
  previousBody: string | null;
}

function computeLineDiff(
  oldLines: string[],
  newLines: string[],
): { added: number; removed: number; changed: number } {
  let added = 0;
  let removed = 0;
  let changed = 0;

  const maxLen = Math.max(oldLines.length, newLines.length);
  for (let i = 0; i < maxLen; i++) {
    const oldLine = i < oldLines.length ? oldLines[i] : undefined;
    const newLine = i < newLines.length ? newLines[i] : undefined;

    if (oldLine === newLine) continue;

    if (oldLine !== undefined && newLine !== undefined) {
      changed += 1;
    } else if (newLine !== undefined) {
      added += 1;
    } else {
      removed += 1;
    }
  }

  return { added, removed, changed };
}

export function ResponseDiffInline({ currentBody, previousBody }: Props) {
  const [showDetail, setShowDetail] = useState(false);

  const diff = useMemo(() => {
    if (!previousBody || previousBody === currentBody) return null;
    const oldLines = previousBody.split("\n");
    const newLines = currentBody.split("\n");
    return computeLineDiff(oldLines, newLines);
  }, [currentBody, previousBody]);

  const hasDiff = diff !== null && (diff.added > 0 || diff.removed > 0 || diff.changed > 0);

  if (!hasDiff) return null;

  const totalChanges = diff!.added + diff!.removed + diff!.changed;

  return (
    <div className="flex items-center gap-1.5">
      <button
        type="button"
        onClick={() => setShowDetail(!showDetail)}
        className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium transition ${
          showDetail
            ? "bg-cobweb-500/20 text-cobweb-300"
            : "text-neutral-500 hover:bg-neutral-800/50 hover:text-neutral-300"
        }`}
        title="Show changes from last run"
      >
        {showDetail ? <X className="h-3 w-3" /> : <GitCompare className="h-3 w-3" />}
        {showDetail ? "Hide diff" : `${totalChanges} changes`}
      </button>
      {showDetail && (
        <span className="text-[10px] text-neutral-600">
          <span className="text-emerald-500">+{diff!.added}</span>
          {" / "}
          <span className="text-amber-400">~{diff!.changed}</span>
          {" / "}
          <span className="text-rose-400">-{diff!.removed}</span>
        </span>
      )}
    </div>
  );
}
