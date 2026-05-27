/**
 * Tag management sidecar methods.
 */

import { call } from "./client";

export interface TagCount {
  tag: string;
  count: number;
}

export interface TagListResponse {
  tags: TagCount[];
  suggestions: string[];
}

export interface AssignTagsInput {
  collection_id: string;
  request_id: string;
  tags: string[];
}

export interface RemoveTagInput {
  collection_id: string;
  request_id: string;
  tag: string;
}

export interface BulkAssignInput {
  collection_id: string;
  request_ids: string[];
  tags: string[];
}

export interface TagSearchResult {
  collection_id: string;
  request_id: string;
  name: string;
  method: string | null;
  url: string | null;
  tags: string[];
}

export interface TagSearchResponse {
  results: TagSearchResult[];
}

export const tagsMethods = {
  listTags(): Promise<TagListResponse> {
    return call("/api/tags");
  },
  assignTags(input: AssignTagsInput): Promise<string[]> {
    return call("/api/tags/assign", { method: "POST", body: JSON.stringify(input) });
  },
  removeTag(input: RemoveTagInput): Promise<string[]> {
    return call("/api/tags/remove", { method: "POST", body: JSON.stringify(input) });
  },
  searchByTags(tags: string[], mode: "any" | "all" = "any"): Promise<TagSearchResponse> {
    const params = new URLSearchParams({ tags: tags.join(","), mode });
    return call(`/api/tags/search?${params}`);
  },
  bulkAssignTags(input: BulkAssignInput): Promise<{ updated: number }> {
    return call("/api/tags/bulk", { method: "POST", body: JSON.stringify(input) });
  },
};
