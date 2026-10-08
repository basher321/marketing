"use client";

import { useParams } from "next/navigation";

import ContentEditor from "@/components/organic/content-editor";
import { OrganicHeader } from "@/components/organic/shared";

// Content editor (SPEC-FE-050): master + per-platform versions, preview,
// approval and scheduling.
export default function ContentPage() {
  const { id } = useParams<{ id: string }>();
  return (
    <>
      <OrganicHeader title="Post editor" subtitle="One master post, adapted for each platform. Preview shows exactly what will be sent." />
      <ContentEditor id={id} />
    </>
  );
}
