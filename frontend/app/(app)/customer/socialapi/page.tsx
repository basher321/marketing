"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { errorText } from "@/components/organic/shared";
import SocialApiInbox from "@/components/socialapi/inbox";
import { fetchKey, sapiKeys } from "@/lib/api/socialapi";

// Customer Service › SocialAPI inbox (SPEC-FE-054 / SPEC-BE-083): comments,
// DMs and reviews from the accounts connected through SocialAPI.ai, read live.
export default function SocialApiInboxPage() {
  const key = useQuery({ queryKey: sapiKeys.key, queryFn: fetchKey });
  return (
    <>
      <Link href="/customer" className="text-xs text-muted underline">
        ← Customer Service
      </Link>
      <h1 className="m-0 mb-1 text-[22px] font-bold">SocialAPI inbox</h1>
      <p className="m-0 mb-5 text-muted">Comments, DMs and reviews from the accounts connected through SocialAPI.ai.</p>
      {key.isError ? (
        <p className="text-[13px] text-danger">{errorText(key.error)}</p>
      ) : !key.data ? null : key.data.status === "not_configured" ? (
        <p className="text-[13px] text-muted">
          Add your SocialAPI key first in{" "}
          <Link href="/marketing/organic/socialapi" className="underline">
            Organic Marketing › SocialAPI
          </Link>
          .
        </p>
      ) : (
        <SocialApiInbox />
      )}
    </>
  );
}
