"use client";

import { Suspense } from "react";

import CreateForm from "@/components/organic/create-form";
import { OrganicHeader } from "@/components/organic/shared";

// Create (SPEC-FE-050): Manual and AI/Prompt modes. Both create a master post
// plus one version per platform on the backend, then open the editor.
export default function CreatePage() {
  return (
    <>
      <OrganicHeader title="Create a post" subtitle="Write it yourself, or describe it and let AI draft it. You preview and approve before anything is published." />
      <Suspense fallback={<p className="text-[13px] text-muted">Loading…</p>}>
        <CreateForm />
      </Suspense>
    </>
  );
}
