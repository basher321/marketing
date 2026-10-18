"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import ApprovalsPanel from "@/components/chat/approvals-panel";
import ChatPanel from "@/components/chat/chat-panel";
import ChatSidebar from "@/components/chat/chat-sidebar";
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

export default function ChatPage() {
  return (
    <>
      <h1 className="m-0 mb-1 text-[22px] font-bold">{"Command Chat"}</h1>
      <p className="m-0 mb-4 text-muted">{"Talk to your business by typing or speaking, in any language. Direct all three engines."}</p>
      {/* useSearchParams needs a Suspense boundary for the static build. */}
      <Suspense fallback={<div className="cc-layout"><div className="cc-panel cc-shimmer" /></div>}>
        <ChatWorkspace />
      </Suspense>
    </>
  );
}
