"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import { apiErrorText } from "@/components/settings/users-roles";
import { fetchLocaleOptions, tenantKeys, updateTenant } from "@/lib/api/tenant";
import type { LocaleOptions, Tenant } from "@/lib/types/tenant";

type Option = { value: string; label: string };

// A searchable dropdown over a long list (SPEC-FE-048). Clicking the field opens
// the WHOLE list (the current choice is highlighted and scrolled into view);
// typing filters it by name or code ("jap" -> "Japan (JP)", "yen" -> "JPY —
// Japanese Yen (¥)"). Click, or arrow keys + Enter, picks an entry; Escape or
// leaving the field without picking keeps the previous value. `acceptRaw` also
// lets a typed code that isn't an entry through (a regional language tag such
// as en-US). The browser's <datalist> was replaced because it only lists the
// entries matching the text already in the box, so a filled field showed one.
function LookupField({
  id,
  label,
  options,
  value,
  onChange,
  placeholder,
  acceptRaw,
  disabled,
}: {
  id: string;
  label: string;
  options: Option[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  acceptRaw?: (text: string) => string | null;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const listRef = useRef<HTMLUListElement>(null);
  const current = options.find((o) => o.value === value);
  const shown = current?.label ?? value;

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    return options.filter((o) => o.label.toLowerCase().includes(q) || o.value.toLowerCase() === q);
  }, [options, query]);

  // Opening (or a new filter) highlights the current choice, else the first match.
  useEffect(() => {
    if (!open) return;
    const i = matches.findIndex((o) => o.value === value);
    setActive(i >= 0 ? i : 0);
  }, [open, matches, value]);

  useEffect(() => {
    if (open) listRef.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [open, active]);

  const pick = (v: string) => {
    if (v !== value) onChange(v);
    setOpen(false);
    setQuery("");
  };
  const close = () => {
    // Leaving with typed text: take it only if it is exactly a code (or an accepted raw tag).
    const typed = query.trim();
    if (typed) {
      const byCode = options.find((o) => o.value.toLowerCase() === typed.toLowerCase());
      const raw = byCode ? byCode.value : acceptRaw ? acceptRaw(typed) : null;
      if (raw && raw !== value) onChange(raw);
    }
    setOpen(false);
    setQuery("");
  };

  return (
    <div className="form-row">
      <label htmlFor={id}>{label}</label>
      <div className="relative">
        <input
          id={id}
          role="combobox"
          aria-expanded={open}
          aria-controls={`${id}_list`}
          aria-autocomplete="list"
          aria-activedescendant={open && matches[active] ? `${id}_opt_${active}` : undefined}
          className="w-full"
          value={open ? query : shown}
          placeholder={open ? shown || placeholder : placeholder}
          disabled={disabled}
          autoComplete="off"
          onFocus={() => setOpen(true)}
          onClick={() => setOpen(true)}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onBlur={close}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown" || e.key === "ArrowUp") {
              e.preventDefault();
              setOpen(true);
              const step = e.key === "ArrowDown" ? 1 : -1;
              setActive((a) => Math.min(Math.max(a + step, 0), Math.max(matches.length - 1, 0)));
            } else if (e.key === "Enter" && open) {
              e.preventDefault();
              if (matches[active]) pick(matches[active].value);
              else close();
            } else if (e.key === "Escape") {
              setQuery("");
              setOpen(false);
            }
          }}
        />
        {open && (
          <ul
            id={`${id}_list`}
            ref={listRef}
            role="listbox"
            className="absolute left-0 right-0 top-full z-20 m-0 mt-1 max-h-64 list-none overflow-auto rounded-md border border-border bg-panel p-1 shadow-lg"
          >
            {matches.length === 0 && <li className="px-2 py-1.5 text-xs text-muted">No matches</li>}
            {matches.map((o, i) => (
              <li
                key={o.value}
                id={`${id}_opt_${i}`}
                data-index={i}
                role="option"
                aria-selected={o.value === value}
                className={`cursor-pointer rounded px-2 py-1.5 text-[13px] ${i === active ? "bg-accent-soft" : ""} ${o.value === value ? "font-semibold" : ""}`}
                // mousedown, not click: it runs before the input's blur closes the list.
                onMouseDown={(e) => {
                  e.preventDefault();
                  pick(o.value);
                }}
                onMouseEnter={() => setActive(i)}
              >
                {o.label}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

const LANGUAGE_TAG = /^([a-z]{2})(-([A-Za-z]{4}|[A-Za-z]{2}|\d{3}))?$/;

// Company tab (SPEC-FE-036, worldwide since SPEC-FE-048): the tenant's profile
// columns (SPEC-BE-051). Every country, currency, language and timezone comes
// from GET /tenants/locale-options (SPEC-BE-072), the same lists the backend
// validates against.
export default function CompanyForm({ tenant }: { tenant: Tenant }) {
  const queryClient = useQueryClient();
  const options = useQuery({ queryKey: tenantKeys.localeOptions, queryFn: fetchLocaleOptions, staleTime: Infinity });
  const [name, setName] = useState(tenant.name);
  const [country, setCountry] = useState(tenant.country_code ?? "");
  const [currency, setCurrency] = useState(tenant.currency);
  const [timezone, setTimezone] = useState(tenant.timezone);
  const [language, setLanguage] = useState(tenant.default_language);

  const lists = useMemo(() => buildOptions(options.data, country), [options.data, country]);

  const pickCountry = (code: string) => {
    setCountry(code);
    const c = options.data?.countries.find((x) => x.code === code);
    if (!c) return;
    // A country fills in its currency, and its timezone when it has only one;
    // both can still be changed (SPEC-FE-048).
    if (c.currency) setCurrency(c.currency);
    if (c.timezones.length === 1) setTimezone(c.timezones[0]);
  };

  const save = useMutation({
    mutationFn: () =>
      updateTenant({
        name: name.trim(),
        ...(country.trim() ? { country_code: country.trim() } : {}),
        currency,
        timezone,
        default_language: language,
      }),
    onSuccess: (t) => queryClient.setQueryData(tenantKeys.me, t),
  });

  const loading = options.isPending;
  const currencyChanged = currency !== tenant.currency;

  return (
    <form
      className="card"
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <h3 className="mt-0">Company profile</h3>
      {options.isError && (
        <p className="mt-0 text-xs text-danger" role="alert">
          {apiErrorText(options.error, "Could not load the country and currency lists.")}
        </p>
      )}
      <div className="form-grid-2">
        <div className="form-row">
          <label htmlFor="org_name">Company name</label>
          <input id="org_name" required maxLength={255} value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="form-row">
          <label htmlFor="org_slug">Workspace (used to sign in)</label>
          <input id="org_slug" value={tenant.slug} disabled />
        </div>
        <LookupField
          id="org_country"
          label="Country"
          placeholder="Type to search, e.g. Bangladesh"
          options={lists.countries}
          value={country}
          onChange={pickCountry}
          disabled={loading}
        />
        <LookupField
          id="org_currency"
          label="Currency"
          placeholder="Type to search, e.g. USD or Euro"
          options={lists.currencies}
          value={currency}
          onChange={setCurrency}
          disabled={loading}
        />
        <LookupField
          id="org_tz"
          label="Timezone"
          placeholder="Type to search, e.g. Dhaka"
          options={lists.timezones}
          value={timezone}
          onChange={setTimezone}
          disabled={loading}
        />
        <LookupField
          id="org_lang"
          label="Default language"
          placeholder="Type to search, e.g. English"
          options={lists.languages}
          value={language}
          onChange={setLanguage}
          acceptRaw={(t) => {
            const m = LANGUAGE_TAG.exec(t);
            return m && options.data?.languages.some((l) => l.code === m[1]) ? t : null;
          }}
          disabled={loading}
        />
      </div>
      {currencyChanged && (
        <p className="m-0 mb-3 text-xs text-warn" role="status">
          Existing products, orders and campaigns keep their current currency; prices aren&apos;t converted. New records
          will use {currency}.
        </p>
      )}
      <p className="m-0 mb-3 text-xs text-muted">
        Currency and timezone are used for prices, budgets and reports across the app.
      </p>
      <button type="submit" className="btn" disabled={save.isPending || loading}>
        {save.isPending ? "Saving…" : "Save changes"}
      </button>
      {save.isSuccess && !save.isPending && <span className="ml-3 text-[13px] text-success">Saved</span>}
      {save.isError && (
        <p className="mb-0 mt-3 text-xs text-danger" role="alert">
          {apiErrorText(save.error, "Only owners and managers can edit company settings.")}
        </p>
      )}
    </form>
  );
}

// Option labels. Timezones are sorted by UTC offset, with the selected
// country's own zones first (so a US company sees the US zones at the top).
function buildOptions(data: LocaleOptions | undefined, country: string) {
  if (!data) return { countries: [], currencies: [], languages: [], timezones: [] } as Record<string, Option[]>;
  const minutes = (offset: string) => {
    const sign = offset.startsWith("-") ? -1 : 1;
    const [h, m] = offset.slice(1).split(":").map(Number);
    return sign * (h * 60 + m);
  };
  const own = new Set(data.countries.find((c) => c.code === country)?.timezones ?? []);
  const zones = [...data.timezones].sort(
    (a, b) =>
      Number(own.has(b.name)) - Number(own.has(a.name)) ||
      minutes(a.offset) - minutes(b.offset) ||
      a.name.localeCompare(b.name),
  );
  return {
    countries: data.countries.map((c) => ({ value: c.code, label: `${c.name} (${c.code})` })),
    currencies: data.currencies.map((c) => ({
      value: c.code,
      label: c.symbol && c.symbol !== c.code ? `${c.code} — ${c.name} (${c.symbol})` : `${c.code} — ${c.name}`,
    })),
    timezones: zones.map((z) => ({ value: z.name, label: `(UTC${z.offset}) ${z.name}` })),
    languages: data.languages.map((l) => ({
      value: l.code,
      label: l.native_name && l.native_name !== l.name ? `${l.name} — ${l.native_name} (${l.code})` : `${l.name} (${l.code})`,
    })),
  };
}
