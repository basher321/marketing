"use client";

import Link from "next/link";
import { useState } from "react";

import ConversationsTable, {
  channelLabel,
  displayCustomer,
} from "@/components/customer/conversations-table";
import ReplyDraftPanel from "@/components/customer/reply-draft-panel";
import type { InboxItem } from "@/lib/types/conversations";

// Customer Service (SPEC-FE-013 + SPEC-FE-014): the mockup's grid-2 - the Open
// Conversations table (left) selects the conversation whose AI reply draft the
// panel (right) shows. The selection lives here, lifted between the two.
export default function CustomerPage() {
  const [selected, setSelected] = useState<InboxItem | null>(null);

  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h1 className="m-0 mb-1 text-[22px] font-bold">{"Customer Service"}</h1>
        {/* SPEC-FE-054: the separate inbox for accounts connected through SocialAPI.ai */}
        <Link href="/customer/socialapi" className="btn btn-secondary btn-sm no-underline">
          SocialAPI inbox →
        </Link>
      </div>
      <p className="m-0 mb-5 text-muted">{"Unified inbox — WhatsApp, Messenger, IG DM, email."}</p>
      <div className="grid-2">
        <ConversationsTable selectedId={selected?.id ?? null} onSelect={setSelected} />
        <ReplyDraftPanel
          conversationId={selected?.id ?? null}
          customer={selected ? displayCustomer(selected.customer_name) : null}
          channel={selected ? channelLabel(selected.channel) : null}
        />
      </div>
    </>
  );
}
