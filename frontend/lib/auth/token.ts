/**
 * Session token storage (SPEC-FE-004, extended by SPEC-FE-024 and SPEC-FE-070).
 *
 * DELIBERATE TRADEOFF: tokens live in localStorage. That is simple and
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
 * One login per tab (SPEC-FE-070), so different users can work side by side
 * in one browser:
 * - Each user's pair is stored once, under `ai-orchestrator.session.<user id>`.
 *   All tabs of the same user share it, so one tab's refresh serves them all
 *   (the refresh itself is serialised across tabs in client.ts).
 * - sessionStorage `ai-orchestrator.tab_user` pins which user this tab is.
 *   It survives a reload, and a duplicated tab copies it.
 * - A new tab has no pin yet: it takes `ai-orchestrator.last_user`, the most
 *   recent login in this browser, and pins it at once, so a later login in
 *   another tab never switches it.
 * - Signing out removes only that user's pair, so other users' tabs stay
 *   signed in.
 *
 * No call site of apiFetch() may special-case "no token" behavior itself.
 * Every accessor tolerates storage being unavailable (server render, private
 * mode, blocked site data): reads return null, writes are no-ops.
 */
const SESSION_PREFIX = "ai-orchestrator.session.";
const LAST_USER_KEY = "ai-orchestrator.last_user";
const TAB_USER_KEY = "ai-orchestrator.tab_user";
// Before SPEC-FE-070: one pair per browser. Moved into a session on first read.
const LEGACY_ACCESS_KEY = "ai-orchestrator.access_token";
const LEGACY_REFRESH_KEY = "ai-orchestrator.refresh_token";

interface StoredSession {
  access_token: string | null;
  refresh_token: string | null;
}

function local(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

function tab(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.sessionStorage;
  } catch {
    return null;
  }
}

function safe(fn: () => void): void {
  try {
    fn();
  } catch {
    // Storage unavailable or full: the session will not survive a refresh.
  }
}

/** The user id (`sub`) inside a JWT. Read only to pick the storage slot; the backend verifies the token. */
export function tokenSubject(token: string): string | null {
  try {
    const part = token.split(".")[1];
    if (!part) return null;
    const json = atob(part.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(part.length / 4) * 4, "="));
    const sub = (JSON.parse(json) as { sub?: unknown }).sub;
    return typeof sub === "string" && sub ? sub : null;
  } catch {
    return null;
  }
}

function readSession(user: string): StoredSession | null {
  try {
    const raw = local()?.getItem(SESSION_PREFIX + user);
    return raw ? (JSON.parse(raw) as StoredSession) : null;
  } catch {
    return null;
  }
}

function writeSession(user: string, change: Partial<StoredSession>): void {
  const next = { access_token: null, refresh_token: null, ...readSession(user), ...change };
  safe(() => local()?.setItem(SESSION_PREFIX + user, JSON.stringify(next)));
}

function migrateLegacy(): void {
  const store = local();
  if (!store) return;
  safe(() => {
    const access = store.getItem(LEGACY_ACCESS_KEY);
    const refresh = store.getItem(LEGACY_REFRESH_KEY);
    if (access === null && refresh === null) return;
    const user = (refresh && tokenSubject(refresh)) || (access && tokenSubject(access));
    if (user) {
      writeSession(user, { access_token: access, refresh_token: refresh });
      if (!store.getItem(LAST_USER_KEY)) store.setItem(LAST_USER_KEY, user);
    }
    store.removeItem(LEGACY_ACCESS_KEY);
    store.removeItem(LEGACY_REFRESH_KEY);
  });
}

/** The user this tab is signed in as (pinned on first use), or null. */
export function currentUser(): string | null {
  migrateLegacy();
  let pinned: string | null = null;
  try {
    pinned = tab()?.getItem(TAB_USER_KEY) ?? null;
  } catch {
    pinned = null;
  }
  if (pinned) return pinned;
  let last: string | null = null;
  try {
    last = local()?.getItem(LAST_USER_KEY) ?? null;
  } catch {
    last = null;
  }
  if (last && readSession(last)) {
    safe(() => tab()?.setItem(TAB_USER_KEY, last));
    return last;
  }
  return null;
}

/** Make `user` this tab's login and the browser's most recent one (a sign-in). */
function signInAs(user: string): void {
  safe(() => tab()?.setItem(TAB_USER_KEY, user));
  safe(() => local()?.setItem(LAST_USER_KEY, user));
}

export function getAuthToken(): string | null {
  const user = currentUser();
  return user ? readSession(user)?.access_token ?? null : null;
}

export function setAuthToken(token: string): void {
  const user = tokenSubject(token) ?? currentUser();
  if (!user) return;
  if (user !== currentUser()) signInAs(user);
  writeSession(user, { access_token: token });
}

export function getRefreshToken(): string | null {
  const user = currentUser();
  return user ? readSession(user)?.refresh_token ?? null : null;
}

export function setRefreshToken(token: string): void {
  const user = tokenSubject(token) ?? currentUser();
  if (!user) return;
  if (user !== currentUser()) signInAs(user);
  writeSession(user, { refresh_token: token });
}

/** A sign-in (login / sign-up): this tab becomes that user, and new tabs start as them. */
export function signIn(accessToken: string, refreshToken: string): void {
  const user = tokenSubject(accessToken) ?? tokenSubject(refreshToken);
  if (!user) return;
  signInAs(user);
  writeSession(user, { access_token: accessToken, refresh_token: refreshToken });
}

/** Sign-out (logout, rejected session): removes this tab's user's tokens only. */
export function clearAuthToken(): void {
  const user = currentUser();
  const store = local();
  safe(() => {
    if (user && store) {
      store.removeItem(SESSION_PREFIX + user);
      if (store.getItem(LAST_USER_KEY) === user) store.removeItem(LAST_USER_KEY);
    }
    tab()?.removeItem(TAB_USER_KEY);
  });
}
