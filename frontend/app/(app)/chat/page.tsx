"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import ApprovalsPanel from "@/components/chat/approvals-panel";
import ChatPanel from "@/components/chat/chat-panel";
import ChatSidebar from "@/components/chat/chat-sidebar";
import Inbox from "@/components/inbox/inbox";
import { fetchChats, orchestratorKeys } from "@/lib/api/orchestrator";

// Command Chat (SPEC-FE-008/009/010 behavior; SPEC-FE-061 generative-UI look,
// SPEC-FE-062 voice). SPEC-FE-066: many chats and projects. The open chat is
// ?c=<id> and an open project ?p=<id>, so reload and back keep them; the
// right column holds the history (top) and Pending Approvals (below).
// SPEC-FE-067: plain /chat opens the latest chat; a new, empty chat is ?new=1.
function ChatWorkspace() {
  const params = useSearchParams();
  const router = useRouter();
  // A chat deleted while open counts as closed at once; the URL catches up a
  // render later, and fetching it meanwhile would 404.
  const [gone, setGone] = useState<string | null>(null);
  const urlChat = params.get("c");
  const chatId = urlChat && urlChat !== gone ? urlChat : null;
  const projectId = params.get("p");
  const isNew = params.get("new") === "1";
  // A request from the Dashboard's quick actions or the command palette.
  const ask = isNew ? (params.get("ask") ?? "") : "";
  // The same list (and cache) as the sidebar's: pinned first, then the latest.
  const latest = useQuery({
    queryKey: orchestratorKeys.chatList("", false, null),
    queryFn: () => fetchChats("", false, null),
    enabled: !urlChat && !isNew,
  });
  const latestId = latest.data?.items[0]?.id ?? null;
  const [newChatProject, setNewChatProject] = useState<string | null>(null);
  // Bumped when the user opens another chat or starts a new one, so the panel
  // starts clean; not when a chat is created by sending (it stays mounted).
  const [panelKey, setPanelKey] = useState(0);
  const [drawer, setDrawer] = useState(false);
  // A new ?ask= while a new chat is already open starts it clean with that
  // text; sending (which drops ask from the URL) keeps the panel mounted.
  useEffect(() => {
    if (ask) setPanelKey((k) => k + 1);
  }, [ask]);

  const go = (c: string | null, p: string | null, fresh = false) => {
    const qs = new URLSearchParams();
    if (c) qs.set("c", c);
    else if (fresh) qs.set("new", "1");
    if (p) qs.set("p", p);
    router.replace(qs.toString() ? `/chat?${qs.toString()}` : "/chat", { scroll: false });
  };
  useEffect(() => {
    if (!urlChat && !isNew && latestId) go(latestId, projectId);
  }, [urlChat, isNew, latestId]);
  // Plain /chat waits for the list, so the empty chat doesn't flash before the latest one opens.
  const resolving = !urlChat && !isNew && (latest.isPending || !!latestId);

  return (
    <div className="cc-layout">
      {resolving ? <div className="cc-panel cc-shimmer" /> : <ChatPanel
        key={panelKey}
        chatId={chatId}
        newChatProjectId={chatId ? null : newChatProject}
        initialText={chatId ? "" : ask}
        onChatCreated={(id) => go(id, projectId)}
        onOpenHistory={() => setDrawer(true)}
      />}
      <aside className="cc-side">
        <ChatSidebar
          activeChatId={chatId}
          openProjectId={projectId}
          onOpenChat={(id) => {
            if (id !== chatId) setPanelKey((k) => k + 1);
            go(id, projectId);
            setDrawer(false);
          }}
          onNewChat={(pid) => {
            setNewChatProject(pid ?? null);
            setPanelKey((k) => k + 1);
            go(null, pid ?? projectId, true);
            setDrawer(false);
          }}
          onOpenProject={(pid) => go(chatId, pid)}
          onChatDeleted={(id) => {
            if (id === chatId) {
              setGone(id);
              setPanelKey((k) => k + 1);
              go(null, projectId, true);
            }
          }}
          open={drawer}
          onClose={() => setDrawer(false)}
        />
        <ApprovalsPanel collapsible />
      </aside>
    </div>
  );
}

// SPEC-FE-076: two tabs, Command (everything above) and Inbox (?tab=inbox, an
// open conversation is ?conv=<key>; ?c= stays the Command chat id).
function ChatTabs() {
  const params = useSearchParams();
  const router = useRouter();
  const tab = params.get("tab") === "inbox" ? "inbox" : "command";
  const select = (t: "command" | "inbox") => router.replace(t === "inbox" ? "/chat?tab=inbox" : "/chat", { scroll: false });
  return (
    <>
      <div className="tabs" role="tablist">
        {(["command", "inbox"] as const).map((t) => (
          <div
            key={t}
            role="tab"
            aria-selected={tab === t}
            tabIndex={0}
            className={tab === t ? "tab active" : "tab"}
            onClick={() => select(t)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") select(t);
            }}
          >
            {t === "command" ? "Command" : "Inbox"}
          </div>
        ))}
      </div>
      {tab === "inbox" ? <Inbox initialKey={params.get("conv")} /> : <ChatWorkspace />}
    </>
  );
}

export default function ChatPage() {
  return (
    <>
      <h1 className="page-title">{"Command Chat"}</h1>
      <p className="page-subtitle mb-4">{"Talk to your business by typing or speaking, in any language. Direct all three engines."}</p>
      {/* useSearchParams needs a Suspense boundary for the static build. */}
      <Suspense fallback={<div className="cc-layout"><div className="cc-panel cc-shimmer" /></div>}>
        <ChatTabs />
      </Suspense>
    </>
  );
}
