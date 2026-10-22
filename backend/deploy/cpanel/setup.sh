#!/bin/bash
# One-time setup of the PilotSonic backend on cPanel (s106.srvx.ws) at https://api.pilotsonic.com.
# Package = app/, deploy/sql/, requirements.txt, passenger_wsgi.py, run_jobs.py and this file, extracted
# into ~/pilotsonic-backend. Run from the cPanel Terminal:  bash ~/pilotsonic-backend/setup.sh
# Needs ~/pilotsonic-backend/.env first. Safe to run again. Scheduled jobs are cron lines
# calling run_jobs.py (see its docstring), not the in-process scheduler.
set -e
APP=pilotsonic-backend
DOMAIN=api.pilotsonic.com
ROOT="$HOME/$APP"
PYV=3.12
cd "$ROOT"

if [ ! -s .env ]; then
  echo "STOP: $ROOT/.env is missing. Create it with the Railway variables first."; exit 1
fi

# Host-specific values (replace any copied from Railway).
setkv() { grep -v "^$1=" .env > .env.tmp || true; mv .env.tmp .env; echo "$1=$2" >> .env; }
setkv SCHEDULER_ENABLED false
setkv MEDIA_ROOT "$HOME/pilotsonic-media"
setkv PUBLIC_BASE_URL "https://$DOMAIN"
mkdir -p "$HOME/pilotsonic-media"
chmod 600 .env

echo "== subdomain"
uapi SubDomain addsubdomain domain=api rootdomain=pilotsonic.com dir="$DOMAIN" | grep -E "status|error" || true

echo "== python app"
cp passenger_wsgi.py /tmp/pilotsonic_passenger_wsgi.py
cloudlinux-selector create --json --interpreter python --version "$PYV" --app-root "$APP" \
  --domain "$DOMAIN" --app-uri / --startup-file passenger_wsgi.py --entry-point application \
  || echo "(app already exists, continuing)"
cp /tmp/pilotsonic_passenger_wsgi.py passenger_wsgi.py   # the selector may write its own default

echo "== packages (takes a few minutes)"
source "$HOME/virtualenv/$APP/$PYV/bin/activate"
pip install --upgrade pip -q
pip install -r requirements.txt a2wsgi -q

echo "== .env keys"
# Settings use extra="forbid", so a key it doesn't know (e.g. Railway's PYTHONUNBUFFERED)
# stops the app from starting. Unknown keys are removed; the original is kept as .env.bak.
cp .env .env.bak
python - <<'EOF'
from app.config import Settings
known = set(Settings.model_fields)
keep, drop = [], []
for line in open(".env", encoding="utf-8").read().splitlines():
    key = line.split("=", 1)[0].strip()
    if "=" in line and not line.lstrip().startswith("#") and key not in known:
        drop.append(key)
    else:
        keep.append(line)
open(".env", "w", encoding="utf-8").write("\n".join(keep) + "\n")
print("removed:", drop)
EOF

echo "== database changes (deploy/sql, every statement safe to re-run)"
# The app's login (app_user on Neon) doesn't own the schema, so changes to existing types/tables
# must first be run once by the owner in the Neon SQL Editor. Here a statement the app login may
# not run is skipped; the step fails only if what it creates is still missing.
python - <<'PYSQL'
import glob, re, sys
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError
from app.config import get_settings
url = get_settings().DATABASE_URL_SYNC
url = url.get_secret_value() if hasattr(url, "get_secret_value") else url
engine = create_engine(url)
skipped = 0
for path in sorted(glob.glob("deploy/sql/*.sql")):
    if path.endswith("_owner_grants.sql"):
        continue  # owner-only by design
    sql = re.sub(r"--[^\n]*", "", open(path, encoding="utf-8").read())
    # ALTER TYPE ... ADD VALUE can't run inside a transaction block: autocommit.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        for stmt in (s.strip() for s in sql.split(";")):
            if not stmt:
                continue
            try:
                conn.execute(text(stmt))
            except ProgrammingError as exc:
                if "must be owner" not in str(exc) and "permission denied" not in str(exc):
                    raise
                skipped += 1
    print("checked", path)
with engine.connect() as conn:
    missing = [name for name, sql in [
        ("order_status awaiting_confirmation/returned", "SELECT count(*) = 2 FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid WHERE t.typname = 'order_status' AND e.enumlabel IN ('awaiting_confirmation','returned')"),
        ("integration_provider twilio", "SELECT count(*) = 1 FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid WHERE t.typname = 'integration_provider' AND e.enumlabel = 'twilio'"),
        ("tables", "SELECT count(*) = 3 FROM information_schema.tables WHERE table_name IN ('order_status_events','sms_messages','expenses')"),
        ("app can write the new tables", "SELECT coalesce(has_table_privilege(to_regclass('order_status_events'),'INSERT') AND has_table_privilege(to_regclass('sms_messages'),'INSERT') AND has_table_privilege(to_regclass('expenses'),'INSERT'), false)"),
    ] if not conn.execute(text(sql)).scalar()]
if missing:
    print("STOP: database changes missing:", ", ".join(missing))
    print("Run deploy/sql/2026-10-21_orders_sms_expenses.sql, then *_owner_grants.sql, in the Neon SQL Editor as the owner, then run this script again.")
    sys.exit(1)
print("database ok" + (f" ({skipped} owner-only statements already in place)" if skipped else ""))
PYSQL

echo "== checks"
python -c "from app.config import get_settings; print('settings ok, APP_ENV =', get_settings().APP_ENV)"
python -c "import passenger_wsgi; print('app imports and database ok')"

cloudlinux-selector restart --json --interpreter python --app-root "$APP"
uapi SSL start_autossl_check | grep -E "status|error" || true

echo "== health"
curl -s -m 30 "https://$DOMAIN/health" || curl -sk -m 30 "https://$DOMAIN/health" || true
echo
echo "DONE"
