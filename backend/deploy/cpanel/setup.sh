#!/bin/bash
# One-time setup of the PilotSonic backend on cPanel (s106.srvx.ws) at https://api.pilotsonic.com.
# Package = app/, requirements.txt, passenger_wsgi.py, run_jobs.py and this file, extracted
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

echo "== checks"
python -c "from app.config import get_settings; print('settings ok, APP_ENV =', get_settings().APP_ENV)"
python -c "import passenger_wsgi; print('app imports and database ok')"

cloudlinux-selector restart --json --interpreter python --app-root "$APP"
uapi SSL start_autossl_check | grep -E "status|error" || true

echo "== health"
curl -s -m 30 "https://$DOMAIN/health" || curl -sk -m 30 "https://$DOMAIN/health" || true
echo
echo "DONE"
