import { GitCompare, X } from "lucide-react";
import { DiffEditor } from "@monaco-editor/react";
import type { ExecuteResponse } from "../lib/sidecar";

interface Props {
  open: boolean;
  onClose: () => void;
  currentResponse: ExecuteResponse | null;
  previousResponse: ExecuteResponse | null;
}

export function DiffModal({ open, onClose, currentResponse, previousResponse }: Props) {
  if (!open) return null;

  const leftBody = previousResponse
    ? prettify(previousResponse.body)
    : "// No previous response to compare.\n// Send a request twice to see the diff.";
  const rightBody = currentResponse
    ? prettify(currentResponse.body)
    : "// No current response.";

  const leftLabel = previousResponse
    ? `Previous — ${previousResponse.status} ${previousResponse.status_text}`
    : "Previous";
  const rightLabel = currentResponse
    ? `Current — ${currentResponse.status} ${currentResponse.status_text}`
    : "Current";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="glass flex h-[680px] w-[1080px] max-h-[90vh] max-w-[95vw] animate-slide-in flex-col overflow-hidden rounded-xl border border-glass-light shadow-2xl shadow-black/60">
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-100">
            <GitCompare className="h-4 w-4 text-cobweb-400" />
            Response Diff
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex items-center gap-4 border-b border-glass px-4 py-2 text-xs">
          <div className="flex-1">
            <span className="text-neutral-500">Left:</span>{" "}
            <span className="text-neutral-300">{leftLabel}</span>
          </div>
          <div className="flex-1">
            <span className="text-neutral-500">Right:</span>{" "}
            <span className="text-neutral-300">{rightLabel}</span>
          </div>
        </div>

        <div className="min-h-0 flex-1">
          <DiffEditor
            original={leftBody}
            modified={rightBody}
            language="json"
            theme="vs-dark"
            height="100%"
            options={{
              readOnly: true,
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
              fontSize: 12,
              lineHeight: 18,
              renderSideBySide: true,
              padding: { top: 8, bottom: 8 },
            }}
          />
        </div>
      </div>
    </div>
  );
}

function prettify(body: string): string {
  try {
    return JSON.stringify(JSON.parse(body), null, 2);
  } catch {
    return body;
  }
}
