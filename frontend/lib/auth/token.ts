/**
 * Session token storage (SPEC-FE-004, extended by SPEC-FE-024).
 *
 * DELIBERATE TRADEOFF: both tokens live in localStorage. That is simple and
 * survives a browser refresh, but any script running on the page (an XSS bug)
 * can read them. httpOnly cookies would avoid that; revisit if a later
 * security-hardening spec requires it.
 *
 * - Access token: sent as `Authorization: Bearer ...` by apiFetch(); lives 15
 *   minutes.
 * - Refresh token (SPEC-FE-024): lives 7 days. When the access token expires,
 *   apiFetch() silently exchanges it for a new pair (lib/api/client.ts), so an
 *   active user stays signed in instead of being sent to /login every 15
 *   minutes.
 *
 * No call site of apiFetch() may special-case "no token" behavior itself.
 * Every accessor tolerates localStorage being unavailable (server render,
 * private mode, blocked site data): reads return null, writes are no-ops.
 */
const ACCESS_TOKEN_KEY = "ai-orchestrator.access_token";
const REFRESH_TOKEN_KEY = "ai-orchestrator.refresh_token";

function read(key: string): string | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Storage unavailable: the session will not survive a refresh.
  }
}

export function getAuthToken(): string | null {
  return read(ACCESS_TOKEN_KEY);
}

export function setAuthToken(token: string): void {
  write(ACCESS_TOKEN_KEY, token);
}

export function getRefreshToken(): string | null {
  return read(REFRESH_TOKEN_KEY);
}

export function setRefreshToken(token: string): void {
  write(REFRESH_TOKEN_KEY, token);
}

/** Sign-out: removes both tokens (logout, rejected session). */
export function clearAuthToken(): void {
  try {
    window.localStorage.removeItem(ACCESS_TOKEN_KEY);
    window.localStorage.removeItem(REFRESH_TOKEN_KEY);
  } catch {
    // Storage unavailable: nothing was stored.
  }
}
