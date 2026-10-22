import type { SmsNumber, SmsSettings, SmsSettingsSave } from "../types/sms";
import { apiFetch } from "./client";

export const smsKeys = {
  settings: ["sms", "settings"] as const,
  numbers: ["sms", "numbers"] as const,
};

/** GET /tenants/me/sms (SPEC-BE-108 FR2). */
export function fetchSmsSettings(): Promise<SmsSettings> {
  return apiFetch<SmsSettings>("/api/v1/tenants/me/sms");
}

/** PUT /tenants/me/sms (manager+). */
export function saveSmsSettings(body: SmsSettingsSave): Promise<SmsSettings> {
  return apiFetch<SmsSettings>("/api/v1/tenants/me/sms", { method: "PUT", body: body as Record<string, unknown> });
}

/** Super admin: GET /platform/sms/numbers (SPEC-BE-108 FR1). */
export function fetchSmsNumbers(): Promise<{ items: SmsNumber[] }> {
  return apiFetch<{ items: SmsNumber[] }>("/api/v1/platform/sms/numbers");
}

/** Super admin: PUT /platform/companies/{id}/sms-number ("" removes it). */
export function assignSmsNumber(companyId: string, number: string): Promise<{ company_id: string; number: string | null }> {
  return apiFetch(`/api/v1/platform/companies/${encodeURIComponent(companyId)}/sms-number`, {
    method: "PUT",
    body: { number },
  });
}
