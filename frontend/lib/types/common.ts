/**
 * Shared cross-domain types (SPEC-FE-003).
 *
 * ApiError is the single error type apiFetch() rejects with, so every caller
 * can catch exactly one thing. It is a class (not just an interface) because
 * it must exist at runtime to be thrown and checked with `instanceof`.
 * Shape: { status, message, body }.
 */
export class ApiError extends Error {
  /** HTTP status code, or 0 when the request never reached the server (network failure). */
  readonly status: number;
  /** Parsed JSON error body, the raw text if it was not JSON, or undefined when there was no response. */
  readonly body: unknown;

  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

/**
 * True only for the backend's role check (SPEC-FE-059): a 403 whose message is
 * "Insufficient permissions…" (require_permission / require_role / Command Chat).
 * Other 403s carry their own reason (SocialAPI or Zernio refusing, "Only the
 * owner can …", an expired media link) and must show that text instead.
 */
export function isRoleDenied(err: unknown): boolean {
  // err.message is the backend's {"error"} (AppError) or {"detail"} (HTTPException) text.
  return err instanceof ApiError && err.status === 403 && err.message.startsWith("Insufficient permissions");
}
