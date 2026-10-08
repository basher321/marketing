"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useRef, useState, type DragEvent } from "react";

import { uploadMedia, videoStatus } from "@/lib/api/meta";
import type { MediaResult } from "@/lib/types/meta";

import { errorText } from "./tree";

// Drag & drop (or click) upload straight to the Meta ad account through the
// backend (SPEC-FE-039). Images come back with a hash; videos are polled until
// Meta finishes processing them.
export default function MediaUploader({
  accept,
  label,
  onUploaded,
  disabled,
}: {
  accept: "image" | "video" | "both";
  label: string;
  onUploaded: (m: MediaResult) => void;
  disabled?: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [processing, setProcessing] = useState<string | null>(null);
  const upload = useMutation({
    mutationFn: uploadMedia,
    onSuccess: (m) => {
      if (m.type === "video" && m.status !== "ready" && m.video_id) setProcessing(m.video_id);
      onUploaded(m);
    },
  });
  useQuery({
    queryKey: ["meta", "video", processing],
    queryFn: async () => {
      const m = await videoStatus(processing as string);
      if (m.status === "ready" || m.status === "error") {
        onUploaded(m);
        setProcessing(null);
      }
      return m;
    },
    enabled: Boolean(processing),
    refetchInterval: 4000,
  });
  const types = accept === "image" ? "image/jpeg,image/png" : accept === "video" ? "video/mp4,video/quicktime" : "image/jpeg,image/png,video/mp4,video/quicktime";
  const pick = (files: FileList | null) => {
    const file = files?.[0];
    if (file) upload.mutate(file);
  };
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    if (!disabled) pick(e.dataTransfer.files);
  };
  return (
    <div>
      <div
        role="button"
        tabIndex={0}
        aria-disabled={disabled}
        className={`rounded-md border-2 border-dashed p-4 text-center text-[13px] ${over ? "border-accent bg-accent-soft" : "border-border"} ${disabled ? "opacity-50" : "cursor-pointer"}`}
        onClick={() => !disabled && input.current?.click()}
        onKeyDown={(e) => e.key === "Enter" && !disabled && input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
      >
        {upload.isPending ? "Uploading to Meta…" : processing ? "Meta is processing the video…" : label}
      </div>
      <input ref={input} type="file" accept={types} className="hidden" onChange={(e) => pick(e.target.files)} />
      {upload.isError && (
        <p className="m-0 mt-1 text-xs text-danger" role="alert">
          {errorText(upload.error)}
        </p>
      )}
    </div>
  );
}
