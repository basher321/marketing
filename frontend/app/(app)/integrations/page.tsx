import Link from "next/link";

import AIModels from "@/components/integrations/ai-models";
import IntegrationsGrid from "@/components/integrations/integrations-grid";
import { KeyCard } from "@/components/socialapi/publishing";

// Title and subtitle copied from the reference mockup (SPEC-FE-002). One page
// for every key (SPEC-FE-037): AI models with a fallback order (SPEC-BE-053),
// the SocialAPI.ai key (SPEC-FE-054), then platform connections (SPEC-FE-021 /
// SPEC-BE-052). Nothing goes in .env.
export default function IntegrationsPage() {
  return (
    <>
      <h1 className="m-0 mb-1 text-[22px] font-bold">{"Integrations"}</h1>
      <p className="m-0 mb-5 text-muted">{"Connect the platforms your business runs on."}</p>
      <AIModels />
      <div id="socialapi" className="mt-4">
        <KeyCard />
        <p className="-mt-2 mb-4 text-xs text-muted">
          After saving the key:{" "}
          <Link href="/marketing/organic/socialapi" className="text-accent underline">
            connect accounts and post
          </Link>{" "}
          ·{" "}
          <Link href="/customer/socialapi" className="text-accent underline">
            SocialAPI inbox
          </Link>
        </p>
      </div>
      <IntegrationsGrid />
    </>
  );
}
