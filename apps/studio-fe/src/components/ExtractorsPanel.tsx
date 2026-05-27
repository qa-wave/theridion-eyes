import { useState } from "react";
import { Plus, Trash2, Play } from "lucide-react";
import type { Extractor } from "../state/types";
import type { ExecuteResponse } from "../lib/sidecar";
import { sidecar } from "../lib/sidecar";

interface Props {
  extractors: Extractor[];
  onChange: (extractors: Extractor[]) => void;
  response: ExecuteResponse | null;
}

const SOURCES: Extractor["source"][] = ["body", "header", "status"];

export function ExtractorsPanel({ extractors, onChange, response }: Props) {
  const [extractedValues, setExtractedValues] = useState<Record<string, string | null>>({});
  const [busy, setBusy] = useState(false);

  function addRow() {
    onChange([...extractors, { name: "", source: "body", path: "" }]);
  }

  function removeRow(index: number) {
    onChange(extractors.filter((_, i) => i !== index));
  }

  function updateRow(index: number, patch: Partial<Extractor>) {
    onChange(extractors.map((ex, i) => (i === index ? { ...ex, ...patch } : ex)));
  }

  async function runExtract() {
    if (!response) return;
    const validRules = extractors.filter((ex) => ex.name.trim());
    if (validRules.length === 0) return;

    setBusy(true);
    try {
      const result = await sidecar.extractVariables({
        response_body: response.body,
        response_headers: response.headers,
        response_status: response.status,
        rules: validRules.map((ex) => ({
          name: ex.name,
          source: ex.source,
          path: ex.path,
        })),
      });
      setExtractedValues(result.extracted);
    } catch {
      // silently ignore — user can retry
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <p className="text-[11px] uppercase tracking-widest text-neutral-500">
          Response Extractors
          <span className="ml-2 normal-case text-neutral-600">
            Capture values for chaining
          </span>
        </p>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={runExtract}
            disabled={!response || extractors.length === 0 || busy}
            className="flex items-center gap-1.5 rounded-md bg-cobweb-500/20 px-2.5 py-1 text-[11px] font-medium text-cobweb-400 transition-colors hover:bg-cobweb-500/30 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Play size={12} />
            Extract
          </button>
          <button
            type="button"
            onClick={addRow}
            className="flex items-center gap-1.5 rounded-md bg-white/[0.06] px-2.5 py-1 text-[11px] font-medium text-neutral-400 transition-colors hover:bg-white/[0.1] hover:text-neutral-200"
          >
            <Plus size={12} />
            Add
          </button>
        </div>
      </div>

      {extractors.length === 0 ? (
        <div className="flex items-center justify-center rounded-lg border border-dashed border-neutral-800 py-8">
          <p className="text-[12px] text-neutral-600">
            No extractors configured. Add one to capture response values.
          </p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-glass">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="border-b border-glass bg-neutral-900/60">
                <th className="px-3 py-2 text-left text-[11px] font-medium uppercase tracking-wider text-neutral-500">
                  Variable Name
                </th>
                <th className="px-3 py-2 text-left text-[11px] font-medium uppercase tracking-wider text-neutral-500">
                  Source
                </th>
                <th className="px-3 py-2 text-left text-[11px] font-medium uppercase tracking-wider text-neutral-500">
                  Path
                </th>
                <th className="px-3 py-2 text-left text-[11px] font-medium uppercase tracking-wider text-neutral-500">
                  Value
                </th>
                <th className="w-10 px-2 py-2" />
              </tr>
            </thead>
            <tbody>
              {extractors.map((ex, i) => (
                <tr
                  key={i}
                  className="border-b border-glass/50 last:border-b-0 hover:bg-white/[0.02]"
                >
                  <td className="px-2 py-1.5">
                    <input
                      type="text"
                      value={ex.name}
                      onChange={(e) => updateRow(i, { name: e.target.value })}
                      placeholder="e.g. auth_token"
                      className="w-full rounded border border-glass bg-neutral-900/50 px-2 py-1 text-[12px] text-neutral-100 placeholder:text-neutral-600 outline-none focus:border-cobweb-500/50"
                    />
                  </td>
                  <td className="px-2 py-1.5">
                    <select
                      value={ex.source}
                      onChange={(e) =>
                        updateRow(i, {
                          source: e.target.value as Extractor["source"],
                        })
                      }
                      className="w-full rounded border border-glass bg-neutral-900/50 px-2 py-1 text-[12px] text-neutral-100 outline-none focus:border-cobweb-500/50"
                    >
                      {SOURCES.map((s) => (
                        <option key={s} value={s}>
                          {s}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-2 py-1.5">
                    <input
                      type="text"
                      value={ex.path}
                      onChange={(e) => updateRow(i, { path: e.target.value })}
                      placeholder={
                        ex.source === "body"
                          ? "e.g. data.token"
                          : ex.source === "header"
                          ? "e.g. X-Request-Id"
                          : ""
                      }
                      disabled={ex.source === "status"}
                      className="w-full rounded border border-glass bg-neutral-900/50 px-2 py-1 text-[12px] text-neutral-100 placeholder:text-neutral-600 outline-none focus:border-cobweb-500/50 disabled:opacity-40"
                    />
                  </td>
                  <td className="px-2 py-1.5">
                    <span className="inline-block max-w-[200px] truncate text-[12px] text-neutral-400">
                      {extractedValues[ex.name] != null
                        ? extractedValues[ex.name]
                        : "\u2014"}
                    </span>
                  </td>
                  <td className="px-2 py-1.5 text-center">
                    <button
                      type="button"
                      onClick={() => removeRow(i)}
                      className="rounded p-1 text-neutral-600 transition-colors hover:bg-rose-500/10 hover:text-rose-400"
                    >
                      <Trash2 size={13} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!response && extractors.length > 0 && (
        <p className="text-[11px] text-neutral-600">
          Send a request first, then click Extract to capture values.
        </p>
      )}
    </div>
  );
}
