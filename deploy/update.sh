#!/usr/bin/env bash
# Collect prices and rebuild the site. Run by the systemd timer.
# PUBLISH=pi (default): the Pi serves SITE_DIR itself (Caddy container + Tailscale Funnel).
# PUBLISH=github: commit docs/ and push to GitHub Pages instead.
set -euo pipefail
cd "$(dirname "$0")/.."

envval() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2-; }
PUBLISH=$(envval PUBLISH); PUBLISH=${PUBLISH:-pi}
SITE_DIR=$(envval SITE_DIR); SITE_DIR=${SITE_DIR:-docs}

git pull --rebase --quiet origin main || true
python3 run.py all

if [ -f "$SITE_DIR/robots.txt" ] && grep -q "Disallow: /" "$SITE_DIR/robots.txt"; then
  echo "Site was built from demo data; refusing to publish." >&2
  exit 1
fi

if [ "$PUBLISH" = github ]; then
  git add docs
  if git diff --cached --quiet; then echo "No site changes."; exit 0; fi
  git commit --quiet -m "Price update $(date -u +%Y-%m-%dT%H:%MZ)"
  git push --quiet origin HEAD:main
  echo "Published to GitHub Pages."
else
  echo "Site rebuilt in $SITE_DIR (served by the Pi)."
fi
