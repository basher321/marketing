/** Order confirmation SMS settings (SPEC-FE-073), mirroring app/schemas/sms.py (SPEC-BE-108). */
export type SmsStatus = "not_configured" | "no_number" | "blocked" | "ready";

export interface SmsSettings {
  status: SmsStatus;
  reason: string | null;
  number: string | null;
  auto_confirm: boolean;
  language: "en" | "bn" | "auto";
  template: string | null;
  default_template: string;
  preview: string;
  segments: number;
}

export interface SmsSettingsSave {
  auto_confirm?: boolean;
  language?: "en" | "bn" | "auto";
  /** "" = back to the default text. */
  template?: string;
}

export interface SmsNumber {
  number: string | null;
  name: string | null;
  sms: boolean;
  company_id: string | null;
  company_name: string | null;
}
