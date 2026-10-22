"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { AuthShell, NeuField, NeuSuccess } from "@/components/auth/auth-shell";
import PasswordInput from "@/components/auth/password-input";
import { register } from "@/lib/api/auth";
import { setAuthToken, setRefreshToken } from "@/lib/auth/token";
import { ApiError } from "@/lib/types/common";

// "Acme Fashion BD!" -> "acme-fashion-bd": the same shape the backend's
// normalize_tenant_slug accepts (lowercase letters, digits, hyphens).
function suggestSlug(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 63);
}

// The backend's own message; a 422 carries FastAPI's validation list (the
// password-policy and slug messages), shown instead of a bare status.
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

// The new company starts in the user's own timezone and country (SPEC-FE-048):
// the browser timezone, and the region of the browser language when it has one
// ("en-GB" -> GB; plain "en" -> none). The backend derives the currency from the
// country, and simply ignores anything it can't use, so sign-up never fails on it.
function detectedLocale(): { timezone?: string; country_code?: string } {
  const out: { timezone?: string; country_code?: string } = {};
  try {
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (zone) out.timezone = zone;
    const region = new Intl.Locale(navigator.language).region;
    if (region && /^[A-Z]{2}$/.test(region)) out.country_code = region;
  } catch {
    // Older browser: keep the defaults (USD, UTC), editable in Settings.
  }
  return out;
}

// Free sign-up for a new organization (SPEC-FE-038): POST /auth/register
// creates the tenant and its active owner and returns the owner's tokens, so
// the new owner lands on the dashboard straight away. Same neumorphic design
// as /login, on a rounded card because the form is too tall for a circle.
export default function SignupPage() {
  const router = useRouter();
  const [company, setCompany] = useState("");
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError("The two passwords don't match.");
      return;
    }
    setSubmitting(true);
    try {
      const tokens = await register({
        tenant_name: company.trim(),
        tenant_slug: slug.trim(),
        email: email.trim(),
        password,
        first_name: firstName.trim() || null,
        last_name: lastName.trim() || null,
        ...detectedLocale(),
      });
      setAuthToken(tokens.access_token);
      setRefreshToken(tokens.refresh_token);
      setSuccess(true);
      setTimeout(() => router.replace("/dashboard"), 1300);
    } catch (err) {
      setError(messageOf(err));
      setSubmitting(false);
    }
  }

  return (
    <AuthShell
      below={
        success ? null : (
          <>
            Already have a workspace?{" "}
            <Link href="/login" className="neu-link">
              Sign in
            </Link>
          </>
        )
      }
    >
      {success ? (
        <NeuSuccess title="You're all set" subtitle="Workspace created" />
      ) : (
        <>
          <h1 className="neu-title">Create workspace</h1>
          <p className="neu-sub">Free sign-up for your organization. You&apos;ll be its owner.</p>
          <form method="post" onSubmit={onSubmit} className="neu-form">
            <NeuField label="Company name" htmlFor="company">
              <input
                id="company"
                className="neu-input"
                autoComplete="organization"
                maxLength={255}
                required
                value={company}
                onChange={(e) => {
                  setCompany(e.target.value);
                  if (!slugEdited) setSlug(suggestSlug(e.target.value));
                }}
              />
            </NeuField>
            <NeuField label="Workspace (used to sign in)" htmlFor="slug">
              <input
                id="slug"
                className="neu-input"
                placeholder="acme"
                maxLength={63}
                required
                value={slug}
                onChange={(e) => {
                  setSlugEdited(true);
                  setSlug(e.target.value);
                }}
              />
            </NeuField>
            <p className="neu-hint">Lowercase letters, digits and hyphens.</p>
            <div className="neu-row">
              <NeuField label="First name" htmlFor="first_name">
                <input id="first_name" className="neu-input" autoComplete="given-name" maxLength={100} value={firstName} onChange={(e) => setFirstName(e.target.value)} />
              </NeuField>
              <NeuField label="Last name" htmlFor="last_name">
                <input id="last_name" className="neu-input" autoComplete="family-name" maxLength={100} value={lastName} onChange={(e) => setLastName(e.target.value)} />
              </NeuField>
            </div>
            <NeuField label="Email" htmlFor="email">
              <input id="email" type="email" className="neu-input" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
            </NeuField>
            <div className="neu-row">
              <NeuField label="Password" htmlFor="password">
                <PasswordInput id="password" className="neu-input" autoComplete="new-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
              </NeuField>
              <NeuField label="Confirm password" htmlFor="confirm">
                <PasswordInput id="confirm" className="neu-input" autoComplete="new-password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} />
              </NeuField>
            </div>
            <p className="neu-hint">At least 10 characters, with an uppercase letter, a lowercase letter and a digit; not a common password.</p>
            {error && (
              <p role="alert" className="neu-error">
                {error}
              </p>
            )}
            <button type="submit" className="neu-btn" disabled={submitting}>
              {submitting ? "Creating…" : "Create workspace"}
            </button>
          </form>
        </>
      )}
    </AuthShell>
  );
}
