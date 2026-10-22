#!/bin/bash
# One-time setup of the PilotSonic frontend on cPanel at https://pilotsonic.com.
# Package = this folder's app.js + setup.sh, plus standalone/ = .next-cpanel/standalone with
# .next-cpanel/static and public/ copied in (no @img/sharp), built with NEXT_BUILD_DIR=.next-cpanel
# NEXT_PUBLIC_API_BASE_URL=https://api.pilotsonic.com npm run build. Zip with forward slashes.
# Run from the cPanel Terminal:  bash ~/pilotsonic-frontend/setup.sh   (safe to run again)
set -e
APP=pilotsonic-frontend
NODEV=$(ls /opt/alt | grep -E '^alt-nodejs[0-9]+$' | sed 's/alt-nodejs//' | sort -n | tail -1)
echo "== node version $NODEV"
cp "$HOME/$APP/app.js" /tmp/pilotsonic_app.js
cloudlinux-selector create --json --interpreter nodejs --version "$NODEV" --app-root "$APP" \
  --domain pilotsonic.com --app-uri / --app-mode production --startup-file app.js \
  || echo "(app already exists, continuing)"
cp /tmp/pilotsonic_app.js "$HOME/$APP/app.js"
# A plain restart can leave the old Node process serving the old build: stop, end any
# leftover process of this app, then start.
cloudlinux-selector stop --json --interpreter nodejs --app-root "$APP" || true
pkill -u "$(id -un)" -f "$HOME/$APP/app.js" || true
sleep 3
cloudlinux-selector start --json --interpreter nodejs --app-root "$APP"
uapi SSL start_autossl_check | grep -E "status|error" || true
echo "== check"
curl -s -o /dev/null -w "pilotsonic.com -> HTTP %{http_code}\n" -m 60 https://pilotsonic.com/login || true
echo "DONE"
