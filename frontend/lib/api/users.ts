import type { MyProfile } from "../types/users";
import { apiFetch } from "./client";

export const userKeys = { me: ["users", "me"] as const };

/** GET /users/me (SPEC-BE-113 FR2): every role, the caller only. */
export function fetchMyProfile(): Promise<MyProfile> {
  return apiFetch<MyProfile>("/api/v1/users/me");
}

export function updateMyProfile(body: { first_name?: string; last_name?: string; phone?: string }): Promise<MyProfile> {
  return apiFetch<MyProfile>("/api/v1/users/me", { method: "PATCH", body });
}

export function uploadMyAvatar(file: File): Promise<MyProfile> {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<MyProfile>("/api/v1/users/me/avatar", { method: "PUT", body: form });
}

export function removeMyAvatar(): Promise<MyProfile> {
  return apiFetch<MyProfile>("/api/v1/users/me/avatar", { method: "DELETE" });
}
