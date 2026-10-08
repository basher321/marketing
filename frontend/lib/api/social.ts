/**
 * Connected social accounts (SPEC-BE-075) and their sign-in (SPEC-BE-080).
 * Read: any role. "Use my Meta connection" and sign-in: manager+.
 * Tokens never reach the browser: the backend exchanges the code.
 */
import type { OAuthCallbackResult, OAuthSelectResult, SocialAccountList, SocialFlow, UseMetaResult } from "../types/social";
import { apiFetch } from "./client";

export const socialKeys = {
  accounts: ["social", "accounts"] as const,
};

export const fetchSocialAccounts = () => apiFetch<SocialAccountList>("/api/v1/social/accounts");
export const connectFromMeta = () => apiFetch<UseMetaResult>("/api/v1/social/accounts/use-meta", { method: "POST" });

export const oauthConnect = (flow: SocialFlow) => apiFetch<{ login_url: string }>(`/api/v1/social/oauth/${flow}/connect`);
export const oauthCallback = (flow: SocialFlow, code: string, state: string) =>
  apiFetch<OAuthCallbackResult>(`/api/v1/social/oauth/${flow}/callback`, { method: "POST", body: { code, state } });
export const oauthSelect = (flow: SocialFlow, accountId: string, includeInstagram: boolean) =>
  apiFetch<OAuthSelectResult>(`/api/v1/social/oauth/${flow}/select`, {
    method: "POST",
    body: { account_id: accountId, include_instagram: includeInstagram },
  });
