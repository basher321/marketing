import Link from "next/link";

import CampaignsTable from "@/components/marketing/campaigns-table";
import ContentCalendar from "@/components/marketing/content-calendar";
import SummaryCards from "@/components/marketing/summary-cards";

// Entry points to the two Marketing areas (SPEC-FE-049).
const AREAS = [
  {
    href: "/marketing/paid",
    title: "Paid Marketing",
    text: "Campaign → Ad set → Ad on Meta, TikTok, Google, LinkedIn and more. Review, schedule, publish and pause.",
  },
  {
    href: "/marketing/organic",
    title: "Organic Marketing",
    text: "Posts for your social accounts: write or generate, adapt per platform, schedule and track.",
  },
];

// Marketing Automation: title/subtitle from the reference mockup (SPEC-FE-002),
// the summary cards (SPEC-FE-012), and the Active Campaigns table + Content
// Calendar (backed by SPEC-BE-038).
export default function MarketingPage() {
  return (
    <>
      <h1 className="m-0 mb-1 text-[22px] font-bold">{"Marketing Automation"}</h1>
      <p className="m-0 mb-5 text-muted">{"Content, scheduling, ads — coordinated across every channel."}</p>
      <div className="mb-4 grid gap-4 md:grid-cols-2">
        {AREAS.map((a) => (
          <Link key={a.href} href={a.href} className="card block text-inherit no-underline hover:border-accent" data-testid={`area-${a.href.split("/").pop()}`}>
            <div className="mb-1 font-semibold">{a.title} →</div>
            <p className="m-0 text-[13px] text-muted">{a.text}</p>
          </Link>
        ))}
      </div>
      <SummaryCards />
      <CampaignsTable />
      <ContentCalendar />
    </>
  );
}
