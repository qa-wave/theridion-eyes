import { useState, useRef, useEffect, useCallback } from "react";
import { Play, Download, ExternalLink, Copy, Check } from "lucide-react";
import { sidecar } from "../lib/sidecar";
import type { CollectionSummary } from "../lib/sidecar";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------


// ---------------------------------------------------------------------------
// ANSI → React spans
// ---------------------------------------------------------------------------

interface AnsiSpan {
  text: string;
  className: string;
}

function parseAnsi(raw: string): AnsiSpan[] {
  const spans: AnsiSpan[] = [];
  const regex = /\x1b\[(\d+)m/g;
  let lastIndex = 0;
  let currentClass = "";

  const classMap: Record<string, string> = {
    "0": "",
    "1": "font-bold",
    "2": "opacity-60",
    "31": "text-red-400",
    "32": "text-emerald-400",
    "33": "text-amber-400",
  };

  let match: RegExpExecArray | null;
  while ((match = regex.exec(raw)) !== null) {
    if (match.index > lastIndex) {
      spans.push({ text: raw.slice(lastIndex, match.index), className: currentClass });
    }
    const code = match[1];
    if (code === "0") {
      currentClass = "";
    } else {
      const mapped = classMap[code] || "";
      if (mapped) {
        currentClass = currentClass ? `${currentClass} ${mapped}` : mapped;
      }
    }
    lastIndex = regex.lastIndex;
  }

  if (lastIndex < raw.length) {
    spans.push({ text: raw.slice(lastIndex), className: currentClass });
  }

  return spans;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface CliRunnerPanelProps {
  collections: CollectionSummary[];
  selectedCollectionId?: string;
  environmentId?: string;
}

export function CliRunnerPanel({ collections, selectedCollectionId, environmentId }: CliRunnerPanelProps) {
  const [collectionId, setCollectionId] = useState(selectedCollectionId || "");
  const [running, setRunning] = useState(false);
  const [output, setOutput] = useState<string | null>(null);
  const [traceId, setTraceId] = useState<string | null>(null);
  const [progress, setProgress] = useState<{ current: number; total: number } | null>(null);
  const [copied, setCopied] = useState(false);
  const terminalRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (selectedCollectionId) {
      setCollectionId(selectedCollectionId);
    }
  }, [selectedCollectionId]);

  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [output]);

  const handleRun = useCallback(async () => {
    if (!collectionId || running) return;

    setRunning(true);
    setOutput(null);
    setTraceId(null);
    setProgress(null);

    try {
      const result = await sidecar.runCliWithTrace(collectionId, environmentId);
      setOutput(result.output);
      setTraceId(result.trace_id);
      setProgress({ current: result.passed + result.failed + result.skipped, total: result.passed + result.failed + result.skipped });
    } catch (err) {
      setOutput(`\x1b[31mError: ${err instanceof Error ? err.message : "Unknown error"}\x1b[0m`);
    } finally {
      setRunning(false);
    }
  }, [collectionId, environmentId, running]);

  const handleDownloadTrace = useCallback(async () => {
    if (!traceId) return;
    try {
      const blob = await sidecar.downloadTrace(traceId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `trace-${traceId}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Failed to download trace:", err);
    }
  }, [traceId]);

  const handleViewHtml = useCallback(async () => {
    if (!traceId) return;
    try {
      const result = await sidecar.traceToHtml(traceId);
      const blob = new Blob([result.html], { type: "text/html" });
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank");
    } catch (err) {
      console.error("Failed to generate HTML trace:", err);
    }
  }, [traceId]);

  const handleCopy = useCallback(async () => {
    if (!output) return;
    // Strip ANSI codes for clipboard
    const plain = output.replace(/\x1b\[\d+m/g, "");
    await navigator.clipboard.writeText(plain);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [output]);

  const parsedOutput = output ? parseAnsi(output) : [];

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-neutral-800 bg-neutral-925">
        <select
          className="flex-1 bg-neutral-900 text-neutral-200 text-sm border border-neutral-700 rounded px-2 py-1 focus:outline-none focus:border-emerald-500"
          value={collectionId}
          onChange={(e) => setCollectionId(e.target.value)}
          disabled={running}
        >
          <option value="">Select collection...</option>
          {collections.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>

        <button
          onClick={handleRun}
          disabled={!collectionId || running}
          className="flex items-center gap-1.5 px-3 py-1 bg-emerald-600 hover:bg-emerald-500 disabled:bg-neutral-700 disabled:text-neutral-500 text-white text-sm font-medium rounded transition-colors"
        >
          <Play size={14} />
          {running ? "Running..." : "Run"}
        </button>

        {output && (
          <>
            <button
              onClick={handleCopy}
              className="flex items-center gap-1 px-2 py-1 text-neutral-400 hover:text-neutral-200 text-sm transition-colors"
              title="Copy output"
            >
              {copied ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
            </button>

            {traceId && (
              <>
                <button
                  onClick={handleDownloadTrace}
                  className="flex items-center gap-1 px-2 py-1 text-neutral-400 hover:text-neutral-200 text-sm transition-colors"
                  title="Download trace JSON"
                >
                  <Download size={14} />
                </button>
                <button
                  onClick={handleViewHtml}
                  className="flex items-center gap-1 px-2 py-1 text-neutral-400 hover:text-neutral-200 text-sm transition-colors"
                  title="View HTML trace"
                >
                  <ExternalLink size={14} />
                </button>
              </>
            )}
          </>
        )}
      </div>

      {/* Progress bar */}
      {running && progress && progress.total > 0 && (
        <div className="h-1 bg-neutral-800">
          <div
            className="h-full bg-emerald-500 transition-all duration-300"
            style={{ width: `${(progress.current / progress.total) * 100}%` }}
          />
        </div>
      )}

      {/* Terminal output */}
      <div
        ref={terminalRef}
        className="flex-1 overflow-auto bg-black p-4 font-mono text-sm leading-relaxed"
      >
        {!output && !running && (
          <div className="text-neutral-600 italic">
            Select a collection and click Run to execute all requests.
          </div>
        )}
        {running && !output && (
          <div className="text-neutral-400 animate-pulse">
            Executing requests...
          </div>
        )}
        {parsedOutput.length > 0 && (
          <pre className="whitespace-pre-wrap break-words">
            {parsedOutput.map((span, i) => (
              <span key={i} className={span.className}>
                {span.text}
              </span>
            ))}
          </pre>
        )}
      </div>
    </div>
  );
}
