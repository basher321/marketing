"use client";

import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";

import { fetchMediaItem, mediaKeys } from "@/lib/api/media";
import { uploadChatFile } from "@/lib/api/orchestrator";
import type { FileRead, MessageFile } from "@/lib/types/orchestrator";
import { formatNumber } from "@/lib/format/number";

// Chat attachments (SPEC-FE-064, backend SPEC-BE-096): 📎 picker, drag-and-drop
// and paste. Each file uploads at once (with progress), is read by the
// backend ("Reading…"), and shows its summary; Send waits for all of them.

export const MAX_FILES = 20;
export const MAX_BYTES = 100 * 1024 * 1024;
const ACCEPT = ".pdf,.docx,.xlsx,.csv,.tsv,.txt,.md,.json,.jpg,.jpeg,.png,.webp,.gif,.zip";

export type AttachmentState = "uploading" | "reading" | "ready" | "error";
export interface Attachment {
  id: string;
  file: File;
  state: AttachmentState;
  progress: number;
  result: FileRead | null;
  error: string | null;
  preview: string | null; // object URL for images
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${formatNumber(n / 1024)} KB`;
  return `${formatNumber(n / 1024 / 1024)} MB`;
}

const KIND_ICON: Record<string, string> = {
  pdf: "📕", docx: "📘", xlsx: "📗", csv: "📗", text: "📄", json: "🧾", image: "🖼️", zip: "🗜️",
};

function guessIcon(file: File): string {
  const n = file.name.toLowerCase();
  if (file.type.startsWith("image/")) return "🖼️";
  if (n.endsWith(".pdf")) return "📕";
  if (n.endsWith(".docx")) return "📘";
  if (n.endsWith(".xlsx") || n.endsWith(".csv") || n.endsWith(".tsv")) return "📗";
  if (n.endsWith(".zip")) return "🗜️";
  return "📄";
}

/** The attachments of the message being written. */
export function useAttachments() {
  const [items, setItems] = useState<Attachment[]>([]);
  const controllers = useRef(new Map<string, AbortController>());
  const patch = useCallback((id: string, p: Partial<Attachment>) => setItems((list) => list.map((a) => (a.id === id ? { ...a, ...p } : a))), []);

  useEffect(() => {
    const ctrls = controllers.current;
    return () => ctrls.forEach((c) => c.abort());
  }, []);

  const current = useRef<Attachment[]>([]);
  useEffect(() => {
    current.current = items;
  }, [items]);

  // Uploads start here, outside the state updater (React may run updaters twice).
  const add = useCallback(
    (files: FileList | File[]) => {
      const incoming = Array.from(files);
      const room = MAX_FILES - current.current.filter((a) => !a.id.startsWith("over-")).length;
      const accepted = incoming.slice(0, Math.max(0, room));
      const next = accepted.map<Attachment>((file) => {
        const tooBig = file.size > MAX_BYTES;
        return {
          id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
          file,
          state: tooBig ? "error" : "uploading",
          progress: 0,
          result: null,
          error: tooBig ? "The file can be at most 100 MB." : null,
          preview: file.type.startsWith("image/") ? URL.createObjectURL(file) : null,
        };
      });
      const over = incoming.length - accepted.length;
      const extra: Attachment[] = over > 0
        ? [{ id: `over-${Date.now()}`, file: incoming[accepted.length], state: "error", progress: 0, result: null,
             error: `Only ${MAX_FILES} files per message; ${over} left out.`, preview: null }]
        : [];
      current.current = [...current.current, ...next, ...extra];
      setItems((list) => [...list, ...next, ...extra]);
      for (const a of next) {
        if (a.state === "error") continue;
        const ctrl = new AbortController();
        controllers.current.set(a.id, ctrl);
        uploadChatFile(a.file, (f) => patch(a.id, f >= 1 ? { progress: 1, state: "reading" } : { progress: f }), ctrl.signal)
          .then((res) => patch(a.id, { state: "ready", progress: 1, result: res }))
          .catch((err: unknown) => patch(a.id, { state: "error", error: err instanceof Error ? err.message : String(err) }))
          .finally(() => controllers.current.delete(a.id));
      }
    },
    [patch],
  );

  const remove = useCallback((id: string) => {
    controllers.current.get(id)?.abort();
    setItems((list) => {
      const gone = list.find((a) => a.id === id);
      if (gone?.preview) URL.revokeObjectURL(gone.preview);
      return list.filter((a) => a.id !== id);
    });
  }, []);

  const clear = useCallback(() => {
    setItems((list) => {
      list.forEach((a) => a.preview && URL.revokeObjectURL(a.preview));
      return [];
    });
  }, []);

  const busy = items.some((a) => a.state === "uploading" || a.state === "reading");
  const ready = items.filter((a) => a.state === "ready" && a.result).map((a) => a.result as FileRead);
  return { items, add, remove, clear, busy, ready };
}

export function AttachButton({ onFiles, disabled }: { onFiles: (f: FileList) => void; disabled?: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <input
        ref={input}
        type="file"
        multiple
        accept={ACCEPT}
        className="hidden"
        data-testid="chat-file-input"
        onChange={(e) => {
          if (e.target.files?.length) onFiles(e.target.files);
          e.target.value = "";
        }}
      />
      <button
        type="button"
        className="cc-icon-btn"
        onClick={() => input.current?.click()}
        disabled={disabled}
        aria-label="Attach files"
        title="Attach files: PDF, Word, Excel, CSV, images or ZIP (up to 100 MB each)"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M21.4 11.1l-9.2 9.2a6 6 0 0 1-8.5-8.5l9.2-9.2a4 4 0 0 1 5.7 5.7l-9.2 9.2a2 2 0 0 1-2.8-2.8l8.5-8.5" />
        </svg>
      </button>
    </>
  );
}

export function AttachmentChips({ items, onRemove }: { items: Attachment[]; onRemove: (id: string) => void }) {
  if (!items.length) return null;
  return (
    <div className="cc-attach-row" data-testid="chat-attachments">
      {items.map((a) => (
        <div key={a.id} className={`cc-attach ${a.state === "error" ? "is-error" : ""}`} title={a.result?.summary || a.error || a.file.name}>
          {a.preview ? <img src={a.preview} alt="" className="cc-attach-thumb" /> : <span className="cc-attach-icon" aria-hidden="true">{guessIcon(a.file)}</span>}
          <div className="min-w-0 flex-1">
            <div className="truncate text-[12px] font-medium">{a.file.name}</div>
            <div className="truncate text-[11px] text-muted">
              {a.state === "uploading"
                ? `Uploading ${Math.round(a.progress * 100)}% · ${formatBytes(a.file.size)}`
                : a.state === "reading"
                  ? "Reading…"
                  : a.state === "error"
                    ? <span className="text-danger">{a.error}</span>
                    : `${formatBytes(a.file.size)} · ${a.result?.summary}`}
            </div>
            {(a.state === "uploading" || a.state === "reading") && (
              <div className="cc-attach-bar" aria-hidden="true">
                <span className={a.state === "reading" ? "cc-shimmer" : ""} style={{ width: `${Math.max(4, a.progress * 100)}%` }} />
              </div>
            )}
          </div>
          <button type="button" className="cc-link" onClick={() => onRemove(a.id)} aria-label={`Remove ${a.file.name}`}>
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}

/** Drag-and-drop over the chat: an overlay while files hover. */
export function useDropZone(onFiles: (f: FileList) => void) {
  const [over, setOver] = useState(false);
  const depth = useRef(0);
  const hasFiles = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes("Files");
  return {
    over,
    props: {
      onDragEnter: (e: DragEvent) => {
        if (!hasFiles(e)) return;
        e.preventDefault();
        depth.current += 1;
        setOver(true);
      },
      onDragOver: (e: DragEvent) => {
        if (hasFiles(e)) e.preventDefault();
      },
      onDragLeave: (e: DragEvent) => {
        if (!hasFiles(e)) return;
        depth.current = Math.max(0, depth.current - 1);
        if (depth.current === 0) setOver(false);
      },
      onDrop: (e: DragEvent) => {
        if (!hasFiles(e)) return;
        e.preventDefault();
        depth.current = 0;
        setOver(false);
        if (e.dataTransfer.files.length) onFiles(e.dataTransfer.files);
      },
    },
  };
}

export function DropOverlay() {
  return (
    <div className="cc-drop-overlay" aria-hidden="true">
      <div className="cc-drop-box">
        <div className="text-3xl">📎</div>
        <div className="mt-1 font-semibold">Drop files to attach</div>
        <div className="text-[12px] text-muted">PDF, Word, Excel, CSV, images or ZIP · up to 100 MB each</div>
      </div>
    </div>
  );
}

function FileThumb({ mediaId }: { mediaId: string }) {
  const q = useQuery({ queryKey: mediaKeys.item(mediaId), queryFn: () => fetchMediaItem(mediaId), staleTime: 30 * 60_000 });
  if (!q.data) return <span className="cc-attach-thumb cc-shimmer" />;
  return <img src={q.data.url} alt="" className="cc-attach-thumb" />;
}

/** The files of a sent user message (after a reload too). */
export function MessageFiles({ files }: { files: MessageFile[] }) {
  return (
    <div className="grid w-full max-w-[420px] gap-1.5" data-testid="chat-message-files">
      {files.map((f) => (
        <div key={f.id} className="cc-attach cc-attach-sent" title={f.summary}>
          {f.kind === "image" && f.media_ids[0] ? <FileThumb mediaId={f.media_ids[0]} /> : <span className="cc-attach-icon" aria-hidden="true">{KIND_ICON[f.kind] ?? "📄"}</span>}
          <div className="min-w-0 flex-1 text-left">
            <div className="truncate text-[12px] font-medium">{f.name}</div>
            <div className="truncate text-[11px] text-muted">{formatBytes(f.bytes)} · {f.summary}</div>
          </div>
        </div>
      ))}
    </div>
  );
}
