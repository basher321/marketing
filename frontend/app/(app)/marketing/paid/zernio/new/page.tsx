"use client";

import ZernioWizard from "@/components/zernio/wizard";

// Zernio "New campaign" (SPEC-FE-055): reached from Ad Manager › "Zernio (all
// platforms)". One wizard for Facebook, Instagram, TikTok, LinkedIn, Pinterest,
// X and Google Ads through the server's Zernio key.
export default function ZernioNewCampaignPage() {
  return (
    <div className="mx-auto max-w-[1000px]">
      <div className="mb-5">
        <h1 className="page-title">New campaign · Zernio</h1>
        <p className="page-subtitle mb-0">Choose a platform, then its account, goal, budget, audience and ad. Only the options that platform offers are shown.</p>
      </div>
      <ZernioWizard />
    </div>
  );
}
