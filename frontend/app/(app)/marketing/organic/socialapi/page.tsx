"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { OrganicHeader } from "@/components/organic/shared";
import { AccountsCard, AnalyticsCard, Composer, KeyCard, PostsCard } from "@/components/socialapi/publishing";
import { fetchKey, sapiKeys } from "@/lib/api/socialapi";

// Organic Marketing › SocialAPI (SPEC-FE-054 / SPEC-BE-083): post to many
// platforms through the company's own SocialAPI.ai key - another option next
// to the direct connections on the Accounts tab, which are unchanged.
export default function SocialApiPage() {
  const key = useQuery({ queryKey: sapiKeys.key, queryFn: fetchKey });
  const ready = key.data != null && key.data.status !== "not_configured";
  return (
    <>
      <OrganicHeader
        title="SocialAPI"
        subtitle="Publish and schedule on Instagram, Facebook, Threads, TikTok, LinkedIn, YouTube, X, Pinterest, Google Business and more through SocialAPI.ai."
        action={
          <Link href="/customer/socialapi" className="btn btn-secondary no-underline">
            SocialAPI inbox
          </Link>
        }
      />
      <KeyCard />
      {ready && (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            <AccountsCard />
            <Composer />
          </div>
          <PostsCard />
          <AnalyticsCard />
        </>
      )}
    </>
  );
}
