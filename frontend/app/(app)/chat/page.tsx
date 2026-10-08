import ApprovalsPanel from "@/components/chat/approvals-panel";
import ChatPanel from "@/components/chat/chat-panel";

// Command Chat (SPEC-FE-008 chat, SPEC-FE-009 plan card, SPEC-FE-010 pending
// approvals), markup from the reference mockup's .chat-container.
export default function ChatPage() {
  return (
    <>
      <h1 className="m-0 mb-1 text-[22px] font-bold">{"Command Chat"}</h1>
      <p className="m-0 mb-5 text-muted">{"Talk to your business. Direct all three engines in plain language."}</p>
      <div className="chat-container">
        <ChatPanel />
        <ApprovalsPanel />
      </div>
    </>
  );
}
