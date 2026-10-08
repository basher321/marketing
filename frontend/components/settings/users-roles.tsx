"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { createUser, deleteUser, fetchUsers, tenantKeys, updateUser } from "@/lib/api/tenant";
import { ApiError } from "@/lib/types/common";
import type { OrgUser, RoleType } from "@/lib/types/tenant";

/** A readable message: 403 in plain words; FastAPI 422 field errors joined; else the backend's text. */
export function apiErrorText(err: Error, forbidden: string): string {
  if (err instanceof ApiError) {
    if (err.status === 403) return forbidden;
    const detail = (err.body as { detail?: unknown } | undefined)?.detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d: { msg?: string }) => (d.msg ?? "").replace(/^Value error, /, ""))
        .filter(Boolean)
        .join(" ");
    }
  }
  return err.message;
}

// Live role_type values and what each can do (app RBAC: owner > admin >
// manager > agent > viewer; operator -> agent, analyst -> viewer).
export const ROLES: { value: RoleType; label: string; can: string }[] = [
  { value: "owner", label: "Owner", can: "Everything, including users, billing-level settings and data reset." },
  { value: "manager", label: "Manager (company admin)", can: "Runs the business: edits catalog, campaigns, workflows, KB, integrations; approves within limits." },
  { value: "operator", label: "Operator", can: "Day-to-day work: replies to customers and handles tasks; can't change settings." },
  { value: "analyst", label: "Analyst", can: "Read-only access to data and reports." },
  { value: "viewer", label: "Viewer", can: "Read-only access." },
];
const ROLE_LABEL = Object.fromEntries(ROLES.map((r) => [r.value, r.label.split(" (")[0]]));
const OWNER_ONLY = "Only the owner can manage users.";

// A temporary password that satisfies the backend policy (upper, lower, digit, symbol).
function tempPassword(): string {
  const pick = (s: string) => s[Math.floor(Math.random() * s.length)];
  const body = Array.from({ length: 8 }, () => pick("abcdefghjkmnpqrstuvwxyz23456789")).join("");
  return `${pick("ABCDEFGHJKLMNPQRSTUVWXYZ")}${body}${pick("23456789")}!`;
}

function when(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }) : "Never";
}

function AddUserForm({ onDone }: { onDone: () => void }) {
  const queryClient = useQueryClient();
  const [f, setF] = useState({ email: "", first_name: "", last_name: "", role: "manager" as RoleType, password: tempPassword() });
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((cur) => ({ ...cur, [k]: v }));
  const add = useMutation({
    mutationFn: () =>
      createUser({ email: f.email.trim(), password: f.password, first_name: f.first_name.trim() || null, last_name: f.last_name.trim() || null, role: f.role }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: tenantKeys.users });
      onDone();
    },
  });
  return (
    <form
      className="mb-4 rounded-md border border-border p-4"
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        add.mutate();
      }}
    >
      <div className="form-grid-2">
        <div className="form-row">
          <label htmlFor="nu_email">Email</label>
          <input id="nu_email" type="email" required value={f.email} onChange={(e) => set("email", e.target.value)} />
        </div>
        <div className="form-row">
          <label htmlFor="nu_role">Role</label>
          <select id="nu_role" value={f.role} onChange={(e) => set("role", e.target.value as RoleType)}>
            {ROLES.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
        </div>
        <div className="form-row">
          <label htmlFor="nu_first">First name</label>
          <input id="nu_first" maxLength={100} value={f.first_name} onChange={(e) => set("first_name", e.target.value)} />
        </div>
        <div className="form-row">
          <label htmlFor="nu_last">Last name</label>
          <input id="nu_last" maxLength={100} value={f.last_name} onChange={(e) => set("last_name", e.target.value)} />
        </div>
        <div className="form-row">
          <label htmlFor="nu_password">Temporary password</label>
          <div className="flex gap-2">
            <input id="nu_password" className="flex-1" required value={f.password} onChange={(e) => set("password", e.target.value)} />
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => set("password", tempPassword())}>
              Generate
            </button>
          </div>
          <span className="text-xs text-muted">Share it with the user; they can change it with “Forgot password”.</span>
        </div>
      </div>
      <div className="flex gap-2">
        <button type="submit" className="btn btn-sm" disabled={add.isPending}>
          {add.isPending ? "Adding…" : "Add user"}
        </button>
        <button type="button" className="btn btn-secondary btn-sm" disabled={add.isPending} onClick={onDone}>
          Cancel
        </button>
      </div>
      {add.isError && (
        <p className="mb-0 mt-3 text-xs text-danger" role="alert">
          {apiErrorText(add.error, OWNER_ONLY)}
        </p>
      )}
    </form>
  );
}

function UserRow({ user }: { user: OrgUser }) {
  const queryClient = useQueryClient();
  const refresh = () => void queryClient.invalidateQueries({ queryKey: tenantKeys.users });
  const update = useMutation({ mutationFn: (body: Parameters<typeof updateUser>[1]) => updateUser(user.id, body), onSuccess: refresh });
  const remove = useMutation({ mutationFn: () => deleteUser(user.id), onSuccess: refresh });
  const err = update.error ?? remove.error;
  const name = [user.first_name, user.last_name].filter(Boolean).join(" ") || "—";
  return (
    <tr>
      <td>
        {name}
        <div className="text-xs text-muted">{user.email}</div>
        {err && (
          <div className="text-xs text-danger" role="alert">
            {apiErrorText(err, OWNER_ONLY)}
          </div>
        )}
      </td>
      <td>
        <select
          aria-label={`Role of ${user.email}`}
          className="rounded-md border border-border bg-panel px-2 py-1 text-[13px] text-text"
          value={user.role}
          disabled={update.isPending}
          onChange={(e) => update.mutate({ role: e.target.value as RoleType })}
        >
          {ROLES.map((r) => (
            <option key={r.value} value={r.value}>
              {ROLE_LABEL[r.value]}
            </option>
          ))}
        </select>
      </td>
      <td>
        <span className={`badge ${user.status === "active" ? "badge-success" : "badge-neutral"}`}>{user.status}</span>
      </td>
      <td className="text-[13px]">{when(user.last_login_at)}</td>
      <td className="whitespace-nowrap text-right">
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={update.isPending}
          onClick={() => update.mutate({ status: user.status === "active" ? "disabled" : "active" })}
        >
          {user.status === "active" ? "Deactivate" : "Activate"}
        </button>{" "}
        <button
          type="button"
          className="btn btn-ghost btn-sm text-danger"
          disabled={remove.isPending}
          onClick={() => {
            if (window.confirm(`Delete ${user.email}? They will no longer be able to sign in.`)) remove.mutate();
          }}
        >
          Delete
        </button>
      </td>
    </tr>
  );
}

// Users & Roles tab (SPEC-FE-036) over the owner-only user API (SPEC-BE-037).
// A non-owner gets 403 on the list, so the tab explains that instead.
export default function UsersRoles() {
  const users = useQuery({ queryKey: tenantKeys.users, queryFn: fetchUsers, retry: false });
  const [adding, setAdding] = useState(false);
  const forbidden = users.error instanceof ApiError && users.error.status === 403;

  return (
    <div className="card">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="m-0">Users & roles</h3>
        {users.isSuccess && !adding && (
          <button type="button" className="btn btn-sm" onClick={() => setAdding(true)}>
            + Add user
          </button>
        )}
      </div>
      {adding && <AddUserForm onDone={() => setAdding(false)} />}
      {users.isPending ? (
        <p className="text-[13px] text-muted">Loading users…</p>
      ) : forbidden ? (
        <p className="text-[13px] text-muted">{OWNER_ONLY} Ask your workspace owner to add or change users.</p>
      ) : users.isError ? (
        <p className="text-[13px] text-danger" role="alert">
          Failed to load users: {users.error.message}
        </p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>User</th>
              <th>Role</th>
              <th>Status</th>
              <th>Last sign-in</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {users.data.map((u) => (
              <UserRow key={u.id} user={u} />
            ))}
          </tbody>
        </table>
      )}
      <h4 className="mb-2 mt-5 text-[13px]">What each role can do</h4>
      <ul className="m-0 list-none p-0 text-[13px]">
        {ROLES.map((r) => (
          <li key={r.value} className="mb-1">
            <b>{r.label}:</b> <span className="text-muted">{r.can}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
