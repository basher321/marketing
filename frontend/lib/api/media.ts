/**
 * Media library (SPEC-BE-074). Reads: any role; upload/derive: agent+;
 * delete: manager+ (409 while a scheduled post uses the item).
 */
import type { DeriveRatio, MediaItem, MediaKind, MediaList } from "../types/media";
import { apiFetch } from "./client";

const V1 = "/api/v1";
const enc = encodeURIComponent;

export const mediaKeys = {
  list: (kind?: MediaKind | "") => ["media", "list", kind ?? ""] as const,
  item: (id: string) => ["media", "item", id] as const,
};

// `q` (SPEC-FE-056) searches by name; existing callers omit it.
export const fetchMedia = (kind?: MediaKind | "", page = 1, q = "") =>
  apiFetch<MediaList>(`${V1}/media?page=${page}${kind ? `&kind=${kind}` : ""}${q ? `&q=${enc(q)}` : ""}`);

// One item with a fresh signed URL (SPEC-FE-057: Command Chat previews).
export const fetchMediaItem = (id: string) => apiFetch<MediaItem>(`${V1}/media/${enc(id)}`);

export function uploadMedia(file: File): Promise<MediaItem> {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<MediaItem>(`${V1}/media`, { method: "POST", body: form });
}

export const deriveMedia = (id: string, ratio: DeriveRatio, mode: "crop" | "pad" = "crop") =>
  apiFetch<MediaItem>(`${V1}/media/${enc(id)}/derive`, { method: "POST", body: { ratio, mode } });

export const deleteMedia = (id: string) => apiFetch<void>(`${V1}/media/${enc(id)}`, { method: "DELETE" });
