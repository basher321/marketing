import type {
  LoginRequest,
  MessageResponse,
  PasswordResetConfirmBody,
  PasswordResetRequestBody,
  RegisterRequest,
  TokenResponse,
} from "../types/auth";
import { apiFetch } from "./client";

/**
 * POST /api/v1/auth/register (SPEC-BE-037, used by SPEC-FE-038's sign-up):
 * creates a new organization (tenant) and its active owner, and returns the
 * owner's tokens. 409 if the workspace slug or email is taken, 422 for a weak
 * password or an invalid slug.
 */
export function register(body: RegisterRequest): Promise<TokenResponse> {
  return apiFetch<TokenResponse>("/api/v1/auth/register", { method: "POST", body: { ...body } });
}

/**
 * POST /api/v1/auth/login (SPEC-FE-004). Rejects with the ApiError apiFetch
 * throws; its message is the backend's own `error` text (e.g. "Invalid
 * credentials.", "This account has been disabled.").
 */
export function login(body: LoginRequest): Promise<TokenResponse> {
  return apiFetch<TokenResponse>("/api/v1/auth/login", { method: "POST", body: { ...body } });
}

/**
 * POST /api/v1/auth/password-reset/request (SPEC-BE-040): always 202 with the
 * same generic message, whether or not the account exists.
 */
export function requestPasswordReset(body: PasswordResetRequestBody): Promise<MessageResponse> {
  return apiFetch<MessageResponse>("/api/v1/auth/password-reset/request", { method: "POST", body: { ...body } });
}

/** POST /api/v1/auth/password-reset/confirm: 400 invalid/expired link, 422 weak password. */
export function confirmPasswordReset(body: PasswordResetConfirmBody): Promise<MessageResponse> {
  return apiFetch<MessageResponse>("/api/v1/auth/password-reset/confirm", { method: "POST", body: { ...body } });
}
