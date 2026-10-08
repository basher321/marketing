import EngineCards from "@/components/dashboard/engine-cards";
import RecentActivity from "@/components/dashboard/recent-activity";
import SummaryCards from "@/components/dashboard/summary-cards";

// Dashboard (SPEC-FE-005 summary cards, SPEC-FE-006 engine cards, SPEC-FE-007
// recent activity), markup from the reference mockup.
export default function DashboardPage() {
  return (
    <>
      <h1 className="m-0 mb-1 text-[22px] font-bold">{"Dashboard"}</h1>
      <p className="m-0 mb-5 text-muted">{"What's happening across your business, right now."}</p>
      <SummaryCards />
      <h2 className="section-title">Automation Engines</h2>
      <EngineCards />
      <h2 className="section-title">Recent Activity</h2>
      <RecentActivity />
    </>
  );
}
