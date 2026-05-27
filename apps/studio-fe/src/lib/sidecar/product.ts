import { call, getSidecarBaseUrl } from "./client";
import type { StoredCollection } from "./collections";

export type FeatureStatus = "stable" | "beta" | "experimental" | "hidden" | "archived";
export type FeatureArea =
  | "release"
  | "core"
  | "protocol"
  | "testing"
  | "security"
  | "ai"
  | "ci"
  | "governance"
  | "ecosystem";

export interface FeatureEntry {
  id: string;
  label: string;
  area: FeatureArea;
  status: FeatureStatus;
  ui: boolean;
  tests: boolean;
  docs: boolean;
  summary: string;
  next_step: string;
}

export interface FeatureRegistryOutput {
  generated_at: string;
  totals: Record<string, number>;
  features: FeatureEntry[];
}

export interface ReadinessCheck {
  id: string;
  label: string;
  status: "pass" | "warn" | "fail";
  detail: string;
}

export interface ReadinessOutput {
  version: string;
  platform: string;
  python: string;
  storage_home: string;
  checks: ReadinessCheck[];
  summary: Record<"pass" | "warn" | "fail", number>;
}

export interface CollectionHealthIssue {
  severity: "info" | "warn" | "fail";
  path: string;
  message: string;
}

export interface CollectionHealthOutput {
  collection_id: string;
  collection_name: string;
  request_count: number;
  folder_count: number;
  assertion_coverage_pct: number;
  auth_coverage_pct: number;
  variable_count: number;
  issues: CollectionHealthIssue[];
}

export interface SampleWorkspaceOutput {
  collection_id: string;
  collection_name: string;
  request_count: number;
  message: string;
}

export interface RedactionPreviewOutput {
  redacted: string;
  replacements: number;
}

export const productMethods = {
  featureRegistry: () => call<FeatureRegistryOutput>("/api/product/features"),
  releaseReadiness: () => call<ReadinessOutput>("/api/product/readiness"),
  collectionHealth: (collectionId: string) =>
    call<CollectionHealthOutput>(`/api/product/collections/${collectionId}/health`),
  createSampleWorkspace: () =>
    call<SampleWorkspaceOutput>("/api/product/sample-workspace", { method: "POST" }),
  redactionPreview: (value: string) =>
    call<RedactionPreviewOutput>("/api/product/redaction/preview", {
      method: "POST",
      body: JSON.stringify({ value }),
    }),
  downloadCiArtifactPack: async (report: unknown) => {
    const baseUrl = await getSidecarBaseUrl();
    const res = await fetch(`${baseUrl}/api/product/ci-artifact-pack`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ report }),
    });
    if (!res.ok) throw new Error(`sidecar ${res.status}: ${await res.text()}`);
    return res.blob();
  },
  stableCollections: (collections: StoredCollection[]) =>
    collections.filter((collection) => collection.items.length > 0),
} as const;
