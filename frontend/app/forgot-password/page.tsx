"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";

import { AuthShell, NeuField } from "@/components/auth/auth-shell";
import { requestPasswordReset } from "@/lib/api/auth";

// Forgot password (SPEC-FE-025; neumorphic style, SPEC-FE-038). Outside the app shell and route guard, like
// /login. The backend answers with the same generic message whether or not the
// account exists, and that message is shown as-is.
export default function ForgotPasswordPage() {
  const [tenantSlug, setTenantSlug] = useState("");
  const [email, setEmail] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const res = await requestPasswordReset({ email, tenant_slug: tenantSlug });
      setDone(res.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthShell
      circle
      below={
        <Link href="/login" className="neu-link">
          ← Back to sign in
        </Link>
      }
    >
      <h1 className="neu-title">Reset password</h1>
      {done ? (
        <>
          <p role="status" className="neu-status">
            {done}
          </p>
          <p className="neu-sub">The link is valid for 30 minutes and can be used once.</p>
        </>
      ) : (
        <>
          <p className="neu-sub">Enter your workspace and email, and we&apos;ll send you a link to choose a new password.</p>
          <form method="post" onSubmit={onSubmit} className="neu-form">
            <NeuField label="Workspace" htmlFor="tenant_slug">
              <input
                id="tenant_slug"
                className="neu-input"
                autoComplete="organization"
                required
                value={tenantSlug}
                onChange={(e) => setTenantSlug(e.target.value)}
              />
            </NeuField>
            <NeuField label="Email" htmlFor="email">
              <input
                id="email"
                type="email"
                className="neu-input"
                autoComplete="username"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </NeuField>
            {error && (
              <p role="alert" className="neu-error">
                {error}
              </p>
            )}
            <button type="submit" className="neu-btn" disabled={submitting}>
              {submitting ? "Sending…" : "Send reset link"}
            </button>
          </form>
        </>
      )}
    </AuthShell>
  );
}
