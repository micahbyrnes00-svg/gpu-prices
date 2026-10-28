#!/bin/bash
# themachine price worker: collect eBay prices, build the site + API, post Discord deals, then publish to the Pi.
# Run by the orbit-prices.timer user unit every 6 hours. The Pi only serves what this uploads.
set -uo pipefail
REPO="$HOME/gpu-prices"
OUT="$HOME/orbit-site"                 # build output (SITE_DIR)
KEY="$HOME/.ssh/orbit_publish"         # upload-only key; the Pi limits it to /home/pi/worker
PI="pi@micahbyrnespi"
cd "$REPO" || exit 1
start=$(date +%s)
export DATA_DIR="$REPO/data" SITE_DIR="$OUT" PUBLISH=pi
command -v claude >/dev/null || export AI_CMD=""   # no Claude CLI here: template summaries

status() {  # status.json the Pi's Orbit reads (ok, error, timing)
    python3 - "$@" <<'PY' > "$HOME/.cache/orbit-worker-status.json"
import json, sys, time
ok, err, start = sys.argv[1] == "1", sys.argv[2], int(sys.argv[3])
print(json.dumps({"ts": time.time(), "ok": ok, "error": err[:300], "seconds": int(time.time()) - start, "host": "themachine"}))
PY
}
upload() { rsync -a --timeout=60 -e "ssh -i $KEY -o BatchMode=yes -o IdentitiesOnly=yes" "$@"; }

git pull -q --rebase origin main || true
mkdir -p "$HOME/.cache"
if ! python3 run.py all > "$HOME/.cache/orbit-worker.log" 2>&1; then
    status 0 "run.py failed: $(tail -1 "$HOME/.cache/orbit-worker.log")" "$start"
    upload "$HOME/.cache/orbit-worker-status.json" "$PI:status.json"
    exit 1
fi
if grep -q "Disallow: /" "$OUT/robots.txt" 2>/dev/null; then
    status 0 "Built from demo data; not published" "$start"; upload "$HOME/.cache/orbit-worker-status.json" "$PI:status.json"; exit 1
fi
# consistent copy of the database for Orbit's Market tab and alerts on the Pi
sqlite3 "$DATA_DIR/prices.db" ".backup '$HOME/.cache/prices-snapshot.db'"
if upload --delete-delay --delay-updates "$OUT/" "$PI:site/" \
   && upload "$HOME/.cache/prices-snapshot.db" "$PI:data/prices.db"; then
    status 1 "" "$start"
else
    status 0 "Upload to the Pi failed" "$start"
fi
upload "$HOME/.cache/orbit-worker-status.json" "$PI:status.json"
echo "worker done in $(( $(date +%s) - start ))s"
