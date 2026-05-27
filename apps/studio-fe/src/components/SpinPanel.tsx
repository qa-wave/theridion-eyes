/**
 * SpinPanel — Automated backend testing module UI.
 *
 * Layout:
 *   Left sidebar — scenario list (discovered .spin.yaml files)
 *   Center — Monaco YAML editor for the selected scenario
 *   Right — Run trace: per-step status, assertions, captured vars
 *
 * Features:
 *   - Discover .spin.yaml files in workspace
 *   - New scenario via template picker
 *   - Dry-run validation (no execution) on YAML change
 *   - Run scenario — real-time per-step status display
 *   - Verify Pact contracts against provider URL
 *   - Schema validation panel
 *   - DB snapshot/compare panel
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  Circle,
  Code2,
  Database,
  FileCode2,
  FilePlus,
  Loader2,
  Play,
  RefreshCw,
  Shield,
  Timer,
  Workflow,
  XCircle,
  Zap,
} from "lucide-react";
import { sidecar } from "../lib/sidecar";
import { EmptyState } from "./EmptyState";
import type {
  SpinRunResult,
  SpinScenarioInfo,
  SpinStepResult,
  SpinDryRunOutput,
} from "../lib/sidecar/spin";

// ---------------------------------------------------------------------------
// Constants + helpers
// ---------------------------------------------------------------------------

const SPIN_ACCENT = "#a3e635"; // lime-400 — Spin brand accent

const SCENARIO_TEMPLATES: Record<string, string> = {
  "HTTP Workflow": `name: "My HTTP workflow"
environment: staging
variables:
  api_url: https://api.example.com
steps:
  - name: "Health check"
    http_request:
      method: GET
      url: "{{api_url}}/health"
    assert:
      status: 200
      response_time_lt: 500
`,
  "Pact Contract": `name: "Contract verification"
environment: staging
steps:
  - name: "Verify order creation"
    http_request:
      method: POST
      url: "{{api_url}}/orders"
      body:
        user_id: 1
        items: []
    assert:
      status: 201
      schema: "openapi://createOrder"
`,
  "DB Integration": `name: "Database state test"
environment: staging
variables:
  db_url: "postgresql://user:pass@localhost:5432/app"
  api_url: https://api.example.com
setup:
  - db.snapshot:
      connection_string: "{{db_url}}"
      table: orders
steps:
  - name: "Create entity"
    http_request:
      method: POST
      url: "{{api_url}}/orders"
      body:
        user_id: 42
      capture:
        order_id: "$.id"
    assert:
      status: 201
  - name: "Verify DB state"
    sql_assert:
      connection_string: "{{db_url}}"
      query: "SELECT status FROM orders WHERE id = {{order_id}}"
      expect:
        status: pending
teardown:
  - db.expect_changes:
      connection_string: "{{db_url}}"
      table: orders
      delta: 1
`,
  "Kafka Pipeline": `name: "Kafka message pipeline"
environment: staging
variables:
  api_url: https://api.example.com
  kafka: "localhost:9092"
steps:
  - name: "Trigger action"
    http_request:
      method: POST
      url: "{{api_url}}/actions"
      body:
        type: user_created
        user_id: 42
      capture:
        action_id: "$.id"
    assert:
      status: 202
  - name: "Wait for processing"
    wait_seconds: 2
  - name: "Verify event on queue"
    kafka_consume_assert:
      bootstrap_servers: "{{kafka}}"
      topic: "user.events"
      timeout_seconds: 5
      payload_contains:
        action_id: "{{action_id}}"
`,
};

function statusIcon(status: string, size = 14) {
  switch (status) {
    case "passed":
      return <CheckCircle2 size={size} className="text-lime-400" />;
    case "failed":
      return <XCircle size={size} className="text-red-400" />;
    case "error":
      return <AlertCircle size={size} className="text-orange-400" />;
    case "running":
      return <Loader2 size={size} className="animate-spin text-lime-400" />;
    default:
      return <Circle size={size} className="text-neutral-500" />;
  }
}

function durationLabel(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ScenarioListItem({
  info,
  active,
  onSelect,
}: {
  info: SpinScenarioInfo;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      onClick={onSelect}
      className={`w-full text-left px-3 py-2 rounded transition-colors group ${
        active ? "bg-white/[0.08]" : "hover:bg-white/[0.04]"
      }`}
    >
      <div className="flex items-center gap-2">
        <FileCode2
          size={13}
          className={info.valid ? "text-lime-400/70" : "text-red-400/70"}
        />
        <span className="truncate text-xs font-medium text-neutral-200">
          {info.name ?? info.relative_path}
        </span>
        {!info.valid && (
          <AlertCircle size={11} className="ml-auto shrink-0 text-red-400" />
        )}
      </div>
      <div className="mt-0.5 pl-5 flex items-center gap-2">
        <span className="text-[10px] text-neutral-500">
          {info.step_count} {info.step_count === 1 ? "step" : "steps"}
        </span>
        {info.environment && (
          <span className="text-[10px] text-neutral-600">{info.environment}</span>
        )}
      </div>
    </button>
  );
}

function StepResultRow({ result }: { result: SpinStepResult }) {
  const [expanded, setExpanded] = useState(false);
  const hasDetail =
    result.assertions.length > 0 ||
    result.error ||
    Object.keys(result.captured_vars).length > 0;

  return (
    <div className="border border-white/[0.06] rounded-md overflow-hidden">
      <button
        onClick={() => hasDetail && setExpanded((v) => !v)}
        className={`w-full text-left flex items-center gap-2 px-3 py-2 transition-colors ${
          hasDetail ? "hover:bg-white/[0.03]" : ""
        }`}
      >
        {statusIcon(result.status)}
        <span className="flex-1 text-xs text-neutral-200 truncate">{result.step_name}</span>
        <span className="text-[10px] text-neutral-500 shrink-0">
          {durationLabel(result.duration_ms)}
        </span>
        <span className="text-[10px] text-neutral-600 shrink-0 w-16 text-right">
          {result.step_type}
        </span>
        {hasDetail && (
          <ChevronRight
            size={12}
            className={`text-neutral-500 shrink-0 transition-transform ${
              expanded ? "rotate-90" : ""
            }`}
          />
        )}
      </button>

      {expanded && hasDetail && (
        <div className="px-3 pb-3 space-y-2 border-t border-white/[0.06]">
          {result.error && (
            <div className="mt-2 text-xs text-red-400 bg-red-400/10 rounded px-2 py-1">
              {result.error}
            </div>
          )}

          {result.assertions.length > 0 && (
            <div className="mt-2 space-y-1">
              {result.assertions.map((a, i) => (
                <div key={i} className="flex items-start gap-2 text-[11px]">
                  {a.passed ? (
                    <CheckCircle2 size={11} className="text-lime-400 mt-0.5 shrink-0" />
                  ) : (
                    <XCircle size={11} className="text-red-400 mt-0.5 shrink-0" />
                  )}
                  <span className="text-neutral-400 font-mono">{a.name}</span>
                  {!a.passed && (
                    <span className="text-neutral-500 ml-auto">
                      expected{" "}
                      <span className="text-emerald-400">{String(a.expected)}</span>{" "}
                      got{" "}
                      <span className="text-red-400">{String(a.actual)}</span>
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}

          {Object.keys(result.captured_vars).length > 0 && (
            <div className="mt-2">
              <div className="text-[10px] text-neutral-500 mb-1">Captured variables</div>
              {Object.entries(result.captured_vars).map(([k, v]) => (
                <div key={k} className="flex gap-2 text-[11px] font-mono">
                  <span className="text-lime-400">{"{{" + k + "}}"}</span>
                  <span className="text-neutral-400">=</span>
                  <span className="text-neutral-200">{String(v)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function RunSummaryBar({ result }: { result: SpinRunResult }) {
  const statusColor =
    result.status === "passed"
      ? "text-lime-400 bg-lime-400/10"
      : result.status === "failed"
      ? "text-red-400 bg-red-400/10"
      : "text-orange-400 bg-orange-400/10";

  return (
    <div className={`flex items-center gap-3 px-3 py-2 rounded-md text-xs ${statusColor}`}>
      {statusIcon(result.status, 14)}
      <span className="font-medium">{result.status.toUpperCase()}</span>
      <span className="text-neutral-400">·</span>
      <span className="text-neutral-300">
        {result.passed_steps}/{result.total_steps} steps passed
      </span>
      <span className="text-neutral-400">·</span>
      <span className="text-neutral-300">{durationLabel(result.duration_ms)}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Panel
// ---------------------------------------------------------------------------

export function SpinPanel() {
  const [scenarios, setScenarios] = useState<SpinScenarioInfo[]>([]);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [editorContent, setEditorContent] = useState("");
  const [dryRunResult, setDryRunResult] = useState<SpinDryRunOutput | null>(null);
  const [runResult, setRunResult] = useState<SpinRunResult | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [showTemplates, setShowTemplates] = useState(false);
  const [activeTab, setActiveTab] = useState<"trace" | "contracts" | "schema" | "db">("trace");
  const dryRunTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Load scenario list
  const refreshScenarios = useCallback(async () => {
    try {
      const result = await sidecar.listScenarios();
      setScenarios(result.scenarios);
    } catch {
      // Silently fail — workspace dir may not have any spin files
    }
  }, []);

  useEffect(() => {
    refreshScenarios();
  }, [refreshScenarios]);

  // Auto dry-run on editor change
  useEffect(() => {
    if (!editorContent.trim()) {
      setDryRunResult(null);
      return;
    }
    if (dryRunTimer.current) clearTimeout(dryRunTimer.current);
    dryRunTimer.current = setTimeout(async () => {
      try {
        const result = await sidecar.dryRunWorkflow(editorContent);
        setDryRunResult(result);
      } catch {
        // Ignore transient errors
      }
    }, 800);
    return () => {
      if (dryRunTimer.current) clearTimeout(dryRunTimer.current);
    };
  }, [editorContent]);

  const handleSelectScenario = useCallback(async (path: string) => {
    setSelectedPath(path);
    setRunResult(null);
    // We can't read the file directly from frontend — show a placeholder
    setEditorContent(`# Loading scenario: ${path}\n# Run to execute it.`);
  }, []);

  const handleRunScenario = useCallback(async () => {
    if (!selectedPath) return;
    setIsRunning(true);
    setRunResult(null);
    try {
      const result = await sidecar.runScenario(selectedPath, {});
      setRunResult(result);
    } catch (err) {
      setRunResult({
        scenario_name: selectedPath,
        status: "error",
        total_steps: 0,
        passed_steps: 0,
        failed_steps: 0,
        duration_ms: 0,
        steps: [],
        setup_results: [],
        teardown_results: [],
        error: String(err),
      });
    } finally {
      setIsRunning(false);
    }
  }, [selectedPath]);

  const handleNewScenario = useCallback((templateName: string) => {
    setEditorContent(SCENARIO_TEMPLATES[templateName] ?? "");
    setSelectedPath(null);
    setRunResult(null);
    setShowTemplates(false);
  }, []);

  return (
    <div className="flex h-full overflow-hidden">
      {/* ── Left sidebar: scenario list ─────────────────────────────────── */}
      <div className="flex w-56 shrink-0 flex-col border-r border-white/[0.06] bg-neutral-950">
        <div className="flex items-center justify-between px-3 py-2 border-b border-white/[0.06]">
          <div className="flex items-center gap-1.5">
            <Workflow size={13} style={{ color: SPIN_ACCENT }} />
            <span className="text-xs font-semibold text-neutral-200">Spin</span>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={refreshScenarios}
              className="p-1 rounded hover:bg-white/[0.06] text-neutral-500"
              title="Refresh"
            >
              <RefreshCw size={11} />
            </button>
            <button
              onClick={() => setShowTemplates((v) => !v)}
              className="p-1 rounded hover:bg-white/[0.06] text-neutral-500"
              title="New scenario"
            >
              <FilePlus size={11} />
            </button>
          </div>
        </div>

        {/* Template picker */}
        {showTemplates && (
          <div className="border-b border-white/[0.06] bg-neutral-925 p-2 space-y-1">
            <p className="text-[10px] text-neutral-500 px-1 mb-1">Choose template</p>
            {Object.keys(SCENARIO_TEMPLATES).map((name) => (
              <button
                key={name}
                onClick={() => handleNewScenario(name)}
                className="w-full text-left text-xs text-neutral-300 px-2 py-1 rounded hover:bg-white/[0.06] transition-colors"
              >
                {name}
              </button>
            ))}
          </div>
        )}

        {/* Scenario list */}
        <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
          {scenarios.length === 0 ? (
            <EmptyState
              icon={FileCode2}
              title="No .spin.yaml files found"
              description="Click + to create one"
            />
          ) : (
            scenarios.map((s) => (
              <ScenarioListItem
                key={s.path}
                info={s}
                active={selectedPath === s.path}
                onSelect={() => handleSelectScenario(s.path)}
              />
            ))
          )}
        </div>
      </div>

      {/* ── Center: YAML editor ─────────────────────────────────────────── */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Toolbar */}
        <div className="flex items-center gap-2 px-3 py-2 border-b border-white/[0.06] bg-neutral-925 shrink-0">
          <Code2 size={13} className="text-neutral-500" />
          <span className="text-xs text-neutral-400 flex-1 truncate">
            {selectedPath ?? "New scenario"}
          </span>

          {/* Dry-run validation indicator */}
          {dryRunResult && (
            <div className={`flex items-center gap-1 text-[10px] ${
              dryRunResult.valid ? "text-lime-400" : "text-red-400"
            }`}>
              {dryRunResult.valid ? (
                <CheckCircle2 size={11} />
              ) : (
                <XCircle size={11} />
              )}
              {dryRunResult.valid
                ? `Valid — ${dryRunResult.step_count} steps`
                : `${dryRunResult.errors.length} error(s)`}
            </div>
          )}

          <button
            onClick={handleRunScenario}
            disabled={isRunning || (!selectedPath && !editorContent)}
            className="flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-medium transition-colors disabled:opacity-40"
            style={{
              backgroundColor: isRunning ? undefined : `${SPIN_ACCENT}20`,
              color: SPIN_ACCENT,
              borderWidth: 1,
              borderColor: `${SPIN_ACCENT}40`,
            }}
          >
            {isRunning ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Play size={12} />
            )}
            {isRunning ? "Running..." : "Run"}
          </button>
        </div>

        {/* Dry-run errors */}
        {dryRunResult && !dryRunResult.valid && (
          <div className="px-3 py-2 bg-red-900/20 border-b border-red-900/30">
            {dryRunResult.errors.map((e, i) => (
              <div key={i} className="flex items-start gap-1.5 text-[11px] text-red-400">
                <AlertCircle size={11} className="mt-0.5 shrink-0" />
                {e}
              </div>
            ))}
          </div>
        )}

        {/* Monaco editor area — placeholder (Monaco loaded via CDN) */}
        <div className="flex-1 overflow-auto bg-neutral-950">
          {editorContent ? (
            <textarea
              value={editorContent}
              onChange={(e) => setEditorContent(e.target.value)}
              className="w-full h-full resize-none bg-transparent text-xs text-neutral-200 font-mono p-4 focus:outline-none"
              spellCheck={false}
              placeholder="Paste or type your .spin.yaml scenario here..."
            />
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-4 text-neutral-600">
              <Workflow size={40} style={{ color: `${SPIN_ACCENT}40` }} />
              <div className="text-center">
                <p className="text-sm text-neutral-400">No scenario selected</p>
                <p className="text-xs text-neutral-600 mt-1">
                  Pick one from the sidebar or create new
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Right panel: run trace / tools ─────────────────────────────── */}
      <div className="flex w-80 shrink-0 flex-col border-l border-white/[0.06] bg-neutral-950">
        {/* Tab bar */}
        <div className="flex border-b border-white/[0.06] shrink-0">
          {(["trace", "contracts", "schema", "db"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`flex-1 py-2 text-[11px] font-medium transition-colors ${
                activeTab === tab
                  ? "text-neutral-200 border-b-2"
                  : "text-neutral-500 hover:text-neutral-400"
              }`}
              style={
                activeTab === tab
                  ? { borderBottomColor: SPIN_ACCENT }
                  : undefined
              }
            >
              {tab === "trace" && "Trace"}
              {tab === "contracts" && "Contracts"}
              {tab === "schema" && "Schema"}
              {tab === "db" && "DB State"}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-y-auto">
          {activeTab === "trace" && (
            <TraceTab result={runResult} isRunning={isRunning} />
          )}
          {activeTab === "contracts" && <ContractsTab />}
          {activeTab === "schema" && <SchemaTab />}
          {activeTab === "db" && <DbStateTab />}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Trace tab
// ---------------------------------------------------------------------------

function TraceTab({
  result,
  isRunning,
}: {
  result: SpinRunResult | null;
  isRunning: boolean;
}) {
  if (isRunning) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 p-6 text-neutral-500">
        <Loader2 size={24} className="animate-spin" style={{ color: SPIN_ACCENT }} />
        <span className="text-xs">Running scenario...</span>
      </div>
    );
  }

  if (!result) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 p-6 text-neutral-600">
        <Timer size={24} />
        <span className="text-xs">Run a scenario to see results</span>
      </div>
    );
  }

  return (
    <div className="p-3 space-y-3">
      <RunSummaryBar result={result} />

      {result.error && (
        <div className="text-xs text-red-400 bg-red-400/10 rounded px-2 py-1">
          {result.error}
        </div>
      )}

      {result.setup_results.length > 0 && (
        <div>
          <div className="text-[10px] text-neutral-500 mb-1 uppercase tracking-wider">Setup</div>
          <div className="space-y-1">
            {result.setup_results.map((r, i) => (
              <StepResultRow key={i} result={r} />
            ))}
          </div>
        </div>
      )}

      {result.steps.length > 0 && (
        <div>
          <div className="text-[10px] text-neutral-500 mb-1 uppercase tracking-wider">Steps</div>
          <div className="space-y-1">
            {result.steps.map((r, i) => (
              <StepResultRow key={i} result={r} />
            ))}
          </div>
        </div>
      )}

      {result.teardown_results.length > 0 && (
        <div>
          <div className="text-[10px] text-neutral-500 mb-1 uppercase tracking-wider">Teardown</div>
          <div className="space-y-1">
            {result.teardown_results.map((r, i) => (
              <StepResultRow key={i} result={r} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Contracts tab
// ---------------------------------------------------------------------------

function ContractsTab() {
  const [contractPath, setContractPath] = useState("");
  const [providerUrl, setProviderUrl] = useState("");
  const [verifyResult, setVerifyResult] = useState<null | Awaited<ReturnType<typeof sidecar.verifyContract>>>(null);
  const [isVerifying, setIsVerifying] = useState(false);

  const handleVerify = async () => {
    if (!contractPath || !providerUrl) return;
    setIsVerifying(true);
    try {
      const r = await sidecar.verifyContract({ contract_path: contractPath, provider_url: providerUrl });
      setVerifyResult(r);
    } finally {
      setIsVerifying(false);
    }
  };

  return (
    <div className="p-3 space-y-3">
      <div className="flex items-center gap-1.5 mb-1">
        <Shield size={12} style={{ color: SPIN_ACCENT }} />
        <span className="text-xs font-medium text-neutral-300">Pact Contract Verify</span>
      </div>
      <input
        className="w-full bg-neutral-900 border border-white/[0.06] rounded px-2 py-1.5 text-xs text-neutral-200 placeholder-neutral-600 focus:outline-none"
        placeholder="Contract file path (.contract.json)"
        value={contractPath}
        onChange={(e) => setContractPath(e.target.value)}
      />
      <input
        className="w-full bg-neutral-900 border border-white/[0.06] rounded px-2 py-1.5 text-xs text-neutral-200 placeholder-neutral-600 focus:outline-none"
        placeholder="Provider URL (https://api.example.com)"
        value={providerUrl}
        onChange={(e) => setProviderUrl(e.target.value)}
      />
      <button
        onClick={handleVerify}
        disabled={isVerifying || !contractPath || !providerUrl}
        className="flex items-center gap-1.5 w-full justify-center rounded px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-40"
        style={{ backgroundColor: `${SPIN_ACCENT}20`, color: SPIN_ACCENT, border: `1px solid ${SPIN_ACCENT}40` }}
      >
        {isVerifying ? <Loader2 size={11} className="animate-spin" /> : <Play size={11} />}
        Verify Contract
      </button>

      {verifyResult && (
        <div className="space-y-2">
          <div className={`flex items-center gap-2 text-xs rounded px-2 py-1 ${
            verifyResult.status === "passed" ? "text-lime-400 bg-lime-400/10" : "text-red-400 bg-red-400/10"
          }`}>
            {statusIcon(verifyResult.status, 12)}
            {verifyResult.passed}/{verifyResult.total_interactions} interactions passed
          </div>
          {verifyResult.results.map((r, i) => (
            <div key={i} className="text-[11px] border border-white/[0.06] rounded px-2 py-1.5">
              <div className="flex items-center gap-1.5">
                {statusIcon(r.passed ? "passed" : "failed", 11)}
                <span className="text-neutral-300">{r.description}</span>
              </div>
              {r.failures.map((f, j) => (
                <div key={j} className="text-red-400/80 pl-5 mt-0.5">{f}</div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Schema tab
// ---------------------------------------------------------------------------

function SchemaTab() {
  const [payload, setPayload] = useState('{"id": 1, "name": "test"}');
  const [schemaRef, setSchemaRef] = useState("jsonschema");
  const [rawSchema, setRawSchema] = useState('{"type": "object"}');
  const [result, setResult] = useState<null | { valid: boolean; errors: string[] }>(null);
  const [isValidating, setIsValidating] = useState(false);

  const handleValidate = async () => {
    setIsValidating(true);
    try {
      let parsedPayload: unknown;
      try {
        parsedPayload = JSON.parse(payload);
      } catch {
        setResult({ valid: false, errors: ["Invalid JSON payload"] });
        return;
      }
      const input: Parameters<typeof sidecar.spinValidateSchema>[0] = {
        payload: parsedPayload,
        schema_ref: schemaRef,
      };
      if (schemaRef === "jsonschema") {
        try {
          input.raw_schema = JSON.parse(rawSchema) as Record<string, unknown>;
        } catch {
          setResult({ valid: false, errors: ["Invalid JSON schema"] });
          return;
        }
      }
      const r = await sidecar.spinValidateSchema(input);
      setResult(r);
    } finally {
      setIsValidating(false);
    }
  };

  return (
    <div className="p-3 space-y-3">
      <div className="flex items-center gap-1.5 mb-1">
        <Zap size={12} style={{ color: SPIN_ACCENT }} />
        <span className="text-xs font-medium text-neutral-300">Schema Validation</span>
      </div>
      <div>
        <label className="text-[10px] text-neutral-500 uppercase tracking-wider">Schema ref</label>
        <input
          className="mt-1 w-full bg-neutral-900 border border-white/[0.06] rounded px-2 py-1.5 text-xs text-neutral-200 font-mono focus:outline-none"
          placeholder='jsonschema | openapi://opId | asyncapi://channel'
          value={schemaRef}
          onChange={(e) => setSchemaRef(e.target.value)}
        />
      </div>
      {schemaRef === "jsonschema" && (
        <div>
          <label className="text-[10px] text-neutral-500 uppercase tracking-wider">JSON Schema</label>
          <textarea
            className="mt-1 w-full h-20 bg-neutral-900 border border-white/[0.06] rounded px-2 py-1.5 text-xs text-neutral-200 font-mono resize-none focus:outline-none"
            value={rawSchema}
            onChange={(e) => setRawSchema(e.target.value)}
          />
        </div>
      )}
      <div>
        <label className="text-[10px] text-neutral-500 uppercase tracking-wider">Payload (JSON)</label>
        <textarea
          className="mt-1 w-full h-20 bg-neutral-900 border border-white/[0.06] rounded px-2 py-1.5 text-xs text-neutral-200 font-mono resize-none focus:outline-none"
          value={payload}
          onChange={(e) => setPayload(e.target.value)}
        />
      </div>
      <button
        onClick={handleValidate}
        disabled={isValidating}
        className="flex items-center gap-1.5 w-full justify-center rounded px-3 py-1.5 text-xs font-medium disabled:opacity-40"
        style={{ backgroundColor: `${SPIN_ACCENT}20`, color: SPIN_ACCENT, border: `1px solid ${SPIN_ACCENT}40` }}
      >
        {isValidating ? <Loader2 size={11} className="animate-spin" /> : <CheckCircle2 size={11} />}
        Validate
      </button>
      {result && (
        <div className={`rounded px-2 py-1.5 text-xs ${
          result.valid ? "bg-lime-400/10 text-lime-400" : "bg-red-400/10 text-red-400"
        }`}>
          {result.valid ? "Valid" : "Invalid"}
          {result.errors.map((e, i) => (
            <div key={i} className="mt-0.5 opacity-80 text-[11px]">{e}</div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// DB State tab
// ---------------------------------------------------------------------------

function DbStateTab() {
  const [connStr, setConnStr] = useState("sqlite:///test.db");
  const [table, setTable] = useState("orders");
  const [snapshot, setSnapshot] = useState<null | Awaited<ReturnType<typeof sidecar.dbSnapshot>>>(null);
  const [compareResult, setCompareResult] = useState<null | Awaited<ReturnType<typeof sidecar.dbCompare>>>(null);
  const [expectedDelta, setExpectedDelta] = useState("1");
  const [isLoading, setIsLoading] = useState(false);

  const handleSnapshot = async () => {
    setIsLoading(true);
    try {
      const r = await sidecar.dbSnapshot({ connection_string: connStr, table });
      setSnapshot(r);
      setCompareResult(null);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCompare = async () => {
    if (!snapshot) return;
    setIsLoading(true);
    try {
      const r = await sidecar.dbCompare({
        connection_string: connStr,
        table,
        snapshot_before: snapshot.snapshot,
        expected_delta: parseInt(expectedDelta, 10) || 0,
      });
      setCompareResult(r);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="p-3 space-y-3">
      <div className="flex items-center gap-1.5 mb-1">
        <Database size={12} style={{ color: SPIN_ACCENT }} />
        <span className="text-xs font-medium text-neutral-300">DB State</span>
      </div>
      <input
        className="w-full bg-neutral-900 border border-white/[0.06] rounded px-2 py-1.5 text-xs text-neutral-200 font-mono placeholder-neutral-600 focus:outline-none"
        placeholder="Connection string"
        value={connStr}
        onChange={(e) => setConnStr(e.target.value)}
      />
      <input
        className="w-full bg-neutral-900 border border-white/[0.06] rounded px-2 py-1.5 text-xs text-neutral-200 placeholder-neutral-600 focus:outline-none"
        placeholder="Table name"
        value={table}
        onChange={(e) => setTable(e.target.value)}
      />
      <button
        onClick={handleSnapshot}
        disabled={isLoading}
        className="flex items-center gap-1.5 w-full justify-center rounded px-3 py-1.5 text-xs font-medium disabled:opacity-40"
        style={{ backgroundColor: `${SPIN_ACCENT}20`, color: SPIN_ACCENT, border: `1px solid ${SPIN_ACCENT}40` }}
      >
        {isLoading ? <Loader2 size={11} className="animate-spin" /> : <Database size={11} />}
        Take Snapshot
      </button>

      {snapshot && (
        <div className="text-xs border border-white/[0.06] rounded p-2 space-y-1">
          <div className="text-neutral-400">
            <span className="text-neutral-500">Table:</span>{" "}
            <span className="font-mono">{snapshot.table}</span>
          </div>
          <div className="text-neutral-400">
            <span className="text-neutral-500">Rows:</span>{" "}
            <span style={{ color: SPIN_ACCENT }}>{snapshot.row_count}</span>
          </div>
        </div>
      )}

      {snapshot && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <input
              className="flex-1 bg-neutral-900 border border-white/[0.06] rounded px-2 py-1.5 text-xs text-neutral-200 focus:outline-none"
              placeholder="Expected delta (e.g. 1)"
              value={expectedDelta}
              onChange={(e) => setExpectedDelta(e.target.value)}
            />
            <button
              onClick={handleCompare}
              disabled={isLoading}
              className="rounded px-2 py-1.5 text-xs font-medium disabled:opacity-40"
              style={{ backgroundColor: `${SPIN_ACCENT}20`, color: SPIN_ACCENT, border: `1px solid ${SPIN_ACCENT}40` }}
            >
              Compare
            </button>
          </div>
          {compareResult && (
            <div className={`rounded px-2 py-1.5 text-xs ${
              compareResult.passed ? "bg-lime-400/10 text-lime-400" : "bg-red-400/10 text-red-400"
            }`}>
              {compareResult.passed ? "Delta matches" : "Delta mismatch"}
              <div className="text-neutral-400 mt-0.5">
                Before: {compareResult.rows_before} → After: {compareResult.rows_after} (Δ{compareResult.actual_delta > 0 ? "+" : ""}{compareResult.actual_delta})
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
