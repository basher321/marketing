"use client";

import type { ReactNode } from "react";

// Shared neumorphic ("soft UI") auth shell (SPEC-FE-038), styles copied from
// D:\erp\frontend\src\app\login\page.tsx and scoped by the `.neu-*` prefix so
// the rest of the app's stylesheet is untouched. `circle` is the ERP login's
// round card (short forms); otherwise the same look on a rounded card, for
// forms too tall for a circle (sign-up, reset password).
export function AuthShell({
  children,
  below,
  circle = false,
}: {
  children: ReactNode;
  below?: ReactNode;
  circle?: boolean;
}) {
  return (
    <main className="neu-page">
      <div className={circle ? "neu-circle" : "neu-card"}>{children}</div>
      {below && <div className="neu-below">{below}</div>}
      {/* Written via dangerouslySetInnerHTML (as in the ERP page) so React's
          hydration never text-diffs the <style> children. */}
      <style dangerouslySetInnerHTML={{ __html: NEU_CSS }} />
    </main>
  );
}

/** Floating-label pill field; the input itself is the child (plain input or PasswordInput). */
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

/** Check-mark "Success!" animation shown before navigating on. */
export function NeuSuccess({ title = "Success!", subtitle }: { title?: string; subtitle: string }) {
  return (
    <div className="neu-success" role="status">
      <div className="neu-check-bubble">
        <svg viewBox="0 0 24 24" width="44" height="44" fill="none" stroke="#22c55e" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" className="neu-check-svg" aria-hidden="true">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      </div>
      <div className="neu-success-title">{title}</div>
      <div className="neu-success-sub">{subtitle}</div>
    </div>
  );
}

const NEU_CSS = `
  .neu-page {
    --neu-bg: #e5e5e5;
    --neu-light: #ffffff;
    --neu-dark: #babecc;
    --neu-darker: #a3a7b3;
    --neu-text: #4a4a4a;
    --neu-mute: #6b7280;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    background: var(--neu-bg);
    padding: 24px;
    gap: 22px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  }
  .neu-circle {
    width: min(480px, 92vmin);
    height: min(480px, 92vmin);
    border-radius: 50%;
    background: var(--neu-bg);
    box-shadow: -14px -14px 28px var(--neu-light), 14px 14px 28px var(--neu-dark);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: clamp(40px, 8vmin, 70px);
    animation: neu-rise 0.5s cubic-bezier(0.34, 1.2, 0.64, 1);
  }
  .neu-card {
    width: min(520px, 100%);
    border-radius: 36px;
    background: var(--neu-bg);
    box-shadow: -14px -14px 28px var(--neu-light), 14px 14px 28px var(--neu-dark);
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: clamp(28px, 6vmin, 48px);
    animation: neu-rise 0.5s cubic-bezier(0.34, 1.2, 0.64, 1);
  }
  @keyframes neu-rise {
    from { opacity: 0; transform: translateY(14px) scale(0.98); }
    to   { opacity: 1; transform: translateY(0)   scale(1); }
  }
  .neu-title {
    font-size: clamp(26px, 5vmin, 34px);
    font-weight: 700;
    color: var(--neu-text);
    margin: 0 0 18px 0;
    letter-spacing: 0.3px;
  }
  .neu-sub { color: var(--neu-mute); font-size: 13px; text-align: center; margin: -8px 0 16px 0; }
  .neu-form { width: 100%; display: flex; flex-direction: column; gap: 14px; }
  .neu-row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
  .neu-field { position: relative; display: block; }
  .neu-label {
    position: absolute;
    top: -8px;
    left: 20px;
    background: var(--neu-bg);
    padding: 0 8px;
    font-size: 10.5px;
    color: var(--neu-mute);
    font-weight: 500;
    letter-spacing: 0.4px;
    z-index: 2;
    border-radius: 4px;
    pointer-events: none;
  }
  .neu-page .neu-input {
    width: 100%;
    padding: 13px 20px;
    border: none;
    outline: none;
    background: var(--neu-bg);
    color: var(--neu-text);
    font-size: 14px;
    border-radius: 30px;
    box-shadow: inset -3px -3px 6px var(--neu-light), inset 3px 3px 6px var(--neu-dark);
    transition: box-shadow 0.2s ease;
    font-family: inherit;
  }
  .neu-input::placeholder { color: #a0a4ad; }
  .neu-page .neu-input:focus {
    box-shadow: inset -4px -4px 8px var(--neu-light), inset 4px 4px 8px var(--neu-darker);
  }
  .neu-btn {
    width: 100%;
    padding: 13px;
    border: none;
    background: var(--neu-bg);
    color: var(--neu-text);
    font-size: 15px;
    font-weight: 600;
    border-radius: 30px;
    cursor: pointer;
    box-shadow: -4px -4px 8px var(--neu-light), 4px 4px 8px var(--neu-dark);
    transition: box-shadow 0.15s ease, transform 0.15s ease;
    margin-top: 6px;
    font-family: inherit;
    letter-spacing: 0.5px;
  }
  .neu-btn:hover:not(:disabled) {
    box-shadow: -5px -5px 10px var(--neu-light), 5px 5px 10px var(--neu-dark);
    transform: translateY(-1px);
  }
  .neu-btn:active:not(:disabled) {
    box-shadow: inset -3px -3px 6px var(--neu-light), inset 3px 3px 6px var(--neu-dark);
    transform: translateY(0);
  }
  .neu-btn:disabled {
    cursor: default;
    box-shadow: inset -3px -3px 6px var(--neu-light), inset 3px 3px 6px var(--neu-dark);
    color: var(--neu-mute);
  }
  .neu-error { color: #dc2626; font-size: 12px; text-align: center; padding: 4px 0; margin: 0; }
  .neu-hint { color: var(--neu-mute); font-size: 11.5px; margin: -4px 0 0 20px; }
  .neu-status { color: var(--neu-text); font-size: 13.5px; text-align: center; margin: 0 0 8px 0; }
  .neu-below { color: var(--neu-mute); font-size: 13px; }
  .neu-link {
    color: var(--neu-text);
    font-weight: 600;
    text-decoration: none;
    border-bottom: 1px dashed var(--neu-dark);
  }
  .neu-link:hover { color: #111827; }
  .neu-small-link { font-size: 12px; color: var(--neu-mute); text-decoration: none; text-align: right; margin: -6px 12px 0 0; }
  .neu-small-link:hover { color: var(--neu-text); text-decoration: underline; }
  .neu-success { display: flex; flex-direction: column; align-items: center; gap: 10px; text-align: center; }
  .neu-check-bubble {
    width: clamp(80px, 18vmin, 100px);
    height: clamp(80px, 18vmin, 100px);
    border-radius: 50%;
    background: var(--neu-bg);
    box-shadow: -7px -7px 14px var(--neu-light), 7px 7px 14px var(--neu-dark);
    display: flex;
    align-items: center;
    justify-content: center;
    animation: neu-pop 0.55s cubic-bezier(0.34, 1.56, 0.64, 1);
  }
  @keyframes neu-pop {
    0%   { transform: scale(0.4); opacity: 0; }
    70%  { transform: scale(1.08); opacity: 1; }
    100% { transform: scale(1); opacity: 1; }
  }
  .neu-check-svg { stroke-dasharray: 30; stroke-dashoffset: 30; animation: neu-draw 0.4s ease 0.2s forwards; }
  @keyframes neu-draw { to { stroke-dashoffset: 0; } }
  .neu-success-title {
    font-size: 24px;
    font-weight: 700;
    color: var(--neu-text);
    margin-top: 10px;
    animation: neu-fade 0.3s ease 0.4s both;
  }
  .neu-success-sub { font-size: 13px; color: var(--neu-mute); animation: neu-fade 0.3s ease 0.55s both; }
  @keyframes neu-fade {
    from { opacity: 0; transform: translateY(4px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  .neu-input:-webkit-autofill,
  .neu-input:-webkit-autofill:focus {
    -webkit-text-fill-color: var(--neu-text);
    -webkit-box-shadow: inset -3px -3px 6px var(--neu-light), inset 3px 3px 6px var(--neu-dark),
      inset 0 0 0 1000px var(--neu-bg) !important;
    transition: background-color 5000s ease-in-out 0s;
  }
  @media (max-width: 520px) { .neu-row { grid-template-columns: 1fr; } }
`;
