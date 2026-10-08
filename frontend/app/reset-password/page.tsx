"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { AuthShell, NeuField } from "@/components/auth/auth-shell";
import PasswordInput from "@/components/auth/password-input";
import { confirmPasswordReset } from "@/lib/api/auth";
import { ApiError } from "@/lib/types/common";

// The backend's own message. A 422 carries FastAPI's validation list (e.g. the
// password-policy messages); its texts are shown instead of a bare status.
function messageOf(err: unknown): string {
  if (err instanceof ApiError && err.body && typeof err.body === "object") {
    const detail = (err.body as { detail?: unknown }).detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d) => String((d as { msg?: unknown }).msg ?? "").replace(/^Value error, /, ""))
        .filter(Boolean)
        .join(" ");
    }
  }
  return err instanceof Error ? err.message : String(err);
}

function ResetForm() {
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError("The two passwords don't match.");
      return;
    }
    setSubmitting(true);
    try {
      const res = await confirmPasswordReset({ token, new_password: password });
      setDone(res.message);
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (!token) {
    return (
      <p role="alert" className="neu-error">
        This reset link is incomplete. Request a new one from the sign-in page.
      </p>
    );
  }
  if (done) {
    return (
      <>
        <p role="status" className="neu-status">
          {done}
        </p>
        <Link href="/login" className="neu-btn block text-center no-underline">
          Sign in
        </Link>
      </>
    );
  }
  return (
    <form method="post" onSubmit={onSubmit} className="neu-form">
      <NeuField label="New password" htmlFor="new_password">
        <PasswordInput
          id="new_password"
          className="neu-input"
          autoComplete="new-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </NeuField>
      <NeuField label="Confirm new password" htmlFor="confirm_password">
        <PasswordInput
          id="confirm_password"
          className="neu-input"
          autoComplete="new-password"
          required
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />
      </NeuField>
      <p className="neu-hint">At least 10 characters, with an uppercase letter, a lowercase letter and a digit; not a common password.</p>
      {error && (
        <p role="alert" className="neu-error">
          {error}
        </p>
      )}
      <button type="submit" className="neu-btn" disabled={submitting}>
        {submitting ? "Saving…" : "Set new password"}
      </button>
    </form>
  );
}

// Reset password (SPEC-FE-025; neumorphic style, SPEC-FE-038): reached from the emailed link
// /reset-password?token=…; outside the app shell and route guard.
export default function ResetPasswordPage() {
  return (
    <AuthShell
      below={
        <Link href="/login" className="neu-link">
          ← Back to sign in
        </Link>
      }
    >
      <h1 className="neu-title">Choose a new password</h1>
      {/* useSearchParams needs a Suspense boundary in the App Router. */}
      <Suspense fallback={<p className="neu-sub">Loading…</p>}>
        <ResetForm />
      </Suspense>
    </AuthShell>
  );
}
