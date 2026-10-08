"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";

import { fetchBrandSettings, kbKeys, saveBrandSettings } from "@/lib/api/kb";
import type { BrandSettings, LanguageCode } from "@/lib/types/kb";

// The mockup's three "Primary language" options map onto the backend's
// (primary_language, supported_languages) pair (SPEC-BE-012):
const LANGUAGE_OPTIONS: { label: string; primary: LanguageCode; supported: LanguageCode[] }[] = [
  { label: "Bangla (default) + English", primary: "bn", supported: ["bn", "en"] },
  { label: "English only", primary: "en", supported: ["en"] },
  { label: "Bangla only", primary: "bn", supported: ["bn"] },
];

// The option matching the stored pair; a stored pair outside the three options
// falls back to the option with the same primary language.
function optionIndexFor(s: BrandSettings): number {
  const same = (a: string[], b: string[]) => a.length === b.length && a.every((x) => b.includes(x));
  const exact = LANGUAGE_OPTIONS.findIndex(
    (o) => o.primary === s.primary_language && same(o.supported, s.supported_languages),
  );
  if (exact >= 0) return exact;
  const byPrimary = LANGUAGE_OPTIONS.findIndex((o) => o.primary === s.primary_language);
  return byPrimary >= 0 ? byPrimary : 1;
}

type FormState = { name: string; tone: number; style: number; lang: number; terms: string };

function toForm(s: BrandSettings): FormState {
  return {
    name: s.brand_name,
    tone: s.tone,
    style: s.style,
    lang: optionIndexFor(s),
    // Stored as a list; the mockup's textarea is comma-separated.
    terms: s.forbidden_terms.join(", "),
  };
}

// Brand Settings card (SPEC-FE-015), markup from the reference mockup. Every
// field has a real backing field (SPEC-BE-012), so none is shown disabled.
export default function BrandSettingsForm() {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: kbKeys.brand, queryFn: fetchBrandSettings });
  const [form, setForm] = useState<FormState | null>(null);
  const [saved, setSaved] = useState(false);

  // Pre-fill once the real values arrive (and after each successful save).
  useEffect(() => {
    if (query.data) setForm(toForm(query.data));
  }, [query.data]);

  const save = useMutation({
    mutationFn: (f: FormState) => {
      const lang = LANGUAGE_OPTIONS[f.lang];
      return saveBrandSettings({
        brand_name: f.name,
        tone: f.tone,
        style: f.style,
        primary_language: lang.primary,
        supported_languages: lang.supported,
        forbidden_terms: f.terms.split(",").map((t) => t.trim()).filter(Boolean),
      });
    },
    onMutate: () => setSaved(false),
    onSuccess: (data) => {
      queryClient.setQueryData(kbKeys.brand, data);
      setSaved(true);
    },
    // On failure the typed values stay in the form; the message shows below.
  });

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setSaved(false);
    setForm((f) => (f ? { ...f, [key]: value } : f));
  };

  return (
    <div className="card">
      <h3 className="mt-0">Brand Settings</h3>
      {query.isPending ? (
        <p className="text-[13px] text-muted">Loading brand settings…</p>
      ) : query.isError ? (
        <p className="text-[13px] text-danger" role="alert">
          Failed to load brand settings: {query.error.message}
        </p>
      ) : form === null ? null : (
        <form
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            save.mutate(form);
          }}
        >
          <div className="form-row">
            <label htmlFor="brand_name">Brand name</label>
            <input
              id="brand_name"
              required
              maxLength={255}
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
            />
          </div>
          <div className="form-grid-2">
            <div className="form-row">
              <label htmlFor="tone">Tone: Formal ↔ Playful</label>
              <input
                id="tone"
                type="range"
                min={0}
                max={100}
                value={form.tone}
                onChange={(e) => set("tone", Number(e.target.value))}
              />
            </div>
            <div className="form-row">
              <label htmlFor="style">Style: Concise ↔ Detailed</label>
              <input
                id="style"
                type="range"
                min={0}
                max={100}
                value={form.style}
                onChange={(e) => set("style", Number(e.target.value))}
              />
            </div>
          </div>
          <div className="form-row">
            <label htmlFor="language">Primary language</label>
            <select id="language" value={form.lang} onChange={(e) => set("lang", Number(e.target.value))}>
              {LANGUAGE_OPTIONS.map((o, i) => (
                <option key={o.label} value={i}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <div className="form-row">
            <label htmlFor="forbidden_terms">Forbidden terms (comma-separated)</label>
            <textarea
              id="forbidden_terms"
              rows={2}
              value={form.terms}
              onChange={(e) => set("terms", e.target.value)}
            />
          </div>
          <button type="submit" className="btn" disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save Brand Settings"}
          </button>
          {save.isError && (
            <p className="mb-0 mt-3 text-xs text-danger" role="alert">
              {save.error.message}
            </p>
          )}
          {saved && <p className="mb-0 mt-3 text-xs text-success">Saved.</p>}
        </form>
      )}
    </div>
  );
}
