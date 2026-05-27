import { useState } from "react";
import { Play, ChevronDown } from "lucide-react";
import { CodeEditor } from "./CodeEditor";
import { sidecar } from "../lib/sidecar";
import type { ScriptAssertionItem, ExecuteResponse } from "../lib/sidecar";

type Phase = "pre" | "post";

interface Props {
  preRequestScript: string;
  onPreRequestScriptChange: (s: string) => void;
  postResponseScript: string;
  onPostResponseScriptChange: (s: string) => void;
  /** The latest response — needed to build post-response context. */
  response?: ExecuteResponse | null;
  /** Current environment variables — seeded into script context. */
  envVars?: Record<string, string>;
}

interface RunResult {
  variables: Record<string, string>;
  headers: Record<string, string>;
  logs: string[];
  assertions: ScriptAssertionItem[];
  error: string | null;
}

const SNIPPETS: Record<Phase, { label: string; code: string }[]> = {
  pre: [
    { label: "Set header", code: 'setHeader("Authorization", "Bearer " + get("token"))' },
    { label: "Set variable", code: 'set("timestamp", "{{$timestamp}}")' },
    { label: "Log variable", code: 'log("Current token:", get("token"))' },
  ],
  post: [
    { label: "Extract from JSON", code: 'set("userId", response.json.data.id)' },
    { label: "Assert status 200", code: 'assert(response.status, "Expected successful status")' },
    { label: "Log response body", code: 'log("Response:", response.body)' },
    { label: "Save token", code: 'set("token", response.json.access_token)' },
  ],
};

const COMMANDS_HELP = [
  { fn: "set(key, value)", desc: "Store a variable for later use" },
  { fn: "get(key)", desc: "Retrieve a stored variable" },
  { fn: "log(...args)", desc: "Print to the output console" },
  { fn: 'assert(value, "msg")', desc: "Check a truthy condition" },
  { fn: "setHeader(name, value)", desc: "Set a request header (pre only)" },
];

export function ScriptsPanel({
  preRequestScript,
  onPreRequestScriptChange,
  postResponseScript,
  onPostResponseScriptChange,
  response,
  envVars,
}: Props) {
  const [phase, setPhase] = useState<Phase>("pre");
  const [result, setResult] = useState<RunResult | null>(null);
  const [running, setRunning] = useState(false);
  const [showHelp, setShowHelp] = useState(false);

  const script = phase === "pre" ? preRequestScript : postResponseScript;
  const onChange = phase === "pre" ? onPreRequestScriptChange : onPostResponseScriptChange;

  async function runScript() {
    if (!script.trim()) return;
    setRunning(true);
    setResult(null);
    try {
      const context: Record<string, unknown> = {};
      if (envVars) context.env = envVars;
      if (phase === "post" && response) {
        let jsonBody: unknown = null;
        try { jsonBody = JSON.parse(response.body); } catch { /* not JSON */ }
        context.response = {
          status: response.status,
          headers: response.headers,
          body: response.body,
          elapsed_ms: response.elapsed_ms,
          json: jsonBody,
        };
      }
      const out = await sidecar.executeScriptSafe({ script, phase, context });
      setResult(out);
    } catch (err) {
      setResult({
        variables: {},
        headers: {},
        logs: [],
        assertions: [],
        error: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setRunning(false);
    }
  }

  function insertSnippet(code: string) {
    onChange(script ? script + "\n" + code : code);
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      {/* Phase toggle + actions */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1">
          <div className="flex rounded-md border border-glass overflow-hidden text-[11px]">
            <button
              type="button"
              onClick={() => { setPhase("pre"); setResult(null); }}
              className={`px-3 py-1 transition ${
                phase === "pre"
                  ? "bg-cobweb-600/20 text-cobweb-400"
                  : "text-neutral-500 hover:text-neutral-300 hover:bg-neutral-800/40"
              }`}
            >
              Pre-request
            </button>
            <button
              type="button"
              onClick={() => { setPhase("post"); setResult(null); }}
              className={`px-3 py-1 transition ${
                phase === "post"
                  ? "bg-cobweb-600/20 text-cobweb-400"
                  : "text-neutral-500 hover:text-neutral-300 hover:bg-neutral-800/40"
              }`}
            >
              Post-response
            </button>
          </div>
          <span className="ml-2 text-[11px] text-neutral-600">
            {phase === "pre" ? "Runs before each send" : "Runs after response"}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <SnippetsDropdown snippets={SNIPPETS[phase]} onInsert={insertSnippet} />
          <button
            type="button"
            onClick={() => setShowHelp((h) => !h)}
            className={`rounded-md border border-glass px-2 py-0.5 text-[11px] transition ${
              showHelp ? "bg-cobweb-600/20 text-cobweb-400" : "text-neutral-500 hover:text-neutral-300"
            }`}
          >
            Commands
          </button>
          <button
            type="button"
            onClick={() => void runScript()}
            disabled={running || !script.trim()}
            className="inline-flex items-center gap-1 rounded-md bg-cobweb-600/20 px-2.5 py-1 text-[11px] font-medium text-cobweb-400 transition hover:bg-cobweb-600/30 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Play className="h-3 w-3" />
            {running ? "Running..." : "Run"}
          </button>
        </div>
      </div>

      {/* Commands reference sidebar */}
      {showHelp && (
        <div className="rounded-lg border border-glass bg-neutral-900/50 p-3">
          <p className="mb-2 text-[11px] font-medium uppercase tracking-widest text-neutral-500">
            Available commands
          </p>
          <div className="space-y-1.5">
            {COMMANDS_HELP.map((cmd) => (
              <div key={cmd.fn} className="flex items-baseline gap-3">
                <code className="shrink-0 rounded bg-neutral-800/50 px-1.5 py-0.5 font-mono text-[11px] text-cobweb-400">
                  {cmd.fn}
                </code>
                <span className="text-[11px] text-neutral-500">{cmd.desc}</span>
              </div>
            ))}
          </div>
          <p className="mt-2 text-[10px] text-neutral-600">
            Use dot notation for context access: <code className="text-neutral-500">response.json.data.id</code>,{" "}
            <code className="text-neutral-500">response.status</code>
          </p>
        </div>
      )}

      {/* Editor */}
      <div className="min-h-[180px] flex-1 overflow-hidden rounded-lg border border-glass bg-neutral-900/50">
        <CodeEditor
          value={script}
          onChange={onChange}
          language="javascript"
          placeholder={
            phase === "pre"
              ? '// set("token", "value")\n// setHeader("Authorization", "Bearer " + get("token"))'
              : '// set("userId", response.json.data.id)\n// assert(response.status, "Expected 200")'
          }
        />
      </div>

      {/* Output panel */}
      {result && (
        <div className="max-h-[200px] overflow-auto rounded-lg border border-glass bg-neutral-950/60 p-3">
          <p className="mb-1.5 text-[10px] font-medium uppercase tracking-widest text-neutral-600">
            Output
          </p>
          <div className="space-y-1 font-mono text-[11px]">
            {/* Logs */}
            {result.logs.map((log, i) => (
              <div key={`log-${i}`} className="text-neutral-400">
                <span className="mr-1.5 text-neutral-600">LOG</span>
                {log}
              </div>
            ))}
            {/* Assertions */}
            {result.assertions.map((a, i) => (
              <div
                key={`assert-${i}`}
                className={a.passed ? "text-emerald-400" : "text-rose-400"}
              >
                <span className="mr-1">{a.passed ? "\u2713" : "\u2717"}</span>
                {a.message}
              </div>
            ))}
            {/* Variables set */}
            {Object.keys(result.variables).length > 0 && (
              <div className="mt-1 border-t border-glass/50 pt-1">
                <span className="text-neutral-600">Variables set:</span>
                {Object.entries(result.variables).map(([k, v]) => (
                  <div key={k} className="ml-3 text-neutral-400">
                    <span className="text-cobweb-400">{k}</span>
                    <span className="text-neutral-600"> = </span>
                    <span className="text-emerald-300">{v}</span>
                  </div>
                ))}
              </div>
            )}
            {/* Headers set */}
            {Object.keys(result.headers).length > 0 && (
              <div className="mt-1 border-t border-glass/50 pt-1">
                <span className="text-neutral-600">Headers set:</span>
                {Object.entries(result.headers).map(([k, v]) => (
                  <div key={k} className="ml-3 text-neutral-400">
                    <span className="text-amber-400">{k}</span>
                    <span className="text-neutral-600">: </span>
                    {v}
                  </div>
                ))}
              </div>
            )}
            {/* Error */}
            {result.error && (
              <div className="mt-1 text-rose-400">
                <span className="mr-1">ERROR</span>
                {result.error}
              </div>
            )}
            {/* Empty state */}
            {!result.error && result.logs.length === 0 && result.assertions.length === 0 &&
             Object.keys(result.variables).length === 0 && Object.keys(result.headers).length === 0 && (
              <div className="text-neutral-600">Script executed with no output.</div>
            )}
          </div>
        </div>
      )}

      {/* Empty state help */}
      {!script.trim() && !result && (
        <p className="text-[11px] leading-relaxed text-neutral-600">
          {phase === "pre"
            ? "Write commands that run before each request. Set headers, generate tokens, or prepare variables."
            : "Write commands that run after receiving a response. Extract values, validate assertions, or log data."}
        </p>
      )}
    </div>
  );
}

function SnippetsDropdown({
  snippets,
  onInsert,
}: {
  snippets: { label: string; code: string }[];
  onInsert: (code: string) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1 rounded-md border border-glass px-2 py-0.5 text-[11px] text-neutral-500 transition hover:bg-white/[0.04] hover:text-neutral-300"
      >
        Snippets
        <ChevronDown className="h-3 w-3" />
      </button>
      {open && (
        <div className="absolute right-0 top-full z-20 mt-1 w-64 rounded-md border border-neutral-700 bg-neutral-900 py-1 shadow-lg">
          {snippets.map((s) => (
            <button
              key={s.label}
              type="button"
              onClick={() => { onInsert(s.code); setOpen(false); }}
              className="w-full px-3 py-1.5 text-left text-xs text-neutral-300 hover:bg-neutral-800"
            >
              {s.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
