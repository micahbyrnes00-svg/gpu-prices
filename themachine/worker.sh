#!/bin/bash
# themachine price worker: collect eBay prices, build the site + API, post Discord deals, then publish to the Pi.
# Run by the orbit-prices.timer user unit every 6 hours. The Pi only serves what this uploads.
#   worker.sh                 collect + build + publish
#   worker.sh --publish-only  skip collection/build; re-upload the last build (for retries)
# Uploads always target directories: the Pi's restricted rrsync (-wo /home/pi/worker) mishandles
# named-file destinations ("unlink(4) failed" via /proc/self/fd/4), so files are staged under their final names.
set -euo pipefail
REPO="$HOME/gpu-prices"
OUT="$HOME/orbit-site"                 # build output (SITE_DIR)
KEY="$HOME/.ssh/orbit_publish"         # upload-only key; the Pi limits it to /home/pi/worker
PI="pi@micahbyrnespi"
STAGE="$HOME/.cache/orbit-publish"     # status.json + prices.db, uploaded as directory contents
PUBLISH_ONLY=0
[ "${1:-}" = "--publish-only" ] && PUBLISH_ONLY=1
cd "$REPO"
start=$(date +%s)
export DATA_DIR="$REPO/data" SITE_DIR="$OUT" PUBLISH=pi
command -v claude >/dev/null || export AI_CMD=""   # no Claude CLI here: template summaries
mkdir -p "$HOME/.cache" "$STAGE"

status() {  # status.json the Pi's Orbit reads (ok, error, timing)
    python3 - "$@" <<'PY' > "$HOME/.cache/orbit-worker-status.json"
import json, sys, time
ok, err, start = sys.argv[1] == "1", sys.argv[2], int(sys.argv[3])
print(json.dumps({"ts": time.time(), "ok": ok, "error": err[:300], "seconds": int(time.time()) - start, "host": "themachine"}))
PY
    cp "$HOME/.cache/orbit-worker-status.json" "$STAGE/status.json"
}
upload() { rsync -a --timeout=60 -e "ssh -i $KEY -o BatchMode=yes -o IdentitiesOnly=yes" "$@"; }
send_status() { upload "$STAGE/status.json" "$PI:./"; }
fail() {  # record and publish the failure, then exit nonzero
    status 0 "$1" "$start"
    send_status || true
    exit 1
}

if [ "$PUBLISH_ONLY" = 0 ]; then
    # Update code only on a clean fast-forward; never rebase over local edits.
    if [ -z "$(git status --porcelain --untracked-files=no)" ]; then
        git fetch -q origin main && git merge -q --ff-only origin/main \
            || echo "git: not a fast-forward of origin/main; running local code" >&2
    else
        echo "git: local changes present; skipping update" >&2
    fi
    python3 run.py all > "$HOME/.cache/orbit-worker.log" 2>&1 \
        || fail "run.py failed: $(tail -1 "$HOME/.cache/orbit-worker.log")"
fi

[ -f "$OUT/robots.txt" ] || fail "No build to publish"
# A demo build blocks every crawler; single-bot opt-outs (Google-Extended) are normal production policy.
python3 - "$OUT/robots.txt" <<'PY' || fail "Built from demo data; not published"
import sys
from urllib.robotparser import RobotFileParser
r = RobotFileParser()
r.parse(open(sys.argv[1]).read().splitlines())
sys.exit(0 if r.can_fetch("OrbitPublishCheck", "/") else 1)
PY

# consistent copy of the database for Orbit's Market tab and alerts on the Pi
rm -f "$STAGE/prices.db"
sqlite3 "$DATA_DIR/prices.db" ".backup '$STAGE/prices.db'" || fail "Database snapshot failed"
upload --delete-delay --delay-updates "$OUT/" "$PI:site/" || fail "Site upload to the Pi failed"
upload "$STAGE/prices.db" "$PI:data/" || fail "Database upload to the Pi failed"
status 1 "" "$start"
send_status
echo "worker done in $(( $(date +%s) - start ))s"
