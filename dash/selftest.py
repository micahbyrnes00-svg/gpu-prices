"""Quick check that the Pi Command backend works: python3 dash/selftest.py LOGIN"""
import json
import sys
import urllib.request

login = sys.argv[1] if len(sys.argv) > 1 else ""
req = urllib.request.Request("http://127.0.0.1:8099/api/status", headers={"Tailscale-User-Login": login})
d = json.load(urllib.request.urlopen(req, timeout=60))
print("services:  ", ", ".join(f"{s['unit']}={s['active']}" for s in d["services"]))
print("containers:", ", ".join(f"{c['name']}={c['state']}" for c in d["containers"]))
print("timers:    ", d["timers"])
ts = d["tailscale"]
print("tailscale: ", ts.get("dns"), "funnel:", ts.get("funnel"), "peers:", [p["name"] for p in ts.get("peers", [])])
print("market:    ", {k: v for k, v in d["market"].items() if k not in ("rows", "deals")})
print("backups:   ", str(d["backups"])[:300])
