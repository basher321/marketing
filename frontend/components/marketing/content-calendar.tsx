"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchContentCalendar, marketingListKeys } from "@/lib/api/marketing";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const SHORT: Record<string, string> = {
  facebook: "FB", instagram: "IG", tiktok: "TikTok", whatsapp: "WhatsApp",
  messenger: "Messenger", email: "Email", sms: "SMS", web: "Web",
};

// "FB Post", "IG Story" (mockup): channel abbreviation + the content asset's
// real format, capitalized. No wording is invented beyond that.
function label(channel: string, format: string): string {
  return `${SHORT[channel] ?? channel} ${format.charAt(0).toUpperCase()}${format.slice(1).replace("_", " ")}`;
}

// Marketing "Content Calendar" (backend SPEC-BE-038): the current Monday-Sunday
// week in the tenant's timezone, markup and inline values from the mockup.
export default function ContentCalendar() {
  const query = useQuery({ queryKey: marketingListKeys.calendar, queryFn: fetchContentCalendar });
  return (
    <>
      <h2 className="section-title">Content Calendar</h2>
      <div className="card">
        {query.isPending ? (
          <p className="m-0 text-[13px] text-muted">Loading calendar…</p>
        ) : query.isError ? (
          <p className="m-0 text-[13px] text-danger" role="alert">
            Failed to load calendar: {query.error.message}
          </p>
        ) : (
          <div className="grid grid-cols-7 gap-2 text-center">
            {query.data.days.map((d, i) => (
              <div key={d.date}>
                <b>{WEEKDAYS[i]}</b>
                {d.posts.length === 0 ? (
                  <div className="mt-2 rounded-md border border-dashed border-border bg-bg p-2 text-xs text-muted">Empty</div>
                ) : (
                  <div className="mt-2 rounded-md bg-accent-soft p-2 text-xs">
                    {d.posts.map((p) => (
                      <div key={p.id}>{label(p.channel, p.format)}</div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
