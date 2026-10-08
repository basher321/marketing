"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import MediaPicker from "@/components/organic/media-picker";
import { Empty, StatusBadge, errorText } from "@/components/organic/shared";
import {
  connectAccount,
  createPost,
  deleteKey,
  deletePost,
  disconnectAccount,
  fetchAccountAnalytics,
  fetchAccounts,
  chooseFacebookPage,
  fetchBoards,
  fetchConstraints,
  fetchFacebookPages,
  fetchKey,
  fetchPosts,
  publishPost,
  retryPost,
  SAPI_CHANNEL,
  saveKey,
  sapiKeys,
  testKey,
} from "@/lib/api/socialapi";
import { sapiLabel, type KeyStatus, type PostMode, type SapiAccount, type SapiPost } from "@/lib/types/socialapi";

// SocialAPI.ai publishing (SPEC-FE-054 / SPEC-BE-083): the company's key, the
// accounts connected through SocialAPI, a composer and the posts list. Posts
// made here live in SocialAPI; the direct connections and the Organic
// calendar/history are untouched.

const when = (v: string | null) => (v ? new Date(v).toLocaleString() : "—");
const SAPI_BADGE: Record<string, string> = { active: "connected", reconnect_required: "expired", partial: "publishing" };
const badge = (s: string) => SAPI_BADGE[s] ?? s;

export function KeyCard() {
  const qc = useQueryClient();
  const key = useQuery({ queryKey: sapiKeys.key, queryFn: fetchKey });
  const [value, setValue] = useState("");
  // The outcome of the last Save / Test / Remove, always shown (success too).
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const refresh = () => void qc.invalidateQueries({ queryKey: sapiKeys.all });
  const outcome = (verb: string) => (r: KeyStatus) => {
    refresh();
    const count = r.account_count != null ? ` · ${r.account_count} account${r.account_count === 1 ? "" : "s"} found` : "";
    setNote(r.last_error ? { ok: false, text: `${verb}, but SocialAPI answered: ${r.last_error}` } : { ok: true, text: `${verb}: the key works${count}.` });
  };
  const failed = (e: unknown) => setNote({ ok: false, text: errorText(e) });
  const save = useMutation({ mutationFn: () => saveKey(value.trim()), onSuccess: (r) => { setValue(""); outcome("Saved and tested")(r); }, onError: failed });
  const test = useMutation({ mutationFn: testKey, onSuccess: outcome("Tested"), onError: failed });
  const remove = useMutation({ mutationFn: deleteKey, onSuccess: () => { refresh(); setNote({ ok: true, text: "Key removed." }); }, onError: failed });
  const k = key.data;
  const busy = save.isPending || test.isPending || remove.isPending;
  return (
    <section className="card mb-4" data-testid="sapi-key">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="font-semibold">SocialAPI key</span>
        {k && <StatusBadge status={k.status === "connected" ? "connected" : k.status === "error" ? "error" : "not_connected"} />}
        {k?.key_masked && <span className="text-xs text-muted">{k.key_masked}</span>}
        {k?.account_count != null && <span className="text-xs text-muted">· {k.account_count} accounts</span>}
        {k && (
          <a href={k.docs_url} target="_blank" rel="noreferrer" className="ml-auto text-xs text-accent underline">
            SocialAPI docs ↗
          </a>
        )}
      </div>
      <p className="m-0 mb-2 text-xs text-muted">
        Paste the API key from your SocialAPI.ai dashboard (it starts with <code>sapi_key_</code>). It is stored encrypted and never shown again.
        SocialAPI publishes organic posts and answers comments, DMs and reviews; it has no paid-ads features.
      </p>
      {k?.last_error && <p className="m-0 mb-2 text-xs text-danger">{k.last_error}</p>}
      {k?.last_ok_at && <p className="m-0 mb-2 text-xs text-muted">Last worked: {when(k.last_ok_at)}</p>}
      <form
        className="flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setNote(null);
          if (value.trim()) save.mutate();
          else setNote({ ok: false, text: k?.key_masked ? "Paste a new key to replace the saved one, or use Test to check the saved key." : "Paste your SocialAPI key first." });
        }}
      >
        <input
          type="password"
          autoComplete="off"
          className="min-w-[260px] flex-1"
          placeholder={k?.key_masked ? "Paste a new key to replace it" : "sapi_key_…"}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          aria-label="SocialAPI key"
        />
        <button type="submit" className="btn" disabled={busy}>
          {save.isPending ? "Saving & testing…" : "Save & test"}
        </button>
        {k?.key_masked && (
          <>
            <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => { setNote(null); test.mutate(); }}>
              {test.isPending ? "Testing…" : "Test"}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={busy}
              onClick={() => { setNote(null); if (window.confirm("Remove the SocialAPI key? Accounts stay connected in SocialAPI.")) remove.mutate(); }}
            >
              Remove
            </button>
          </>
        )}
      </form>
      {busy && <p className="m-0 mt-2 text-xs text-muted">Checking the key with SocialAPI…</p>}
      {note && !busy && (
        <p className={`m-0 mt-2 text-xs ${note.ok ? "text-success" : "text-danger"}`} role="status" data-testid="sapi-key-note">
          {note.text}
        </p>
      )}
    </section>
  );
}

function Avatar({ a }: { a: SapiAccount }) {
  return a.avatar_url ? (
    <img src={a.avatar_url} alt="" className="h-8 w-8 rounded-full object-cover" />
  ) : (
    <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent-soft text-xs font-semibold">{sapiLabel(a.platform).slice(0, 1)}</span>
  );
}

// A Facebook account is the sign-in (its name is the person's own); posts go to
// the Page chosen here. SocialAPI sets page_name once one Page is active.
function FacebookPagePicker({ a }: { a: SapiAccount }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(!a.page_name);
  const [pick, setPick] = useState("");
  const pages = useQuery({ queryKey: sapiKeys.facebookPages(a.id), queryFn: () => fetchFacebookPages(a.id), enabled: open && !!a.login_id });
  const choose = useMutation({
    mutationFn: () => chooseFacebookPage(a.id, pick),
    onSuccess: () => {
      setOpen(false);
      void qc.invalidateQueries({ queryKey: sapiKeys.all });
    },
  });
  if (!a.login_id) return null;
  if (!open)
    return (
      <button type="button" className="ml-10 text-left text-xs text-accent underline" onClick={() => setOpen(true)}>
        Change Page
      </button>
    );
  const items = pages.data?.items ?? [];
  return (
    <div className="ml-10 flex flex-wrap items-center gap-2 text-xs" data-testid="sapi-fb-pages">
      {!a.page_name && <span className="text-warn">No Facebook Page chosen yet: posts need a Page.</span>}
      <select value={pick} onChange={(e) => setPick(e.target.value)} aria-label="Facebook Page" className="text-xs">
        <option value="">{pages.isPending ? "Loading Pages…" : items.length ? "Choose a Page" : "No Pages found for this login"}</option>
        {items.map((p) => (
          <option key={p.id} value={p.id} disabled={!p.assignable}>
            {p.name}
            {p.assigned_account_id ? " (connected)" : ""}
            {!p.assignable ? " (can't be used with this login)" : ""}
          </option>
        ))}
      </select>
      <button type="button" className="btn btn-sm" disabled={!pick || choose.isPending} onClick={() => choose.mutate()}>
        {choose.isPending ? "Saving…" : "Use this Page"}
      </button>
      {a.page_name && (
        <button type="button" className="text-muted underline" onClick={() => setOpen(false)}>
          Cancel
        </button>
      )}
      {(pages.error ?? choose.error) && <span className="w-full text-danger">{errorText(pages.error ?? choose.error)}</span>}
    </div>
  );
}

export function AccountsCard() {
  const qc = useQueryClient();
  const accounts = useQuery({ queryKey: sapiKeys.accounts, queryFn: fetchAccounts });
  const [platform, setPlatform] = useState("instagram");
  // The sign-in tab (SocialAPI -> the platform -> /marketing/organic/socialapi/callback)
  // says when it finished, so this list refreshes without a reload.
  useEffect(() => {
    if (typeof BroadcastChannel === "undefined") return;
    const ch = new BroadcastChannel(SAPI_CHANNEL);
    ch.onmessage = () => void qc.invalidateQueries({ queryKey: sapiKeys.all });
    return () => ch.close();
  }, [qc]);
  const connect = useMutation({
    mutationFn: (_tab: Window | null) => connectAccount(platform),
    // OAuth: SocialAPI's sign-in opens in a new tab, never this one.
    onSuccess: (r, tab) => {
      if (!r.auth_url) {
        tab?.close();
        return void qc.invalidateQueries({ queryKey: sapiKeys.accounts });
      }
      if (tab && !tab.closed) tab.location.href = r.auth_url;
      else window.open(r.auth_url, "_blank", "noopener");
    },
    onError: (_e, tab) => tab?.close(),
  });
  const disconnect = useMutation({ mutationFn: disconnectAccount, onSuccess: () => void qc.invalidateQueries({ queryKey: sapiKeys.accounts }) });
  const data = accounts.data;
  return (
    <section className="card" data-testid="sapi-accounts">
      <div className="mb-2 font-semibold">Accounts via SocialAPI</div>
      {accounts.isError && <p className="m-0 mb-2 text-xs text-danger">{errorText(accounts.error)}</p>}
      {data && (
        <div className="mb-3 flex flex-wrap gap-2">
          <select value={platform} onChange={(e) => setPlatform(e.target.value)} aria-label="Platform to connect">
            {data.connectable.map((p) => (
              <option key={p.platform} value={p.platform}>
                {p.label}
              </option>
            ))}
          </select>
          {/* The tab is opened in the click itself (pop-up blockers allow it), then pointed at the sign-in. */}
          <button type="button" className="btn btn-sm" disabled={connect.isPending} onClick={() => connect.mutate(window.open("about:blank", "_blank"))}>
            {connect.isPending ? "Opening…" : "Connect ↗"}
          </button>
        </div>
      )}
      {connect.isError && <p className="m-0 mb-2 text-xs text-danger">{errorText(connect.error)}</p>}
      {disconnect.isError && <p className="m-0 mb-2 text-xs text-danger">{errorText(disconnect.error)}</p>}
      {!data ? (
        <Empty>Loading…</Empty>
      ) : data.items.length === 0 ? (
        <Empty>No accounts yet. Connect one above.</Empty>
      ) : (
        <ul className="m-0 grid list-none gap-2 p-0">
          {data.items.map((a) => (
            <li key={a.id} className="rounded-md border border-border p-2">
              <div className="flex items-center gap-2">
              <Avatar a={a} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px] font-medium">{a.page_name ?? a.name ?? a.username ?? a.id}</span>
                <span className="block truncate text-xs text-muted">
                  {sapiLabel(a.platform)}
                  {a.page_name && a.name && a.page_name !== a.name ? ` · signed in as ${a.name}` : ""}
                  {a.username ? ` · @${a.username}` : ""}
                  {a.reconnect_reason ? ` · ${a.reconnect_reason}` : ""}
                </span>
              </span>
              <StatusBadge status={badge(a.status)} />
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={disconnect.isPending}
                onClick={() => window.confirm(`Disconnect ${a.name ?? sapiLabel(a.platform)} from SocialAPI?`) && disconnect.mutate(a.id)}
              >
                Disconnect
              </button>
              </div>
              {a.platform === "facebook" && <FacebookPagePicker a={a} />}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function BoardSelect({ accountId, value, onChange }: { accountId: string; value: string; onChange: (v: string) => void }) {
  const boards = useQuery({ queryKey: sapiKeys.boards(accountId), queryFn: () => fetchBoards(accountId) });
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} aria-label="Pinterest board" className="ml-6 mt-1 text-xs">
      <option value="">{boards.isPending ? "Loading boards…" : "Choose a board"}</option>
      {(boards.data?.items ?? []).map((b) => (
        <option key={b.board_id} value={b.board_id}>
          {b.name}
        </option>
      ))}
    </select>
  );
}

export function Composer() {
  const qc = useQueryClient();
  const accounts = useQuery({ queryKey: sapiKeys.accounts, queryFn: fetchAccounts });
  const limits = useQuery({ queryKey: sapiKeys.constraints, queryFn: fetchConstraints, staleTime: 3_600_000 });
  const [text, setText] = useState("");
  const [title, setTitle] = useState("");
  const [firstComment, setFirstComment] = useState("");
  const [media, setMedia] = useState<string[]>([]);
  const [chosen, setChosen] = useState<Record<string, string>>({}); // account id -> board id ("" = none)
  const [mode, setMode] = useState<PostMode>("now");
  const [at, setAt] = useState("");
  const active = (accounts.data?.items ?? []).filter((a) => a.status === "active");
  const picked = active.filter((a) => a.id in chosen);
  const maxLen = Math.min(
    ...picked.map((a) => limits.data?.items.find((c) => c.platform === a.platform)?.text_max_length ?? Infinity),
  );
  const create = useMutation({
    mutationFn: () =>
      createPost({
        text,
        title: title.trim() || null,
        targets: picked.map((a) => ({ account_id: a.id, board_id: chosen[a.id] || null })),
        media_ids: media,
        first_comment: firstComment.trim() || null,
        mode,
        // datetime-local is the browser's wall-clock time; sent with its offset.
        scheduled_at: mode === "schedule" && at ? new Date(at).toISOString() : null,
      }),
    onSuccess: () => {
      setText("");
      setTitle("");
      setFirstComment("");
      setMedia([]);
      void qc.invalidateQueries({ queryKey: ["socialapi", "posts"] });
    },
  });
  const needsBoard = picked.some((a) => a.platform === "pinterest" && !chosen[a.id]);
  return (
    <section className="card" data-testid="sapi-composer">
      <div className="mb-2 font-semibold">New post</div>
      <div className="form-row">
        <label htmlFor="sapi_text">Text</label>
        <textarea id="sapi_text" rows={5} value={text} onChange={(e) => setText(e.target.value)} placeholder="Write your post…" />
        {Number.isFinite(maxLen) && (
          <p className={`m-0 text-xs ${text.length > maxLen ? "text-danger" : "text-muted"}`}>
            {text.length.toLocaleString()} / {maxLen.toLocaleString()} (the strictest chosen platform)
          </p>
        )}
      </div>
      <div className="form-grid-2">
        <div className="form-row">
          <label htmlFor="sapi_title">Title (LinkedIn, YouTube, Pinterest, Google)</label>
          <input id="sapi_title" value={title} onChange={(e) => setTitle(e.target.value)} />
        </div>
        <div className="form-row">
          <label htmlFor="sapi_fc">First comment (Instagram, Facebook, YouTube)</label>
          <input id="sapi_fc" value={firstComment} onChange={(e) => setFirstComment(e.target.value)} />
        </div>
      </div>
      <div className="form-row">
        <label>Image or video</label>
        <MediaPicker value={media} onChange={(ids) => setMedia(ids)} />
      </div>
      <div className="form-row">
        <label>Post to</label>
        {active.length === 0 ? (
          <p className="m-0 text-xs text-muted">Connect an account first.</p>
        ) : (
          <div className="grid gap-1">
            {active.map((a) => (
              <div key={a.id}>
                <label className="flex items-center gap-2 text-[13px]">
                  <input
                    type="checkbox"
                    checked={a.id in chosen}
                    onChange={(e) =>
                      setChosen((c) => {
                        const next = { ...c };
                        if (e.target.checked) next[a.id] = "";
                        else delete next[a.id];
                        return next;
                      })
                    }
                  />
                  {sapiLabel(a.platform)} · {a.page_name ?? a.name ?? a.username ?? a.id}
                </label>
                {a.platform === "pinterest" && a.id in chosen && (
                  <BoardSelect accountId={a.id} value={chosen[a.id]} onChange={(v) => setChosen((c) => ({ ...c, [a.id]: v }))} />
                )}
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="form-row">
        <label htmlFor="sapi_mode">When</label>
        <div className="flex flex-wrap gap-2">
          <select id="sapi_mode" value={mode} onChange={(e) => setMode(e.target.value as PostMode)}>
            <option value="now">Publish now</option>
            <option value="schedule">Schedule</option>
            <option value="draft">Save as draft in SocialAPI</option>
          </select>
          {mode === "schedule" && (
            <input type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} aria-label="Publish at (your browser's time)" />
          )}
        </div>
        {mode === "schedule" && <p className="m-0 text-xs text-muted">In your browser&apos;s timezone; SocialAPI publishes it at that moment.</p>}
      </div>
      <button
        type="button"
        className="btn"
        disabled={!text.trim() || picked.length === 0 || needsBoard || (mode === "schedule" && !at) || create.isPending}
        onClick={() => create.mutate()}
      >
        {create.isPending ? "Sending…" : mode === "now" ? "Publish" : mode === "schedule" ? "Schedule" : "Save draft"}
      </button>
      {needsBoard && <p className="m-0 mt-2 text-xs text-warn">Choose a board for each Pinterest account.</p>}
      {create.isError && <p className="m-0 mt-2 text-xs text-danger" role="alert">{errorText(create.error)}</p>}
      {create.data && (
        <p className="m-0 mt-2 text-xs text-success">
          Post {create.data.status}
          {create.data.targets.some((t) => t.error) ? " — some accounts failed, see below." : "."}
        </p>
      )}
    </section>
  );
}

function PostRow({ p }: { p: SapiPost }) {
  const qc = useQueryClient();
  const done = () => void qc.invalidateQueries({ queryKey: ["socialapi", "posts"] });
  const publish = useMutation({ mutationFn: () => publishPost(p.id), onSuccess: done });
  const retry = useMutation({ mutationFn: () => retryPost(p.id), onSuccess: done });
  const remove = useMutation({ mutationFn: () => deletePost(p.id), onSuccess: done });
  const err = publish.error ?? retry.error ?? remove.error;
  return (
    <tr>
      <td className="max-w-[280px] text-xs">
        <div className="truncate" title={p.text ?? ""}>
          {p.title ? <strong>{p.title} · </strong> : null}
          {p.text}
        </div>
        <div className="text-muted">
          {p.published_at ? `Published ${when(p.published_at)}` : p.scheduled_at ? `Scheduled ${when(p.scheduled_at)}` : `Created ${when(p.created_at)}`}
          {p.media_count ? ` · ${p.media_count} media` : ""}
        </div>
        {err && <div className="text-danger">{errorText(err)}</div>}
      </td>
      <td>
        <StatusBadge status={badge(p.status)} />
      </td>
      <td className="text-xs">
        {p.targets.map((t) => (
          <div key={t.account_id} className="mb-1">
            {sapiLabel(t.platform)}{" "}
            {t.permalink ? (
              <a href={t.permalink} target="_blank" rel="noreferrer" className="text-accent underline">
                Open ↗
              </a>
            ) : (
              <span className="text-muted">{t.status ?? ""}</span>
            )}
            {t.metrics && (
              <span className="text-muted">
                {" "}
                · ♥ {t.metrics.likes ?? "—"} · 💬 {t.metrics.comments ?? "—"} · ↻ {t.metrics.shares ?? "—"}
              </span>
            )}
            {t.error && <div className="text-danger">{t.error}</div>}
          </div>
        ))}
      </td>
      <td className="whitespace-nowrap text-right">
        {(p.status === "draft" || p.status === "scheduled") && (
          <button type="button" className="btn btn-secondary btn-sm mr-1" disabled={publish.isPending} onClick={() => publish.mutate()}>
            Publish now
          </button>
        )}
        {(p.status === "failed" || p.status === "partial") && (
          <button type="button" className="btn btn-secondary btn-sm mr-1" disabled={retry.isPending} onClick={() => retry.mutate()}>
            Retry
          </button>
        )}
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={remove.isPending}
          onClick={() =>
            window.confirm(p.status === "published" || p.status === "partial" ? "Delete this post from the platforms that allow it?" : "Delete this post?") &&
            remove.mutate()
          }
        >
          {p.status === "scheduled" ? "Cancel" : "Delete"}
        </button>
      </td>
    </tr>
  );
}

const RANGES = ["7d", "30d", "90d"] as const;

/** Per-account daily history from SocialAPI: latest value for gauges (followers), total for counters. */
export function AnalyticsCard() {
  const accounts = useQuery({ queryKey: sapiKeys.accounts, queryFn: fetchAccounts });
  const [picked, setPicked] = useState("");
  const [range, setRange] = useState<(typeof RANGES)[number]>("30d");
  const accountId = picked || accounts.data?.items[0]?.id || "";
  const stats = useQuery({
    queryKey: sapiKeys.analytics(accountId, range),
    queryFn: () => fetchAccountAnalytics(accountId, range),
    enabled: !!accountId,
  });
  if (!accounts.data?.items.length) return null;
  return (
    <section className="card mt-4" data-testid="sapi-analytics">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="font-semibold">Account analytics</span>
        <select className="ml-auto" value={accountId} onChange={(e) => setPicked(e.target.value)} aria-label="Account">
          {accounts.data.items.map((a) => (
            <option key={a.id} value={a.id}>
              {sapiLabel(a.platform)} · {a.page_name ?? a.name ?? a.username ?? a.id}
            </option>
          ))}
        </select>
        <select value={range} onChange={(e) => setRange(e.target.value as (typeof RANGES)[number])} aria-label="Range">
          {RANGES.map((r) => (
            <option key={r} value={r}>
              Last {r.replace("d", " days")}
            </option>
          ))}
        </select>
      </div>
      {stats.isError ? (
        <p className="m-0 text-xs text-danger">{errorText(stats.error)}</p>
      ) : !stats.data ? (
        <Empty>Loading…</Empty>
      ) : stats.data.series.length === 0 ? (
        <Empty>SocialAPI has no analytics for this account yet.</Empty>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {stats.data.series.map((s) => {
            const values = s.points.map((p) => p.value).filter((v): v is number => v != null);
            const shown = values.length === 0 ? null : s.kind === "gauge" ? values[values.length - 1] : values.reduce((x, y) => x + y, 0);
            return (
              <div key={s.metric} className="rounded-md border border-border p-3">
                <div className="text-xs text-muted">{s.metric.replace(/_/g, " ")}</div>
                <div className="text-[20px] font-bold">{shown == null ? "—" : shown.toLocaleString()}</div>
                <div className="text-[11px] text-muted">{s.kind === "gauge" ? "latest" : `total, ${stats.data.start} → ${stats.data.end}`}</div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

const STATUSES = ["", "scheduled", "published", "partial", "failed", "draft"];

export function PostsCard() {
  const [status, setStatus] = useState("");
  const posts = useQuery({ queryKey: sapiKeys.posts(status), queryFn: () => fetchPosts(status), refetchInterval: 30_000 });
  return (
    <section className="card mt-4" style={{ padding: 0 }} data-testid="sapi-posts">
      <div className="flex flex-wrap items-center justify-between gap-2 p-4">
        <span className="font-semibold">Posts via SocialAPI</span>
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s ? s : "All statuses"}
            </option>
          ))}
        </select>
      </div>
      {posts.isError ? (
        <p className="m-0 p-4 text-xs text-danger">{errorText(posts.error)}</p>
      ) : !posts.data ? (
        <Empty>Loading…</Empty>
      ) : posts.data.items.length === 0 ? (
        <Empty>No posts yet.</Empty>
      ) : (
        <table>
          <tbody>
            {posts.data.items.map((p) => (
              <PostRow key={p.id} p={p} />
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
