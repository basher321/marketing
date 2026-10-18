/**
 * Integrations API (SPEC-FE-021, SPEC-FE-037): platform connections
 * (SPEC-BE-052) and AI models with a fallback order (SPEC-BE-053). Keys are
 * entered here, never in .env. Reads are open to any role; writes need
 * manager+ (403 otherwise).
 */
import type {
  AIModelList,
  AIModelTestResult,
  AIModelUpdate,
  ProviderModels,
  AIProvider,
  CatalogProvider,
  IntegrationSave,
  IntegrationStatus,
  IntegrationTestResult,
} from "../types/integrations";
import { apiFetch } from "./client";

export const integrationKeys = {
  all: ["integrations"] as const,
  list: ["integrations", "list"] as const,
  catalog: ["integrations", "catalog"] as const,
  aiModels: ["integrations", "ai-models"] as const,
};

export function fetchIntegrations(): Promise<IntegrationStatus[]> {
  return apiFetch<IntegrationStatus[]>("/api/v1/integrations");
}

export function fetchCatalog(): Promise<CatalogProvider[]> {
  return apiFetch<CatalogProvider[]>("/api/v1/integrations/catalog");
}

/** Saves the credentials (encrypted server-side) and runs the connection test. */
export function saveIntegration(provider: string, body: IntegrationSave): Promise<IntegrationTestResult> {
  return apiFetch<IntegrationTestResult>(`/api/v1/integrations/${encodeURIComponent(provider)}`, {
    method: "PUT",
    body: { ...body },
  });
}

export function testIntegration(provider: string): Promise<IntegrationTestResult> {
  return apiFetch<IntegrationTestResult>(`/api/v1/integrations/${encodeURIComponent(provider)}/test`, { method: "POST" });
}

export function disconnectIntegration(provider: string): Promise<void> {
  return apiFetch<void>(`/api/v1/integrations/${encodeURIComponent(provider)}`, { method: "DELETE" });
}

/** The company's read-only view (SPEC-BE-101); the Super admin edits under PLATFORM_AI_BASE. */
export const AI_BASE = "/api/v1/ai-models";
export const PLATFORM_AI_BASE = "/api/v1/platform/ai-models";

export function fetchAIModels(base: string = AI_BASE): Promise<AIModelList> {
  return apiFetch<AIModelList>(base);
}

export function updateAIModel(provider: AIProvider, body: AIModelUpdate, base: string = AI_BASE): Promise<AIModelList> {
  return apiFetch<AIModelList>(`${base}/${provider}`, { method: "PUT", body: { ...body } });
}

export function setAIModelOrder(order: AIProvider[], base: string = AI_BASE): Promise<AIModelList> {
  return apiFetch<AIModelList>(`${base}/order`, { method: "PUT", body: { order } });
}

export function fetchProviderModels(provider: AIProvider, base: string = AI_BASE): Promise<ProviderModels> {
  return apiFetch<ProviderModels>(`${base}/${provider}/models`);
}

export function testAIModel(provider: AIProvider, base: string = AI_BASE): Promise<AIModelTestResult> {
  return apiFetch<AIModelTestResult>(`${base}/${provider}/test`, { method: "POST" });
}

export function deleteAIModelKey(provider: AIProvider, base: string = AI_BASE): Promise<AIModelList> {
  return apiFetch<AIModelList>(`${base}/${provider}`, { method: "DELETE" });
}
