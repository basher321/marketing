/**
 * Auth types (SPEC-FE-004), mirroring the backend's app/schemas/auth.py field
 * for field: LoginRequest -> POST /api/v1/auth/login body, TokenResponse -> its
 * 200 response.
 */
export interface LoginRequest {
  email: string;
  password: string;
  tenant_slug: string;
}

/** POST /api/v1/auth/register body — backend RegisterRequest (SPEC-BE-037). */
export interface RegisterRequest {
  tenant_name: string;
  /** Normalized by the backend ("My Shop!" -> "my-shop"); becomes the login workspace. */
  tenant_slug: string;
  email: string;
  password: string;
  first_name: string | null;
  last_name: string | null;
  /** Detected from the browser (SPEC-FE-048); the backend maps old zone names and ignores unusable values. */
  timezone?: string;
  /** Region of the browser language ("en-GB" -> "GB"); the company currency follows it. */
  country_code?: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

/** POST /api/v1/auth/password-reset/request body — backend PasswordResetRequest (SPEC-BE-040). */
export interface PasswordResetRequestBody {
  email: string;
  tenant_slug: string;
}

/** POST /api/v1/auth/password-reset/confirm body — backend PasswordResetConfirm. */
export interface PasswordResetConfirmBody {
  token: string;
  new_password: string;
}

/** backend MessageResponse. */
export interface MessageResponse {
  message: string;
}
