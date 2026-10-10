import ApprovalsPanel from "@/components/chat/approvals-panel";
import ChatPanel from "@/components/chat/chat-panel";

// Command Chat (SPEC-FE-008/009/010 behavior; SPEC-FE-061 generative-UI look,
// SPEC-FE-062 voice commands and spoken replies).
export default function ChatPage() {
  return (
    <>
      <h1 className="m-0 mb-1 text-[22px] font-bold">{"Command Chat"}</h1>
      <p className="m-0 mb-4 text-muted">{"Talk to your business by typing or speaking, in any language. Direct all three engines."}</p>
      <div className="cc-layout">
        <ChatPanel />
        <ApprovalsPanel />
      </div>
    </>
  );
}
