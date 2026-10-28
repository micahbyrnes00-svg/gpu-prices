#!/bin/bash
# Update themachine's Orbit metrics collector from GitHub (no sudo needed).
set -euo pipefail
dir="$HOME/.local/lib/picommand"; base=https://raw.githubusercontent.com/micahbyrnes00-svg/gpu-prices/main/themachine
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
for f in metrics.py sampler.py; do curl -fsSL "$base/$f" -o "$tmp/$f"; done
python3 -m py_compile "$tmp/metrics.py" "$tmp/sampler.py"
cp -a "$dir/metrics.py" "$dir/metrics.py.bak" 2>/dev/null || true
cp -a "$dir/sampler.py" "$dir/sampler.py.bak" 2>/dev/null || true
install -m 644 "$tmp/metrics.py" "$tmp/sampler.py" "$dir/"
systemctl --user restart orbit-sampler.service
sleep 3
python3 -c "import json;d=json.load(open('$HOME/.cache/orbit/metrics.json'));print('ORBIT METRICS OK · disk io:', [x['dev'] for x in d.get('io',{}).get('disks',[])])"
