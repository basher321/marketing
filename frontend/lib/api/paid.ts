/** Paid Marketing lists (SPEC-BE-079). Reads: any role. Pause/resume: manager+ (403 otherwise). */
import type { AdItem, AdSetItem, PaidList, PaidListQuery, PaidStatusResult } from "../types/paid";
import { apiFetch } from "./client";

const V1 = "/api/v1/paid";

export const paidKeys = {
  all: ["paid"] as const,
  adSets: (q: PaidListQuery) => ["paid", "ad-sets", q] as const,
  ads: (q: PaidListQuery) => ["paid", "ads", q] as const,
};

function query(q: PaidListQuery): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(q)) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  return params.toString();
}

export const fetchAdSets = (q: PaidListQuery) => apiFetch<PaidList<AdSetItem>>(`${V1}/ad-sets?${query(q)}`);
export const fetchAds = (q: PaidListQuery) => apiFetch<PaidList<AdItem>>(`${V1}/ads?${query(q)}`);

export const setPaidStatus = (level: "ad-sets" | "ads", id: string, resume: boolean) =>
  apiFetch<PaidStatusResult>(`${V1}/${level}/${encodeURIComponent(id)}/${resume ? "resume" : "pause"}`, { method: "POST" });
