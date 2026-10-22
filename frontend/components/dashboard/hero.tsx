"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Icon, type IconName } from "@/components/shell/icons";
import { askHref } from "@/components/shell/nav";
import { useSignedInUser } from "@/components/shell/topbar";
import { fetchWorkflows, workflowKeys } from "@/lib/api/workflows";

// Dashboard head in the PilotSonic design: a time-of-day greeting with the
// signed-in user's first name, the live Autopilot pill (the real number of
// enabled workflows) and four quick actions. A quick action opens a new
// Command Chat with its request in the composer, ready to send.
// SPEC-FE-078: each card opens its page; the small "Ask the agent" link keeps the old prompt.
const QUICK: { href: string; prompt: string; title: string; sub: string; icon: IconName; color: string }[] = [
  { href: "/marketing/organic/create", prompt: "Create 7 organic posts and schedule them", title: "Create posts", sub: "Write, schedule or publish posts", icon: "pen", color: "#ec4899" },
  { href: "/marketing/paid", prompt: "How are my ads doing?", title: "Review ads", sub: "Spend, ROAS and campaign results", icon: "mega", color: "#f59e0b" },
  { href: "/ecommerce?tab=inventory", prompt: "What is low on stock?", title: "Check stock", sub: "Find items that need a restock", icon: "bag", color: "#0ea5e9" },
  { href: "/chat?tab=inbox", prompt: "Any customers waiting for a reply?", title: "Reply to customers", sub: "Every channel in one inbox", icon: "users", color: "#10b981" },
];

function greeting(hour: number): string {
  if (hour < 5) return "Working late";
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  if (hour < 21) return "Good evening";
  return "Good night";
}

export default function DashboardHero() {
  const user = useSignedInUser();
  const workflows = useQuery({ queryKey: workflowKeys.list, queryFn: fetchWorkflows });
  // The browser's clock, read after mount so server and client markup agree.
  const [hello, setHello] = useState("Hello");
  useEffect(() => setHello(greeting(new Date().getHours())), []);
  const first = user.data?.first_name?.trim() || null;
  const enabled = workflows.data?.filter((w) => w.status === "Enabled").length ?? 0;

  return (
    <>
      <div className="hero">
        <div>
          <h1 className="page-title">{first ? `${hello}, ${first}` : hello}</h1>
          <p className="page-subtitle">What&apos;s happening across your business, right now.</p>
        </div>
        {workflows.isSuccess && (
          <Link href="/workflows" className={`live-pill${enabled === 0 ? " off" : ""}`}>
            <i />
            <span>
              {enabled === 0
                ? "Autopilot is idle, no workflows enabled"
                : `Autopilot is on, ${enabled} workflow${enabled === 1 ? "" : "s"} running`}
            </span>
          </Link>
        )}
      </div>
      <div className="qa">
        {QUICK.map((q) => (
          <div key={q.title} className="relative">
            <Link href={q.href} className="qa-card" style={{ ["--c" as string]: q.color }}>
              <span className="qa-ico">
                <Icon name={q.icon} />
              </span>
              <span>
                <b>{q.title}</b>
                <small>{q.sub}</small>
              </span>
              <Icon name="arrow" className="ic qa-go" />
            </Link>
            <Link href={askHref(q.prompt)} className="mt-1 block text-right text-[11.5px] text-muted hover:text-accent">
              Ask the agent →
            </Link>
          </div>
        ))}
      </div>
    </>
  );
}
