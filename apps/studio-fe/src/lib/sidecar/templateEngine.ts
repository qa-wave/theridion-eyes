/**
 * Sidecar client — template engine (render, validate, extract variables).
 */

import { call } from "./client";

// ---- Types ----

export interface RenderOptions {
  allow_env?: boolean;
}

export interface TemplateRenderInput {
  template: string;
  variables: Record<string, unknown>;
  options?: RenderOptions;
}

export interface TemplateRenderOutput {
  rendered: string;
  variables_used: string[];
  warnings: string[];
}

export interface TemplateValidateInput {
  template: string;
}

export interface TemplateValidateOutput {
  valid: boolean;
  errors: string[];
}

export interface TemplateExtractInput {
  template: string;
}

export interface TemplateExtractOutput {
  variables: string[];
}

// ---- Methods ----

export const templateEngineMethods = {
  templateRender(input: TemplateRenderInput): Promise<TemplateRenderOutput> {
    return call<TemplateRenderOutput>("/api/template/render", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  templateValidate(input: TemplateValidateInput): Promise<TemplateValidateOutput> {
    return call<TemplateValidateOutput>("/api/template/validate", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  templateExtractVariables(input: TemplateExtractInput): Promise<TemplateExtractOutput> {
    return call<TemplateExtractOutput>("/api/template/variables", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
} as const;
