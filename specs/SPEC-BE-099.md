# SPEC-BE-099: Command Chat — chat history (many chats) and Projects

Status: IMPLEMENTED and verified (2026-10-10). The UI is SPEC-FE-066.
- **DDL applied:** `orchestrator_projects`, `orchestrator_chats` (+ the user indexes), `orchestrator_files.project_id`.
  Backfill: each user's earlier messages became one "Earlier chat" (pilotsonic 72 messages, pilotsonic1 10); no message
  is left without `session_id`.
- **Verified:** 38/38 rolled-back checks on the live DB (privacy 404s, per-chat clarification and draft job list,
  project evidence, reset). Real AI titles: "Product Listings From Spreadsheet", "পণ্য তালিকা ও কম স্টক".
  Regressions: command eval 31/31, BE-095 27/27, BE-096 29/30 (the known encrypted-ZIP test artifact, checked
  separately), BE-097 43/43, BE-098 27/27. ruff/mypy at the baseline (1 / 7).
- **Deviations:**
  - The sending rule (amended below): no `chat_id` continues the user's latest chat, and `new_chat: true` or a
    `project_id` starts a new one. "No chat_id = new chat" broke multi-turn clarifications and the chat edits of a
    draft job list from older clients.
  - One line was added to the planner system prompt (`orchestrator_service._system_prompt`): a `project` in the context
    is background (instructions as preferences, file values as the user's); its name and description are labels, not a
    request. Without it, the real model once read the project "Eid launch / Eid campaign products" as an ad request and
    asked for a budget.

Asked: "In this page http://localhost:3000/chat, I need another two features for command chat, one is project as do claude
and two is chat history as do claude or others, so that user can get previous chat and can do continue from from previous
chat. You can use it upper part of right sidebar of chatbox or you can do as standard. You will follow spec driven
development and do not change anything in the entire software except these changes."

**User's decisions (2026-10-10):** everything private: each person sees only their own chats and their own projects
(`user_id` / `created_by` must be the caller; anyone else's → 404). AI-written titles. Approved as written.

## Context

- **Today:** each company has **one** Command Chat thread. `GET /orchestrator/messages` returns every message of the
  company (pilotsonic: 72, pilotsonic1: 10), and every user of the company sees the same thread.
- **What's tied to the thread:**
  - the pending clarification ("Start over") is the company's latest AI question (`_pending_draft`);
  - the open draft job list is the company's latest draft (`job_board_service.open_draft`);
  - summary, progress and failure messages find their place through the plan's `correlation_id`.
- **Spare column:** the live `orchestrator_messages.session_id` (uuid, indexed `(session_id, created_at)`) has never
  been used. It becomes the chat id; no message is rewritten.

## Requirements

- **FR1 (chats):** a new table `orchestrator_chats`. Each message belongs to one chat (`session_id`).
  - **Routes** (all scoped to the company and to who may see the chat, FR3; another company's or another person's chat →
    404):
    - `GET /orchestrator/chats?q=&project_id=&limit=&before=`: the user's chats, newest activity first. Pinned first,
      archived excluded unless `?archived=true`, each with `id, title, project, pinned, last_message_at,
      message_count, preview`. `q` searches titles and message text.
    - `POST /orchestrator/chats {project_id?}` → a new, empty chat.
    - `GET /orchestrator/chats/{id}` → the chat.
    - `GET /orchestrator/chats/{id}/messages` → its messages (as today's message list).
    - `PATCH /orchestrator/chats/{id} {title?, pinned?, project_id?, archived?}`: rename, pin, move into or out of a
      project, archive.
    - `DELETE /orchestrator/chats/{id}`: soft delete. Its messages stay for audit, hidden from every list; plans
      already running keep running, and their approvals stay in Pending Approvals.
  - **Sending:** `POST /orchestrator/messages {chat_id?, new_chat?, project_id?, …}` writes into that chat. A new chat is
    created (and returned as `chat_id` on the result) when `new_chat: true` or a `project_id` is given, so "send from an
    empty screen" starts a chat. With none of them, the message continues the user's latest chat.
    - **Why (found by the regression run):** callers that send no chat id kept one continuous conversation before, e.g.
      the SPEC-BE-085 multi-turn golden case and job-list chat edits. Starting a new chat for them broke the
      continuation.
  - **Continue:** the planner sees only **this chat's** recent turns:
    - the pending clarification and the open draft job list come from this chat, not the company's latest, so two chats
      never answer each other's questions;
    - "Start over" acts on this chat;
    - summaries, progress and failure messages go into the chat whose message started the plan.
  - **Titles:** set from the first message. The company's AI text chain writes a short title (≤ 60 characters, in the
    message's language) in the background. Until then, and if the AI fails, it is the first 60 characters. Renaming by
    hand stops automatic titles.
  - **Old messages:** each company's existing thread becomes one chat, "Earlier chat" (DDL backfill), owned by the user
    who wrote its first user message; nothing is lost.
- **FR2 (projects, like Claude Projects):** a new table `orchestrator_projects` (`name`, `description`, `instructions`,
  `emoji`, `archived_at`).
  - **Routes:**
    - `GET /orchestrator/projects` → each with its chat count and last activity.
    - `POST /orchestrator/projects`, `PATCH /orchestrator/projects/{id}`, `DELETE` (archive; its chats stay, outside any
      project).
    - **Files:** `POST /orchestrator/projects/{id}/files {file_id}` (a file uploaded with SPEC-BE-096) and `DELETE …/files/{file_id}`.
  - **Instructions:** sent to the planner with every message in the project's chats ("Use a friendly tone; our brand is
    PilotSonic; prices are in BDT…"), at most 4,000 characters, as data under the rules (they can't override the
    approval policy or the guards).
  - **Project files:** knowledge for every chat in the project: their extracted text and records join the planner's
    context and the **evidence** (SPEC-BE-085), so values from them count as the user's. At most 20 files.
  - **New chats:** a chat started in a project belongs to it; "move to project" changes it later.
- **FR3 (who sees what):** everything private (the user's choice). A chat is its creator's; a project is its creator's,
  and so are the chats in it. Pending Approvals stays company-wide (it's the approval queue, not chat history).
- **FR4 (unchanged):** the planner, guards, approval policy, job lists, voice, files, every other route.
  `GET /orchestrator/messages` (no chat) keeps working for old clients and returns the user's latest chat.

## DDL (additive)

```sql
CREATE TABLE orchestrator_projects (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  created_by uuid REFERENCES users(id) ON DELETE SET NULL, name text NOT NULL, description text, instructions text,
  emoji text, archived_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE orchestrator_chats (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  user_id uuid REFERENCES users(id) ON DELETE SET NULL, project_id uuid REFERENCES orchestrator_projects(id) ON DELETE SET NULL,
  title text NOT NULL DEFAULT 'New chat', title_source text NOT NULL DEFAULT 'auto', pinned boolean NOT NULL DEFAULT false,
  archived_at timestamptz, deleted_at timestamptz, last_message_at timestamptz, created_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX orchestrator_chats_user ON orchestrator_chats (tenant_id, user_id, last_message_at DESC);
ALTER TABLE orchestrator_files ADD COLUMN project_id uuid REFERENCES orchestrator_projects(id) ON DELETE SET NULL;
-- backfill: one "Earlier chat" per company that has messages; its messages get session_id = that chat.
```

## Acceptance criteria (live DB, rolled back; a real AI title once)

- **AC1:** two chats of one user keep separate histories. A clarifying question in chat A is answered only in chat A;
  chat B starts fresh. A job list's summary lands in the chat that made it.
- **AC2:** list, search (title and text), rename, pin, archive, delete and move-to-project all work; another company's
  or another person's chat → 404.
- **AC3:** the first message makes a title (AI, or first words when the AI fails).
- **AC4:** a project's instructions reach the planner; a project file's values count as evidence (a price from it isn't
  removed by the guard).
- **AC5:** the backfill turns each company's old thread into one "Earlier chat", with every message kept. The stub
  eval stays 31/31; SPEC-BE-095/096/097 checks still pass; ruff/mypy baseline unchanged.

## Target files

`api/v1/orchestrator.py`, `schemas/orchestrator.py`, `services/orchestrator_service.py`,
`services/job_board_service.py` (open draft per chat), `models/orchestrator.py`, `services/tenant_service.py` (reset
deletes chats and projects). **New (needs approval):** `services/chat_service.py` (chats, projects, titles).
