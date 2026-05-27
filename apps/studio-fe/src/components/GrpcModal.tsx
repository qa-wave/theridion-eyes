import { useState } from "react";
import { ChevronDown, ChevronRight, FileCode, Loader2, Lock, Play, Radio, RefreshCw, Search, Server, X } from "lucide-react";
import { sidecar } from "../lib/sidecar";
import type { GrpcMethodInfo, GrpcService, GrpcTlsConfig } from "../lib/sidecar";
import { CodeEditor } from "./CodeEditor";

interface Props { open: boolean; onClose: () => void; }

type DiscoveryMode = "reflect" | "load-proto";

export function GrpcModal({ open, onClose }: Props) {
  // Connection
  const [host, setHost] = useState("localhost:50051");
  const [discoveryMode, setDiscoveryMode] = useState<DiscoveryMode>("reflect");
  const [protoContent, setProtoContent] = useState("");

  // TLS
  const [tlsEnabled, setTlsEnabled] = useState(false);
  const [showTls, setShowTls] = useState(false);
  const [caCert, setCaCert] = useState("");
  const [clientCert, setClientCert] = useState("");
  const [clientKey, setClientKey] = useState("");

  // Metadata
  const [metadataRaw, setMetadataRaw] = useState("{}");

  // Services
  const [services, setServices] = useState<GrpcService[]>([]);
  const [expandedServices, setExpandedServices] = useState<Set<string>>(new Set());
  const [selectedService, setSelectedService] = useState("");
  const [selectedMethod, setSelectedMethod] = useState("");
  const [selectedMethodInfo, setSelectedMethodInfo] = useState<GrpcMethodInfo | null>(null);

  // Request / response
  const [payload, setPayload] = useState("{}");
  const [result, setResult] = useState<{
    ok: boolean;
    result: unknown;
    error: string | null;
    elapsed_ms: number;
    status_code?: string | null;
    trailers?: Record<string, string>;
  } | null>(null);

  const [busy, setBusy] = useState<"" | "discover" | "invoke" | "describe">("");
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  function buildTls(): GrpcTlsConfig | undefined {
    if (!tlsEnabled) return undefined;
    return {
      enabled: true,
      ca_cert: caCert || null,
      client_cert: clientCert || null,
      client_key: clientKey || null,
    };
  }

  function parseMetadata(): Record<string, string> {
    try { return JSON.parse(metadataRaw) as Record<string, string>; }
    catch { return {}; }
  }

  async function discover() {
    setBusy("discover"); setError(null); setServices([]);
    try {
      let res: { services: GrpcService[] };
      if (discoveryMode === "reflect") {
        res = await sidecar.grpcReflect(host, buildTls(), parseMetadata());
      } else {
        if (!protoContent.trim()) {
          setError("Paste .proto file content first");
          return;
        }
        res = await sidecar.grpcLoadProto({ proto_content: protoContent });
      }
      setServices(res.services);
      const expanded = new Set(res.services.map((s) => s.name));
      setExpandedServices(expanded);
      if (res.services.length > 0) {
        const firstSvc = res.services[0];
        setSelectedService(firstSvc.name);
        if (firstSvc.methods.length > 0) {
          const firstMethod = firstSvc.methods[0];
          setSelectedMethod(firstMethod.name);
          setSelectedMethodInfo(firstMethod);
          if (discoveryMode === "reflect") {
            await describeMethod(firstSvc.name, firstMethod.name);
          }
        }
      }
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(""); }
  }

  async function describeMethod(svc: string, method: string) {
    try {
      const desc = await sidecar.grpcDescribe({
        host,
        service: svc,
        method,
        tls: buildTls(),
        metadata: parseMetadata(),
      });
      setPayload(JSON.stringify(desc.template, null, 2));
    } catch {
      // If describe fails, keep existing payload
    }
  }

  async function selectMethod(svc: GrpcService, method: GrpcMethodInfo) {
    setSelectedService(svc.name);
    setSelectedMethod(method.name);
    setSelectedMethodInfo(method);
    if (discoveryMode === "reflect") {
      setBusy("describe"); setError(null);
      try {
        await describeMethod(svc.name, method.name);
      } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
      finally { setBusy(""); }
    }
  }

  function toggleService(name: string) {
    setExpandedServices((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name); else next.add(name);
      return next;
    });
  }

  async function invoke() {
    if (!selectedService || !selectedMethod) return;
    setBusy("invoke"); setError(null); setResult(null);
    try {
      let parsedPayload: Record<string, unknown> = {};
      try { parsedPayload = JSON.parse(payload) as Record<string, unknown>; }
      catch { setError("Invalid JSON payload"); setBusy(""); return; }
      const res = await sidecar.grpcInvoke({
        host,
        service: selectedService,
        method: selectedMethod,
        payload: parsedPayload,
        metadata: parseMetadata(),
        timeout_seconds: 10,
        tls: buildTls(),
      });
      setResult(res);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(""); }
  }

  const isStreaming = selectedMethodInfo
    ? (selectedMethodInfo.client_streaming || selectedMethodInfo.server_streaming)
    : false;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="glass flex h-[640px] w-[960px] max-h-[90vh] max-w-[95vw] animate-slide-in flex-col overflow-hidden rounded-xl border border-glass-light shadow-2xl shadow-black/60">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-100">
            <Server className="h-4 w-4 text-cobweb-400" /> gRPC
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Discovery mode toggle + host bar */}
        <div className="flex items-center gap-2 border-b border-glass px-4 py-2.5">
          {/* Mode toggle */}
          <div className="flex rounded-md border border-glass bg-neutral-900/40 p-0.5">
            <button
              type="button"
              onClick={() => setDiscoveryMode("reflect")}
              className={`flex items-center gap-1 rounded px-2.5 py-1 text-[11px] font-medium transition ${
                discoveryMode === "reflect"
                  ? "bg-cobweb-950/60 text-cobweb-200"
                  : "text-neutral-500 hover:text-neutral-300"
              }`}
            >
              <Search className="h-3 w-3" /> Reflect
            </button>
            <button
              type="button"
              onClick={() => setDiscoveryMode("load-proto")}
              className={`flex items-center gap-1 rounded px-2.5 py-1 text-[11px] font-medium transition ${
                discoveryMode === "load-proto"
                  ? "bg-cobweb-950/60 text-cobweb-200"
                  : "text-neutral-500 hover:text-neutral-300"
              }`}
            >
              <FileCode className="h-3 w-3" /> Load .proto
            </button>
          </div>

          {discoveryMode === "reflect" && (
            <>
              <span className="shrink-0 rounded bg-emerald-600/20 px-2 py-0.5 text-[10px] font-bold text-emerald-300">gRPC</span>
              <input
                value={host}
                onChange={(e) => setHost(e.target.value)}
                placeholder="localhost:50051"
                className="flex-1 rounded-md border border-glass bg-neutral-900/50 px-3 py-1.5 font-mono text-xs text-neutral-100 placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none"
                spellCheck={false}
              />
              {/* TLS toggle */}
              <button
                type="button"
                onClick={() => setShowTls((v) => !v)}
                title="TLS / mTLS settings"
                className={`rounded-md border px-2 py-1.5 text-xs transition ${
                  tlsEnabled
                    ? "border-cobweb-500/40 bg-cobweb-950/30 text-cobweb-300"
                    : "border-glass text-neutral-500 hover:text-neutral-200"
                }`}
              >
                <Lock className="h-3.5 w-3.5" />
              </button>
            </>
          )}

          {/* Discover / Load button */}
          <button
            type="button"
            onClick={discover}
            disabled={busy !== "" || (discoveryMode === "reflect" && !host.trim())}
            className="inline-flex items-center gap-1.5 rounded-md border border-glass px-3 py-1.5 text-xs text-neutral-400 transition hover:bg-white/[0.04] hover:text-neutral-200 disabled:opacity-40"
          >
            {busy === "discover"
              ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
              : discoveryMode === "reflect"
                ? <RefreshCw className="h-3.5 w-3.5" />
                : <FileCode className="h-3.5 w-3.5" />}
            {discoveryMode === "reflect" ? "Reflect" : "Parse"}
          </button>

          <button
            type="button"
            onClick={invoke}
            disabled={busy !== "" || !selectedMethod}
            className="bg-accent-gradient inline-flex items-center gap-1.5 rounded-md px-4 py-1.5 text-xs font-medium text-white shadow-glow-sm transition disabled:opacity-40 disabled:shadow-none"
          >
            {busy === "invoke" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />} Invoke
          </button>
        </div>

        {/* TLS panel */}
        {showTls && discoveryMode === "reflect" && (
          <div className="border-b border-glass bg-neutral-950/40 px-4 py-3">
            <div className="flex items-center gap-3 mb-2">
              <label className="flex items-center gap-2 text-xs text-neutral-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={tlsEnabled}
                  onChange={(e) => setTlsEnabled(e.target.checked)}
                  className="accent-cobweb-500"
                />
                Enable TLS
              </label>
            </div>
            {tlsEnabled && (
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <p className="mb-1 text-[10px] text-neutral-500">CA Certificate (PEM)</p>
                  <textarea
                    value={caCert}
                    onChange={(e) => setCaCert(e.target.value)}
                    placeholder="-----BEGIN CERTIFICATE-----&#10;..."
                    rows={3}
                    className="w-full resize-none rounded border border-glass bg-neutral-900/50 px-2 py-1 font-mono text-[10px] text-neutral-300 placeholder-neutral-700 focus:outline-none"
                    spellCheck={false}
                  />
                </div>
                <div>
                  <p className="mb-1 text-[10px] text-neutral-500">Client Certificate (PEM)</p>
                  <textarea
                    value={clientCert}
                    onChange={(e) => setClientCert(e.target.value)}
                    placeholder="-----BEGIN CERTIFICATE-----&#10;..."
                    rows={3}
                    className="w-full resize-none rounded border border-glass bg-neutral-900/50 px-2 py-1 font-mono text-[10px] text-neutral-300 placeholder-neutral-700 focus:outline-none"
                    spellCheck={false}
                  />
                </div>
                <div>
                  <p className="mb-1 text-[10px] text-neutral-500">Client Private Key (PEM)</p>
                  <textarea
                    value={clientKey}
                    onChange={(e) => setClientKey(e.target.value)}
                    placeholder="-----BEGIN PRIVATE KEY-----&#10;..."
                    rows={3}
                    className="w-full resize-none rounded border border-glass bg-neutral-900/50 px-2 py-1 font-mono text-[10px] text-neutral-300 placeholder-neutral-700 focus:outline-none"
                    spellCheck={false}
                  />
                </div>
              </div>
            )}
          </div>
        )}

        {error && (
          <div className="border-b border-rose-800/30 bg-rose-950/20 px-4 py-2 text-xs text-rose-400">{error}</div>
        )}

        {/* Main content */}
        <div className="flex min-h-0 flex-1">
          {/* Service/method browser OR .proto editor */}
          {discoveryMode === "load-proto" && services.length === 0 ? (
            <div className="flex flex-1 flex-col">
              <p className="border-b border-glass px-4 py-2 text-[11px] uppercase tracking-widest text-neutral-500">Paste .proto content</p>
              <div className="flex-1">
                <CodeEditor value={protoContent} onChange={setProtoContent} language="plaintext" placeholder='syntax = "proto3"; ...' />
              </div>
            </div>
          ) : (
            <>
              {/* Sidebar: services */}
              <div className="w-64 shrink-0 overflow-y-auto border-r border-glass p-3">
                <p className="mb-2 text-[11px] uppercase tracking-widest text-neutral-500">Services</p>
                {services.length === 0 ? (
                  <p className="py-4 text-center text-xs text-neutral-600">
                    {discoveryMode === "reflect" ? "Click Reflect to discover" : "Click Parse to load"}
                  </p>
                ) : services.map((svc) => (
                  <div key={svc.name} className="mb-1">
                    <button
                      type="button"
                      onClick={() => toggleService(svc.name)}
                      className="flex w-full items-center gap-1.5 rounded-md px-1.5 py-1 text-left text-xs font-medium text-neutral-300 transition hover:bg-white/[0.03]"
                    >
                      {expandedServices.has(svc.name)
                        ? <ChevronDown className="h-3 w-3 shrink-0 text-neutral-500" />
                        : <ChevronRight className="h-3 w-3 shrink-0 text-neutral-500" />}
                      <span className="truncate">{svc.name.split(".").pop()}</span>
                      <span className="ml-auto text-[10px] text-neutral-600">{svc.methods.length}</span>
                    </button>
                    {expandedServices.has(svc.name) && svc.methods.map((m) => (
                      <button
                        key={m.name}
                        type="button"
                        onClick={() => selectMethod(svc, m)}
                        className={`mt-0.5 flex w-full items-center gap-1.5 rounded-md px-2 py-1 pl-6 text-left font-mono text-[11px] transition ${
                          selectedService === svc.name && selectedMethod === m.name
                            ? "bg-cobweb-950/30 text-cobweb-200 border border-cobweb-400/20"
                            : "text-neutral-400 hover:bg-white/[0.03] border border-transparent"
                        }`}
                      >
                        <span className="truncate">{m.name}</span>
                        {(m.client_streaming || m.server_streaming) && (
                          <span className="ml-auto inline-flex items-center gap-0.5 rounded bg-amber-600/20 px-1.5 py-0.5 text-[9px] font-medium text-amber-300">
                            <Radio className="h-2.5 w-2.5" />
                            {m.client_streaming && m.server_streaming ? "bidi" : m.server_streaming ? "srv" : "cli"}
                          </span>
                        )}
                      </button>
                    ))}
                  </div>
                ))}
              </div>

              {/* Editor + Response */}
              <div className="flex min-w-0 flex-1 flex-col">
                {/* Method info bar */}
                <div className="flex items-center gap-2 border-b border-glass px-3 py-1.5">
                  <span className="text-[11px] uppercase tracking-widest text-neutral-500">Payload</span>
                  {selectedMethod && (
                    <span className="font-mono text-[11px] text-cobweb-400">
                      {selectedService.split(".").pop()}/{selectedMethod}
                    </span>
                  )}
                  {isStreaming && (
                    <span className="inline-flex items-center gap-0.5 rounded bg-amber-600/20 px-1.5 py-0.5 text-[9px] font-medium text-amber-300">
                      <Radio className="h-2.5 w-2.5" /> streaming
                    </span>
                  )}
                  {selectedMethodInfo && (
                    <span className="ml-auto text-[10px] text-neutral-600">
                      {selectedMethodInfo.input_type} &rarr; {selectedMethodInfo.output_type}
                    </span>
                  )}
                  {busy === "describe" && <Loader2 className="ml-auto h-3 w-3 animate-spin text-cobweb-400" />}
                </div>

                {/* Payload editor */}
                <div className="h-[45%] border-b border-glass">
                  <CodeEditor value={payload} onChange={setPayload} language="json" placeholder="{}" />
                </div>

                {/* Metadata editor (collapsed by default) */}
                <details className="border-b border-glass">
                  <summary className="cursor-pointer select-none px-3 py-1.5 text-[11px] uppercase tracking-widest text-neutral-500 hover:text-neutral-400">
                    Metadata (custom headers)
                  </summary>
                  <div className="h-16">
                    <CodeEditor value={metadataRaw} onChange={setMetadataRaw} language="json" placeholder='{"x-api-key": "..."}' />
                  </div>
                </details>

                {/* Response */}
                <div className="px-3 py-1.5 text-[11px] uppercase tracking-widest text-neutral-500">
                  Response
                  {result && (
                    <>
                      <span className={`ml-2 font-mono normal-case ${result.ok ? "text-emerald-400" : "text-rose-400"}`}>
                        {result.elapsed_ms.toFixed(0)}ms
                      </span>
                      {result.status_code && (
                        <span className={`ml-2 rounded px-1.5 py-0.5 font-mono text-[10px] normal-case ${
                          result.ok ? "bg-emerald-900/30 text-emerald-400" : "bg-rose-900/30 text-rose-400"
                        }`}>
                          {result.status_code}
                        </span>
                      )}
                    </>
                  )}
                </div>
                <div className="min-h-0 flex-1">
                  {result ? (
                    <CodeEditor
                      value={JSON.stringify(result.ok ? result.result : { error: result.error, trailers: result.trailers }, null, 2)}
                      language="json"
                      readOnly
                    />
                  ) : (
                    <div className="flex h-full items-center justify-center text-xs text-neutral-600">
                      Invoke a method to see response
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
