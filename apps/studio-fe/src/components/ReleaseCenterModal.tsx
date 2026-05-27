import { useEffect, useMemo, useRef, useState } from "react";
import {
  CheckCircle2,
  Download,
  FlaskConical,
  Gauge,
  Loader2,
  Shield,
  X,
  XCircle,
} from "lucide-react";
import { sidecar, type CollectionHealthOutput, type FeatureRegistryOutput, type ReadinessOutput, type StoredCollection } from "../lib/sidecar";
import { useFocusTrap } from "../hooks/useFocusTrap";

type Tab = "readiness" | "features" | "health" | "secrets" | "ci";

interface Props {
  open: boolean;
  collections: StoredCollection[];
  onClose: () => void;
  onRefreshCollections: () => void | Promise<void>;
  onToast: (type: "success" | "error" | "info", message: string) => void;
}

const tabs: Array<{ id: Tab; label: string }> = [
  { id: "readiness", label: "Readiness" },
  { id: "features", label: "Features" },
  { id: "health", label: "Health" },
  { id: "secrets", label: "Secrets" },
  { id: "ci", label: "CI Pack" },
];

export function ReleaseCenterModal({
  open,
  collections,
  onClose,
  onRefreshCollections,
  onToast,
}: Props) {
  const [tab, setTab] = useState<Tab>("readiness");
  const [readiness, setReadiness] = useState<ReadinessOutput | null>(null);
  const [features, setFeatures] = useState<FeatureRegistryOutput | null>(null);
  const [health, setHealth] = useState<CollectionHealthOutput | null>(null);
  const [selectedCollectionId, setSelectedCollectionId] = useState("");
  const [redactionInput, setRedactionInput] = useState(
    "Authorization: Bearer abc.def.ghi\napi_key=secret-value",
  );
  const [redacted, setRedacted] = useState("");
  const [busy, setBusy] = useState(false);
  const trapRef = useRef<HTMLDivElement>(null);
  useFocusTrap(trapRef, open);

  useEffect(() => {
    if (!open) return;
    let ignore = false;
    setBusy(true);
    Promise.all([sidecar.releaseReadiness(), sidecar.featureRegistry()])
      .then(([nextReadiness, nextFeatures]) => {
        if (ignore) return;
        setReadiness(nextReadiness);
        setFeatures(nextFeatures);
      })
      .catch((e: unknown) => {
        if (!ignore) onToast("error", e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!ignore) setBusy(false);
      });
    return () => {
      ignore = true;
    };
  }, [open, onToast]);

  useEffect(() => {
    if (!open || collections.length === 0 || selectedCollectionId) return;
    setSelectedCollectionId(collections[0].id);
  }, [collections, open, selectedCollectionId]);

  useEffect(() => {
    if (!open || !selectedCollectionId) return;
    let ignore = false;
    sidecar.collectionHealth(selectedCollectionId)
      .then((result) => {
        if (!ignore) setHealth(result);
      })
      .catch((e: unknown) => {
        if (!ignore) onToast("error", e instanceof Error ? e.message : String(e));
      });
    return () => {
      ignore = true;
    };
  }, [open, onToast, selectedCollectionId]);

  const groupedFeatures = useMemo(() => {
    const groups: Record<string, NonNullable<typeof features>["features"]> = {};
    for (const feature of features?.features ?? []) {
      if (!groups[feature.area]) groups[feature.area] = [];
      groups[feature.area].push(feature);
    }
    return groups;
  }, [features]);

  async function createSampleWorkspace() {
    setBusy(true);
    try {
      const result = await sidecar.createSampleWorkspace();
      await onRefreshCollections();
      setSelectedCollectionId(result.collection_id);
      onToast("success", result.message);
    } catch (e) {
      onToast("error", e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function previewRedaction() {
    setBusy(true);
    try {
      const result = await sidecar.redactionPreview(redactionInput);
      setRedacted(result.redacted);
      onToast("info", `${result.replacements} replacements`);
    } catch (e) {
      onToast("error", e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function downloadCiPack() {
    if (!selectedCollectionId) {
      onToast("error", "Select a collection before downloading CI artifacts.");
      return;
    }
    const report = {
      collection_id: selectedCollectionId,
      collection_name: collections.find((c) => c.id === selectedCollectionId)?.name ?? "Collection",
      results: [],
      total_requests: health?.request_count ?? 0,
      successful_requests: 0,
      failed_requests: 0,
      total_assertions: 0,
      passed_assertions: 0,
      failed_assertions: 0,
      total_elapsed_ms: 0,
    };
    setBusy(true);
    try {
      const blob = await sidecar.downloadCiArtifactPack(report);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "theridion-ci-artifacts.zip";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      onToast("error", e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div ref={trapRef} className="flex h-[680px] w-[920px] max-h-[92vh] max-w-[96vw] overflow-hidden rounded-lg border border-neutral-800 bg-neutral-950 shadow-2xl">
        <div className="flex w-56 shrink-0 flex-col border-r border-neutral-800 bg-neutral-950">
          <div className="border-b border-neutral-800 px-4 py-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-neutral-100">
              <Gauge className="h-4 w-4 text-emerald-400" />
              Release Center
            </div>
          </div>
          <div className="flex-1 py-2">
            {tabs.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setTab(item.id)}
                className={`flex w-full items-center px-4 py-2 text-left text-xs ${
                  tab === item.id
                    ? "bg-emerald-500/10 text-emerald-200"
                    : "text-neutral-400 hover:bg-neutral-900 hover:text-neutral-200"
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
          <div className="border-t border-neutral-800 p-3">
            <button
              type="button"
              onClick={createSampleWorkspace}
              disabled={busy}
              className="flex w-full items-center justify-center gap-2 rounded-md border border-emerald-700 bg-emerald-600 px-3 py-2 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-60"
            >
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FlaskConical className="h-3.5 w-3.5" />}
              Sample Workspace
            </button>
          </div>
        </div>

        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-center justify-between border-b border-neutral-800 px-4 py-3">
            <span className="text-xs font-semibold uppercase tracking-widest text-neutral-500">
              {tabs.find((item) => item.id === tab)?.label}
            </span>
            <button type="button" onClick={onClose} className="rounded-md p-1 text-neutral-500 hover:bg-neutral-900 hover:text-neutral-200">
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            {tab === "readiness" && (
              <div className="space-y-3">
                <div className="grid grid-cols-3 gap-3">
                  <Metric label="Pass" value={readiness?.summary.pass ?? 0} tone="pass" />
                  <Metric label="Warn" value={readiness?.summary.warn ?? 0} tone="warn" />
                  <Metric label="Fail" value={readiness?.summary.fail ?? 0} tone="fail" />
                </div>
                <div className="rounded-md border border-neutral-800">
                  {readiness?.checks.map((check) => (
                    <div key={check.id} className="flex items-center gap-3 border-b border-neutral-800 px-3 py-2 last:border-b-0">
                      {check.status === "pass" ? <CheckCircle2 className="h-4 w-4 text-emerald-400" /> : <XCircle className="h-4 w-4 text-amber-400" />}
                      <div className="min-w-0 flex-1">
                        <div className="text-sm text-neutral-200">{check.label}</div>
                        <div className="truncate text-xs text-neutral-500">{check.detail}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {tab === "features" && (
              <div className="space-y-4">
                {Object.entries(groupedFeatures).map(([area, items]) => (
                  <section key={area}>
                    <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-neutral-500">{area}</h3>
                    <div className="divide-y divide-neutral-800 rounded-md border border-neutral-800">
                      {items.map((feature) => (
                        <div key={feature.id} className="p-3">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-neutral-100">{feature.label}</span>
                            <Badge label={feature.status} />
                            {feature.ui && <Badge label="UI" muted />}
                            {feature.tests && <Badge label="tests" muted />}
                          </div>
                          <p className="mt-1 text-xs text-neutral-400">{feature.summary}</p>
                          <p className="mt-1 text-xs text-neutral-600">{feature.next_step}</p>
                        </div>
                      ))}
                    </div>
                  </section>
                ))}
              </div>
            )}

            {tab === "health" && (
              <div className="space-y-3">
                <select
                  value={selectedCollectionId}
                  onChange={(e) => setSelectedCollectionId(e.target.value)}
                  className="rounded-md border border-neutral-800 bg-neutral-900 px-3 py-2 text-xs text-neutral-100 outline-none"
                >
                  {collections.map((collection) => (
                    <option key={collection.id} value={collection.id}>{collection.name}</option>
                  ))}
                </select>
                {health && (
                  <>
                    <div className="grid grid-cols-4 gap-3">
                      <Metric label="Requests" value={health.request_count} />
                      <Metric label="Folders" value={health.folder_count} />
                      <Metric label="Asserts" value={`${health.assertion_coverage_pct}%`} />
                      <Metric label="Auth" value={`${health.auth_coverage_pct}%`} />
                    </div>
                    <div className="divide-y divide-neutral-800 rounded-md border border-neutral-800">
                      {health.issues.length === 0 ? (
                        <div className="p-3 text-sm text-emerald-300">No collection health issues found.</div>
                      ) : health.issues.map((issue, index) => (
                        <div key={`${issue.path}-${index}`} className="p-3">
                          <div className="flex items-center gap-2">
                            <Badge label={issue.severity} />
                            <span className="font-mono text-xs text-neutral-500">{issue.path}</span>
                          </div>
                          <div className="mt-1 text-sm text-neutral-300">{issue.message}</div>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            )}

            {tab === "secrets" && (
              <div className="grid h-full grid-cols-2 gap-3">
                <textarea
                  value={redactionInput}
                  onChange={(e) => setRedactionInput(e.target.value)}
                  className="h-full min-h-[360px] resize-none rounded-md border border-neutral-800 bg-neutral-900 p-3 font-mono text-xs text-neutral-100 outline-none"
                />
                <div className="flex min-h-[360px] flex-col rounded-md border border-neutral-800 bg-neutral-900">
                  <div className="flex items-center justify-between border-b border-neutral-800 px-3 py-2">
                    <span className="text-xs text-neutral-400">Preview</span>
                    <button type="button" onClick={previewRedaction} className="flex items-center gap-2 rounded-md border border-neutral-700 px-2 py-1 text-xs text-neutral-300 hover:bg-neutral-800">
                      <Shield className="h-3.5 w-3.5" />
                      Redact
                    </button>
                  </div>
                  <pre className="flex-1 overflow-auto whitespace-pre-wrap p-3 text-xs text-neutral-200">{redacted}</pre>
                </div>
              </div>
            )}

            {tab === "ci" && (
              <div className="space-y-4">
                <p className="text-sm text-neutral-400">
                  Generate the artifact contract used by CI integrations: summary JSON,
                  redacted report JSON, Markdown, JUnit XML, and trace HTML.
                </p>
                <button
                  type="button"
                  onClick={downloadCiPack}
                  disabled={!selectedCollectionId || busy}
                  className="flex items-center gap-2 rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-200 hover:bg-neutral-800 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <Download className="h-4 w-4" />
                  Download CI artifact pack
                </button>
                <div className="rounded-md border border-neutral-800 p-3 text-xs text-neutral-500">
                  Selected collection: {collections.find((c) => c.id === selectedCollectionId)?.name ?? "None"}
                </div>
              </div>
            )}

            {busy && !readiness && (
              <div className="flex h-full items-center justify-center text-neutral-500">
                <Loader2 className="h-5 w-5 animate-spin" />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: React.ReactNode; tone?: "pass" | "warn" | "fail" }) {
  const toneClass = tone === "pass" ? "text-emerald-300" : tone === "fail" ? "text-rose-300" : tone === "warn" ? "text-amber-300" : "text-neutral-100";
  return (
    <div className="rounded-md border border-neutral-800 bg-neutral-900 p-3">
      <div className={`text-xl font-semibold ${toneClass}`}>{value}</div>
      <div className="text-[10px] uppercase tracking-widest text-neutral-500">{label}</div>
    </div>
  );
}

function Badge({ label, muted }: { label: string; muted?: boolean }) {
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wider ${muted ? "border-neutral-700 text-neutral-500" : "border-emerald-800 text-emerald-300"}`}>
      {label}
    </span>
  );
}
