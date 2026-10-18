/** Connected social accounts (SPEC-BE-075), mirroring app/schemas/social.py. */
export type SocialPlatform = "facebook" | "instagram" | "tiktok" | "linkedin";
export type SocialStatus = "connected" | "expired" | "error" | "missing_permissions" | "not_connected";

export interface SocialAccount {
  integration_id: string | null;
  platform: SocialPlatform;
  label: string;
  account_name: string | null;
  handle: string | null;
  avatar_url: string | null;
  status: SocialStatus;
  missing_permissions: string[];
  capabilities: Record<string, boolean>;
  limits: Record<string, unknown>;
  /** e.g. TikTok: privacy_level_options, comment_disabled, username. */
  extra: Record<string, unknown>;
  last_error: string | null;
  last_published_at: string | null;
  notes: string[];
  /** SPEC-BE-080: connection details (null / empty when not connected). */
  /** "socialapi" (SPEC-BE-104): no direct connection, the company's SocialAPI account posts instead. */
  connected_via: "oauth" | "token" | "socialapi" | null;
  account_id: string | null;
  scopes: string[];
  token_status: TokenStatus | null;
  token_expires_at: string | null;
  reconnect_by: string | null;
  last_checked_at: string | null;
  last_synced_at: string | null;
  oauth_available: boolean;
}

export type TokenStatus = "valid" | "expiring_soon" | "expired" | "no_expiry" | "unknown";

export interface SocialAccountList {
  items: SocialAccount[];
}

/** Sign-in flows (SPEC-BE-080): Instagram comes with its Facebook Page. */
export type SocialFlow = "meta" | "tiktok" | "linkedin";
export const PLATFORM_FLOW: Record<SocialPlatform, SocialFlow> = { facebook: "meta", instagram: "meta", tiktok: "tiktok", linkedin: "linkedin" };
export const FLOW_LABEL: Record<SocialFlow, string> = { meta: "Facebook", tiktok: "TikTok", linkedin: "LinkedIn" };

export interface OAuthChoice {
  id: string;
  name: string;
  handle: string | null;
  avatar_url: string | null;
  instagram: { id: string; username: string | null } | null;
}

export interface OAuthCallbackResult {
  flow: SocialFlow;
  saved: boolean;
  ok: boolean;
  message: string;
  choices: OAuthChoice[];
  scopes: string[];
}

export interface OAuthSelectResult {
  saved: string[];
  ok: boolean;
  message: string;
}

export interface UseMetaResult {
  facebook: boolean;
  instagram: boolean;
  message: string;
}

export const PLATFORM_LABEL: Record<SocialPlatform, string> = {
  facebook: "Facebook",
  instagram: "Instagram",
  tiktok: "TikTok",
  linkedin: "LinkedIn",
};

export const PLATFORMS: SocialPlatform[] = ["facebook", "instagram", "tiktok", "linkedin"];
