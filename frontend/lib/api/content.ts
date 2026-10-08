/**
 * Campaign Wizard creative API (SPEC-FE-016, SPEC-FE-031) against backend
 * app/api/v1/content.py (SPEC-BE-029/030/046). AI generation calls the LLM:
 * without a configured AI model the backend answers 503 "No AI model is
 * configured; cannot generate creative.". Hand-written variants and edits work
 * without any provider. Unknown SKUs -> 422; writes need manager+ (403).
 */
import type {
  CreativeAsset,
  CreativeGenerateRequest,
  CreativeManualCreate,
  VariantEdit,
} from "../types/content";
import { apiFetch } from "./client";

export function generateCreatives(body: CreativeGenerateRequest): Promise<CreativeAsset> {
  return apiFetch<CreativeAsset>("/api/v1/content/creatives", { method: "POST", body: { ...body } });
}

/** Hand-written variants; variant 0 comes back selected. */
export function createManualCreative(body: CreativeManualCreate): Promise<CreativeAsset> {
  return apiFetch<CreativeAsset>("/api/v1/content/creatives/manual", { method: "POST", body: { ...body } });
}

export function fetchCreative(assetId: string): Promise<CreativeAsset> {
  return apiFetch<CreativeAsset>(`/api/v1/content/creatives/${encodeURIComponent(assetId)}`);
}

/** Replaces one variant's text; the selection is unchanged. */
export function editVariant(assetId: string, index: number, body: VariantEdit): Promise<CreativeAsset> {
  return apiFetch<CreativeAsset>(`/api/v1/content/creatives/${encodeURIComponent(assetId)}/variants/${index}`, {
    method: "PATCH",
    body: { ...body },
  });
}

/** Persists the selection server-side and returns the updated asset. */
export function selectVariant(assetId: string, variantIndex: number): Promise<CreativeAsset> {
  return apiFetch<CreativeAsset>(`/api/v1/content/creatives/${encodeURIComponent(assetId)}/select`, {
    method: "POST",
    body: { variant_index: variantIndex },
  });
}
