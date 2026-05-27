/**
 * Snippets library — sidecar client methods.
 */

import { call } from "./client";

// ---- Types ---------------------------------------------------------------

export interface Snippet {
  id: string;
  name: string;
  category: string;
  description: string;
  method: string;
  url: string;
  headers: Record<string, string>;
  body: string | null;
  auth: Record<string, unknown> | null;
  tags: string[];
  created_at: number;
  updated_at: number;
  builtin: boolean;
}

export interface SnippetCreate {
  name: string;
  category?: string;
  description?: string;
  method?: string;
  url?: string;
  headers?: Record<string, string>;
  body?: string | null;
  auth?: Record<string, unknown> | null;
  tags?: string[];
}

export interface SnippetUpdate {
  name?: string;
  category?: string;
  description?: string;
  method?: string;
  url?: string;
  headers?: Record<string, string>;
  body?: string | null;
  auth?: Record<string, unknown> | null;
  tags?: string[];
}

export interface SnippetList {
  items: Snippet[];
}

export interface SnippetExport {
  snippets: Snippet[];
}

// ---- Methods -------------------------------------------------------------

export const snippetsMethods = {
  listSnippets: (params?: {
    category?: string;
    tag?: string;
    search?: string;
  }) => {
    const sp = new URLSearchParams();
    if (params?.category) sp.set("category", params.category);
    if (params?.tag) sp.set("tag", params.tag);
    if (params?.search) sp.set("search", params.search);
    const qs = sp.toString();
    return call<SnippetList>(`/api/snippets${qs ? `?${qs}` : ""}`);
  },

  getSnippet: (id: string) => call<Snippet>(`/api/snippets/${id}`),

  createSnippet: (data: SnippetCreate) =>
    call<Snippet>("/api/snippets", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  updateSnippet: (id: string, data: SnippetUpdate) =>
    call<Snippet>(`/api/snippets/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  deleteSnippet: (id: string) =>
    call<void>(`/api/snippets/${id}`, { method: "DELETE" }),

  listSnippetCategories: () => call<string[]>("/api/snippets/categories"),

  exportSnippets: () => call<SnippetExport>("/api/snippets/export"),

  importSnippets: (snippets: SnippetCreate[]) =>
    call<SnippetList>("/api/snippets/import", {
      method: "POST",
      body: JSON.stringify({ snippets }),
    }),
};
