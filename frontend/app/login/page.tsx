"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { AuthShell, NeuField, NeuSuccess } from "@/components/auth/auth-shell";
import PasswordInput from "@/components/auth/password-input";
import { login } from "@/lib/api/auth";
import { setAuthToken, setRefreshToken } from "@/lib/auth/token";

// Login page (SPEC-FE-004, restyled by SPEC-FE-038 after the ERP's neumorphic
// login). Outside the (app) route group, so no sidebar or topbar. The fields
// are exactly the backend's LoginRequest (tenant_slug, email, password); the
// auth logic, token storage and redirect are unchanged. On success a short
// check-mark animation plays before navigating to the dashboard.
export default function LoginPage() {
  const router = useRouter();
  const [tenantSlug, setTenantSlug] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const tokens = await login({ email: email.trim(), password, tenant_slug: tenantSlug.trim().toLowerCase() });
      // Both tokens are kept: the refresh token lets apiFetch renew the session
      // silently (SPEC-FE-024; see lib/auth/token.ts).
      setAuthToken(tokens.access_token);
      setRefreshToken(tokens.refresh_token);
      setSuccess(true);
      // Long enough to see the check mark, short enough not to feel like a stall.
      setTimeout(() => router.replace("/dashboard"), 1300);
    } catch (err) {
      // The backend's own message (lockout wait, invalid credentials, ...).
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  }

  return (
    <AuthShell
      circle
      below={
        success ? null : (
          <>
            New company?{" "}
            <Link href="/signup" className="neu-link">
              Create workspace
            </Link>
          </>
        )
      }
    >
      {success ? (
        <NeuSuccess title="Welcome back" subtitle="Opening your dashboard" />
      ) : (
        <>
          <h1 className="neu-title">Welcome back</h1>
          <p className="neu-sub">Sign in to your PilotSonic workspace. New here? Create a workspace in a minute.</p>
          {/* method="post": a submit before hydration must never put the password in the URL. */}
          <form method="post" onSubmit={onSubmit} className="neu-form">
            <NeuField label="Workspace" htmlFor="tenant_slug">
              <input
                id="tenant_slug"
                name="tenant_slug"
                className="neu-input"
                placeholder="acme"
                autoComplete="organization"
                required
                value={tenantSlug}
                onChange={(e) => setTenantSlug(e.target.value)}
              />
            </NeuField>
            <NeuField label="Email" htmlFor="email">
              <input
                id="email"
                name="email"
                type="email"
                className="neu-input"
                autoComplete="username"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </NeuField>
            <NeuField label="Password" htmlFor="password">
              <PasswordInput
                id="password"
                name="password"
                className="neu-input"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </NeuField>
            <Link href="/forgot-password" className="neu-small-link">
              Forgot password?
            </Link>
            {error !== null && (
              <p role="alert" className="neu-error">
                {error}
              </p>
            )}
            <button type="submit" className="neu-btn" disabled={submitting}>
              {submitting ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </>
      )}
    </AuthShell>
  );
}
