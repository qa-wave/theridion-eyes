/**
 * NewTestDialog — modal pro ruční vytvoření testovacího souboru.
 *
 * Obsahuje:
 *  - dropdown frameworku (načteno z /api/silk/frameworks)
 *  - Monaco editor s template kódem daného frameworku
 *  - pole filename + volitelný workspace dir
 *  - tlačítko Uložit → POST /api/silk/spec/save
 */

import { useEffect, useRef, useState } from "react";
import Editor from "@monaco-editor/react";
import { FileCode, RefreshCw, Save, X } from "lucide-react";
import { sidecar } from "../lib/sidecar";
import type { SilkFramework } from "../lib/sidecar/silk";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Mapuje framework id na Monaco language string. */
function frameworkToLanguage(id: string): string {
  if (id.startsWith("playwright-ts")) return "typescript";
  if (id.startsWith("playwright-js")) return "javascript";
  if (id === "cypress") return "javascript";
  if (id === "webdriverio") return "javascript";
  if (id.endsWith("-python") || id === "selenium-python") return "python";
  if (id.endsWith("-java") || id === "selenium-java") return "java";
  if (id.endsWith("-csharp") || id === "selenium-csharp") return "csharp";
  if (id === "espresso") return "kotlin";
  if (id === "xcuitest") return "swift";
  if (id === "maestro") return "yaml";
  return "typescript";
}

/** Navrhne výchozí jméno souboru podle frameworku. */
function defaultFilename(fw: SilkFramework): string {
  // file_extension already includes the leading dot (e.g. ".spec.ts").
  return `my_test${fw.file_extension}`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface NewTestDialogProps {
  /** Volitelná callback po úspěšném uložení — spec_path výsledného souboru. */
  onSaved?: (specPath: string) => void;
  onCancel: () => void;
}

export function NewTestDialog({ onSaved, onCancel }: NewTestDialogProps) {
  const [frameworks, setFrameworks] = useState<SilkFramework[]>([]);
  const [loadingFrameworks, setLoadingFrameworks] = useState(true);
  const [frameworksError, setFrameworksError] = useState<string | null>(null);

  const [selectedFrameworkId, setSelectedFrameworkId] = useState<string>("playwright-ts");
  const [code, setCode] = useState<string>("");
  const [filename, setFilename] = useState<string>("my_test.spec.ts");
  const [workspaceDir, setWorkspaceDir] = useState<string>("");

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedPath, setSavedPath] = useState<string | null>(null);

  // Prevent re-setting code when user already edited it
  const userEditedCode = useRef(false);

  // Load frameworks on mount
  useEffect(() => {
    setLoadingFrameworks(true);
    setFrameworksError(null);
    sidecar
      .silkFrameworks()
      .then(({ frameworks: fws }) => {
        setFrameworks(fws);
        const initial = fws.find((f) => f.id === "playwright-ts") ?? fws[0];
        if (initial) {
          setSelectedFrameworkId(initial.id);
          setCode(initial.template);
          setFilename(defaultFilename(initial));
        }
      })
      .catch((e: unknown) => {
        setFrameworksError(e instanceof Error ? e.message : String(e));
        // Fallback: prázdný editor + default framework id
        setCode("// Framework templates not available — write your test manually");
      })
      .finally(() => setLoadingFrameworks(false));
  }, []);

  const selectedFramework = frameworks.find((f) => f.id === selectedFrameworkId) ?? null;

  // When framework changes, load its template (unless user already edited)
  const handleFrameworkChange = (id: string) => {
    setSelectedFrameworkId(id);
    setSaveError(null);
    setSavedPath(null);
    const fw = frameworks.find((f) => f.id === id);
    if (fw) {
      if (!userEditedCode.current) {
        setCode(fw.template);
      }
      setFilename(defaultFilename(fw));
      userEditedCode.current = false;
    }
  };

  const handleCodeChange = (value: string | undefined) => {
    userEditedCode.current = true;
    setCode(value ?? "");
  };

  const handleSave = async () => {
    if (!filename.trim() || !selectedFrameworkId) return;
    setSaving(true);
    setSaveError(null);
    setSavedPath(null);
    try {
      const res = await sidecar.silkSpecSave({
        framework: selectedFrameworkId,
        filename: filename.trim(),
        code,
        workspace_dir: workspaceDir.trim() || undefined,
      });
      setSavedPath(res.spec_path);
      onSaved?.(res.spec_path);
    } catch (e: unknown) {
      setSaveError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const language = frameworkToLanguage(selectedFrameworkId);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="flex w-[780px] max-h-[90vh] flex-col rounded-lg border border-neutral-800 bg-neutral-925 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-neutral-800 px-5 py-3 shrink-0">
          <div className="flex items-center gap-2 text-neutral-100">
            <FileCode size={16} className="text-emerald-400" />
            <h2 className="font-semibold text-sm">Nový test (ruční tvorba)</h2>
          </div>
          <button
            onClick={onCancel}
            className="text-neutral-500 hover:text-neutral-300 transition-colors"
            aria-label="Zavřít"
          >
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="flex flex-1 min-h-0 flex-col gap-4 overflow-y-auto p-5">
          {/* Row: framework + filename + workspace */}
          <div className="flex gap-3 items-end flex-wrap">
            {/* Framework select */}
            <div className="flex flex-col gap-1 min-w-[200px]">
              <label className="text-xs text-neutral-500">Framework</label>
              {loadingFrameworks ? (
                <div className="flex items-center gap-1.5 text-xs text-neutral-500 h-7">
                  <RefreshCw size={11} className="animate-spin" />
                  Načítám…
                </div>
              ) : (
                <select
                  value={selectedFrameworkId}
                  onChange={(e) => handleFrameworkChange(e.target.value)}
                  className="rounded bg-neutral-950 border border-neutral-800 px-3 py-1.5 text-xs text-neutral-200 focus:outline-none focus:border-emerald-600 transition-colors"
                >
                  {frameworks.length === 0 ? (
                    <option value="playwright-ts">playwright-ts (default)</option>
                  ) : (
                    <>
                      {/* Group by kind */}
                      {["web", "mobile"].map((kind) => {
                        const group = frameworks.filter((f) => f.kind === kind);
                        if (group.length === 0) return null;
                        return (
                          <optgroup
                            key={kind}
                            label={kind === "web" ? "Web" : "Mobile"}
                          >
                            {group.map((f) => (
                              <option key={f.id} value={f.id}>
                                {f.label}
                              </option>
                            ))}
                          </optgroup>
                        );
                      })}
                    </>
                  )}
                </select>
              )}
              {frameworksError && (
                <span className="text-[10px] text-amber-400">
                  Nelze načíst seznam frameworků
                </span>
              )}
            </div>

            {/* Filename */}
            <div className="flex flex-col gap-1 flex-1 min-w-[180px]">
              <label className="text-xs text-neutral-500">Název souboru</label>
              <input
                value={filename}
                onChange={(e) => setFilename(e.target.value)}
                placeholder="my_test.spec.ts"
                className="rounded bg-neutral-950 border border-neutral-800 px-3 py-1.5 text-xs text-neutral-200 placeholder-neutral-600 focus:outline-none focus:border-emerald-600 transition-colors"
                spellCheck={false}
              />
            </div>

            {/* Workspace dir */}
            <div className="flex flex-col gap-1 flex-1 min-w-[180px]">
              <label className="text-xs text-neutral-500">Workspace dir (volitelné)</label>
              <input
                value={workspaceDir}
                onChange={(e) => setWorkspaceDir(e.target.value)}
                placeholder="/path/to/project"
                className="rounded bg-neutral-950 border border-neutral-800 px-3 py-1.5 text-xs text-neutral-200 placeholder-neutral-600 focus:outline-none focus:border-emerald-600 transition-colors"
                spellCheck={false}
              />
            </div>
          </div>

          {/* Monaco editor */}
          <div className="flex flex-col gap-1 flex-1 min-h-[300px]">
            <div className="flex items-center justify-between">
              <label className="text-xs text-neutral-500">
                Kód testu
                <span className="ml-2 text-neutral-700">({language})</span>
              </label>
              {selectedFramework && (
                <button
                  type="button"
                  onClick={() => {
                    setCode(selectedFramework.template);
                    userEditedCode.current = false;
                  }}
                  className="text-[10px] text-neutral-600 hover:text-neutral-400 transition-colors"
                >
                  Obnovit template
                </button>
              )}
            </div>
            <div className="flex-1 rounded border border-neutral-800 overflow-hidden min-h-[300px]">
              <Editor
                height="100%"
                defaultLanguage={language}
                language={language}
                value={code}
                onChange={handleCodeChange}
                theme="vs-dark"
                options={{
                  fontSize: 12,
                  minimap: { enabled: false },
                  scrollBeyondLastLine: false,
                  wordWrap: "on",
                  lineNumbers: "on",
                  renderLineHighlight: "gutter",
                  tabSize: 2,
                }}
              />
            </div>
          </div>

          {/* Success / error messages */}
          {savedPath && (
            <div className="flex items-start gap-2 rounded border border-emerald-800 bg-emerald-950/40 px-3 py-2.5 text-xs text-emerald-300">
              <Save size={12} className="mt-0.5 shrink-0" />
              <span>
                Uloženo: <span className="font-mono text-emerald-200 break-all">{savedPath}</span>
              </span>
            </div>
          )}
          {saveError && (
            <div className="rounded border border-red-800 bg-red-950/40 px-3 py-2 text-xs text-red-400">
              {saveError}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-neutral-800 px-5 py-3 shrink-0">
          <span className="text-[10px] text-neutral-600">
            {selectedFramework
              ? `${selectedFramework.label} · ${selectedFramework.file_extension}`
              : ""}
          </span>
          <div className="flex gap-2">
            <button
              onClick={onCancel}
              className="rounded px-3 py-1.5 text-xs bg-neutral-800 hover:bg-neutral-700 text-neutral-300 transition-colors"
            >
              Zavřít
            </button>
            <button
              onClick={() => void handleSave()}
              disabled={saving || !filename.trim()}
              className="flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium bg-emerald-700 hover:bg-emerald-600 disabled:opacity-40 disabled:cursor-not-allowed text-white transition-colors"
            >
              {saving ? (
                <RefreshCw size={11} className="animate-spin" />
              ) : (
                <Save size={11} />
              )}
              {saving ? "Ukládám…" : "Uložit"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
