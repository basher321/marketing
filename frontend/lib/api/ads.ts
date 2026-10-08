/**
 * Multi-platform Ad Manager (SPEC-BE-062): the platform list and the builder
 * for TikTok, Google Ads, LinkedIn, X, Snapchat and Pinterest. Meta keeps its
 * own builder in ./meta.ts.
 */
import type {
  AdFields,
  BuilderPlatform,
  CampaignCreate,
  CampaignFields,
  GroupFields,
  LookupItem,
  MediaResult,
  PlatformList,
  PlatformTree,
  StatusResult,
  ValidateResult,
  Level,
} from "../types/ads";
import { apiFetch } from "./client";

const V1 = "/api/v1/ads";
const enc = encodeURIComponent;

export const adsKeys = {
  platforms: ["ads", "platforms"] as const,
  tree: (id: string) => ["ads", "tree", id] as const,
  lookup: (platform: string, kind: string, q = "") => ["ads", "lookup", platform, kind, q] as const,
};

export const fetchPlatforms = () => apiFetch<PlatformList>(`${V1}/platforms`);

/** Imports results for every published TikTok/Google/YouTube/LinkedIn/X/Snapchat/Pinterest campaign (throttled 5 min). */
export const syncPlatformResults = () =>
  apiFetch<{ synced_campaigns: number; rows_written: number; last_sync_at: string; errors: { campaign_id: string | null; message: string; at: string }[] }>(
    `${V1}/results/sync`,
    { method: "POST" },
  );

export const createPlatformCampaign = (platform: BuilderPlatform, body: CampaignCreate) =>
  apiFetch<PlatformTree>(`${V1}/${enc(platform)}/campaigns`, { method: "POST", body: { ...body } });
export const fetchPlatformTree = (id: string) => apiFetch<PlatformTree>(`${V1}/campaigns/${enc(id)}`);
export const updatePlatformCampaign = (id: string, body: CampaignFields) =>
  apiFetch<PlatformTree>(`${V1}/campaigns/${enc(id)}`, { method: "PATCH", body: { ...body } });

export const addGroup = (campaignId: string, body: GroupFields = {}) =>
  apiFetch<PlatformTree>(`${V1}/campaigns/${enc(campaignId)}/groups`, { method: "POST", body: { ...body } });
export const updateGroup = (id: string, body: GroupFields) =>
  apiFetch<PlatformTree>(`${V1}/groups/${enc(id)}`, { method: "PATCH", body: { ...body } });
export const duplicateGroup = (id: string) => apiFetch<PlatformTree>(`${V1}/groups/${enc(id)}/duplicate`, { method: "POST" });
export const deleteGroup = (id: string) => apiFetch<PlatformTree>(`${V1}/groups/${enc(id)}`, { method: "DELETE" });

export const addPlatformAd = (groupId: string, body: AdFields = {}) =>
  apiFetch<PlatformTree>(`${V1}/groups/${enc(groupId)}/ads`, { method: "POST", body: { ...body } });
export const updatePlatformAd = (id: string, body: AdFields) =>
  apiFetch<PlatformTree>(`${V1}/ads/${enc(id)}`, { method: "PATCH", body: { ...body } });
export const duplicatePlatformAd = (id: string) => apiFetch<PlatformTree>(`${V1}/ads/${enc(id)}/duplicate`, { method: "POST" });
export const deletePlatformAd = (id: string) => apiFetch<PlatformTree>(`${V1}/ads/${enc(id)}`, { method: "DELETE" });

export const validatePlatformCampaign = (id: string) =>
  apiFetch<ValidateResult>(`${V1}/campaigns/${enc(id)}/validate`, { method: "POST" });
export const publishPlatformCampaign = (id: string, mode: "active" | "paused") =>
  apiFetch<PlatformTree>(`${V1}/campaigns/${enc(id)}/publish`, { method: "POST", body: { mode } });

const LEVEL_PATH: Record<Level, string> = { campaign: "campaigns", group: "groups", ad: "ads" };
export const setPlatformStatus = (level: Level, id: string, resume: boolean) =>
  apiFetch<StatusResult>(`${V1}/${LEVEL_PATH[level]}/${enc(id)}/${resume ? "resume" : "pause"}`, { method: "POST" });

export const platformLookup = (platform: BuilderPlatform, kind: string, q: string) =>
  apiFetch<LookupItem[]>(`${V1}/${enc(platform)}/lookup/${enc(kind)}?q=${enc(q)}`);

export function uploadPlatformMedia(platform: BuilderPlatform, file: File): Promise<MediaResult> {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<MediaResult>(`${V1}/${enc(platform)}/media`, { method: "POST", body: form });
}
