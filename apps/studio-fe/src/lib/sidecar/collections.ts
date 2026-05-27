/**
 * Collection CRUD types + sidecar methods.
 */

import { call, getSidecarBaseUrl } from "./client";
import type { AuthConfig, ExecuteRequestInput, CollectionVariable } from "./types";
import type { Assertion } from "./testing";
import type { CaptureRule } from "./requests";
import type { RequestExample, RequestExampleInput } from "./advanced";

/** Tree node — either a folder (`is_folder=true`, has child items) or a request. */
export interface CollectionItem {
  id: string;
  name: string;
  is_folder: boolean;
  // request fields (when is_folder=false)
  method?: ExecuteRequestInput["method"];
  url?: string;
  headers?: Record<string, string>;
  body?: string | null;
  auth?: AuthConfig | null;
  assertions?: Assertion[];
  pre_request_script?: string | null;
  post_response_script?: string | null;
  notes?: string | null;
  examples?: RequestExample[];
  captures?: CaptureRule[];
  tags?: string[];
  // folder field (when is_folder=true)
  items?: CollectionItem[];
}

/** Back-compat alias used in older code paths. */
export type SavedRequest = CollectionItem;

export interface StoredCollection {
  id: string;
  name: string;
  version: number;
  items: CollectionItem[];
  variables?: CollectionVariable[];
}

export interface CollectionSummary {
  id: string;
  name: string;
  request_count: number;
}

export interface SaveRequestInput {
  id?: string;
  name: string;
  method: ExecuteRequestInput["method"];
  url: string;
  headers?: Record<string, string>;
  body?: string | null;
  auth?: AuthConfig | null;
  assertions?: Assertion[];
  pre_request_script?: string | null;
  post_response_script?: string | null;
  notes?: string | null;
  examples?: RequestExample[];
  captures?: CaptureRule[];
  parent_folder_id?: string | null;
}

export interface CreateFolderInput {
  name: string;
  parent_folder_id?: string | null;
}

export interface FavoriteItem {
  collection_id: string;
  request_id: string;
  name: string;
  method: string;
  url: string;
}

// ---- Collection Branching types ---------------------------------------------

export interface ForkOutput {
  id: string;
  name: string;
  parent_id: string;
  item_count: number;
}

export interface MergeOutput {
  id: string;
  name: string;
  merged_items: number;
}

export const collectionsMethods = {
  listCollections: () => call<CollectionSummary[]>("/api/collections"),
  getCollection: (id: string) => call<StoredCollection>(`/api/collections/${id}`),
  createCollection: (name: string) =>
    call<StoredCollection>("/api/collections", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  deleteCollection: async (id: string) => {
    const baseUrl = await getSidecarBaseUrl();
    const r = await fetch(`${baseUrl}/api/collections/${id}`, { method: "DELETE" });
    if (!r.ok && r.status !== 204) throw new Error(`delete ${r.status}`);
  },
  saveRequest: (collectionId: string, body: SaveRequestInput) =>
    call<StoredCollection>(`/api/collections/${collectionId}/requests`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteRequest: (collectionId: string, requestId: string) =>
    call<StoredCollection>(
      `/api/collections/${collectionId}/requests/${requestId}`,
      { method: "DELETE" },
    ),
  createFolder: (collectionId: string, body: CreateFolderInput) =>
    call<StoredCollection>(`/api/collections/${collectionId}/folders`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  renameCollection: (collectionId: string, name: string) =>
    call<StoredCollection>(`/api/collections/${collectionId}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    }),
  renameItem: (collectionId: string, itemId: string, name: string) =>
    call<StoredCollection>(
      `/api/collections/${collectionId}/items/${itemId}/rename`,
      { method: "PATCH", body: JSON.stringify({ name }) },
    ),
  moveItem: (collectionId: string, itemId: string, targetFolderId: string | null) =>
    call<StoredCollection>(
      `/api/collections/${collectionId}/items/${itemId}/move`,
      { method: "PATCH", body: JSON.stringify({ target_folder_id: targetFolderId }) },
    ),
  reorderItems: (collectionId: string, parentFolderId: string | null, itemIds: string[]) =>
    call<StoredCollection>(
      `/api/collections/${collectionId}/reorder`,
      { method: "PATCH", body: JSON.stringify({ parent_folder_id: parentFolderId, item_ids: itemIds }) },
    ),
  deleteFolder: (collectionId: string, folderId: string) =>
    call<StoredCollection>(
      `/api/collections/${collectionId}/folders/${folderId}`,
      { method: "DELETE" },
    ),
  duplicateRequest: (collectionId: string, requestId: string) =>
    call<StoredCollection>(
      `/api/collections/${collectionId}/requests/${requestId}/duplicate`,
      { method: "POST" },
    ),
  updateCollectionVariables: (collectionId: string, variables: CollectionVariable[]) =>
    call<StoredCollection>(`/api/collections/${collectionId}/variables`, {
      method: "PATCH",
      body: JSON.stringify({ variables }),
    }),
  listFavorites: () => call<{ items: FavoriteItem[] }>("/api/favorites"),
  addFavorite: (fav: FavoriteItem) =>
    call<{ items: FavoriteItem[] }>("/api/favorites", { method: "POST", body: JSON.stringify(fav) }),
  removeFavorite: (collectionId: string, requestId: string) =>
    call<{ items: FavoriteItem[] }>(`/api/favorites/${collectionId}/${requestId}`, { method: "DELETE" }),
  forkCollection: (collectionId: string) =>
    call<ForkOutput>(`/api/collections/${collectionId}/fork`, { method: "POST" }),
  mergeCollection: (collectionId: string, sourceId: string) =>
    call<MergeOutput>(`/api/collections/${collectionId}/merge`, {
      method: "POST",
      body: JSON.stringify({ source_id: sourceId }),
    }),
  listExamples: (collectionId: string, requestId: string) =>
    call<Array<{ id: string; name: string; method: string; url: string; headers: Record<string, string>; body: string | null; notes: string | null }>>(
      `/api/collections/${collectionId}/requests/${requestId}/examples`,
    ),
  addExample: (collectionId: string, requestId: string, example: {
    name: string; method?: string; url?: string; headers?: Record<string, string>; body?: string | null; notes?: string | null;
  }) =>
    call<StoredCollection>(`/api/collections/${collectionId}/requests/${requestId}/examples`, {
      method: "POST", body: JSON.stringify(example),
    }),
  deleteExample: (collectionId: string, requestId: string, exampleId: string) =>
    call<StoredCollection>(
      `/api/collections/${collectionId}/requests/${requestId}/examples/${exampleId}`,
      { method: "DELETE" },
    ),
  updateRequestExamples: (collectionId: string, requestId: string, examples: RequestExampleInput[]) =>
    call<StoredCollection>(
      `/api/advanced/collections/${collectionId}/requests/${requestId}/examples`,
      { method: "PATCH", body: JSON.stringify({ examples }) },
    ),
  getCollectionStats: (collectionId: string) =>
    call<CollectionStats>(`/api/collections/${collectionId}/stats`),
} as const;

export interface CollectionStats {
  collection_id: string;
  collection_name: string;
  request_breakdown: {
    total: number;
    by_method: Record<string, number>;
    by_folder: Array<{ name: string; request_count: number }>;
  };
  coverage: {
    with_assertions: number;
    without_assertions: number;
    assertion_coverage_pct: number;
    assertion_type_distribution: Record<string, number>;
  };
  auth_usage: {
    with_auth: number;
    without_auth: number;
    auth_coverage_pct: number;
    auth_type_distribution: Record<string, number>;
  };
  url_analysis: {
    unique_base_urls: string[];
    parameterized_urls: number;
    url_patterns: Record<string, number>;
  };
  body_analysis: {
    with_body: number;
    without_body: number;
    content_types: Record<string, number>;
    avg_body_size: number;
  };
  complexity: {
    total_headers: number;
    total_variables_used: number;
    scripts_attached: number;
  };
}
