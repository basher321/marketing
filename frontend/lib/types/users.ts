/** My profile (SPEC-FE-077), mirroring MyProfile in app/schemas/user.py (SPEC-BE-113 FR2). */
export interface MyProfile {
  id: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  phone: string | null;
  /** data: URL or null. */
  avatar_url: string | null;
  role: string;
  company_name: string;
  super_admin: boolean;
}
