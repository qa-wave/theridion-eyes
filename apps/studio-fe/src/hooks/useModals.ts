import { useState } from "react";

export type ModalId =
  | "envManager"
  | "soap"
  | "curlImport"
  | "graphql"
  | "webSocket"
  | "kafka"
  | "diff"
  | "codegen"
  | "testGen"
  | "grpc"
  | "mock"
  | "loadTest"
  | "settings"
  | "import"
  | "serviceMap"
  | "proxy"
  | "swagger"
  | "openapiImport"
  | "jwt"
  | "batch"
  | "monitors"
  | "security"
  | "collVars"
  | "secrets"
  | "webhooks"
  | "multiEnv"
  | "flowEditor"
  | "perfDash"
  | "agentExplorer"
  | "owaspScanner"
  | "requestDiff"
  | "collectionStats"
  | "envComparison"
  | "sse"
  | "changelog"
  | "responseCompare"
  | "pipeline"
  | "bodyDiff"
  | "openapiImport"
  | "docGenerator"
  | "depGraph"
  | "releaseCenter"
  | null;

export function useModals() {
  const [activeModal, setActiveModal] = useState<ModalId>(null);
  return {
    activeModal,
    open: (id: NonNullable<ModalId>) => setActiveModal(id),
    close: () => setActiveModal(null),
    isOpen: (id: NonNullable<ModalId>) => activeModal === id,
  };
}
