"use client";

import { useQuery } from "@tanstack/react-query";

import { useAppBranding } from "@/components/branding/app-branding";
import { AppBrandingCard, ProfileCard } from "@/components/branding/branding-cards";
import BrandingForm from "@/components/settings/branding-form";
import { fetchPlatformMe, platformKeys } from "@/lib/api/platform";
import { fetchTenant, tenantKeys } from "@/lib/api/tenant";
import { fetchMyProfile, userKeys } from "@/lib/api/users";

// Branding (SPEC-FE-077): everyone edits their own profile; the company's logo
// and banner (SPEC-FE-048, moved here from Settings) for those who may change
// them; and, only for PilotSonic's Super admin, the app's own name and logo.
// The backend enforces each of these again.
export default function BrandingPage() {
  const me = useQuery({ queryKey: platformKeys.me, queryFn: fetchPlatformMe, staleTime: 5 * 60_000 });
  const tenant = useQuery({ queryKey: tenantKeys.me, queryFn: fetchTenant });
  // Company branding is manager+ on the backend (PATCH/PUT /tenants/me/branding).
  const profile = useQuery({ queryKey: userKeys.me, queryFn: fetchMyProfile });
  const canBrand = ["owner", "admin", "manager"].includes(profile.data?.role ?? "");
  const app = useAppBranding();
  return (
    <>
      <h1 className="page-title">Branding</h1>
      <p className="page-subtitle">Your profile and how your company looks.</p>
      <div className="flex flex-col gap-4">
        <ProfileCard />
        {tenant.data && canBrand && (
          <div>
            <h2 className="section-title">Company branding</h2>
            <BrandingForm tenant={tenant.data} />
          </div>
        )}
        {me.data?.super_admin && app && <AppBrandingCard branding={app} />}
      </div>
    </>
  );
}
