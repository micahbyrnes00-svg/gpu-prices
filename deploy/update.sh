#!/usr/bin/env bash
# Collect prices, rebuild the site, publish docs/ to GitHub Pages. Run by the systemd timer.
set -euo pipefail
cd "$(dirname "$0")/.."

git pull --rebase --quiet origin main || true
python3 run.py all

if [ -f docs/robots.txt ] && grep -q "Disallow: /" docs/robots.txt; then
  echo "Site was built from demo data; refusing to publish." >&2
  exit 1
fi

git add docs
if git diff --cached --quiet; then
  echo "No site changes."
  exit 0
fi
git commit --quiet -m "Price update $(date -u +%Y-%m-%dT%H:%MZ)"
git push --quiet origin HEAD:main
echo "Published."
