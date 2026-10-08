/**
 * Organic Marketing (SPEC-BE-076) and its analytics (SPEC-BE-078).
 * Reads: any role. Create/edit drafts: agent+. Approve, schedule, publish,
 * cancel, reschedule, retry: manager+ (403 otherwise).
 */
import type {
  AICreate,
  Calendar,
  Content,
  ContentList,
  ContentPatch,
  CopyPart,
  History,
  Insights,
  ManualCreate,
  OrganicImportResult,
  OrganicReport,
  Post,
  Preview,
  Summary,
  Target,
  VersionPatch,
} from "../types/organic";
import type { SocialPlatform } from "../types/social";
import { apiFetch } from "./client";

const V1 = "/api/v1/organic";
const enc = encodeURIComponent;

export const organicKeys = {
  all: ["organic"] as const,
  summary: ["organic", "summary"] as const,
  contents: (status: string, platform: string) => ["organic", "contents", status, platform] as const,
  content: (id: string) => ["organic", "content", id] as const,
  preview: (versionId: string) => ["organic", "preview", versionId] as const,
  calendar: (from: string, to: string) => ["organic", "calendar", from, to] as const,
  history: (status: string, platform: string, page: number) => ["organic", "history", status, platform, page] as const,
  report: (range: string) => ["organic", "report", range] as const,
  insights: (days: number) => ["organic", "insights", days] as const,
};

export const fetchSummary = () => apiFetch<Summary>(`${V1}/summary`);
export const fetchContents = (status = "", platform = "", page = 1) =>
  apiFetch<ContentList>(`${V1}/contents?page=${page}${status ? `&status=${status}` : ""}${platform ? `&platform=${platform}` : ""}`);
export const fetchContent = (id: string) => apiFetch<Content>(`${V1}/contents/${enc(id)}`);
export const createManual = (body: ManualCreate) => apiFetch<Content>(`${V1}/contents`, { method: "POST", body: { ...body } });
export const createAI = (body: AICreate) => apiFetch<Content>(`${V1}/contents/ai`, { method: "POST", body: { ...body } });
export const updateContent = (id: string, body: ContentPatch) => apiFetch<Content>(`${V1}/contents/${enc(id)}`, { method: "PATCH", body: { ...body } });
export const archiveContent = (id: string) => apiFetch<void>(`${V1}/contents/${enc(id)}`, { method: "DELETE" });
export const setTargets = (id: string, add: Target[], remove: SocialPlatform[]) =>
  apiFetch<Content>(`${V1}/contents/${enc(id)}/targets`, { method: "POST", body: { add, remove } });
export const approveContent = (id: string) => apiFetch<Content>(`${V1}/contents/${enc(id)}/approve`, { method: "POST" });
export const scheduleContent = (id: string, items: { version_id: string; scheduled_at_local: string; timezone?: string }[]) =>
  apiFetch<Content>(`${V1}/contents/${enc(id)}/schedule`, { method: "POST", body: { items } });

export const updateVersion = (id: string, body: VersionPatch) => apiFetch<Content>(`${V1}/versions/${enc(id)}`, { method: "PATCH", body: { ...body } });
export const regenerateVersion = (id: string, parts: CopyPart[], instruction?: string) =>
  apiFetch<Content>(`${V1}/versions/${enc(id)}/regenerate`, { method: "POST", body: { parts, instruction: instruction || null, keep_media: true } });
export const revertVersion = (id: string, variantIndex: number) =>
  apiFetch<Content>(`${V1}/versions/${enc(id)}/revert`, { method: "POST", body: { variant_index: variantIndex } });
export const fetchPreview = (id: string) => apiFetch<Preview>(`${V1}/versions/${enc(id)}/preview`);
export const scheduleVersion = (id: string, local: string, timezone?: string) =>
  apiFetch<Post>(`${V1}/versions/${enc(id)}/schedule`, { method: "POST", body: { scheduled_at_local: local, timezone: timezone || null } });
export const publishNow = (id: string) => apiFetch<Post>(`${V1}/versions/${enc(id)}/publish-now`, { method: "POST" });

export const cancelPost = (id: string) => apiFetch<Post>(`${V1}/posts/${enc(id)}/cancel`, { method: "POST" });
export const reschedulePost = (id: string, local: string, timezone?: string) =>
  apiFetch<Post>(`${V1}/posts/${enc(id)}/reschedule`, { method: "POST", body: { scheduled_at_local: local, timezone: timezone || null } });
export const retryPost = (id: string) => apiFetch<Post>(`${V1}/posts/${enc(id)}/retry`, { method: "POST" });

export const fetchCalendar = (from: string, to: string) => apiFetch<Calendar>(`${V1}/calendar?from=${from}&to=${to}`);
export const fetchHistory = (status = "", platform = "", page = 1) =>
  apiFetch<History>(`${V1}/history?page=${page}${status ? `&status=${status}` : ""}${platform ? `&platform=${platform}` : ""}`);

export const fetchInsights = (days: 30 | 60 | 90) => apiFetch<Insights>(`${V1}/insights?days=${days}`);
export const fetchOrganicReport = (range: string) => apiFetch<OrganicReport>(`/api/v1/analytics/organic?range=${enc(range)}`);
export const importOrganicResults = () => apiFetch<OrganicImportResult>("/api/v1/analytics/organic/import", { method: "POST" });
