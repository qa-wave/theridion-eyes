import { useEffect, useState } from "react";
import {
  Globe,
  Loader2,
  Network,
  Play,
  Search,
  Shield,
  X,
} from "lucide-react";
import {
  sidecar,
  type SoapExecuteOutput,
  type SoapOperation,
  type SoapPort,
  type SoapService,
  type WsdlSummary,
  type WsSecurityConfig,
} from "../lib/sidecar";
import { CodeEditor } from "./CodeEditor";

interface Props {
  open: boolean;
  onClose: () => void;
}

interface Picked {
  service: string;
  port: string;
  operation: SoapOperation;
}

type WsseMode = "None" | "UsernameToken" | "Signature" | "Timestamp";

interface WsseState {
  mode: WsseMode;
  // UsernameToken
  username: string;
  password: string;
  useDigest: boolean;
  addTimestamp: boolean;
  ttlSeconds: number;
  // Signature
  keyFilePath: string;
  certFilePath: string;
  keyFilePassword: string;
  signatureAlgorithm: "RSA-SHA256" | "RSA-SHA1";
}

const DEFAULT_WSSE: WsseState = {
  mode: "None",
  username: "",
  password: "",
  useDigest: false,
  addTimestamp: true,
  ttlSeconds: 300,
  keyFilePath: "",
  certFilePath: "",
  keyFilePassword: "",
  signatureAlgorithm: "RSA-SHA256",
};

function buildWsseConfig(s: WsseState): WsSecurityConfig | undefined {
  if (s.mode === "None") return undefined;
  if (s.mode === "UsernameToken") {
    return {
      type: "UsernameToken",
      username: s.username,
      password: s.password,
      password_type: s.useDigest ? "PasswordDigest" : "PasswordText",
      add_nonce: true,
      add_created: true,
      add_timestamp: s.addTimestamp,
      ttl_seconds: s.ttlSeconds,
    };
  }
  if (s.mode === "Signature") {
    return {
      type: "Signature",
      key_file_path: s.keyFilePath || undefined,
      cert_file_path: s.certFilePath || undefined,
      key_file_password: s.keyFilePassword || undefined,
      signature_algorithm: s.signatureAlgorithm,
      add_timestamp: s.addTimestamp,
      ttl_seconds: s.ttlSeconds,
    };
  }
  if (s.mode === "Timestamp") {
    return {
      type: "Timestamp",
      ttl_seconds: s.ttlSeconds,
    };
  }
  return undefined;
}

export function SoapModal({ open, onClose }: Props) {
  const [wsdlUrl, setWsdlUrl] = useState("");
  const [summary, setSummary] = useState<WsdlSummary | null>(null);
  const [picked, setPicked] = useState<Picked | null>(null);
  const [argsText, setArgsText] = useState("{}");
  const [result, setResult] = useState<SoapExecuteOutput | null>(null);
  const [busy, setBusy] = useState<"none" | "inspect" | "execute">("none");
  const [error, setError] = useState<string | null>(null);
  const [wsse, setWsse] = useState<WsseState>(DEFAULT_WSSE);
  const [wsseOpen, setWsseOpen] = useState(false);

  // Reset transient state when reopened. Keep WSDL URL since the user
  // probably wants to keep iterating against the same service.
  useEffect(() => {
    if (!open) return;
    setError(null);
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  async function inspect() {
    setBusy("inspect");
    setError(null);
    setSummary(null);
    setPicked(null);
    setResult(null);
    try {
      const s = await sidecar.inspectWsdl(wsdlUrl);
      setSummary(s);
      // Auto-select the first operation so the editor isn't empty.
      const firstSvc = s.services[0];
      const firstPort = firstSvc?.ports[0];
      const firstOp = firstPort?.operations[0];
      if (firstSvc && firstPort && firstOp) {
        setPicked({
          service: firstSvc.name,
          port: firstPort.name,
          operation: firstOp,
        });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy("none");
    }
  }

  async function execute() {
    if (!picked) return;
    setBusy("execute");
    setError(null);
    setResult(null);
    let parsed: Record<string, unknown>;
    try {
      parsed = argsText.trim() ? JSON.parse(argsText) : {};
      if (typeof parsed !== "object" || Array.isArray(parsed) || parsed === null) {
        throw new Error("args must be a JSON object");
      }
    } catch (e) {
      setError(`Invalid args JSON: ${e instanceof Error ? e.message : String(e)}`);
      setBusy("none");
      return;
    }
    try {
      const wsseConfig = buildWsseConfig(wsse);
      const out = await sidecar.executeSoap({
        wsdl_url: wsdlUrl,
        operation: picked.operation.name,
        args: parsed,
        ...(wsseConfig ? { wsse: wsseConfig } : {}),
      });
      setResult(out);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy("none");
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div
        role="dialog"
        aria-label="SOAP / WSDL"
        className="flex h-[800px] w-[1100px] max-w-[95vw] flex-col overflow-hidden rounded-xl border border-glass-light glass shadow-2xl"
      >
        <header className="flex items-center justify-between border-b border-glass px-4 py-3">
          <h2 className="inline-flex items-center gap-2 text-sm font-semibold text-neutral-100">
            <Globe className="h-4 w-4 text-cobweb-400" /> SOAP / WSDL
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-neutral-500 transition hover:bg-neutral-800 hover:text-neutral-200"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        {/* WSDL URL bar */}
        <div className="flex items-center gap-2 border-b border-glass px-4 py-3">
          <input
            value={wsdlUrl}
            onChange={(e) => setWsdlUrl(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && wsdlUrl.length > 0 && busy === "none") {
                e.preventDefault();
                void inspect();
              }
            }}
            placeholder="https://example.com/service?wsdl"
            className="flex-1 rounded border border-neutral-800 bg-neutral-900 px-3 py-1.5 font-mono text-sm placeholder-neutral-600 focus:border-neutral-600 focus:outline-none"
            spellCheck={false}
          />
          <button
            type="button"
            onClick={inspect}
            disabled={!wsdlUrl || busy === "inspect"}
            className="inline-flex items-center gap-1.5 rounded bg-neutral-800 px-3 py-1.5 text-xs text-neutral-100 transition hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy === "inspect" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Search className="h-3.5 w-3.5" />
            )}
            Inspect
          </button>
        </div>

        {/* WS-Security collapsible section */}
        <WsSecurity wsse={wsse} onChange={setWsse} open={wsseOpen} onToggle={() => setWsseOpen((v) => !v)} />

        {error && (
          <p className="border-b border-rose-900/60 bg-rose-950/30 px-4 py-2 text-xs text-rose-300">
            {error}
          </p>
        )}

        <div className="flex min-h-0 flex-1">
          <OperationsList
            summary={summary}
            picked={picked}
            onPick={setPicked}
            busy={busy === "inspect"}
          />

          <div className="flex min-w-0 flex-1 flex-col">
            {!picked ? (
              <div className="flex flex-1 items-center justify-center text-center text-xs text-neutral-500">
                <div>
                  <Network className="mx-auto mb-3 h-8 w-8 text-neutral-700" />
                  Paste a WSDL URL above and hit Inspect.
                </div>
              </div>
            ) : (
              <>
                <div className="border-b border-glass bg-neutral-950/40 px-4 py-2.5 text-xs">
                  <div className="font-mono text-cobweb-300">
                    {picked.operation.name}
                  </div>
                  <div className="mt-0.5 text-neutral-500">
                    <span className="text-neutral-600">{picked.service} · {picked.port}</span>
                    {picked.operation.soap_action && (
                      <span className="ml-2">
                        SOAPAction:{" "}
                        <span className="font-mono">{picked.operation.soap_action}</span>
                      </span>
                    )}
                  </div>
                  {picked.operation.documentation && (
                    <div className="mt-1.5 italic text-neutral-400">
                      {picked.operation.documentation}
                    </div>
                  )}
                </div>

                <div className="grid min-h-0 flex-1 grid-rows-2 divide-y divide-glass">
                  <div className="flex min-h-0 flex-col">
                    <div className="flex items-center justify-between px-4 pt-3 pb-2">
                      <span className="text-[10px] font-semibold uppercase tracking-wider text-neutral-500">
                        Arguments (JSON)
                      </span>
                      <button
                        type="button"
                        onClick={execute}
                        disabled={busy === "execute"}
                        className="inline-flex items-center gap-1.5 rounded bg-accent-gradient px-3 py-1 text-xs font-medium text-white transition disabled:cursor-not-allowed disabled:bg-neutral-700"
                      >
                        {busy === "execute" ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <Play className="h-3 w-3" />
                        )}
                        Execute
                      </button>
                    </div>
                    <div className="min-h-0 flex-1 overflow-hidden border-t border-neutral-800 bg-neutral-900">
                      <CodeEditor
                        value={argsText}
                        onChange={setArgsText}
                        language="json"
                      />
                    </div>
                  </div>

                  <div className="flex min-h-0 flex-col">
                    <div className="flex items-center justify-between px-4 pt-3 pb-2">
                      <span className="text-[10px] font-semibold uppercase tracking-wider text-neutral-500">
                        Result
                      </span>
                      {result && (
                        <span
                          className={`rounded border px-2 py-0.5 font-mono text-[10px] ${
                            result.ok
                              ? "border-emerald-700 bg-emerald-950/40 text-cobweb-300"
                              : "border-rose-700 bg-rose-950/40 text-rose-300"
                          }`}
                        >
                          {result.ok ? "OK" : "FAULT"}
                        </span>
                      )}
                    </div>
                    <div className="min-h-0 flex-1 overflow-hidden border-t border-neutral-800 bg-neutral-900">
                      {!result ? (
                        <p className="p-4 text-xs text-neutral-600">
                          Press Execute to send the request.
                        </p>
                      ) : result.ok ? (
                        <CodeEditor
                          value={JSON.stringify(result.result, null, 2)}
                          language="json"
                          readOnly
                        />
                      ) : (
                        <pre className="h-full overflow-auto p-4 font-mono text-xs leading-relaxed text-rose-300">
                          {result.fault}
                        </pre>
                      )}
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// WS-Security collapsible panel
// ---------------------------------------------------------------------------

function WsSecurity({
  wsse,
  onChange,
  open,
  onToggle,
}: {
  wsse: WsseState;
  onChange: (s: WsseState) => void;
  open: boolean;
  onToggle: () => void;
}) {
  const isActive = wsse.mode !== "None";

  return (
    <div className="border-b border-glass">
      {/* Toggle row */}
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-xs transition hover:bg-neutral-900/50"
      >
        <Shield
          className={`h-3.5 w-3.5 ${isActive ? "text-cobweb-400" : "text-neutral-600"}`}
        />
        <span className={`font-medium ${isActive ? "text-cobweb-300" : "text-neutral-500"}`}>
          WS-Security
        </span>
        {isActive && (
          <span className="rounded bg-cobweb-900/40 px-1.5 py-0.5 text-[10px] text-cobweb-300 border border-cobweb-700/40">
            {wsse.mode}
          </span>
        )}
        <span className="ml-auto text-neutral-600">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="border-t border-neutral-800/60 bg-neutral-950/30 px-4 py-3">
          {/* Mode selector */}
          <div className="mb-3 flex items-center gap-2">
            <span className="w-20 shrink-0 text-[10px] font-semibold uppercase tracking-wider text-neutral-500">
              Mode
            </span>
            {(["None", "UsernameToken", "Signature", "Timestamp"] as WsseMode[]).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => onChange({ ...wsse, mode: m })}
                className={`rounded px-2.5 py-1 text-xs transition ${
                  wsse.mode === m
                    ? "bg-cobweb-900/50 text-cobweb-200 border border-cobweb-700/60"
                    : "text-neutral-400 hover:bg-neutral-800 hover:text-neutral-200"
                }`}
              >
                {m}
              </button>
            ))}
          </div>

          {/* UsernameToken fields */}
          {wsse.mode === "UsernameToken" && (
            <div className="space-y-2">
              <WsseRow label="Username">
                <input
                  value={wsse.username}
                  onChange={(e) => onChange({ ...wsse, username: e.target.value })}
                  className="w-full rounded border border-neutral-800 bg-neutral-900 px-2 py-1 font-mono text-xs text-neutral-200 placeholder-neutral-600 focus:border-neutral-600 focus:outline-none"
                  placeholder="user"
                />
              </WsseRow>
              <WsseRow label="Password">
                <input
                  type="password"
                  value={wsse.password}
                  onChange={(e) => onChange({ ...wsse, password: e.target.value })}
                  className="w-full rounded border border-neutral-800 bg-neutral-900 px-2 py-1 font-mono text-xs text-neutral-200 placeholder-neutral-600 focus:border-neutral-600 focus:outline-none"
                  placeholder="••••••••"
                />
              </WsseRow>
              <WsseRow label="Auth type">
                <div className="flex items-center gap-3">
                  {(["PasswordText", "PasswordDigest"] as const).map((t) => (
                    <label key={t} className="flex cursor-pointer items-center gap-1.5 text-xs text-neutral-300">
                      <input
                        type="radio"
                        name="password_type"
                        checked={wsse.useDigest === (t === "PasswordDigest")}
                        onChange={() => onChange({ ...wsse, useDigest: t === "PasswordDigest" })}
                        className="accent-cobweb-500"
                      />
                      {t}
                    </label>
                  ))}
                </div>
              </WsseRow>
              <TimestampRow wsse={wsse} onChange={onChange} />
            </div>
          )}

          {/* Signature fields */}
          {wsse.mode === "Signature" && (
            <div className="space-y-2">
              <WsseRow label="Key file">
                <input
                  value={wsse.keyFilePath}
                  onChange={(e) => onChange({ ...wsse, keyFilePath: e.target.value })}
                  className="w-full rounded border border-neutral-800 bg-neutral-900 px-2 py-1 font-mono text-xs text-neutral-200 placeholder-neutral-600 focus:border-neutral-600 focus:outline-none"
                  placeholder="/path/to/key.pem"
                />
              </WsseRow>
              <WsseRow label="Cert file">
                <input
                  value={wsse.certFilePath}
                  onChange={(e) => onChange({ ...wsse, certFilePath: e.target.value })}
                  className="w-full rounded border border-neutral-800 bg-neutral-900 px-2 py-1 font-mono text-xs text-neutral-200 placeholder-neutral-600 focus:border-neutral-600 focus:outline-none"
                  placeholder="/path/to/cert.pem"
                />
              </WsseRow>
              <WsseRow label="Key password">
                <input
                  type="password"
                  value={wsse.keyFilePassword}
                  onChange={(e) => onChange({ ...wsse, keyFilePassword: e.target.value })}
                  className="w-full rounded border border-neutral-800 bg-neutral-900 px-2 py-1 font-mono text-xs text-neutral-200 placeholder-neutral-600 focus:border-neutral-600 focus:outline-none"
                  placeholder="optional"
                />
              </WsseRow>
              <WsseRow label="Algorithm">
                <div className="flex items-center gap-3">
                  {(["RSA-SHA256", "RSA-SHA1"] as const).map((a) => (
                    <label key={a} className="flex cursor-pointer items-center gap-1.5 text-xs text-neutral-300">
                      <input
                        type="radio"
                        name="sig_algo"
                        checked={wsse.signatureAlgorithm === a}
                        onChange={() => onChange({ ...wsse, signatureAlgorithm: a })}
                        className="accent-cobweb-500"
                      />
                      {a}
                      {a === "RSA-SHA256" && (
                        <span className="text-[9px] text-neutral-600">(recommended)</span>
                      )}
                    </label>
                  ))}
                </div>
              </WsseRow>
              <TimestampRow wsse={wsse} onChange={onChange} />
            </div>
          )}

          {/* Timestamp-only fields */}
          {wsse.mode === "Timestamp" && (
            <div className="space-y-2">
              <TimestampRow wsse={wsse} onChange={onChange} showToggle={false} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function WsseRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-20 shrink-0 text-[10px] font-semibold uppercase tracking-wider text-neutral-500">
        {label}
      </span>
      <div className="flex-1">{children}</div>
    </div>
  );
}

function TimestampRow({
  wsse,
  onChange,
  showToggle = true,
}: {
  wsse: WsseState;
  onChange: (s: WsseState) => void;
  showToggle?: boolean;
}) {
  return (
    <div className="flex items-center gap-2">
      {showToggle ? (
        <>
          <span className="w-20 shrink-0 text-[10px] font-semibold uppercase tracking-wider text-neutral-500">
            Timestamp
          </span>
          <label className="flex cursor-pointer items-center gap-1.5 text-xs text-neutral-300">
            <input
              type="checkbox"
              checked={wsse.addTimestamp}
              onChange={(e) => onChange({ ...wsse, addTimestamp: e.target.checked })}
              className="accent-cobweb-500"
            />
            Include
          </label>
        </>
      ) : (
        <span className="w-20 shrink-0 text-[10px] font-semibold uppercase tracking-wider text-neutral-500">
          TTL (s)
        </span>
      )}
      {(wsse.addTimestamp || !showToggle) && (
        <input
          type="number"
          value={wsse.ttlSeconds}
          min={1}
          max={86400}
          onChange={(e) => onChange({ ...wsse, ttlSeconds: Number(e.target.value) })}
          className="w-20 rounded border border-neutral-800 bg-neutral-900 px-2 py-1 text-xs text-neutral-200 focus:border-neutral-600 focus:outline-none"
        />
      )}
      {(wsse.addTimestamp || !showToggle) && (
        <span className="text-[10px] text-neutral-600">seconds TTL</span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Operations list
// ---------------------------------------------------------------------------

function OperationsList({
  summary,
  picked,
  onPick,
  busy,
}: {
  summary: WsdlSummary | null;
  picked: Picked | null;
  onPick: (p: Picked) => void;
  busy: boolean;
}) {
  return (
    <div className="flex w-72 shrink-0 flex-col overflow-y-auto border-r border-glass bg-neutral-950/40 py-2">
      {busy && (
        <p className="px-4 py-3 text-xs text-neutral-500">Inspecting WSDL…</p>
      )}
      {!busy && !summary && (
        <p className="px-4 py-3 text-xs text-neutral-600">
          No WSDL loaded yet.
        </p>
      )}
      {summary?.services.map((svc: SoapService) => (
        <div key={svc.name} className="mb-2">
          <div className="px-4 py-1 text-[10px] font-semibold uppercase tracking-wider text-neutral-500">
            {svc.name}
          </div>
          {svc.ports.map((port: SoapPort) => (
            <div key={port.name}>
              <div className="px-4 py-0.5 text-[10px] text-neutral-600">
                {port.name}
              </div>
              {port.operations.map((op: SoapOperation) => {
                const isActive =
                  picked?.service === svc.name &&
                  picked.port === port.name &&
                  picked.operation.name === op.name;
                return (
                  <button
                    key={op.name}
                    type="button"
                    onClick={() =>
                      onPick({
                        service: svc.name,
                        port: port.name,
                        operation: op,
                      })
                    }
                    className={`flex w-full items-center gap-2 px-4 py-1 text-left text-xs transition ${
                      isActive
                        ? "bg-cobweb-950/30 text-cobweb-200"
                        : "text-neutral-300 hover:bg-neutral-800/60"
                    }`}
                  >
                    <span className="font-mono">{op.name}</span>
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
