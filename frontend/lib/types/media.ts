/** Media library (SPEC-BE-074), mirroring app/schemas/media.py. */
// "audio" = background music for AI videos only (SPEC-BE-094); listed only with ?kind=audio.
export type MediaKind = "image" | "video" | "audio";
export type MediaSource = "upload" | "ai_image" | "ai_video" | "catalog" | "derived";

export interface MediaItem {
  id: string;
  kind: MediaKind;
  mime: string;
  bytes: number;
  width: number | null;
  height: number | null;
  duration_ms: number | null;
  source: MediaSource;
  name: string | null;
  /** Signed URL (24 h), usable directly in <img>/<video>. */
  url: string;
  parent_id: string | null;
  approved: boolean;
  created_at: string;
}

export interface MediaList {
  count: number;
  items: MediaItem[];
}

export type DeriveRatio = "1:1" | "4:5" | "9:16" | "16:9" | "1.91:1" | "2:3";
