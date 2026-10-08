/**
 * The single shared way the frontend talks to the backend (SPEC-FE-003).
 * Every later spec calls apiFetch() (usually from a TanStack Query hook in
 * hooks/use-<domain>.ts); none should call fetch() directly.
 */
import { getAuthToken, getRefreshToken, setAuthToken, setRefreshToken } from "../auth/token";
import { ApiError } from "../types/common";

/**
 * RequestInit, but `body` may also be a plain object or array, which is
 * JSON.stringify'd. (RequestInit's own `body` type cannot express that.)
 */
export type ApiFetchInit = Omit<RequestInit, "body"> & {
  body?: BodyInit | Record<string, unknown> | unknown[] | null;
};

function isPlainJsonBody(body: unknown): body is Record<string, unknown> | unknown[] {
  if (Array.isArray(body)) return true;
  if (body === null || typeof body !== "object") return false;
  const proto = Object.getPrototypeOf(body);
  return proto === Object.prototype || proto === null;
}

function parseMaybeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

// Error message for a non-2xx response: the backend's own `{"error": "..."}`
// shape (AppError handler), then FastAPI's `{"detail": "..."}` when it is a
// string, then the HTTP status text, then "HTTP <status>".
function errorMessage(body: unknown, response: Response): string {
  if (body && typeof body === "object") {
    const { error, detail } = body as { error?: unknown; detail?: unknown };
    if (typeof error === "string" && error) return error;
    if (typeof detail === "string" && detail) return detail;
  }
  return response.statusText || `HTTP ${response.status}`;
}

// One refresh in flight at a time: concurrent 401s (a page firing several queries when the
// token expires) all await the same call instead of each spending the refresh token.
let refreshInFlight: Promise<string | null> | null = null;

/**
 * POST /api/v1/auth/refresh with the stored refresh token (plain fetch, so it can never
 * recurse into apiFetch). Stores the new pair and resolves with the new access token, or
 * null when there is no refresh token or the backend rejects it.
 */
function refreshAccessToken(root: string): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight;
  const refreshToken = getRefreshToken();
  if (refreshToken === null) return Promise.resolve(null);
  refreshInFlight = (async () => {
    try {
      const res = await fetch(`${root}/api/v1/auth/refresh`, {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!res.ok) return null;
      const tokens = (await res.json()) as { access_token: string; refresh_token: string };
      setAuthToken(tokens.access_token);
      setRefreshToken(tokens.refresh_token);
      return tokens.access_token;
    } catch {
      return null;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

/**
 * GET/POST/... `path` on the backend.
 *
 * - Base URL: NEXT_PUBLIC_API_BASE_URL, read on every call; no fallback host.
 *   `path` is the full backend path, e.g. "/api/v1/products" or "/health".
 * - Headers: Accept and Content-Type are application/json, except that a
 *   FormData body gets no Content-Type (the browser sets the multipart
 *   boundary) and is sent untouched. Authorization: Bearer <token> only when
 *   getAuthToken() returns a token.
 * - Resolves with the parsed JSON on 2xx, or undefined for 204 / an empty body.
 * - Rejects only with ApiError: non-2xx (status + parsed body), network
 *   failure (status 0), or a 2xx body that is not valid JSON.
 */
export async function apiFetch<T>(path: string, init: ApiFetchInit = {}): Promise<T> {
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!baseUrl) {
    throw new Error(
      "NEXT_PUBLIC_API_BASE_URL is not set. Copy .env.local.example to .env.local " +
        "and set it to the backend's base URL.",
    );
  }

  const { body, headers: initHeaders, ...rest } = init;
  const headers = new Headers(initHeaders);
  headers.set("Accept", "application/json");

  let requestBody: BodyInit | null | undefined;
  if (typeof FormData !== "undefined" && body instanceof FormData) {
    requestBody = body;
  } else {
    headers.set("Content-Type", "application/json");
    requestBody = isPlainJsonBody(body) ? JSON.stringify(body) : (body as BodyInit | null | undefined);
  }

  const token = getAuthToken();
  if (token !== null) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const root = baseUrl.replace(/\/+$/, "");
  const url = `${root}${path.startsWith("/") ? path : `/${path}`}`;

  const send = async (): Promise<Response> => {
    try {
      return await fetch(url, { ...rest, headers, body: requestBody });
    } catch (err) {
      // Network failure (DNS, connection refused, CORS rejection): status 0.
      throw new ApiError(0, err instanceof Error ? err.message : String(err), undefined);
    }
  };

  let response = await send();

  // Silent refresh (SPEC-FE-024): a 401 on an authenticated, non-auth request means the
  // access token expired (it lives 15 minutes). Swap the stored refresh token for a new pair
  // once, then retry the original request once. If that fails, the original 401 is thrown and
  // the app-level 401 handler (app/(app)/providers.tsx) signs the user out, as before.
  if (response.status === 401 && token !== null && !path.startsWith("/api/v1/auth/")) {
    const fresh = await refreshAccessToken(root);
    if (fresh !== null) {
      headers.set("Authorization", `Bearer ${fresh}`);
      response = await send();
    }
  }

  const text = await response.text();

  if (!response.ok) {
    const errorBody = text ? parseMaybeJson(text) : undefined;
    throw new ApiError(response.status, errorMessage(errorBody, response), errorBody);
  }

  if (response.status === 204 || text === "") {
    return undefined as T;
  }

  try {
    return JSON.parse(text) as T;
  } catch {
    throw new ApiError(response.status, "Response body was not valid JSON", text);
  }
}
