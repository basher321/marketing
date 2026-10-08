/**
 * Zernio paid ads (SPEC-BE-084): every company's paid campaigns through one
 * server-wide Zernio key. Read: any role. Connect, create, boost, pause/resume,
 * edit, delete: manager+. Campaigns are read live from Zernio.
 */
import type {
  ZAdAccount,
  ZAnalytics,
  ZBoostCreate,
  ZCallbackRequest,
  ZCallbackResult,
  ZCampaignCreate,
  ZCampaignList,
  ZCampaignNode,
  ZConnectResult,
  ZCreateResult,
  ZIdentities,
  ZPlatform,
  ZPlatformList,
  ZPost,
  ZPreviewResult,
  ZRange,
  ZReach,
  ZSearchHit,
  ZStatus,
  ZStatusResult,
  ZTargeting,
  ZValidateResult,
} from "../types/zernio";
import { apiFetch } from "./client";

const B = "/api/v1/zernio";

/** BroadcastChannel the sign-in tab uses to tell the wizard an account was connected. */
export const ZERNIO_CHANNEL = "zernio-accounts";

export const zernioKeys = {
  all: ["zernio"] as const,
  status: ["zernio", "status"] as const,
  platforms: ["zernio", "platforms"] as const,
  adAccounts: (accountId: string) => ["zernio", "ad-accounts", accountId] as const,
  identities: (accountId: string, adAccountId: string) => ["zernio", "identities", accountId, adAccountId] as const,
  posts: (accountId: string) => ["zernio", "posts", accountId] as const,
  search: (accountId: string, dimension: string, q: string) => ["zernio", "search", accountId, dimension, q] as const,
  campaigns: (filters: Record<string, string | number | null>) => ["zernio", "campaigns", filters] as const,
  analytics: (id: string, range: ZRange) => ["zernio", "analytics", id, range] as const,
};

const qs = (params: Record<string, string | number | null | undefined>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
};
const enc = encodeURIComponent;

export const fetchStatus = () => apiFetch<ZStatus>(`${B}/status`);
export const fetchPlatforms = () => apiFetch<ZPlatformList>(`${B}/platforms`);
export const connectPlatform = (platform: ZPlatform) => apiFetch<ZConnectResult>(`${B}/connect`, { method: "POST", body: { platform } });
export const finishConnect = (q: ZCallbackRequest) => apiFetch<ZCallbackResult>(`${B}/callback`, { method: "POST", body: q });
export const disconnectAccount = (id: string) => apiFetch<ZStatusResult>(`${B}/accounts/${enc(id)}`, { method: "DELETE" });

export const fetchAdAccounts = (accountId: string) => apiFetch<{ items: ZAdAccount[] }>(`${B}/accounts/${enc(accountId)}/ad-accounts`);
export const fetchIdentities = (accountId: string, adAccountId: string) =>
  apiFetch<ZIdentities>(`${B}/accounts/${enc(accountId)}/identities${qs({ ad_account_id: adAccountId })}`);
export const fetchPosts = (accountId: string) => apiFetch<{ items: ZPost[] }>(`${B}/accounts/${enc(accountId)}/posts`);
export const searchTargeting = (p: { account_id: string; q: string; dimension: string; geo_type?: string | null; ad_account_id?: string | null }) =>
  apiFetch<{ items: ZSearchHit[] }>(`${B}/targeting/search${qs(p)}`);
export const fetchReach = (body: { platform: ZPlatform; account_id: string; ad_account_id: string; targeting: ZTargeting }) =>
  apiFetch<ZReach>(`${B}/targeting/reach`, { method: "POST", body });

export const createCampaign = (body: ZCampaignCreate) => apiFetch<ZCreateResult>(`${B}/campaigns`, { method: "POST", body });
export const validateCampaign = (body: ZCampaignCreate) => apiFetch<ZValidateResult>(`${B}/campaigns/validate`, { method: "POST", body });
export const previewCampaign = (body: ZCampaignCreate) => apiFetch<ZPreviewResult>(`${B}/campaigns/preview`, { method: "POST", body });
export const boostPost = (body: ZBoostCreate) => apiFetch<ZCreateResult>(`${B}/boost`, { method: "POST", body });

export const fetchCampaigns = (f: { platform?: string | null; status?: string | null; q?: string | null; page?: number; range: ZRange }) =>
  apiFetch<ZCampaignList>(`${B}/campaigns${qs(f)}`);
export const setStatus = (level: "campaigns" | "ad-sets" | "ads", id: string, action: "pause" | "resume") =>
  apiFetch<ZStatusResult>(`${B}/${level}/${enc(id)}/${action}`, { method: "POST" });
export const updateCampaign = (id: string, body: { name?: string; budget?: { amount: string; type: "daily" | "lifetime" } }) =>
  apiFetch<ZCampaignNode>(`${B}/campaigns/${enc(id)}`, { method: "PATCH", body });
export const deleteCampaign = (id: string) => apiFetch<{ deleted: boolean; ad_count: number | null }>(`${B}/campaigns/${enc(id)}`, { method: "DELETE" });
export const fetchAnalytics = (id: string, range: ZRange, breakdowns?: string | null) =>
  apiFetch<ZAnalytics>(`${B}/campaigns/${enc(id)}/analytics${qs({ range, breakdowns })}`);
