"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { isCustomName, useAppBrandingStandalone } from "@/components/branding/app-branding";

// Auth shell in the PilotSonic design's sign-in "gate": a dark aurora page with
// the PilotSonic brand and pitch on the left and a glass card on the right.
// Used by /login, /signup, /forgot-password and /reset-password; their forms,
// fields (the backend's real email + password sign-in) and logic are
// unchanged, so the `.neu-*` class names they use are restyled here. The
// design's demo Google button is not shown: the backend has no Google sign-in.
// `circle` is kept for the pages' existing calls; the gate has one card shape.
export function AuthShell({
  children,
  below,
}: {
  children: ReactNode;
  below?: ReactNode;
  circle?: boolean;
}) {
  // SPEC-FE-077: the Super admin's app name and logo, else the built-in PilotSonic brand.
  const app = useAppBrandingStandalone();
  return (
    <main className="gate">
      <Link href="/" className="g-x" aria-label="Back to the PilotSonic website" title="Back to the website">
        ✕
      </Link>
      <div className="g-bg" aria-hidden="true">
        <div className="g-blob b1" />
        <div className="g-blob b2" />
        <div className="g-blob b3" />
        <div className="g-grid" />
      </div>
      <div className="g-wrap">
        <section>
          <Link href="/" className="g-brand rise" style={{ ["--d" as string]: 0 }} aria-label={app?.app_name ?? "PilotSonic"}>
            {app?.logo_dark_url || app?.logo_url ? (
              <img src={app.logo_dark_url ?? app.logo_url ?? ""} alt={`${app.app_name} logo`} style={{ height: 82, width: "auto" }} />
            ) : (
              <span className="pl-m" role="img" aria-label="PilotSonic logo" />
            )}
            {isCustomName(app) ? (
              <span className="text-[34px] font-bold text-white">{app.app_name}</span>
            ) : (
              <span className="pl-w" role="img" aria-label="PilotSonic" />
            )}
          </Link>
          <div className="g-tag rise" style={{ ["--d" as string]: 1 }}>
            <span>AI AGENTS</span>
            <i />
            <span>AUTOMATE</span>
            <i />
            <span>SCALE</span>
          </div>
          <h1 className="g-h1 rise" style={{ ["--d" as string]: 1 }}>
            Your whole business,
            <br />
            <span className="g-grad">run by AI agents.</span>
          </h1>
          <p className="g-p rise" style={{ ["--d" as string]: 2 }}>
            Store, ads, content, support and shipping. Tell the Orchestrator what you want in plain words. Agents do the work and
            wait for your OK before spending money.
          </p>
          <ul className="g-feats">
            <li className="rise" style={{ ["--d" as string]: 3 }}>
              <span className="fi" style={{ ["--c" as string]: "#22d3ee" }}>
                <svg className="ic" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z" />
                  <path d="M9 12h.01M12.5 12h.01M16 12h.01" />
                </svg>
              </span>
              Command Chat that talks to every agent
            </li>
            <li className="rise" style={{ ["--d" as string]: 4 }}>
              <span className="fi" style={{ ["--c" as string]: "#a78bfa" }}>
                <svg className="ic" viewBox="0 0 24 24" aria-hidden="true">
                  <circle cx="6" cy="6" r="2.5" />
                  <circle cx="18" cy="12" r="2.5" />
                  <circle cx="6" cy="18" r="2.5" />
                  <path d="M8.5 6H12a3 3 0 0 1 3 3v.5M8.5 18H12a3 3 0 0 0 3-3v-.5" />
                </svg>
              </span>
              Autopilot workflows that never sleep
            </li>
            <li className="rise" style={{ ["--d" as string]: 5 }}>
              <span className="fi" style={{ ["--c" as string]: "#bef264" }}>
                <svg className="ic" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M5 12.5l4.5 4.5L19 7.5" />
                </svg>
              </span>
              Approvals first, so nothing runs without you
            </li>
          </ul>
          <div className="g-chips rise" style={{ ["--d" as string]: 6 }}>
            <span className="g-chip" style={{ ["--c" as string]: "#22d3ee" }}>
              <i />
              Store <b>· Ads · Support</b>
            </span>
            <span className="g-chip" style={{ ["--c" as string]: "#bef264" }}>
              <i />
              Approvals <b>built in</b>
            </span>
            <span className="g-chip" style={{ ["--c" as string]: "#f472b6" }}>
              <i />
              Bangla <b>ready</b>
            </span>
          </div>
        </section>

        <section className="g-card rise" style={{ ["--d" as string]: 3 }}>
          {children}
          {below && <div className="neu-below">{below}</div>}
          <p className="g-note">By continuing you agree to the Terms and Privacy Policy.</p>
        </section>
      </div>
      {/* Written via dangerouslySetInnerHTML so React's hydration never
          text-diffs the <style> children. */}
      <style dangerouslySetInnerHTML={{ __html: GATE_CSS }} />
    </main>
  );
}

/** A labelled field; the input itself is the child (plain input or PasswordInput). */
export function NeuField({ label, htmlFor, children }: { label: string; htmlFor: string; children: ReactNode }) {
  return (
    <div className="neu-field">
      <label className="neu-label" htmlFor={htmlFor}>
        {label}
      </label>
      {children}
    </div>
  );
}

/** The design's "welcome" moment, shown before navigating on. */
export function NeuSuccess({ title = "Success!", subtitle }: { title?: string; subtitle: string }) {
  return (
    <div className="neu-success" role="status">
      <div className="g-ava">
        <svg viewBox="0 0 24 24" width="38" height="38" fill="none" stroke="#06101f" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" className="neu-check-svg" aria-hidden="true">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      </div>
      <div>
        <h3>{title}</h3>
        <p>{subtitle}</p>
      </div>
      <ul className="g-steps" aria-hidden="true">
        <li className="ok">
          <i />
          Signed in securely
        </li>
        <li className="on">
          <i />
          Loading your workspace
        </li>
      </ul>
    </div>
  );
}

// From the PilotSonic design's AUTH GATE block, adapted to a page (not an
// overlay) and to the real forms' `.neu-*` classes. Always dark, as designed.
const GATE_CSS = `
.gate { --g-violet:#8b5cf6; --g-cyan:#22d3ee; --g-lime:#bef264; --g-pink:#f472b6;
  position: relative; min-height: 100dvh; overflow-x: hidden; background: #060913; color: #f8fafc; font-family: var(--font); color-scheme: dark; }
.g-x { position: fixed; top: calc(env(safe-area-inset-top,0px) + 16px); right: 18px; z-index: 5; width: 42px; height: 42px; border-radius: 14px; display: grid; place-items: center; border: 1px solid rgba(255,255,255,.14); background: rgba(255,255,255,.07); color: #fff; font-size: 16px; text-decoration: none; backdrop-filter: blur(12px); transition: transform .35s var(--ease), background .25s; }
.g-x:hover { transform: rotate(90deg); background: rgba(255,255,255,.14); }
.g-bg { position: fixed; inset: 0; overflow: hidden; pointer-events: none; }
.g-blob { position: absolute; border-radius: 50%; filter: blur(80px); opacity: .55; will-change: transform; }
.g-blob.b1 { width: 560px; height: 560px; left: -140px; top: -120px; background: radial-gradient(circle, var(--g-violet), transparent 68%); animation: gDrift1 16s ease-in-out infinite alternate; }
.g-blob.b2 { width: 620px; height: 620px; right: -180px; top: 8%; background: radial-gradient(circle, var(--g-cyan), transparent 68%); opacity: .4; animation: gDrift2 19s ease-in-out infinite alternate; }
.g-blob.b3 { width: 520px; height: 520px; left: 30%; bottom: -220px; background: radial-gradient(circle, var(--g-pink), transparent 68%); opacity: .32; animation: gDrift3 22s ease-in-out infinite alternate; }
@keyframes gDrift1 { to { transform: translate(160px, 120px) scale(1.15); } }
@keyframes gDrift2 { to { transform: translate(-200px, 90px) scale(.9); } }
@keyframes gDrift3 { to { transform: translate(140px, -120px) scale(1.2); } }
.g-grid { position: absolute; inset: 0; background-image: linear-gradient(rgba(255,255,255,.045) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.045) 1px, transparent 1px); background-size: 56px 56px; -webkit-mask-image: radial-gradient(ellipse at 50% 40%, #000 25%, transparent 75%); mask-image: radial-gradient(ellipse at 50% 40%, #000 25%, transparent 75%); animation: gGrid 24s linear infinite; }
@keyframes gGrid { to { background-position: 56px 56px; } }
.g-wrap { position: relative; z-index: 1; min-height: 100dvh; max-width: 1180px; margin: 0 auto; padding: 40px 28px; display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, 440px); gap: 64px; align-items: center; }
.gate .rise { animation: gRise 1s var(--ease) backwards; animation-delay: calc(var(--d, 0) * 90ms + 100ms); }
@keyframes gRise { from { opacity: 0; transform: translateY(26px); } }
.g-brand { display: flex; align-items: center; gap: 18px; margin-bottom: 16px; text-decoration: none; }
.g-brand .pl-m { width: 74px; height: 82px; filter: drop-shadow(0 0 16px rgba(56,150,255,.7)); animation: plPulse 4.5s ease-in-out infinite; }
.g-brand .pl-w { width: 236px; height: 34px; }
@keyframes plPulse { 50% { filter: drop-shadow(0 0 30px rgba(56,189,248,1)); transform: translateY(-5px); } }
.g-tag { display: flex; align-items: center; flex-wrap: wrap; gap: 14px; margin: 0 0 38px; font-size: 12px; font-weight: 600; letter-spacing: .34em; color: #cbd5e1; }
.g-tag i { width: 5px; height: 5px; border-radius: 50%; background: var(--g-cyan); box-shadow: 0 0 10px var(--g-cyan); }
.g-h1 { margin: 0 0 18px; font-size: clamp(36px, 5.2vw, 62px); line-height: 1.04; font-weight: 800; letter-spacing: -.035em; }
.g-grad { background: linear-gradient(100deg, var(--g-cyan), var(--g-violet) 40%, var(--g-pink) 70%, var(--g-lime)); background-size: 220% 100%; -webkit-background-clip: text; background-clip: text; color: transparent; animation: gShift 7s ease-in-out infinite alternate; }
@keyframes gShift { to { background-position: 100% 0; } }
.g-p { margin: 0 0 30px; max-width: 52ch; font-size: 16.5px; line-height: 1.6; color: #a5b0c8; }
.g-feats { list-style: none; margin: 0 0 34px; padding: 0; display: grid; gap: 14px; }
.g-feats li { display: flex; align-items: center; gap: 14px; font-size: 14.5px; font-weight: 600; color: #dbe3f5; }
.g-feats .fi { flex: none; width: 38px; height: 38px; border-radius: 12px; display: grid; place-items: center; color: var(--c); background: color-mix(in srgb, var(--c) 16%, transparent); border: 1px solid color-mix(in srgb, var(--c) 28%, transparent); }
.g-chips { display: flex; flex-wrap: wrap; gap: 12px; }
.g-chip { display: inline-flex; align-items: center; gap: 10px; padding: 10px 16px; border-radius: 16px; font-size: 12.5px; font-weight: 650; color: #e7ecf8; background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.1); backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px); animation: gFloat 5.5s ease-in-out infinite; }
.g-chip:nth-child(2) { animation-delay: -1.8s; }
.g-chip:nth-child(3) { animation-delay: -3.6s; }
.g-chip i { position: relative; width: 8px; height: 8px; border-radius: 50%; background: var(--c); }
.g-chip i::after { content: ""; position: absolute; inset: 0; border-radius: 50%; background: var(--c); animation: ps-ping 1.8s ease-out infinite; }
.g-chip b { color: var(--c); }
@keyframes gFloat { 50% { transform: translateY(-9px); } }

.g-card { position: relative; isolation: isolate; padding: 34px 30px 26px; border-radius: 30px; background: linear-gradient(160deg, rgba(255,255,255,.1), rgba(255,255,255,.04)); border: 1px solid rgba(255,255,255,.14); backdrop-filter: blur(26px) saturate(160%); -webkit-backdrop-filter: blur(26px) saturate(160%); box-shadow: 0 40px 90px -30px rgba(0,0,0,.7), inset 0 1px 0 rgba(255,255,255,.14); }
.g-card::before { content: ""; position: absolute; inset: -2px; border-radius: inherit; padding: 2px; z-index: -1; pointer-events: none; background: conic-gradient(from var(--ang, 0deg), transparent 0 60%, var(--g-cyan), var(--g-violet), var(--g-pink), transparent); -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0); -webkit-mask-composite: xor; mask-composite: exclude; opacity: .8; animation: gSpin 6s linear infinite; }
@property --ang { syntax: '<angle>'; initial-value: 0deg; inherits: false; }
@keyframes gSpin { to { --ang: 360deg; } }
.g-note { margin: 20px 0 0; font-size: 11.5px; line-height: 1.5; color: #7c88a3; }

.neu-title { margin: 0 0 6px; font-size: 26px; font-weight: 780; letter-spacing: -.02em; color: #f8fafc; }
.neu-sub { margin: 0 0 22px; font-size: 14px; color: #a5b0c8; line-height: 1.55; }
.neu-status { margin: 0 0 14px; font-size: 14px; color: #dbe3f5; line-height: 1.55; }
.neu-form { width: 100%; display: flex; flex-direction: column; gap: 14px; margin-top: 18px; }
.neu-title + .neu-form { margin-top: 22px; }
.neu-sub + .neu-form { margin-top: 0; }
.neu-row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.neu-field { display: block; }
.neu-label { display: block; margin: 0 0 6px; font-size: 12.5px; font-weight: 600; color: #cbd5e1; }
.gate .neu-input { width: 100%; height: 48px; padding: 0 14px; border-radius: 13px; border: 1px solid rgba(255,255,255,.14); background: rgba(255,255,255,.06); color: #fff; font: inherit; font-size: 14.5px; transition: border-color .25s, box-shadow .3s; }
.gate .neu-input::placeholder { color: #64708b; }
.gate .neu-input:focus { outline: 0; border-color: var(--g-cyan); box-shadow: 0 0 0 4px rgba(34,211,238,.16); }
.gate .neu-input:-webkit-autofill, .gate .neu-input:-webkit-autofill:focus { -webkit-text-fill-color: #fff; -webkit-box-shadow: inset 0 0 0 1000px #141a2d !important; caret-color: #fff; transition: background-color 5000s ease-in-out 0s; }
.gate select.neu-input option { background: #0b1020; color: #fff; }
.gate .neu-field button { color: #a5b0c8; }
.gate .neu-field button:hover { color: #fff; }
.neu-btn { margin-top: 6px; height: 52px; width: 100%; border: 0; border-radius: 15px; cursor: pointer; font: inherit; font-size: 15px; font-weight: 700; color: #06101f; background: linear-gradient(100deg, var(--g-cyan), var(--g-lime)); box-shadow: 0 18px 34px -16px var(--g-cyan); transition: transform .4s var(--ease), filter .25s, opacity .25s; }
.neu-btn:hover:not(:disabled) { transform: translateY(-2px); filter: brightness(1.06); }
.neu-btn:active:not(:disabled) { transform: scale(.97); }
.neu-btn:disabled { cursor: default; opacity: .55; }
.neu-btn:focus-visible, .g-x:focus-visible, .neu-link:focus-visible, .neu-small-link:focus-visible, .gate .neu-field button:focus-visible { outline: 2px solid var(--g-cyan); outline-offset: 3px; }
.neu-error { margin: 0; padding: 10px 12px; border-radius: 12px; font-size: 12.5px; line-height: 1.45; color: #fecaca; background: rgba(248,113,113,.1); border: 1px solid rgba(248,113,113,.3); animation: gShake .4s; }
@keyframes gShake { 25% { transform: translateX(-6px); } 75% { transform: translateX(6px); } }
.neu-hint { margin: -6px 0 0; font-size: 11.5px; color: #7c88a3; }
.neu-below { display: flex; align-items: center; justify-content: center; gap: 12px; margin-top: 22px; padding-top: 18px; border-top: 1px solid rgba(255,255,255,.1); color: #a5b0c8; font-size: 13px; flex-wrap: wrap; }
.neu-link { color: var(--g-cyan); font-weight: 700; text-decoration: none; }
.neu-link:hover { color: #fff; }
.neu-small-link { align-self: flex-end; margin-top: -4px; font-size: 12.5px; color: #a5b0c8; text-decoration: none; }
.neu-small-link:hover { color: #fff; }

.neu-success { display: flex; flex-direction: column; align-items: center; gap: 22px; padding: 26px 0 8px; text-align: center; }
.neu-success h3 { margin: 0; font-size: 21px; font-weight: 760; }
.neu-success p { margin: 4px 0 0; font-size: 13px; color: #a5b0c8; }
.g-ava { width: 78px; height: 78px; border-radius: 50%; display: grid; place-items: center; background: linear-gradient(135deg, var(--g-cyan), var(--g-lime)); box-shadow: 0 0 0 4px #0b1020, 0 0 0 6px var(--g-cyan); animation: gPop .8s var(--spring) both; }
@keyframes gPop { from { transform: scale(.4); opacity: 0; } }
.neu-check-svg { stroke-dasharray: 30; stroke-dashoffset: 30; animation: gDraw .45s ease .25s forwards; }
@keyframes gDraw { to { stroke-dashoffset: 0; } }
.g-steps { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; text-align: left; font-size: 13px; color: #64708b; }
.g-steps li { display: flex; align-items: center; gap: 10px; }
.g-steps li i { width: 16px; height: 16px; border-radius: 50%; border: 2px solid #334155; }
.g-steps li.on { color: #fff; }
.g-steps li.on i { border-color: var(--g-cyan); border-top-color: transparent; animation: ps-spin .8s linear infinite; }
.g-steps li.ok { color: #dbe3f5; }
.g-steps li.ok i { background: var(--g-lime); border-color: var(--g-lime); }

@media (max-width: 920px) {
  .g-wrap { grid-template-columns: 1fr; gap: 34px; padding: 72px 18px 40px; }
  .g-brand { margin-bottom: 12px; }
  .g-brand .pl-m { width: 58px; height: 64px; }
  .g-brand .pl-w { width: 190px; height: 27px; }
  .g-tag { font-size: 10.5px; letter-spacing: .26em; margin-bottom: 22px; }
  .g-feats, .g-chips { display: none; }
  .g-p { margin-bottom: 4px; }
  .g-card { padding: 28px 20px 22px; }
}
@media (max-width: 520px) { .neu-row { grid-template-columns: 1fr; } }
@media (prefers-reduced-motion: reduce) {
  .gate *, .gate *::before, .gate *::after { animation-duration: .01ms !important; animation-iteration-count: 1 !important; transition-duration: .01ms !important; }
}
`;
