/**
 * AI Ad Autopilot (SPEC-BE-069) and creative providers (SPEC-BE-070).
 * A run never publishes by itself: publishRun is the only way it goes live.
 */
import type {
  AICampaignCreate,
  AICampaignRun,
  AICampaignRunSummary,
  CreativeKind,
  CreativeSettings,
  Readiness,
  MCPToolSave,
  MCPToolTest,
  VideoAudioSave,
  VideoAudioSettings,
} from "../types/ai-campaigns";
import { apiFetch } from "./client";

const V1 = "/api/v1";
const enc = encodeURIComponent;

export const aiCampaignKeys = {
  list: ["ai-campaigns", "list"] as const,
  readiness: ["ai-campaigns", "readiness"] as const,
  run: (id: string) => ["ai-campaigns", "run", id] as const,
  creative: ["ai-models", "creative"] as const,
  videoAudio: ["ai-models", "video-audio"] as const,
};

/** What the form may offer, from real data (SPEC-FE-046 amendment). */
export const fetchReadiness = () => apiFetch<Readiness>(`${V1}/ai-campaigns/readiness`);
export const startRun = (body: AICampaignCreate) => apiFetch<AICampaignRun>(`${V1}/ai-campaigns`, { method: "POST", body: { ...body } });
export const fetchRuns = () => apiFetch<{ items: AICampaignRunSummary[] }>(`${V1}/ai-campaigns`);
export const fetchRun = (id: string) => apiFetch<AICampaignRun>(`${V1}/ai-campaigns/${enc(id)}`);
export const answerRun = (id: string, answers: string[]) =>
  apiFetch<AICampaignRun>(`${V1}/ai-campaigns/${enc(id)}/answer`, { method: "POST", body: { answers } });
export const retryRun = (id: string, fromStage?: string) =>
  apiFetch<AICampaignRun>(`${V1}/ai-campaigns/${enc(id)}/retry`, { method: "POST", body: fromStage ? { from_stage: fromStage } : {} });
export const cancelRun = (id: string) => apiFetch<AICampaignRun>(`${V1}/ai-campaigns/${enc(id)}/cancel`, { method: "POST" });
export const regenerateAd = (id: string, ref: string, what: "copy" | "image") =>
  apiFetch<AICampaignRun>(`${V1}/ai-campaigns/${enc(id)}/regenerate`, { method: "POST", body: { ref, what } });
export const publishRun = (id: string, acknowledgeWarnings: boolean, mode: "active" | "paused" = "active") =>
  apiFetch<AICampaignRun>(`${V1}/ai-campaigns/${enc(id)}/publish`, { method: "POST", body: { acknowledge_warnings: acknowledgeWarnings, mode } });

export const fetchCreativeSettings = () => apiFetch<CreativeSettings>(`${V1}/ai-models/creative`);
// Sound for AI slideshow videos (SPEC-FE-060).
export const fetchVideoAudio = () => apiFetch<VideoAudioSettings>(`${V1}/ai-models/video-audio`);
export const saveVideoAudio = (body: VideoAudioSave) =>
  apiFetch<VideoAudioSettings>(`${V1}/ai-models/video-audio`, { method: "PUT", body: { ...body } });
export const saveCreativeOrder = (order: Partial<Record<CreativeKind, string[]>>) =>
  apiFetch<CreativeSettings>(`${V1}/ai-models/creative`, { method: "PUT", body: { order } });
export const saveMCPTool = (id: string, body: MCPToolSave) =>
  apiFetch<CreativeSettings>(`${V1}/ai-models/mcp/${enc(id)}`, { method: "PUT", body: { ...body } });
export const deleteMCPTool = (id: string) => apiFetch<CreativeSettings>(`${V1}/ai-models/mcp/${enc(id)}`, { method: "DELETE" });
export const testMCPTool = (id: string) => apiFetch<MCPToolTest>(`${V1}/ai-models/mcp/${enc(id)}/test`, { method: "POST" });
