"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { errorText } from "@/components/organic/shared";
import { platformKeys, removeAppBrandingImage, saveAppBranding, uploadAppBrandingImage } from "@/lib/api/platform";
import { fetchMyProfile, removeMyAvatar, updateMyProfile, uploadMyAvatar, userKeys } from "@/lib/api/users";
import type { AppBranding, AppBrandingSlot } from "@/lib/types/platform";
import type { MyProfile } from "@/lib/types/users";

const INPUT = "w-full rounded-md border border-border bg-panel px-3 py-2 text-[13.5px] text-text";
const ACCEPT = "image/png,image/jpeg,image/webp";
const MAX = 1024 * 1024;

function ImagePick({ label, url, busy, onPick, onRemove }: {
  label: string;
  url: string | null;
  busy: boolean;
  onPick: (f: File) => void;
  onRemove: () => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const [tooBig, setTooBig] = useState(false);
  return (
    <div className="flex items-center gap-3">
      <div className="flex h-16 w-16 items-center justify-center overflow-hidden rounded-xl border border-border bg-bg">
        {url ? <img src={url} alt={`${label} preview`} className="max-h-full max-w-full" /> : <span className="text-[11px] text-muted">None</span>}
      </div>
      <div className="flex flex-col gap-1">
        <span className="text-[13px] font-semibold">{label}</span>
        <div className="flex gap-2">
          <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={() => ref.current?.click()}>Upload</button>
          {url && <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={onRemove}>Remove</button>}
        </div>
        <span className={tooBig ? "text-[11.5px] text-danger" : "text-[11.5px] text-muted"}>PNG, JPEG or WebP, up to 1 MB</span>
      </div>
      <input ref={ref} type="file" accept={ACCEPT} hidden onChange={(e) => {
        const f = e.target.files?.[0];
        e.target.value = "";
        if (!f) return;
        setTooBig(f.size > MAX);
        if (f.size <= MAX) onPick(f);
      }} />
    </div>
  );
}

function ProfileForm({ me }: { me: MyProfile }) {
  const qc = useQueryClient();
  const [first, setFirst] = useState(me.first_name ?? "");
  const [last, setLast] = useState(me.last_name ?? "");
  const [phone, setPhone] = useState(me.phone ?? "");
  const set = (p: MyProfile) => qc.setQueryData(userKeys.me, p);
  const save = useMutation({ mutationFn: () => updateMyProfile({ first_name: first, last_name: last, phone }), onSuccess: set });
  const upload = useMutation({ mutationFn: (f: File) => uploadMyAvatar(f), onSuccess: set });
  const remove = useMutation({ mutationFn: removeMyAvatar, onSuccess: set });
  const err = save.error ?? upload.error ?? remove.error;
  return (
    <div className="card">
      <h3 className="mt-0">My profile</h3>
      <p className="mb-3 text-[13px] text-muted">{me.email} · {me.role} at {me.company_name}</p>
      <ImagePick label="Profile photo" url={me.avatar_url} busy={upload.isPending || remove.isPending}
        onPick={(f) => upload.mutate(f)} onRemove={() => remove.mutate()} />
      <form className="mt-4 flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <div className="grid grid-cols-2 gap-2">
          <input className={INPUT} aria-label="First name" placeholder="First name" maxLength={100} value={first} onChange={(e) => setFirst(e.target.value)} />
          <input className={INPUT} aria-label="Last name" placeholder="Last name" maxLength={100} value={last} onChange={(e) => setLast(e.target.value)} />
        </div>
        <input className={INPUT} aria-label="Phone" placeholder="Phone" maxLength={50} value={phone} onChange={(e) => setPhone(e.target.value)} />
        <button type="submit" className="btn self-start" disabled={save.isPending}>{save.isPending ? "Saving…" : "Save profile"}</button>
        {save.isSuccess && <span className="text-[13px] text-success">Saved.</span>}
      </form>
      {err && <p className="mt-2 text-danger">{errorText(err)}</p>}
    </div>
  );
}

// Everyone's own profile (SPEC-FE-077 / SPEC-BE-113 FR2).
export function ProfileCard() {
  const me = useQuery({ queryKey: userKeys.me, queryFn: fetchMyProfile });
  if (me.isPending) return <div className="card text-muted">Loading profile…</div>;
  if (me.isError) return <div className="card text-danger">{me.error.message}</div>;
  return <ProfileForm key={me.data.id} me={me.data} />;
}

// The app's own name and logo (Super admin only; SPEC-BE-113 FR1).
export function AppBrandingCard({ branding }: { branding: AppBranding }) {
  const qc = useQueryClient();
  const [name, setName] = useState(branding.app_name);
  const [tagline, setTagline] = useState(branding.tagline ?? "");
  const set = (b: AppBranding) => qc.setQueryData(platformKeys.branding, b);
  const save = useMutation({ mutationFn: () => saveAppBranding({ app_name: name.trim(), tagline: tagline.trim() }), onSuccess: set });
  const upload = useMutation({ mutationFn: (x: { slot: AppBrandingSlot; file: File }) => uploadAppBrandingImage(x.slot, x.file), onSuccess: set });
  const remove = useMutation({ mutationFn: (slot: AppBrandingSlot) => removeAppBrandingImage(slot), onSuccess: set });
  const busy = upload.isPending || remove.isPending;
  const err = save.error ?? upload.error ?? remove.error;
  return (
    <div className="card">
      <h3 className="mt-0">App branding <span className="badge badge-neutral">Super admin</span></h3>
      <p className="mb-3 text-[13px] text-muted">The software&apos;s name and logo on the sign-in page, the sidebar and the browser tab, for every company.</p>
      <form className="mb-4 flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); if (name.trim()) save.mutate(); }}>
        <input className={INPUT} aria-label="App name" maxLength={60} value={name} onChange={(e) => setName(e.target.value)} />
        <input className={INPUT} aria-label="Tagline" placeholder="Tagline (optional)" maxLength={160} value={tagline} onChange={(e) => setTagline(e.target.value)} />
        <button type="submit" className="btn self-start" disabled={save.isPending || !name.trim()}>{save.isPending ? "Saving…" : "Save name"}</button>
      </form>
      <div className="flex flex-col gap-3">
        {([["logo", "Logo", branding.logo_url], ["logo_dark", "Logo for dark mode", branding.logo_dark_url], ["favicon", "Browser tab icon", branding.favicon_url]] as const).map(([slot, label, url]) => (
          <ImagePick key={slot} label={label} url={url} busy={busy} onPick={(file) => upload.mutate({ slot, file })} onRemove={() => remove.mutate(slot)} />
        ))}
      </div>
      {err && <p className="mt-2 text-danger">{errorText(err)}</p>}
    </div>
  );
}
