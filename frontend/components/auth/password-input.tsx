"use client";

import { useState, type InputHTMLAttributes } from "react";

// Password field with a show/hide "eye" toggle (SPEC-FE-025). The toggle is a real
// <button type="button"> (never submits the form) with an accessible name and
// aria-pressed, switching the input between type="password" and type="text".
// Padding/width are inline so they beat the mockup's `.form-row input` rule.
export default function PasswordInput(props: Omit<InputHTMLAttributes<HTMLInputElement>, "type">) {
  const [visible, setVisible] = useState(false);
  const label = visible ? "Hide password" : "Show password";
  return (
    <div className="relative">
      <input {...props} type={visible ? "text" : "password"} style={{ width: "100%", paddingRight: 40 }} />
      <button
        type="button"
        aria-label={label}
        aria-pressed={visible}
        title={label}
        onClick={() => setVisible((v) => !v)}
        className="absolute inset-y-0 right-0 flex w-10 cursor-pointer items-center justify-center border-none bg-transparent text-muted hover:text-text"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
          <circle cx="12" cy="12" r="3" />
          {visible && <line x1="3" y1="3" x2="21" y2="21" />}
        </svg>
      </button>
    </div>
  );
}
