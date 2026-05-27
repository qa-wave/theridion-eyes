import { useState, useCallback } from "react";
import { CodeEditor } from "./CodeEditor";
import { sidecar, type SchemaValidateOutput, type SchemaDiffOutput } from "../lib/sidecar";
import { CheckCircle, XCircle, Wand2, GitCompare, Loader2 } from "lucide-react";

interface Props {
  /** Pre-fill the body editor (e.g. from the last response). */
  initialBody?: string;
  /** Pre-fill the schema editor. */
  initialSchema?: string;
  onClose: () => void;
}

export function SchemaValidatorPanel({
  initialBody = "",
  initialSchema = "",
  onClose,
}: Props) {
  const [body, setBody] = useState(initialBody);
  const [schema, setSchema] = useState(initialSchema);
  const [result, setResult] = useState<SchemaValidateOutput | null>(null);
  const [diffResult, setDiffResult] = useState<SchemaDiffOutput | null>(null);
  const [diffOld, setDiffOld] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"validate" | "diff">("validate");

  const handleValidate = useCallback(async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const schemaValue = schema.trim().startsWith("{") ? JSON.parse(schema) : schema;
      const out = await sidecar.validateSchema(body, schemaValue);
      setResult(out);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [body, schema]);

  const handleGenerate = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const out = await sidecar.generateSchema(body);
      setSchema(JSON.stringify(out.schema, null, 2));
      setResult(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [body]);

  const handleDiff = useCallback(async () => {
    setLoading(true);
    setError(null);
    setDiffResult(null);
    try {
      const oldSchema = diffOld.trim().startsWith("{") ? JSON.parse(diffOld) : diffOld;
      const newSchema = schema.trim().startsWith("{") ? JSON.parse(schema) : schema;
      const out = await sidecar.diffSchemas(oldSchema, newSchema);
      setDiffResult(out);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [diffOld, schema]);

  const validationStatus = result
    ? result.valid
      ? "pass"
      : "fail"
    : null;

  return (
    <div className="flex h-full flex-col bg-neutral-950 text-neutral-200">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-neutral-800 px-4 py-2">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold">JSON Schema Validator</h2>
          {validationStatus === "pass" && (
            <span className="flex items-center gap-1 rounded bg-emerald-900/40 px-2 py-0.5 text-xs text-emerald-400">
              <CheckCircle size={12} /> Valid
            </span>
          )}
          {validationStatus === "fail" && (
            <span className="flex items-center gap-1 rounded bg-red-900/40 px-2 py-0.5 text-xs text-red-400">
              <XCircle size={12} /> Invalid ({result!.errors.length} error{result!.errors.length !== 1 ? "s" : ""})
            </span>
          )}
        </div>
        <button
          onClick={onClose}
          className="rounded px-2 py-1 text-xs text-neutral-500 hover:bg-neutral-800 hover:text-neutral-300"
        >
          Close
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-neutral-800 px-4">
        <button
          onClick={() => setTab("validate")}
          className={`px-3 py-1.5 text-xs font-medium ${
            tab === "validate"
              ? "border-b-2 border-emerald-500 text-emerald-400"
              : "text-neutral-500 hover:text-neutral-300"
          }`}
        >
          Validate
        </button>
        <button
          onClick={() => setTab("diff")}
          className={`px-3 py-1.5 text-xs font-medium ${
            tab === "diff"
              ? "border-b-2 border-emerald-500 text-emerald-400"
              : "text-neutral-500 hover:text-neutral-300"
          }`}
        >
          Schema Diff
        </button>
      </div>

      {tab === "validate" ? (
        <>
          {/* Toolbar */}
          <div className="flex items-center gap-2 border-b border-neutral-800 px-4 py-2">
            <button
              onClick={handleValidate}
              disabled={loading || !body.trim() || !schema.trim()}
              className="flex items-center gap-1.5 rounded bg-emerald-600 px-3 py-1 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-40"
            >
              {loading ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle size={12} />}
              Validate
            </button>
            <button
              onClick={handleGenerate}
              disabled={loading || !body.trim()}
              className="flex items-center gap-1.5 rounded bg-neutral-800 px-3 py-1 text-xs font-medium text-neutral-300 hover:bg-neutral-700 disabled:opacity-40"
            >
              <Wand2 size={12} />
              Generate Schema
            </button>
          </div>

          {/* Split editors */}
          <div className="flex flex-1 min-h-0">
            <div className="flex flex-1 flex-col border-r border-neutral-800">
              <div className="px-3 py-1.5 text-[10px] uppercase tracking-wider text-neutral-600">
                JSON Body
              </div>
              <div className="flex-1 min-h-0">
                <CodeEditor
                  value={body}
                  onChange={setBody}
                  language="json"
                  placeholder='Paste a JSON body to validate...'
                />
              </div>
            </div>
            <div className="flex flex-1 flex-col">
              <div className="px-3 py-1.5 text-[10px] uppercase tracking-wider text-neutral-600">
                JSON Schema
              </div>
              <div className="flex-1 min-h-0">
                <CodeEditor
                  value={schema}
                  onChange={setSchema}
                  language="json"
                  placeholder='Paste or generate a JSON Schema...'
                />
              </div>
            </div>
          </div>

          {/* Errors list */}
          {error && (
            <div className="border-t border-red-900/50 bg-red-950/30 px-4 py-2 text-xs text-red-400">
              {error}
            </div>
          )}
          {result && !result.valid && (
            <div className="max-h-48 overflow-auto border-t border-neutral-800">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-neutral-800 text-left text-neutral-500">
                    <th className="px-4 py-1.5 font-medium">Path</th>
                    <th className="px-4 py-1.5 font-medium">Message</th>
                    <th className="px-4 py-1.5 font-medium">Schema Path</th>
                  </tr>
                </thead>
                <tbody>
                  {result.errors.map((err, i) => (
                    <tr key={i} className="border-b border-neutral-800/50 hover:bg-neutral-900">
                      <td className="px-4 py-1.5 font-mono text-red-400">{err.path}</td>
                      <td className="px-4 py-1.5 text-neutral-300">{err.message}</td>
                      <td className="px-4 py-1.5 font-mono text-neutral-500">{err.schema_path}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      ) : (
        <>
          {/* Diff toolbar */}
          <div className="flex items-center gap-2 border-b border-neutral-800 px-4 py-2">
            <button
              onClick={handleDiff}
              disabled={loading || !diffOld.trim() || !schema.trim()}
              className="flex items-center gap-1.5 rounded bg-emerald-600 px-3 py-1 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-40"
            >
              {loading ? <Loader2 size={12} className="animate-spin" /> : <GitCompare size={12} />}
              Compare Schemas
            </button>
          </div>

          {/* Diff split editors */}
          <div className="flex flex-1 min-h-0">
            <div className="flex flex-1 flex-col border-r border-neutral-800">
              <div className="px-3 py-1.5 text-[10px] uppercase tracking-wider text-neutral-600">
                Old Schema
              </div>
              <div className="flex-1 min-h-0">
                <CodeEditor
                  value={diffOld}
                  onChange={setDiffOld}
                  language="json"
                  placeholder='Paste old JSON Schema...'
                />
              </div>
            </div>
            <div className="flex flex-1 flex-col">
              <div className="px-3 py-1.5 text-[10px] uppercase tracking-wider text-neutral-600">
                New Schema
              </div>
              <div className="flex-1 min-h-0">
                <CodeEditor
                  value={schema}
                  onChange={setSchema}
                  language="json"
                  placeholder='Paste new JSON Schema...'
                />
              </div>
            </div>
          </div>

          {/* Diff results */}
          {error && (
            <div className="border-t border-red-900/50 bg-red-950/30 px-4 py-2 text-xs text-red-400">
              {error}
            </div>
          )}
          {diffResult && (
            <div className="max-h-48 overflow-auto border-t border-neutral-800">
              {diffResult.added.length === 0 &&
                diffResult.removed.length === 0 &&
                diffResult.changed.length === 0 && (
                  <div className="px-4 py-3 text-xs text-neutral-500">No differences found.</div>
                )}
              <table className="w-full text-xs">
                <tbody>
                  {diffResult.added.map((f, i) => (
                    <tr key={`a-${i}`} className="border-b border-neutral-800/50">
                      <td className="px-4 py-1.5">
                        <span className="rounded bg-emerald-900/40 px-1.5 py-0.5 text-emerald-400">added</span>
                      </td>
                      <td className="px-4 py-1.5 font-mono text-neutral-300">{f.path}</td>
                      <td className="px-4 py-1.5 text-neutral-500">{f.detail}</td>
                    </tr>
                  ))}
                  {diffResult.removed.map((f, i) => (
                    <tr key={`r-${i}`} className="border-b border-neutral-800/50">
                      <td className="px-4 py-1.5">
                        <span className="rounded bg-red-900/40 px-1.5 py-0.5 text-red-400">removed</span>
                      </td>
                      <td className="px-4 py-1.5 font-mono text-neutral-300">{f.path}</td>
                      <td className="px-4 py-1.5 text-neutral-500">{f.detail}</td>
                    </tr>
                  ))}
                  {diffResult.changed.map((f, i) => (
                    <tr key={`c-${i}`} className="border-b border-neutral-800/50">
                      <td className="px-4 py-1.5">
                        <span className="rounded bg-amber-900/40 px-1.5 py-0.5 text-amber-400">changed</span>
                      </td>
                      <td className="px-4 py-1.5 font-mono text-neutral-300">{f.path}</td>
                      <td className="px-4 py-1.5 text-neutral-500">{f.detail}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
