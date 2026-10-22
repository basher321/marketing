import Link from "next/link";

import AIModels from "@/components/integrations/ai-models";
import IntegrationsGrid from "@/components/integrations/integrations-grid";
import MessagingChannels from "@/components/integrations/messaging-channels";
import { KeyCard } from "@/components/socialapi/publishing";

// Title and subtitle copied from the reference mockup (SPEC-FE-002). SPEC-FE-068:
// the API keys are PilotSonic's (the Super admin's); here a company sees the AI
// models it gets, SocialAPI's status and connects its own pages and accounts.
export default function IntegrationsPage() {
  return (
    <>
      <h1 className="page-title">{"Integrations"}</h1>
      <p className="page-subtitle">{"Connect the platforms your business runs on."}</p>
      <AIModels />
      <div id="socialapi" className="mt-4">
        <KeyCard />
        <p className="-mt-2 mb-4 text-xs text-muted">
          Next:{" "}
          <Link href="/marketing/organic/socialapi" className="text-accent underline">
            connect accounts and post
          </Link>{" "}
          ·{" "}
          <Link href="/customer/socialapi" className="text-accent underline">
            SocialAPI inbox
          </Link>
        </p>
      </div>
      <MessagingChannels />
      <IntegrationsGrid />
    </>
  );
}
