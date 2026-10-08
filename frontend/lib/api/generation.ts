/**
 * Photo / video generation (SPEC-BE-077). Generate, regenerate, edit,
 * cancel: agent+; approve: manager+. Starting returns the queued job(s);
 * poll fetchJob until it ends.
 */
import type { ApproveRequest, GenerationJob, GenerationKind, JobList, PhotoRequest, Readiness, VideoRequest } from "../types/generation";
import { apiFetch } from "./client";

const V1 = "/api/v1/organic";
const enc = encodeURIComponent;

export const generationKeys = {
  readiness: ["generation", "readiness"] as const,
  list: (kind: GenerationKind) => ["generation", "list", kind] as const,
  job: (id: string) => ["generation", "job", id] as const,
};

export const fetchGenerationReadiness = () => apiFetch<Readiness>(`${V1}/generation/providers`);
export const generatePhoto = (body: PhotoRequest) => apiFetch<{ jobs: GenerationJob[] }>(`${V1}/generate/photo`, { method: "POST", body: { ...body } });
export const generateVideo = (body: VideoRequest) => apiFetch<{ jobs: GenerationJob[] }>(`${V1}/generate/video`, { method: "POST", body: { ...body } });
export const fetchJobs = (kind: GenerationKind, page = 1) => apiFetch<JobList>(`${V1}/generations?kind=${kind}&page=${page}`);
export const fetchJob = (id: string) => apiFetch<GenerationJob>(`${V1}/generations/${enc(id)}`);
export const regenerateJob = (id: string, changes: Record<string, unknown> = {}) =>
  apiFetch<GenerationJob>(`${V1}/generations/${enc(id)}/regenerate`, { method: "POST", body: changes });
export const editJob = (id: string, instruction: string) =>
  apiFetch<GenerationJob>(`${V1}/generations/${enc(id)}/edit`, { method: "POST", body: { instruction } });
export const cancelJob = (id: string) => apiFetch<GenerationJob>(`${V1}/generations/${enc(id)}/cancel`, { method: "POST" });
export const approveJob = (id: string, body: ApproveRequest = {}) =>
  apiFetch<GenerationJob>(`${V1}/generations/${enc(id)}/approve`, { method: "POST", body: { ...body } });

export const isRunning = (job: GenerationJob) => job.status === "queued" || job.status === "running";
