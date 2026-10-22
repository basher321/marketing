"use client";

import { useState } from "react";

import BrandSettingsForm from "@/components/kb/brand-settings-form";
import FaqList from "@/components/kb/faq-list";
import { ProductsPricingTab, ShippingTab } from "@/components/kb/kb-tabs";
import Policies from "@/components/kb/policies";

const TABS = ["Brand Voice", "Products & Pricing", "Policies", "FAQs", "Shipping"] as const;
type Tab = (typeof TABS)[number];

// Knowledge Base (SPEC-FE-015; the other four tabs by SPEC-FE-033): everything
// the AI knows about the business. Brand Voice is unchanged; Products & Pricing
// and Shipping are read views of E-Commerce data plus the delivery policy;
// Policies and FAQs are fully editable, and the enabled ones ground AI replies.
export default function KbPage() {
  const [tab, setTab] = useState<Tab>("Brand Voice");
  return (
    <>
      <h1 className="page-title">{"Business Knowledge Base"}</h1>
      <p className="page-subtitle">{"Everything the AI needs to know to speak for your business."}</p>
      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <div
            key={t}
            role="tab"
            aria-selected={tab === t}
            tabIndex={0}
            className={tab === t ? "tab active" : "tab"}
            onClick={() => setTab(t)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") setTab(t);
            }}
          >
            {t}
          </div>
        ))}
      </div>
      {tab === "Brand Voice" && (
        // Mockup .grid-2 (2fr 1fr). The two cards load, fail and save
        // independently of each other.
        <div className="grid-2">
          <BrandSettingsForm />
          <FaqList />
        </div>
      )}
      {tab === "Products & Pricing" && <ProductsPricingTab />}
      {tab === "Policies" && <Policies />}
      {tab === "FAQs" && <FaqList full />}
      {tab === "Shipping" && <ShippingTab />}
    </>
  );
}
