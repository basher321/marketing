"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  conversationKeys,
  editDraft,
  fetchDraft,
  generateDraft,
  handoffConversation,
  sendDraft,
} from "@/lib/api/conversations";
import { ApiError } from "@/lib/types/common";
import type { DraftRead, DraftResponse } from "@/lib/types/conversations";

export type ReplyDraftPanelProps = {
  /** The conversation selected in SPEC-FE-013's table; null before one is selected. */
  conversationId: string | null;
  /** Display values from the selected table row (SPEC-FE-013); null renders "—". */
  customer: string | null;
  channel: string | null;
};

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

// "Confidence: 94% · Grounded in order database + shipping policy" (mockup).
// The backend's confidence is on a 0-1 scale, shown as a rounded percentage.
// Sources are joined by source title with the mockup's " + ". A part with no
// real data (confidence null on non-generated drafts, sources []) is omitted
// rather than filled in; with neither, the line is not rendered.
function GroundingLine({ draft }: { draft: DraftRead }) {
  const hasConfidence = draft.confidence !== null;
  const hasSources = draft.sources.length > 0;
  if (!hasConfidence && !hasSources) return null;
  return (
    <p className="text-xs text-muted">
      {hasConfidence && (
        <>
          Confidence: <b>{Math.round(draft.confidence! * 100)}%</b>
        </>
      )}
      {hasConfidence && hasSources && " · "}
      {hasSources && `Grounded in ${draft.sources.map((s) => s.title).join(" + ")}`}
    </p>
  );
}

// Draft state for one conversation. Rendered with key={conversationId}, so
// switching the selection remounts it: any unsaved edit and inline error are
// discarded and the new conversation's draft is loaded fresh.
function DraftSection({ conversationId }: { conversationId: string }) {
  const queryClient = useQueryClient();
  const draftKey = conversationKeys.draft(conversationId);
  const draftQuery = useQuery({
    queryKey: draftKey,
    queryFn: () => fetchDraft(conversationId),
  });

  const [editText, setEditText] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [handedOffAt, setHandedOffAt] = useState<string | null>(null);

  // A failed action keeps the shown draft and shows the backend's message.
  // 404 / 409 mean the server state moved on (e.g. the draft was already sent
  // by someone else), so the draft and SPEC-FE-013's list are refetched.
  const onActionError = (err: unknown) => {
    setActionError(errorText(err));
    if (err instanceof ApiError && (err.status === 404 || err.status === 409)) {
      void queryClient.invalidateQueries({ queryKey: draftKey });
      void queryClient.invalidateQueries({ queryKey: conversationKeys.list });
    }
  };
  const onActionStart = () => setActionError(null);

  const edit = useMutation({
    mutationFn: (body: string) => editDraft(conversationId, body),
    onMutate: onActionStart,
    onSuccess: (data: DraftResponse) => {
      queryClient.setQueryData(draftKey, data);
      setEditText(null);
    },
    onError: onActionError,
  });
  const send = useMutation({
    mutationFn: () => sendDraft(conversationId),
    onMutate: onActionStart,
    onSuccess: () => {
      // The sent draft is consumed server-side: no pending draft remains.
      queryClient.setQueryData<DraftResponse>(draftKey, { draft: null });
      void queryClient.invalidateQueries({ queryKey: conversationKeys.list });
    },
    onError: onActionError,
  });
  // Handoff leaves the draft pending (so it stays shown) and does not change
  // conversations.status; since SPEC-BE-007 it records a metadata marker, so the
  // list refetch shows the conversation as "Escalated".
  const handoff = useMutation({
    mutationFn: () => handoffConversation(conversationId),
    onMutate: onActionStart,
    onSuccess: (data) => {
      setHandedOffAt(data.handed_off_at);
      void queryClient.invalidateQueries({ queryKey: conversationKeys.list });
    },
    onError: onActionError,
  });
  const generate = useMutation({
    mutationFn: () => generateDraft(conversationId),
    onMutate: onActionStart,
    onSuccess: (data: DraftResponse) => {
      queryClient.setQueryData(draftKey, data);
      void queryClient.invalidateQueries({ queryKey: conversationKeys.list });
    },
    onError: onActionError,
  });

  const busy = edit.isPending || send.isPending || handoff.isPending || generate.isPending;

  if (draftQuery.isPending) {
    return (
      <p className="text-[13px] text-muted" aria-busy="true">
        Loading draft…
      </p>
    );
  }
  if (draftQuery.isError) {
    return (
      <p className="text-[13px] text-danger" role="alert">
        Failed to load draft: {errorText(draftQuery.error)}
      </p>
    );
  }

  const draft = draftQuery.data.draft;
  const errorLine = actionError && (
    <p className="mt-3 text-xs text-danger" role="alert">
      {actionError}
    </p>
  );

  if (draft === null) {
    return (
      <>
        <p className="my-3 text-[13px] text-muted">No pending draft for this conversation</p>
        <button
          type="button"
          className="btn btn-sm"
          disabled={busy}
          onClick={() => generate.mutate()}
        >
          {generate.isPending ? "Generating…" : "Generate Draft"}
        </button>
        {errorLine}
      </>
    );
  }

  const editing = editText !== null;
  return (
    <>
      {editing ? (
        <textarea
          className="my-3 block min-h-[140px] w-full rounded-md border border-border bg-bg p-3 text-[13.5px] text-text"
          value={editText}
          onChange={(e) => setEditText(e.target.value)}
          disabled={edit.isPending}
          aria-label="Edit reply draft"
        />
      ) : (
        // Plain text: the API carries no emphasis markers, so nothing is bolded
        // (same rule as SPEC-FE-007).
        <div className="my-3 whitespace-pre-wrap rounded-md border border-border bg-bg p-3 text-[13.5px]">
          {draft.body}
        </div>
      )}
      <GroundingLine draft={draft} />
      <div className="mt-3 flex gap-2">
        {editing ? (
          <>
            {/* A blank edit would be rejected (422, the backend strips whitespace
                and requires 1+ chars), so Save is disabled for it. */}
            <button
              type="button"
              className="btn btn-sm"
              disabled={busy || editText.trim() === ""}
              onClick={() => edit.mutate(editText)}
            >
              {edit.isPending ? "Saving…" : "Save"}
            </button>
            {/* Cancel discards the local text without calling the backend. */}
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={busy}
              onClick={() => {
                setEditText(null);
                setActionError(null);
              }}
            >
              Cancel
            </button>
          </>
        ) : (
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            disabled={busy}
            onClick={() => setEditText(draft.body)}
          >
            Edit
          </button>
        )}
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={busy}
          onClick={() => handoff.mutate()}
        >
          {handoff.isPending ? "Handing off…" : "Handoff"}
        </button>
        {/* Send has no request body - the backend sends the stored draft - so it
            is disabled while an edit is unsaved rather than sending stale text. */}
        <button
          type="button"
          className="btn btn-sm"
          disabled={busy || editing}
          onClick={() => send.mutate()}
        >
          {send.isPending ? "Sending…" : "Send Reply"}
        </button>
      </div>
      {handedOffAt && !actionError && (
        <p className="mt-3 text-xs text-muted">
          Handed off at {new Date(handedOffAt).toLocaleString()}
        </p>
      )}
      {errorLine}
    </>
  );
}

// Customer Service AI Reply Draft panel (SPEC-FE-014): the right-hand card of
// the page's grid-2, for whichever conversation SPEC-FE-013's table selected.
// Markup and sizes are copied from the reference mockup.
export default function ReplyDraftPanel({ conversationId, customer, channel }: ReplyDraftPanelProps) {
  return (
    <div className="card">
      <h3 className="mt-0 text-sm">AI Reply Draft</h3>
      {conversationId === null ? (
        <p className="text-[13px] text-muted">No conversation selected</p>
      ) : (
        <>
          <p className="text-[13px] text-muted">
            For:{" "}
            <b>
              {customer ?? "—"} · {channel ?? "—"}
            </b>
          </p>
          <DraftSection key={conversationId} conversationId={conversationId} />
        </>
      )}
    </div>
  );
}
