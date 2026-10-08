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
