import BusinessCards from "@/components/dashboard/business-cards";
import DashboardHero from "@/components/dashboard/hero";
import EngineCards from "@/components/dashboard/engine-cards";
import RecentActivity from "@/components/dashboard/recent-activity";
import SummaryCards from "@/components/dashboard/summary-cards";

// Dashboard (SPEC-FE-005 summary cards, SPEC-FE-006 engine cards, SPEC-FE-007
// recent activity), laid out as the PilotSonic dashboard design: greeting,
// Autopilot pill and quick actions first. The two stat-card grids share one
// parent grid (.dash-stats) so every row and column gap is the same (SPEC-FE-079).
export default function DashboardPage() {
  return (
    <>
      <DashboardHero />
      <div className="dash-stats">
        <SummaryCards />
        <BusinessCards />
      </div>
      <h2 className="section-title">Automation Engines</h2>
      <EngineCards />
      <h2 className="section-title">Recent Activity</h2>
      <RecentActivity />
    </>
  );
}
