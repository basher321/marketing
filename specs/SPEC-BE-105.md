# SPEC-BE-105: Hosting and deployment (cPanel host, Neon database, cron jobs)

Status: IMPLEMENTED (2026-10-21). Written after the fact, from the running deployment.
- **Live:** https://pilotsonic.com (frontend) and https://api.pilotsonic.com (backend) on the cPanel host s106.srvx.ws.
  `/health` → `{"status":"ok","database":"ok"}`, SSL valid, CORS allows pilotsonic.com, a wrong sign-in → 401.
- **Jobs:** the crontab ran the per-minute jobs with no errors after the `import app.main` fix (AC5).
- **History:** Vercel files came first (unused), then Railway (2026-10-19, now stopped, not deleted), then this host.

## The problem and the user's decision

- The backend and the frontend need a host that the user manages from cPanel, without SSH from outside (the account
  runs in CloudLinux CageFS; only the cPanel Terminal works).
- The host's PostgreSQL is 10.23 without the extensions the schema needs (SPEC-BE-106), so **the database stays on
  Neon** (PostgreSQL 18, least-privilege login `app_user`, RLS off on the `tenant_isolation_*` tables by the user's
  choice, since the app never sets `app.current_tenant_id`).
- Old hosts are kept until the new one works; the user decides later what to delete.

## Requirements

### R1 — Backend app (CloudLinux "Setup Python App", LiteSpeed)
- Python 3.12 app, app root `~/pilotsonic-backend`, domain `api.pilotsonic.com`, URI `/`, startup file
  `passenger_wsgi.py`, entry point `application`. Package = `app/`, `requirements.txt`, `passenger_wsgi.py`,
  `run_jobs.py`, `deploy/cpanel/setup.sh` (as `setup.sh`).
- LiteSpeed speaks WSGI: `passenger_wsgi.py` wraps the FastAPI app with **a2wsgi** (installed by the setup script,
  not in `requirements.txt`).
- The server loads the file once and **forks** workers. So:
  - a2wsgi's event-loop thread is created per process, on the first request (a loop made before the fork is missing
    in the children, and every request hangs until the worker is killed with signal 15);
  - `on_startup()` (production checks) runs at load, then `engine.dispose()`, so no pooled connection is shared
    across processes.
- There is no ASGI lifespan, so startup is called explicitly; shutdown hooks don't run (nothing needs them while the
  scheduler is off).

### R2 — Settings on the host
- `~/pilotsonic-backend/.env` (mode 600) holds the production variables. `SECRET_KEY` and `ENCRYPTION_KEY` must be
  the values the data was written with, or tokens and every stored credential become unreadable.
- Host-specific values: `SCHEDULER_ENABLED=false`, `MEDIA_ROOT=$HOME/pilotsonic-media`,
  `PUBLIC_BASE_URL=https://api.pilotsonic.com`, `CORS_ORIGINS=https://pilotsonic.com,https://www.pilotsonic.com`,
  `FRONTEND_BASE_URL=https://pilotsonic.com`, `APP_ENV=production`.
- `Settings` uses `extra="forbid"`: a key it doesn't know (for example Railway's `PYTHONUNBUFFERED`) stops the app
  from starting. The setup script removes unknown keys and keeps the original as `.env.bak`.
- `db/session.py`: `pool_pre_ping=True`, because Neon suspends when idle and drops open connections.

### R3 — Scheduled jobs from cron
- The in-process scheduler stays off (LiteSpeed starts and stops processes). `run_jobs.py <job ids…>` runs the same
  functions as `workers/schedules.py` `JOBS`; a coroutine result is run with `asyncio.run`; exit code 1 when any job
  fails or is unknown.
- `run_jobs.py` must `import app.main` first: `app/models/__init__.py` is empty, so only the API's imports register
  every ORM model (without it: "expression 'User' failed to locate a name").
- Crontab (one `flock -n` lock per cadence, so a slow run is skipped, never doubled), output to
  `~/pilotsonic-cron.log`, cleared Sundays 04:00:

  | Cadence | Jobs |
  |---|---|
  | `* * * * *` | publish_tasks generation_tasks plan_jobs workflow_tasks |
  | `*/30 * * * *` | social_token_refresh |
  | `0 */3 * * *` | ad_tasks |
  | `15 */6 * * *` | organic_metrics sync_tasks |

- The 4 inert stub jobs (analytics_tasks, content_tasks, notification_tasks, optimization_tasks) aren't scheduled.
- Only one place may run the jobs: the old host's scheduler must be stopped before the crontab is installed.
- `GET /cron/{job_id}` (Bearer `CRON_SECRET`, 404 while it's empty or for an unknown id) stays for hosts with an HTTP
  cron (Vercel). It is off here.

### R4 — Frontend app (CloudLinux "Setup Node.js App")
- Node (the highest `alt-nodejs` on the host, 24 today), app root `~/pilotsonic-frontend`, domain `pilotsonic.com`,
  mode production, startup file `app.js`, which `chdir`s into `standalone/` and requires `standalone/server.js`.
- Build on the developer machine: `NEXT_BUILD_DIR=.next-cpanel NEXT_PUBLIC_API_BASE_URL=https://api.pilotsonic.com
  npm run build` (`output: "standalone"` in `next.config.mjs`). Package: `app.js`, `setup.sh`, and `standalone/` =
  `.next-cpanel/standalone` plus `.next-cpanel/static` → `standalone/.next-cpanel/static` and `public/` →
  `standalone/public`. Drop `node_modules/@img` and `sharp` (Windows binaries, unused).
- The standalone `node_modules` stays inside `standalone/`: CloudLinux refuses a real `node_modules` in the app root.
- Zip with forward slashes (Python `zipfile`); PowerShell 5.1 `Compress-Archive` writes backslashes.
- `NEXT_PUBLIC_API_BASE_URL` is baked in at build time and also feeds the CSP `connect-src` (SPEC-FE-047).

### R5 — Domains and SSL
- DNS for pilotsonic.com is the host's (aurora/cosmo.ns.frostserver.com). `api` is a cPanel subdomain
  (`uapi SubDomain addsubdomain`); AutoSSL issues both certificates (`uapi SSL start_autossl_check`).

### R6 — Setup scripts (run in the cPanel Terminal; safe to run again)
- `backend/deploy/cpanel/setup.sh`: stops without `.env`; sets the R2 host values; adds the subdomain; creates the
  Python app (keeping our `passenger_wsgi.py`, which the selector may overwrite); installs `requirements.txt` +
  a2wsgi into `~/virtualenv/pilotsonic-backend/3.12`; removes unknown `.env` keys; checks settings and the app import
  (this also connects to the database); restarts; requests SSL; calls `/health`.
- `frontend/deploy/cpanel/setup.sh`: creates the Node app (keeping `app.js`), restarts, requests SSL, checks
  `/login`.
- `*.sh` files are LF in git (`.gitattributes`); CRLF breaks bash on the host.

## Known limits
- **Media:** files uploaded before the move are on the Railway volume (`/data/media`); new uploads go to
  `~/pilotsonic-media`. Copying them, or `STORAGE_PROVIDER=s3` (R2), is not done.
- **Long requests:** LiteSpeed may end very long requests (video generation, big imports). With the scheduler off,
  `run_soon` jobs run inside the request (`scheduler_service.run_soon`).
- **Logs:** a "Broken pipe" logging error appears in `stderr.log` when LiteSpeed closes a worker's stderr; harmless.
- A `platform_admins` row (SPEC-BE-101) is inserted by hand after the super admin's first sign-up.

## Acceptance criteria
1. `GET https://api.pilotsonic.com/health` → 200 `{"status":"ok","database":"ok"}` with a valid certificate.
2. A CORS preflight from `https://pilotsonic.com` to `/api/v1/auth/login` → 200 with that origin allowed.
3. `POST /api/v1/auth/login` with an unknown company → 401 "Invalid credentials." (the database is read).
4. `https://pilotsonic.com/`, `/login`, `/signup`, `/dashboard` → 200, and the built JS points at
   `https://api.pilotsonic.com`.
5. `run_jobs.py publish_tasks generation_tasks plan_jobs workflow_tasks` exits 0, and the cron log shows no errors
   after it is installed.
6. Re-running both setup scripts changes nothing that works and ends with the health check passing.

## Files
- `backend/passenger_wsgi.py`, `backend/run_jobs.py`, `backend/deploy/cpanel/setup.sh`
- `frontend/deploy/cpanel/app.js`, `frontend/deploy/cpanel/setup.sh`, `frontend/next.config.mjs` (standalone,
  `NEXT_BUILD_DIR`)
- `backend/app/config.py` (`CRON_SECRET`), `backend/app/main.py` (`GET /cron/{job_id}`), `backend/app/db/session.py`
  (`pool_pre_ping`)
- Earlier hosts, kept: `backend/railway.json`, `backend/railpack.json`, `backend/.railwayignore`,
  `backend/vercel.json`, `backend/index.py`, `backend/.vercelignore`, `backend/.python-version`
- `.gitattributes`
