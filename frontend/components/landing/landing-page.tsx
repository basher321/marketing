"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type PointerEvent, type ReactNode } from "react";

import { getAuthToken } from "@/lib/auth/token";

import s from "./landing.module.css";

// The PilotSonic website (pilotsonic-website.html): the public page at "/".
// Copy, sections and motion follow the design. Its sign-in buttons open the
// real auth pages instead of the design's simulated Google gate: "Sign in" →
// /login, "Start free" → /signup, or "Open dashboard" when already signed in.

const cx = (...names: (string | false | undefined)[]) => names.filter(Boolean).join(" ");

const LOGS: Record<string, ReactNode[]> = {
  store: [
    <><em>order</em> #4821 received · $64.00</>,
    <><em>stock</em> 3 variants running low</>,
    <><em>draft</em> reorder prepared · <u>awaiting your OK</u></>,
    <><em>ship</em> courier booked, tracking sent <u>✓</u></>,
  ],
  mkt: [
    <><em>read</em> last 30 days of posts and sales</>,
    <><em>write</em> 7 posts in your brand voice <u>✓</u></>,
    <><em>ads</em> Campaign A ROAS 3.8x · scaling +15%</>,
    <><em>draft</em> budget change · <u>awaiting your OK</u></>,
  ],
  sup: [
    <><em>inbox</em> &quot;Where is my order?&quot;</>,
    <><em>lookup</em> order found · status shipped</>,
    <><em>reply</em> sent in Bangla in 4 seconds <u>✓</u></>,
    <><em>handover</em> refund request escalated to you</>,
  ],
};

const AGENT_TABS = [
  { k: "store", title: "🛍 Store agent", sub: "Orders, stock, shipping" },
  { k: "mkt", title: "📣 Marketing agent", sub: "Posts, ads, campaigns" },
  { k: "sup", title: "🎧 Support agent", sub: "Replies and handover" },
];

const STACK = ["Shopify", "WooCommerce", "Meta Ads", "Google Ads", "Instagram", "Facebook", "WhatsApp", "Gmail", "Slack", "Stripe"];

const NUMS = [
  { n: 12400, suffix: "+", label: "Tasks automated daily" },
  { n: 38, suffix: "h", label: "Saved per team weekly" },
  { n: 3, suffix: "x", label: "Faster replies" },
  { n: 99, suffix: "%", label: "Uptime" },
];

function AgentLog() {
  const [k, setK] = useState("store");
  const [shown, setShown] = useState(0);
  useEffect(() => {
    setShown(0);
    const timers = LOGS[k].map((_, i) => window.setTimeout(() => setShown(i + 1), i * 750));
    return () => timers.forEach((t) => window.clearTimeout(t));
  }, [k]);
  return (
    <div className={cx(s.lab, s.reveal)} data-reveal>
      <div className={s.tabs} role="tablist">
        {AGENT_TABS.map((t) => (
          <button key={t.k} type="button" role="tab" aria-selected={k === t.k} className={cx(s.tab, k === t.k && s.on)} onClick={() => setK(t.k)}>
            <b>{t.title}</b>
            <small>{t.sub}</small>
          </button>
        ))}
      </div>
      <div className={s.term}>
        <div className={s.bar2}>
          <i />
          <i />
          <i />
          <small>agent.log</small>
        </div>
        <div className={s.log} aria-live="polite">
          {LOGS[k].slice(0, shown).map((line, i) => (
            <div key={`${k}-${i}`} className={s.ln}>
              <span>›</span>
              <span>{line}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function LandingPage() {
  const root = useRef<HTMLDivElement>(null);
  const [light, setLight] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
  useEffect(() => setSignedIn(getAuthToken() !== null), []);

  // Reveal on scroll and the count-up numbers, as in the design.
  useEffect(() => {
    const el = root.current;
    if (!el) return;
    const count = (b: HTMLElement) => {
      const n = Number(b.dataset.n);
      const suffix = b.dataset.s ?? "";
      let t = 0;
      const step = () => {
        t = Math.min(t + n / 50, n);
        b.textContent = Math.round(t).toLocaleString() + suffix;
        if (t < n) requestAnimationFrame(step);
      };
      step();
    };
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (!e.isIntersecting) continue;
          e.target.classList.add(s.in);
          io.unobserve(e.target);
          e.target.querySelectorAll<HTMLElement>("[data-n]").forEach(count);
        }
      },
      { threshold: 0.15 },
    );
    el.querySelectorAll("[data-reveal]").forEach((r) => io.observe(r));
    return () => io.disconnect();
  }, []);

  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    const card = (e.target as Element).closest<HTMLElement>(`.${s.card}`);
    if (!card) return;
    const r = card.getBoundingClientRect();
    card.style.setProperty("--mx", `${e.clientX - r.left}px`);
    card.style.setProperty("--my", `${e.clientY - r.top}px`);
  };

  const startHref = signedIn ? "/dashboard" : "/signup";
  const startLabel = signedIn ? "Open dashboard" : "Start free";

  return (
    <div ref={root} className={cx(s.ws, light && s.light)} onPointerMove={onPointerMove}>
      <div className={s.aur} aria-hidden="true">
        <i />
        <i />
        <i />
      </div>
      <header>
        <nav className={s.nav}>
          <a className={s.plNav} href="#top" aria-label="PilotSonic">
            <span className="pl-m" />
            <span className="pl-w" />
          </a>
          <div className={s.links}>
            <a href="#features">Features</a>
            <a href="#lab">Live demo</a>
            <a href="#pricing">Pricing</a>
            <a href="#faq">FAQ</a>
          </div>
          <div className={s.row}>
            <button type="button" className={s.ib} aria-label="Toggle theme" onClick={() => setLight((v) => !v)}>
              ◐
            </button>
            <Link className={cx(s.btn, s.ghost)} href={signedIn ? "/dashboard" : "/login"}>
              {signedIn ? "Open dashboard" : "Sign in"}
            </Link>
          </div>
        </nav>
      </header>

      <main className={s.wrap} id="top">
        <div className={s.hero}>
          <span className={s.pill}>
            <b>New</b>Autopilot 2.0 · agents that ask before they spend
          </span>
          <h1>
            Run your whole business with <span className={s.g}>AI agents.</span>
          </h1>
          <p className={s.lede}>
            Store, ads, content, support and shipping. Tell the Orchestrator what you want in plain words. Agents do the work and wait
            for your OK.
          </p>
          <div className={s.cta}>
            <Link className={cx(s.btn, s.big)} href={startHref}>
              {startLabel} →
            </Link>
            <a className={cx(s.btn, s.big, s.ghost)} href="#lab">
              ▶ Watch it work
            </a>
          </div>
          <div className={s.note}>
            <span>No credit card</span>
            <span>5 minute setup</span>
            <span>Human approval built in</span>
          </div>
          <div className={cx(s.stage, s.reveal)} data-reveal>
            <div className={s.shot}>
              <div className={s.bar2}>
                <i />
                <i />
                <i />
                <small>pilotsonic.app/dashboard</small>
              </div>
              <div className={s.sh}>
                <div className={s.side}>
                  <div className={s.on}>▦ Dashboard</div>
                  <div>💬 Command Chat</div>
                  <div>🛍 E-Commerce</div>
                  <div>📣 Marketing</div>
                  <div>🎧 Support</div>
                  <div>⚡ Workflows</div>
                  <div>📈 Analytics</div>
                </div>
                <div className={s.main}>
                  <div className={s.k3}>
                    {[
                      { label: "Revenue today", value: "$12.4k", delta: "▲ 24.8%", bars: [35, 55, 45, 75, 62, 100] },
                      { label: "Orders", value: "147", delta: "▲ 12 new", bars: [50, 40, 70, 60, 85, 95] },
                      { label: "ROAS", value: "3.8x", delta: "▲ scaling", bars: [30, 48, 66, 58, 80, 92] },
                    ].map((k) => (
                      <div key={k.label} className={s.k}>
                        <small>{k.label}</small>
                        <b>{k.value}</b>
                        <em>{k.delta}</em>
                        <div className={s.mb}>
                          {k.bars.map((h, i) => (
                            <s key={i} style={{ height: `${h}%` }} />
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className={s.k2}>
                    <div className={s.pan}>
                      <div className={cx(s.m, s.u)}>Create 7 posts and run a weekend sale</div>
                      <div className={cx(s.m, s.a)}>
                        Done. Posts are drafted and the 15% sale is ready. <b>Approve to publish?</b>
                      </div>
                      <div className={cx(s.m, s.a)}>
                        <span className={s.ty}>
                          <i />
                          <i />
                          <i />
                        </span>
                      </div>
                    </div>
                    <div className={s.pan}>
                      {[
                        ["Store agent", "watching stock"],
                        ["Marketing agent", "writing posts"],
                        ["Support agent", "3 chats"],
                        ["Shipping agent", "idle"],
                      ].map(([name, state]) => (
                        <div key={name} className={s.ag}>
                          <i />
                          {name}
                          <span>{state}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div className={s.mq}>
            <p>Works with your stack</p>
            <div className={s.tr}>
              {[...STACK, ...STACK].map((name, i) => (
                <span key={i} aria-hidden={i >= STACK.length}>
                  {name}
                </span>
              ))}
            </div>
          </div>
        </div>

        <section id="features">
          <div className={cx(s.hd, s.reveal)} data-reveal>
            <span className={s.eb}>The platform</span>
            <h2>
              One command center. <span className={s.g}>Every department.</span>
            </h2>
            <p>Specialist agents handle the busywork. You keep the final say on anything that costs money.</p>
          </div>
          <div className={s.bento}>
            <div className={cx(s.card, s.hot, s.s4, s.reveal)} data-reveal>
              <div className={s.ico}>💬</div>
              <h3>Command Chat</h3>
              <p>
                Say &quot;Create 7 organic posts and schedule them&quot; or &quot;What is low on stock?&quot; The Orchestrator plans, assigns
                agents and reports back.
              </p>
              <div className={s.tags}>
                <span>Plain language</span>
                <span>⌘K palette</span>
                <span>Approvals</span>
                <span>Bangla ready</span>
              </div>
            </div>
            {[
              ["🛍", "E-Commerce", "Inventory, orders and shipping watched around the clock."],
              ["📣", "Marketing", "Posts, ads and campaigns written, scheduled and optimized."],
              ["🎧", "Customer Service", "Instant on-brand replies. Escalates to you only when needed."],
              ["📚", "Knowledge Base", "Teach it once. Every agent answers with your facts."],
            ].map(([ico, title, text]) => (
              <div key={title} className={cx(s.card, s.s2, s.reveal)} data-reveal>
                <div className={s.ico}>{ico}</div>
                <h3>{title}</h3>
                <p>{text}</p>
              </div>
            ))}
            <div className={cx(s.card, s.s3, s.reveal)} data-reveal>
              <div className={s.ico}>⚡</div>
              <h3>Visual Workflows</h3>
              <p>&quot;If this, then that&quot; automations without writing code.</p>
              <div className={s.flow}>
                <span className={s.nd}>Order placed</span>→<span className={cx(s.nd, s.on)}>AI checks stock</span>→
                <span className={s.nd}>Ship + notify</span>
              </div>
            </div>
            <div className={cx(s.card, s.s3, s.reveal)} data-reveal>
              <div className={s.ico}>📈</div>
              <h3>Live Analytics</h3>
              <p>See what the agents did and what it earned you.</p>
              <div className={s.bars}>
                {[35, 52, 44, 70, 62, 88, 100].map((h, i) => (
                  <i key={i} style={{ height: `${h}%` }} />
                ))}
              </div>
            </div>
          </div>
        </section>

        <section id="lab">
          <div className={cx(s.hd, s.reveal)} data-reveal>
            <span className={s.eb}>Live demo</span>
            <h2>
              Watch an agent <span className={s.g}>do the work.</span>
            </h2>
          </div>
          <AgentLog />
          <div className={cx(s.nums, s.reveal)} data-reveal>
            {NUMS.map((n) => (
              <div key={n.label}>
                <b data-n={n.n} data-s={n.suffix}>
                  0
                </b>
                <span>{n.label}</span>
              </div>
            ))}
          </div>
        </section>

        <section id="how">
          <div className={cx(s.hd, s.reveal)} data-reveal>
            <span className={s.eb}>How it works</span>
            <h2>
              From idea to done in <span className={s.g}>three steps.</span>
            </h2>
          </div>
          <div className={s.tl}>
            {[
              ["🔗", "Connect", "Link your store and channels. PilotSonic learns your catalog, tone and goals."],
              ["🧠", "Instruct", "Describe the outcome in plain words, or switch on a ready-made workflow."],
              ["🚀", "Relax", "Agents execute, you approve what matters, and Autopilot keeps going."],
            ].map(([ico, title, text]) => (
              <div key={title} className={cx(s.card, s.reveal)} data-reveal>
                <div className={s.ico}>{ico}</div>
                <h3>{title}</h3>
                <p>{text}</p>
              </div>
            ))}
          </div>
        </section>

        <section id="pricing">
          <div className={cx(s.hd, s.ctr, s.reveal)} data-reveal>
            <span className={s.eb}>Pricing</span>
            <h2>
              Simple plans that <span className={s.g}>scale with you.</span>
            </h2>
          </div>
          <div className={s.pr}>
            <div className={cx(s.card, s.reveal)} data-reveal>
              <h3>Starter</h3>
              <div className={s.pp}>
                $29<small> /mo</small>
              </div>
              <p>For solo owners getting started.</p>
              <ul>
                <li>1 store, 2 agents</li>
                <li>Command Chat</li>
                <li>500 AI actions</li>
              </ul>
              <Link className={cx(s.btn, s.ghost)} href={startHref}>
                {signedIn ? "Open dashboard" : "Start free"}
              </Link>
            </div>
            <div className={cx(s.card, s.hot, s.pop, s.reveal)} data-reveal>
              <span className={s.badge}>Most popular</span>
              <h3>Growth</h3>
              <div className={s.pp}>
                $79<small> /mo</small>
              </div>
              <p>For brands ready to automate.</p>
              <ul>
                <li>3 stores, all 6 agents</li>
                <li>Workflows + approvals</li>
                <li>10,000 AI actions</li>
              </ul>
              <Link className={s.btn} href={startHref}>
                {signedIn ? "Open dashboard" : "Start free"}
              </Link>
            </div>
            <div className={cx(s.card, s.reveal)} data-reveal>
              <h3>Scale</h3>
              <div className={s.pp}>Custom</div>
              <p>For teams and agencies.</p>
              <ul>
                <li>Unlimited stores</li>
                <li>Custom agents</li>
                <li>Priority support</li>
              </ul>
              <Link className={cx(s.btn, s.ghost)} href={startHref}>
                {signedIn ? "Open dashboard" : "Talk to us"}
              </Link>
            </div>
          </div>
        </section>

        <section id="faq">
          <div className={cx(s.hd, s.reveal)} data-reveal>
            <span className={s.eb}>FAQ</span>
            <h2>
              Good <span className={s.g}>questions.</span>
            </h2>
          </div>
          <div style={{ maxWidth: 780, marginTop: 40 }} className={s.reveal} data-reveal>
            <details open>
              <summary>Will the AI spend money without asking?</summary>
              <p>No. Anything that costs money waits for your approval unless you switch it to auto mode.</p>
            </details>
            <details>
              <summary>Can my team use separate workspaces?</summary>
              <p>Yes. Every user gets their own workspace and connects their own accounts.</p>
            </details>
            <details>
              <summary>Does it support Bangla?</summary>
              <p>Yes. Agents can reply to customers in Bangla and English.</p>
            </details>
            <details>
              <summary>How long does setup take?</summary>
              <p>Most stores connect and run their first workflow in about five minutes.</p>
            </details>
          </div>
          <div className={cx(s.cbox, s.reveal)} data-reveal>
            <h2>Ready to hand over the busywork?</h2>
            <p style={{ maxWidth: 480, margin: "0 auto 30px", opacity: 0.9 }}>Let AI run the routine so you can focus on growth.</p>
            <Link className={cx(s.btn, s.big)} href={startHref}>
              {signedIn ? "Open dashboard" : "Get started free"} →
            </Link>
          </div>
        </section>
      </main>
      <footer>
        <div className={cx(s.wrap, s.ft)}>
          <span>© 2026 PilotSonic. All rights reserved.</span>
          <span>Privacy · Terms · Contact</span>
        </div>
      </footer>
    </div>
  );
}
