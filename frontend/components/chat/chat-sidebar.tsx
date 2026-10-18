"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  addProjectFile,
  createProject,
  deleteChat,
  deleteProject,
  fetchChats,
  fetchProject,
  fetchProjects,
  orchestratorKeys,
  removeProjectFile,
  updateChat,
  updateProject,
  uploadChatFile,
} from "@/lib/api/orchestrator";
import type { ChatRead, ProjectRead } from "@/lib/types/orchestrator";

import { formatBytes } from "./attachments";

// Chat history and Projects (SPEC-FE-066, backend SPEC-BE-099), in the upper
// part of the right column (the user's choice); a drawer below 900 px.
// Everything is private: the lists hold only the signed-in user's own chats
// and projects.

function errText(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

function ago(iso: string | null): string {
  if (!iso) return "";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "now";
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  if (s < 86400 * 7) return `${Math.floor(s / 86400)}d`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** Today / Yesterday / Previous 7 days / Previous 30 days / Older (pinned first). */
function groupChats(items: ChatRead[]): [string, ChatRead[]][] {
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  const day = 86400_000;
  const groups: Record<string, ChatRead[]> = {};
  const order = ["Pinned", "Today", "Yesterday", "Previous 7 days", "Previous 30 days", "Older"];
  for (const c of items) {
    const t = new Date(c.last_message_at ?? c.created_at ?? 0).getTime();
    const g = c.pinned ? "Pinned" : t >= start.getTime() ? "Today" : t >= start.getTime() - day ? "Yesterday"
      : t >= start.getTime() - 7 * day ? "Previous 7 days" : t >= start.getTime() - 30 * day ? "Previous 30 days" : "Older";
    (groups[g] ??= []).push(c);
  }
  return order.filter((g) => groups[g]?.length).map((g) => [g, groups[g]]);
}

function ChatRow({ chat, active, projects, onOpen, onChanged }: {
  chat: ChatRead;
  active: boolean;
  projects: ProjectRead[];
  onOpen: () => void;
  onChanged: (deleted?: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [menu, setMenu] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [moving, setMoving] = useState(false);
  const [title, setTitle] = useState(chat.title);
  const [error, setError] = useState<string | null>(null);
  const done = (deleted = false) => {
    setMenu(false);
    setRenaming(false);
    setMoving(false);
    void queryClient.invalidateQueries({ queryKey: orchestratorKeys.chats });
    void queryClient.invalidateQueries({ queryKey: orchestratorKeys.projects });
    onChanged(deleted);
    // A deleted chat is dropped from the cache (after the page has closed it),
    // not refetched: it would 404.
    if (deleted) {
      queryClient.removeQueries({ queryKey: orchestratorKeys.chat(chat.id) });
      queryClient.removeQueries({ queryKey: orchestratorKeys.chatMessages(chat.id) });
    } else {
      void queryClient.invalidateQueries({ queryKey: orchestratorKeys.chat(chat.id) });
    }
  };
  const change = useMutation({
    mutationFn: (c: Parameters<typeof updateChat>[1]) => updateChat(chat.id, c),
    onSuccess: () => done(),
    onError: (e) => setError(errText(e)),
  });
  const remove = useMutation({ mutationFn: () => deleteChat(chat.id), onSuccess: () => done(true), onError: (e) => setError(errText(e)) });

  if (renaming) {
    return (
      <form className="cc-hist-row is-editing" onSubmit={(e) => { e.preventDefault(); if (title.trim()) change.mutate({ title: title.trim() }); }}>
        <input autoFocus value={title} onChange={(e) => setTitle(e.target.value)} aria-label="Chat title" maxLength={60}
               onKeyDown={(e) => e.key === "Escape" && setRenaming(false)} />
        <button type="submit" className="cc-link text-accent">Save</button>
      </form>
    );
  }
  return (
    <div className={`cc-hist-row ${active ? "is-active" : ""}`} data-testid="chat-row">
      <button type="button" className="cc-hist-main" onClick={onOpen} title={chat.title}>
        <span className="flex items-center gap-1.5">
          {chat.project && <span aria-hidden="true">{chat.project.emoji}</span>}
          <span className="truncate font-medium">{chat.title}</span>
        </span>
        {chat.preview && <span className="block truncate text-[11px] text-muted">{chat.preview}</span>}
      </button>
      <span className="text-[10.5px] text-muted">{ago(chat.last_message_at ?? chat.created_at)}</span>
      <button type="button" className="cc-link px-1" aria-label={`Options for ${chat.title}`} onClick={() => setMenu((v) => !v)}>⋯</button>
      {menu && (
        <div className="cc-menu" role="menu">
          <button type="button" role="menuitem" onClick={() => { setRenaming(true); setMenu(false); }}>Rename</button>
          <button type="button" role="menuitem" onClick={() => change.mutate({ pinned: !chat.pinned })}>{chat.pinned ? "Unpin" : "Pin"}</button>
          <button type="button" role="menuitem" onClick={() => setMoving((v) => !v)}>Move to project…</button>
          {moving && (
            <div className="grid gap-0.5 border-y border-border py-1">
              {chat.project && <button type="button" role="menuitem" onClick={() => change.mutate({ project_id: null })}>— No project</button>}
              {projects.filter((p) => p.id !== chat.project?.id).map((p) => (
                <button key={p.id} type="button" role="menuitem" onClick={() => change.mutate({ project_id: p.id })}>{p.emoji} {p.name}</button>
              ))}
              {projects.length === 0 && <span className="px-2 text-[11px] text-muted">No projects yet</span>}
            </div>
          )}
          <button type="button" role="menuitem" onClick={() => change.mutate({ archived: !chat.archived })}>{chat.archived ? "Unarchive" : "Archive"}</button>
          <button type="button" role="menuitem" className="text-danger"
                  onClick={() => window.confirm(`Delete “${chat.title}”? This can't be undone.`) && remove.mutate()}>Delete</button>
          {error && <span className="px-2 text-[11px] text-danger">{error}</span>}
        </div>
      )}
    </div>
  );
}

function ChatList({ items, activeChatId, projects, onOpenChat, onDeleted }: {
  items: ChatRead[];
  activeChatId: string | null;
  projects: ProjectRead[];
  onOpenChat: (id: string) => void;
  onDeleted: (id: string) => void;
}) {
  return (
    <>
      {groupChats(items).map(([group, chats]) => (
        <div key={group} className="grid gap-0.5">
          <div className="cc-hist-group">{group}</div>
          {chats.map((c) => (
            <ChatRow key={c.id} chat={c} active={c.id === activeChatId} projects={projects} onOpen={() => onOpenChat(c.id)}
                     onChanged={(deleted) => deleted && onDeleted(c.id)} />
          ))}
        </div>
      ))}
    </>
  );
}

function ProjectView({ id, activeChatId, projects, onBack, onOpenChat, onNewChat, onDeleted }: {
  id: string;
  activeChatId: string | null;
  projects: ProjectRead[];
  onBack: () => void;
  onOpenChat: (id: string) => void;
  onNewChat: (projectId: string) => void;
  onDeleted: (chatId: string) => void;
}) {
  const queryClient = useQueryClient();
  const project = useQuery({ queryKey: orchestratorKeys.project(id), queryFn: () => fetchProject(id) });
  const chats = useQuery({ queryKey: orchestratorKeys.chatList("", false, id), queryFn: () => fetchChats("", false, id) });
  const [instructions, setInstructions] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [uploading, setUploading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const refresh = (p: ProjectRead) => {
    queryClient.setQueryData(orchestratorKeys.project(id), p);
    void queryClient.invalidateQueries({ queryKey: orchestratorKeys.projects });
    setError(null);
  };
  const save = useMutation({ mutationFn: (p: Parameters<typeof updateProject>[1]) => updateProject(id, p), onSuccess: (p) => { refresh(p); setInstructions(null); setEditing(false); }, onError: (e) => setError(errText(e)) });
  const removeFile = useMutation({ mutationFn: (fid: string) => removeProjectFile(id, fid), onSuccess: refresh, onError: (e) => setError(errText(e)) });
  const archive = useMutation({
    mutationFn: () => deleteProject(id),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: orchestratorKeys.projects }); void queryClient.invalidateQueries({ queryKey: orchestratorKeys.chats }); onBack(); },
    onError: (e) => setError(errText(e)),
  });
  const upload = async (files: FileList) => {
    setError(null);
    for (const f of Array.from(files)) {
      setUploading(f.name);
      try {
        const res = await uploadChatFile(f, () => undefined);
        refresh(await addProjectFile(id, res.id));
      } catch (e) {
        setError(errText(e));
      }
    }
    setUploading(null);
  };
  if (project.isPending) return <div className="cc-shimmer h-24" />;
  if (project.isError) return <p className="text-[12.5px] text-danger">{errText(project.error)}</p>;
  const p = project.data;
  const text = instructions ?? p.instructions;
  return (
    <div className="grid gap-3" data-testid="project-view">
      <button type="button" className="cc-link justify-self-start" onClick={onBack}>← All projects</button>
      {editing ? (
        <form className="grid gap-1.5" onSubmit={(e) => { e.preventDefault(); save.mutate({ name, description: desc }); }}>
          <input value={name} onChange={(e) => setName(e.target.value)} aria-label="Project name" maxLength={80} />
          <textarea value={desc} onChange={(e) => setDesc(e.target.value)} aria-label="Description" rows={2} maxLength={500} />
          <div className="flex justify-end gap-2">
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setEditing(false)}>Cancel</button>
            <button type="submit" className="btn btn-sm" disabled={!name.trim() || save.isPending}>Save</button>
          </div>
        </form>
      ) : (
        <div>
          <div className="flex items-center gap-2 text-[15px] font-semibold">
            <span aria-hidden="true">{p.emoji}</span>
            <span className="min-w-0 flex-1 truncate">{p.name}</span>
            <button type="button" className="cc-link" onClick={() => { setName(p.name); setDesc(p.description); setEditing(true); }}>Edit</button>
          </div>
          {p.description && <p className="m-0 mt-0.5 text-[12px] text-muted">{p.description}</p>}
        </div>
      )}
      <button type="button" className="btn btn-sm" onClick={() => onNewChat(id)} data-testid="project-new-chat">+ New chat in this project</button>
      <div className="grid gap-1">
        <div className="cc-hist-group">Instructions</div>
        <textarea rows={4} value={text} placeholder="How should PilotSonic work in this project? e.g. “Prices are in BDT. Warm, festive tone.”"
                  onChange={(e) => setInstructions(e.target.value)} aria-label="Project instructions" maxLength={4000} />
        {instructions !== null && instructions !== p.instructions && (
          <button type="button" className="btn btn-sm justify-self-end" disabled={save.isPending} onClick={() => save.mutate({ instructions })}>
            {save.isPending ? "Saving…" : "Save instructions"}
          </button>
        )}
      </div>
      <div className="grid gap-1">
        <div className="flex items-center justify-between">
          <span className="cc-hist-group">Files ({p.files.length}/20)</span>
          <button type="button" className="cc-link text-accent" onClick={() => fileInput.current?.click()} disabled={!!uploading}>
            {uploading ? `Adding ${uploading}…` : "+ Add files"}
          </button>
          <input ref={fileInput} type="file" multiple className="hidden" data-testid="project-file-input"
                 accept=".pdf,.docx,.xlsx,.csv,.tsv,.txt,.md,.json,.jpg,.jpeg,.png,.webp,.zip"
                 onChange={(e) => { if (e.target.files?.length) void upload(e.target.files); e.target.value = ""; }} />
        </div>
        {p.files.length === 0 && <span className="text-[11.5px] text-muted">Files here are knowledge for every chat in the project.</span>}
        {p.files.map((f) => (
          <div key={f.id} className="cc-hist-file" title={f.summary}>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[12px]">{f.name}</span>
              <span className="block truncate text-[10.5px] text-muted">{formatBytes(f.bytes)} · {f.summary}</span>
            </span>
            <button type="button" className="cc-link" aria-label={`Remove ${f.name}`} onClick={() => removeFile.mutate(f.id)}>✕</button>
          </div>
        ))}
      </div>
      <div className="grid gap-0.5">
        <div className="cc-hist-group">Chats in this project</div>
        {chats.data?.items.length === 0 && <span className="text-[11.5px] text-muted">No chats yet.</span>}
        {chats.data?.items.map((c) => (
          <ChatRow key={c.id} chat={c} active={c.id === activeChatId} projects={projects} onOpen={() => onOpenChat(c.id)}
                   onChanged={(deleted) => deleted && onDeleted(c.id)} />
        ))}
      </div>
      {error && <p className="m-0 text-[12px] text-danger" role="alert">{error}</p>}
      <button type="button" className="cc-link justify-self-start text-danger"
              onClick={() => window.confirm(`Delete the project “${p.name}”? Its chats are kept, outside any project.`) && archive.mutate()}>
        Delete project
      </button>
    </div>
  );
}

export default function ChatSidebar({ activeChatId, openProjectId, onOpenChat, onNewChat, onOpenProject, onChatDeleted, open, onClose }: {
  activeChatId: string | null;
  openProjectId: string | null;
  onOpenChat: (id: string) => void;
  onNewChat: (projectId?: string | null) => void;
  onOpenProject: (id: string | null) => void;
  onChatDeleted: (id: string) => void;
  open: boolean;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<"chats" | "projects">(openProjectId ? "projects" : "chats");
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [archived, setArchived] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newEmoji, setNewEmoji] = useState("📁");
  const [newDesc, setNewDesc] = useState("");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const t = setTimeout(() => setQ(search.trim()), 300);
    return () => clearTimeout(t);
  }, [search]);
  useEffect(() => {
    if (openProjectId) setTab("projects");
  }, [openProjectId]);
  const chats = useQuery({
    queryKey: orchestratorKeys.chatList(q, archived, null),
    queryFn: () => fetchChats(q, archived, null),
    // A new chat's AI title arrives a few seconds after its first message.
    refetchInterval: (query) => (query.state.data?.items.some((c) => c.title_source === "auto" && c.message_count > 0 && c.last_message_at
      && Date.now() - new Date(c.last_message_at).getTime() < 60_000) ? 3000 : false),
  });
  const projects = useQuery({ queryKey: orchestratorKeys.projects, queryFn: fetchProjects });
  const create = useMutation({
    mutationFn: () => createProject({ name: newName.trim(), emoji: newEmoji.trim() || undefined, description: newDesc.trim() || undefined }),
    onSuccess: (p) => {
      void queryClient.invalidateQueries({ queryKey: orchestratorKeys.projects });
      setCreating(false);
      setNewName("");
      setNewDesc("");
      onOpenProject(p.id);
    },
    onError: (e) => setError(errText(e)),
  });
  const projectList = useMemo(() => projects.data ?? [], [projects.data]);

  return (
    <>
      {open && <div className="cc-hist-backdrop" onClick={onClose} aria-hidden="true" />}
      <section className={`cc-history ${open ? "is-open" : ""}`} aria-label="Chats and projects" data-testid="chat-sidebar">
        <div className="flex items-center gap-2">
          <div className="cc-seg flex-1" role="tablist" aria-label="Chats or projects">
            <button type="button" role="tab" aria-pressed={tab === "chats"} aria-selected={tab === "chats"} onClick={() => { setTab("chats"); onOpenProject(null); }}>Chats</button>
            <button type="button" role="tab" aria-pressed={tab === "projects"} aria-selected={tab === "projects"} onClick={() => setTab("projects")}>Projects</button>
          </div>
          <button type="button" className="cc-link cc-hist-close" aria-label="Close" onClick={onClose}>✕</button>
        </div>

        {tab === "chats" ? (
          <>
            <button type="button" className="btn btn-sm w-full" onClick={() => onNewChat(null)} data-testid="new-chat">+ New chat</button>
            <input className="cc-mini-input w-full" placeholder="Search chats…" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search chats" />
            <div className="cc-hist-list">
              {chats.isPending ? (
                <div className="grid gap-2"><div className="cc-shimmer h-9" /><div className="cc-shimmer h-9" /><div className="cc-shimmer h-9" /></div>
              ) : chats.isError ? (
                <p className="text-[12px] text-danger">{errText(chats.error)}</p>
              ) : chats.data.items.length === 0 ? (
                <p className="text-[12px] text-muted">{q ? "No chats match." : archived ? "No archived chats." : "No chats yet. Start one!"}</p>
              ) : (
                <ChatList items={chats.data.items} activeChatId={activeChatId} projects={projectList} onOpenChat={onOpenChat} onDeleted={onChatDeleted} />
              )}
            </div>
            <label className="flex items-center gap-2 text-[11.5px] text-muted">
              <input type="checkbox" checked={archived} onChange={(e) => setArchived(e.target.checked)} /> Show archived
            </label>
          </>
        ) : openProjectId ? (
          <div className="cc-hist-list">
            <ProjectView id={openProjectId} activeChatId={activeChatId} projects={projectList} onBack={() => onOpenProject(null)}
                         onOpenChat={onOpenChat} onNewChat={(pid) => onNewChat(pid)} onDeleted={onChatDeleted} />
          </div>
        ) : (
          <>
            {creating ? (
              <form className="grid gap-1.5" onSubmit={(e) => { e.preventDefault(); if (newName.trim()) create.mutate(); }} data-testid="new-project-form">
                <div className="flex gap-1.5">
                  <input value={newEmoji} onChange={(e) => setNewEmoji(e.target.value)} aria-label="Emoji" maxLength={4} className="w-12 text-center" />
                  <input autoFocus value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Project name" aria-label="Project name" maxLength={80} className="flex-1" />
                </div>
                <textarea value={newDesc} onChange={(e) => setNewDesc(e.target.value)} placeholder="What is it about? (optional)" aria-label="Project description" rows={2} maxLength={500} />
                {error && <p className="m-0 text-[12px] text-danger">{error}</p>}
                <div className="flex justify-end gap-2">
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => setCreating(false)}>Cancel</button>
                  <button type="submit" className="btn btn-sm" disabled={!newName.trim() || create.isPending}>Create project</button>
                </div>
              </form>
            ) : (
              <button type="button" className="btn btn-sm w-full" onClick={() => setCreating(true)} data-testid="new-project">+ New project</button>
            )}
            <div className="cc-hist-list">
              {projects.isPending ? <div className="cc-shimmer h-12" /> : projectList.length === 0 ? (
                <p className="text-[12px] text-muted">Projects keep instructions and files for a set of chats, like a campaign or a product launch.</p>
              ) : projectList.map((p) => (
                <button key={p.id} type="button" className="cc-proj-row" onClick={() => onOpenProject(p.id)} data-testid="project-row">
                  <span className="cc-proj-emoji" aria-hidden="true">{p.emoji}</span>
                  <span className="min-w-0 flex-1 text-left">
                    <span className="block truncate text-[13px] font-medium">{p.name}</span>
                    <span className="block truncate text-[11px] text-muted">{p.chat_count} chat{p.chat_count === 1 ? "" : "s"}{p.files.length ? ` · ${p.files.length} files` : ""}{p.description ? ` · ${p.description}` : ""}</span>
                  </span>
                </button>
              ))}
            </div>
          </>
        )}
      </section>
    </>
  );
}
