/**
 * Meta connect (SPEC-BE-054), Ads Manager-style builder (SPEC-BE-055) and
 * results (SPEC-BE-056). Every Meta object is created by the backend; the
 * browser only opens Meta's OAuth dialog and renders Meta's preview iframe.
 */
import type {
  AdFields,
  AdSetFields,
  BuilderObjective,
  BuilderTree,
  CampaignFields,
  CampaignResults,
  ExistingPost,
  LookupItem,
  MediaResult,
  MetaChoices,
  MetaConnectUrl,
  MetaSelect,
  MetaSyncResult,
  ObjectivesResult,
  Placements,
  PostCreate,
  PostList,
  PreviewResult,
  ProductSet,
  ReachResult,
  StatusResult,
  Targeting,
  ValidateResult,
} from "../types/meta";
import type { IntegrationStatus } from "../types/integrations";
import { apiFetch } from "./client";

const V1 = "/api/v1";
const enc = encodeURIComponent;

export const metaKeys = {
  objectives: ["meta", "objectives"] as const,
  tree: (id: string) => ["meta", "tree", id] as const,
  results: (id: string, range: string) => ["meta", "results", id, range] as const,
  lookup: (kind: string, q = "") => ["meta", "lookup", kind, q] as const,
};

// --- connect ---
export const metaConnectUrl = () => apiFetch<MetaConnectUrl>(`${V1}/integrations/meta/connect`);
export const metaCallback = (code: string, state: string) =>
  apiFetch<MetaChoices>(`${V1}/integrations/meta/callback`, { method: "POST", body: { code, state } });
export const metaSelect = (body: MetaSelect) =>
  apiFetch<IntegrationStatus>(`${V1}/integrations/meta/select`, { method: "POST", body: { ...body } });

// --- lookups ---
export const fetchObjectives = () => apiFetch<ObjectivesResult>(`${V1}/meta/objectives`);
export const searchTargeting = (type: string, q: string) =>
  apiFetch<LookupItem[]>(`${V1}/meta/targeting/search?type=${enc(type)}&q=${enc(q)}`);
export const fetchCustomAudiences = () => apiFetch<LookupItem[]>(`${V1}/meta/custom-audiences`);
export const fetchApps = () => apiFetch<LookupItem[]>(`${V1}/meta/apps`);
export const fetchLeadForms = () => apiFetch<LookupItem[]>(`${V1}/meta/lead-forms`);
// Ad setup (SPEC-BE-082)
export const fetchProductSets = () => apiFetch<ProductSet[]>(`${V1}/meta/product-sets`);
export const fetchPosts = (platform: ExistingPost["platform"], after?: string | null) =>
  apiFetch<PostList>(`${V1}/meta/posts?platform=${platform}${after ? `&after=${enc(after)}` : ""}`);
export const createPost = (body: PostCreate) => apiFetch<ExistingPost>(`${V1}/meta/posts`, { method: "POST", body: { ...body } });
export const fetchPixels = () => apiFetch<LookupItem[]>(`${V1}/meta/pixels`);
export const reachEstimate = (targeting: Targeting, optimization_goal: string, placements: Placements) =>
  apiFetch<ReachResult>(`${V1}/meta/reach-estimate`, { method: "POST", body: { targeting, optimization_goal, placements } });
export function uploadMedia(file: File): Promise<MediaResult> {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<MediaResult>(`${V1}/meta/media`, { method: "POST", body: form });
}
export const videoStatus = (videoId: string) => apiFetch<MediaResult>(`${V1}/meta/media/videos/${enc(videoId)}`);

// --- tree ---
export const createBuilderCampaign = (name: string, objective: BuilderObjective) =>
  apiFetch<BuilderTree>(`${V1}/campaigns/builder`, { method: "POST", body: { name, objective } });
export const fetchTree = (id: string) => apiFetch<BuilderTree>(`${V1}/campaigns/${enc(id)}/builder`);
export const updateCampaign = (id: string, body: CampaignFields) =>
  apiFetch<BuilderTree>(`${V1}/campaigns/${enc(id)}/builder`, { method: "PATCH", body: { ...body } });
export const addAdSet = (campaignId: string, body: AdSetFields = {}) =>
  apiFetch<BuilderTree>(`${V1}/campaigns/${enc(campaignId)}/ad-sets`, { method: "POST", body: { ...body } });
export const updateAdSet = (id: string, body: AdSetFields) =>
  apiFetch<BuilderTree>(`${V1}/ad-sets/${enc(id)}`, { method: "PATCH", body: { ...body } });
export const duplicateAdSet = (id: string) => apiFetch<BuilderTree>(`${V1}/ad-sets/${enc(id)}/duplicate`, { method: "POST" });
export const deleteAdSet = (id: string) => apiFetch<BuilderTree>(`${V1}/ad-sets/${enc(id)}`, { method: "DELETE" });
export const addAd = (adSetId: string, body: AdFields = {}) =>
  apiFetch<BuilderTree>(`${V1}/ad-sets/${enc(adSetId)}/ads`, { method: "POST", body: { ...body } });
export const updateAd = (id: string, body: AdFields) =>
  apiFetch<BuilderTree>(`${V1}/ads/${enc(id)}`, { method: "PATCH", body: { ...body } });
export const duplicateAd = (id: string) => apiFetch<BuilderTree>(`${V1}/ads/${enc(id)}/duplicate`, { method: "POST" });
export const deleteAd = (id: string) => apiFetch<BuilderTree>(`${V1}/ads/${enc(id)}`, { method: "DELETE" });

// --- review / publish / status ---
export const validateCampaign = (id: string) =>
  apiFetch<ValidateResult>(`${V1}/campaigns/${enc(id)}/validate`, { method: "POST" });
export const previewAd = (adId: string, format: string) =>
  apiFetch<PreviewResult>(`${V1}/ads/${enc(adId)}/preview?format=${enc(format)}`, { method: "POST" });
export const publishCampaign = (id: string, mode: "active" | "paused") =>
  apiFetch<BuilderTree>(`${V1}/campaigns/${enc(id)}/publish`, { method: "POST", body: { mode } });
export function setStatus(level: "campaign" | "ad_set" | "ad", id: string, resume: boolean): Promise<StatusResult | unknown> {
  const action = resume ? "resume" : "pause";
  if (level === "campaign") return apiFetch(`${V1}/campaigns/${enc(id)}/${action}`, { method: "POST" });
  const base = level === "ad_set" ? "ad-sets" : "ads";
  return apiFetch<StatusResult>(`${V1}/${base}/${enc(id)}/${action}`, { method: "POST" });
}

// --- results (SPEC-BE-056) ---
export const fetchCampaignResults = (id: string, range: string) =>
  apiFetch<CampaignResults>(`${V1}/campaigns/${enc(id)}/results?range=${enc(range)}`);
export const syncCampaignResults = (id: string) =>
  apiFetch<MetaSyncResult>(`${V1}/campaigns/${enc(id)}/sync`, { method: "POST" });
export const syncAllMetaResults = () => apiFetch<MetaSyncResult>(`${V1}/analytics/meta/sync`, { method: "POST" });
