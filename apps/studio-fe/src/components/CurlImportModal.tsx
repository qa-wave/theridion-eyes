import { useState } from "react";
import { ClipboardPaste, Terminal, X } from "lucide-react";
import { sidecar, type ParsedCurl } from "../lib/sidecar";

interface Props {
  open: boolean;
  onClose: () => void;
  onImport: (parsed: ParsedCurl) => void;
}

export function CurlImportModal({ open, onClose, onImport }: Props) {
  const [curlText, setCurlText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!open) return null;

  async function handleImport() {
    if (!curlText.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const parsed = await sidecar.parseCurl(curlText);
      if (!parsed.url) {
        setError("Could not extract a URL from the cURL command.");
        return;
      }
      onImport(parsed);
      setCurlText("");
      onClose();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handlePaste() {
    try {
      const text = await navigator.clipboard.readText();
      setCurlText(text);
    } catch {
      // Clipboard permission denied.
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="glass w-full max-w-lg animate-slide-in rounded-xl border border-glass-light shadow-2xl shadow-black/60">
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-100">
            <Terminal className="h-4 w-4 text-cobweb-400" />
            Import cURL
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-4">
          <p className="mb-2 text-[11px] uppercase tracking-widest text-neutral-500">
            Paste a cURL command
          </p>
          <div className="relative">
            <textarea
              value={curlText}
              onChange={(e) => setCurlText(e.target.value)}
              placeholder={'curl -X POST -H \'Content-Type: application/json\' \\\n  -d \'{"key":"value"}\' \\\n  https://api.example.com'}
              rows={8}
              className="w-full resize-y rounded-lg border border-glass bg-neutral-900/50 px-3 py-2 font-mono text-xs text-neutral-100 placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none"
              spellCheck={false}
              autoFocus
            />
            <button
              type="button"
              onClick={handlePaste}
              title="Paste from clipboard"
              className="absolute right-2 top-2 rounded-md p-1.5 text-neutral-500 transition hover:bg-white/[0.06] hover:text-neutral-300"
            >
              <ClipboardPaste className="h-3.5 w-3.5" />
            </button>
          </div>

          {error && (
            <p className="mt-2 rounded-md border border-rose-800/30 bg-rose-950/20 px-2 py-1 text-xs text-rose-400">
              {error}
            </p>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-glass px-4 py-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md px-3 py-1.5 text-xs text-neutral-400 transition hover:bg-white/[0.04] hover:text-neutral-200"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleImport}
            disabled={busy || !curlText.trim()}
            className="rounded-md bg-accent-gradient px-4 py-1.5 text-xs font-medium text-white shadow-glow-sm transition disabled:opacity-40 disabled:shadow-none"
          >
            {busy ? "Parsing\u2026" : "Import"}
          </button>
        </div>
      </div>
    </div>
  );
}
