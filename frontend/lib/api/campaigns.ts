/**
 * Campaign Wizard API (SPEC-FE-030): drafts (SPEC-BE-044), audiences
 * (SPEC-BE-045) and launch (SPEC-BE-047). Reads are open to any role; every
 * write requires manager or above (403 otherwise).
 */
import type {
  Audience,
  AudienceCreate,
  AudienceList,
  CampaignDetail,
  CampaignDraftCreate,
  CampaignDraftUpdate,
} from "../types/campaigns";
import { apiFetch } from "./client";

export const campaignKeys = {
  drafts: ["campaigns", "drafts"] as const,
  detail: (id: string) => ["campaigns", "detail", id] as const,
  audiences: ["campaigns", "audiences"] as const,
};

export function fetchDrafts(): Promise<CampaignDetail[]> {
  return apiFetch<CampaignDetail[]>("/api/v1/campaigns/drafts");
}

export function fetchCampaign(id: string): Promise<CampaignDetail> {
  return apiFetch<CampaignDetail>(`/api/v1/campaigns/${encodeURIComponent(id)}`);
}

export function createDraft(body: CampaignDraftCreate): Promise<CampaignDetail> {
  return apiFetch<CampaignDetail>("/api/v1/campaigns", { method: "POST", body: { ...body } });
}

export function updateDraft(id: string, body: CampaignDraftUpdate): Promise<CampaignDetail> {
  return apiFetch<CampaignDetail>(`/api/v1/campaigns/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: { ...body },
  });
}

/** Goes live, or queues an owner approval (the response's pending_approval_id is then set). */
export function launchCampaign(id: string): Promise<CampaignDetail> {
  return apiFetch<CampaignDetail>(`/api/v1/campaigns/${encodeURIComponent(id)}/launch`, { method: "POST" });
}

export function fetchAudiences(): Promise<AudienceList> {
  return apiFetch<AudienceList>("/api/v1/audiences");
}

export function createAudience(body: AudienceCreate): Promise<Audience> {
  return apiFetch<Audience>("/api/v1/audiences", { method: "POST", body: { ...body } });
}
