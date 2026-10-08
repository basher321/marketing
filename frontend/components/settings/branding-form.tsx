"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type ChangeEvent, type FormEvent } from "react";

import { apiErrorText } from "@/components/settings/users-roles";
import { removeBrandingImage, tenantKeys, updateBrandingText, uploadBrandingImage } from "@/lib/api/tenant";
import type { Branding, BrandingSlot, Tenant } from "@/lib/types/tenant";

const MAX_BYTES = 1024 * 1024;
const TYPES = ["image/png", "image/jpeg", "image/webp"];
const FORBIDDEN = "Only owners and managers can change branding.";

function ImageSlot({
  slot,
  label,
  hint,
  url,
  shape,
  onChange,
}: {
  slot: BrandingSlot;
  label: string;
  hint: string;
  url: string | null;
  shape: string;
  onChange: (b: Branding) => void;
}) {
  const [localError, setLocalError] = useState<string | null>(null);
  const upload = useMutation({ mutationFn: (file: File) => uploadBrandingImage(slot, file), onSuccess: onChange });
  const remove = useMutation({ mutationFn: () => removeBrandingImage(slot), onSuccess: onChange });
  const pick = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    // Quick client check; the backend re-checks the real type from the bytes.
    if (!TYPES.includes(file.type)) return setLocalError("Use a PNG, JPEG or WebP image.");
    if (file.size > MAX_BYTES) return setLocalError("The image must be 1 MB or smaller.");
    setLocalError(null);
    upload.mutate(file);
  };
  const err = localError ?? (upload.error ? apiErrorText(upload.error, FORBIDDEN) : remove.error ? apiErrorText(remove.error, FORBIDDEN) : null);
  return (
    <div className="rounded-lg border border-border p-4">
      <div className="mb-2 text-[13px] font-medium">{label}</div>
      <div className={`mb-3 flex items-center justify-center overflow-hidden rounded-md border border-dashed border-border bg-bg ${shape}`}>
        {url ? (
          // A data: URL preview, so next/image optimisation does not apply.
          <img src={url} alt={label} className="h-full w-full object-cover" data-slot={slot} />
        ) : (
          <span className="text-xs text-muted">No image</span>
        )}
      </div>
      <p className="m-0 mb-2 text-xs text-muted">{hint}</p>
      <div className="flex gap-2">
        <label className="btn btn-secondary btn-sm cursor-pointer">
          {upload.isPending ? "Uploading…" : url ? "Replace" : "Upload"}
          <input type="file" accept="image/png,image/jpeg,image/webp" className="hidden" data-upload={slot} onChange={pick} />
        </label>
        {url && (
          <button type="button" className="btn btn-ghost btn-sm" disabled={remove.isPending} onClick={() => remove.mutate()}>
            Remove
          </button>
        )}
      </div>
      {err && (
        <p className="mb-0 mt-2 text-xs text-danger" role="alert">
          {err}
        </p>
      )}
    </div>
  );
}

// Branding tab (SPEC-FE-036): logo, banner and the company head's photo,
// name and title (SPEC-BE-051). The logo then shows in the sidebar.
export default function BrandingForm({ tenant }: { tenant: Tenant }) {
  const queryClient = useQueryClient();
  const b = tenant.branding;
  const setBranding = (branding: Branding) =>
    queryClient.setQueryData<Tenant>(tenantKeys.me, (old) => (old ? { ...old, branding } : old));
  const [headName, setHeadName] = useState(b.head.name ?? "");
  const [headTitle, setHeadTitle] = useState(b.head.title ?? "");
  const saveText = useMutation({
    mutationFn: () => updateBrandingText({ head_name: headName.trim() || null, head_title: headTitle.trim() || null }),
    onSuccess: setBranding,
  });

  return (
    <div className="card">
      <h3 className="mt-0">Branding</h3>
      <div className="grid gap-4 md:grid-cols-3">
        <ImageSlot slot="logo" label="Logo" hint="Square, e.g. 256×256. Shown in the sidebar." url={b.logo_url} shape="h-28 w-28" onChange={setBranding} />
        <ImageSlot slot="banner" label="Banner" hint="Wide, e.g. 1500×500." url={b.banner_url} shape="h-28 w-full" onChange={setBranding} />
        <ImageSlot slot="head_photo" label="Company head photo" hint="Portrait, e.g. 400×400." url={b.head.photo_url} shape="h-28 w-28 rounded-full" onChange={setBranding} />
      </div>
      <form
        className="mt-4"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          saveText.mutate();
        }}
      >
        <div className="form-grid-2">
          <div className="form-row">
            <label htmlFor="head_name">Company head name</label>
            <input id="head_name" maxLength={120} value={headName} onChange={(e) => setHeadName(e.target.value)} />
          </div>
          <div className="form-row">
            <label htmlFor="head_title">Title</label>
            <input id="head_title" maxLength={120} placeholder="e.g. Founder & CEO" value={headTitle} onChange={(e) => setHeadTitle(e.target.value)} />
          </div>
        </div>
        <button type="submit" className="btn btn-sm" disabled={saveText.isPending}>
          {saveText.isPending ? "Saving…" : "Save"}
        </button>
        {saveText.isSuccess && !saveText.isPending && <span className="ml-3 text-[13px] text-success">Saved</span>}
        {saveText.isError && (
          <p className="mb-0 mt-3 text-xs text-danger" role="alert">
            {apiErrorText(saveText.error, FORBIDDEN)}
          </p>
        )}
      </form>
    </div>
  );
}
