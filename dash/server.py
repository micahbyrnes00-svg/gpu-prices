#!/usr/bin/env python3
"""Pi Command: live stats + management API for the iPhone web app.

Binds to 127.0.0.1 only and is published to the tailnet with `tailscale serve`.
Every request must carry the Tailscale-User-Login header that tailscale serve adds,
and it must match ALLOWED_LOGIN. Management actions are a fixed whitelist.
Standard library only.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
WEB = HERE / "web"
STATE = Path(os.environ.get("DASH_STATE", Path.home() / ".config" / "picommand"))
STATE.mkdir(parents=True, exist_ok=True)
SETTINGS_FILE = STATE / "settings.json"
PORT = int(os.environ.get("DASH_PORT", "8099"))
ALLOWED_LOGIN = os.environ.get("ALLOWED_LOGIN", "")  # empty = allow any (local testing only)

UNITS = ["gpu-prices.timer", "pi-cloud-backup.timer", "tailscaled.service", "docker.service",
         "wayvnc.service", "fieldpi-scan.service", "fieldpi-web.service", "matrixvms.service",
         "shairport-sync.service", "cockpit.socket", "picommand.service"]
DEFAULT_SETTINGS = {"accent": "cyan", "refresh": 2, "compact": False, "reduceMotion": False,
                    "panels": {"system": True, "cores": True, "network": True, "market": True,
                               "services": True, "containers": True, "jobs": True, "links": True}}


def sh(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:  # noqa: BLE001
        return 1, str(e)


# ---------------------------------------------------------------- live stats
class Sampler:
    """Background thread sampling /proc once a second."""

    def __init__(self):
        self.lock = threading.Lock()
        self.data = {}
        self.history = {"cpu": [], "rx": [], "tx": [], "temp": []}
        self._prev_cpu = None
        self._prev_net = None
        self._slow_at = 0
        self._slow = {}
        threading.Thread(target=self._loop, daemon=True).start()

    @staticmethod
    def _cpu_times():
        out = []
        for line in Path("/proc/stat").read_text().splitlines():
            if line.startswith("cpu"):
                parts = line.split()
                vals = list(map(int, parts[1:9]))
                idle = vals[3] + vals[4]
                out.append((sum(vals), idle))
        return out

    @staticmethod
    def _net():
        rx = tx = 0
        for line in Path("/proc/net/dev").read_text().splitlines()[2:]:
            name, rest = line.split(":", 1)
            name = name.strip()
            if name == "lo" or name.startswith(("veth", "docker", "br-")):
                continue
            f = rest.split()
            rx += int(f[0]); tx += int(f[8])
        return rx, tx

    def _sample(self):
        now = time.time()
        cpu = self._cpu_times()
        usage = []
        if self._prev_cpu:
            for (t1, i1), (t0, i0) in zip(cpu, self._prev_cpu):
                dt = t1 - t0
                usage.append(round(100 * (1 - (i1 - i0) / dt), 1) if dt else 0.0)
        self._prev_cpu = cpu
        rx, tx = self._net()
        rxr = txr = 0
        if self._prev_net:
            dt = now - self._prev_net[2]
            rxr, txr = (rx - self._prev_net[0]) / dt, (tx - self._prev_net[1]) / dt
        self._prev_net = (rx, tx, now)
        mem = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            k, v = line.split(":", 1)
            mem[k] = int(v.split()[0]) * 1024
        temp = None
        tz = Path("/sys/class/thermal/thermal_zone0/temp")
        if tz.exists():
            temp = round(int(tz.read_text()) / 1000, 1)
        load = Path("/proc/loadavg").read_text().split()[:3]
        uptime = float(Path("/proc/uptime").read_text().split()[0])
        if now - self._slow_at > 5:
            self._slow = self._slow_stats()
            self._slow_at = now
        d = {
            "ts": now,
            "cpu": usage[0] if usage else 0.0,
            "cores": usage[1:],
            "mem": {"total": mem.get("MemTotal", 0), "avail": mem.get("MemAvailable", 0),
                    "swapTotal": mem.get("SwapTotal", 0), "swapFree": mem.get("SwapFree", 0)},
            "temp": temp,
            "load": [float(x) for x in load],
            "uptime": uptime,
            "net": {"rx": rxr, "tx": txr},
            **self._slow,
        }
        with self.lock:
            self.data = d
            for key, val in (("cpu", d["cpu"]), ("rx", rxr), ("tx", txr), ("temp", temp or 0)):
                h = self.history[key]
                h.append(round(val, 1))
                del h[:-120]

    @staticmethod
    def _slow_stats():
        disks = []
        for mount in ("/", "/boot/firmware"):
            try:
                st = os.statvfs(mount)
                disks.append({"mount": mount, "total": st.f_blocks * st.f_frsize,
                              "free": st.f_bavail * st.f_frsize})
            except OSError:
                pass
        throttled = None
        if shutil.which("vcgencmd"):
            _, out = sh(["vcgencmd", "get_throttled"], 3)
            m = re.search(r"0x[0-9a-fA-F]+", out)
            throttled = m.group(0) if m else None
        clock = None
        if shutil.which("vcgencmd"):
            _, out = sh(["vcgencmd", "measure_clock", "arm"], 3)
            m = re.search(r"=(\d+)", out)
            clock = int(m.group(1)) // 1_000_000 if m else None
        _, out = sh(["ps", "-eo", "pid,pcpu,pmem,comm", "--sort=-pcpu", "--no-headers"], 3)
        procs = []
        for line in out.splitlines()[:8]:
            f = line.split(None, 3)
            if len(f) == 4 and f[3] not in ("ps",):
                procs.append({"pid": int(f[0]), "cpu": float(f[1]), "mem": float(f[2]), "name": f[3]})
        model = ""
        mp = Path("/proc/device-tree/model")
        if mp.exists():
            model = mp.read_text().strip("\x00\n")
        return {"disks": disks, "throttled": throttled, "clock": clock, "procs": procs[:6],
                "model": model, "host": os.uname().nodename}

    def _loop(self):
        while True:
            try:
                self._sample()
            except Exception as e:  # noqa: BLE001
                print("sample error:", e, file=sys.stderr)
            time.sleep(1)

    def snapshot(self):
        with self.lock:
            return {**self.data, "history": {k: list(v) for k, v in self.history.items()}}


# ---------------------------------------------------------------- slower status (cached)
_cache = {}


_bg = {}


def cached_bg(key, ttl, fn, placeholder):
    """Slow lookups (cloud listing) refresh in a background thread; callers never wait."""
    hit = _cache.get(key)
    stale = not hit or time.time() - hit[0] > ttl
    if stale and not _bg.get(key):
        def run():
            try:
                val = fn()
            except Exception as e:  # noqa: BLE001
                val = {"error": str(e)}
            _cache[key] = (time.time(), val)
            _bg[key] = False
        _bg[key] = True
        threading.Thread(target=run, daemon=True).start()
    return hit[1] if hit else placeholder


def cached(key, ttl, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    try:
        val = fn()
    except Exception as e:  # noqa: BLE001
        val = {"error": str(e)}
    _cache[key] = (time.time(), val)
    return val


def services():
    out = []
    for u in UNITS:
        _, load = sh(["systemctl", "show", u, "-p", "LoadState,ActiveState,SubState,Description"], 3)
        props = dict(l.split("=", 1) for l in load.splitlines() if "=" in l)
        if props.get("LoadState") != "loaded":
            continue
        out.append({"unit": u, "active": props.get("ActiveState"), "sub": props.get("SubState"),
                    "desc": props.get("Description", "")})
    return out


def timers():
    code, out = sh(["systemctl", "list-timers", "--all", "--output=json"], 5)
    if code:
        return []
    want = ("gpu-prices", "pi-cloud-backup")
    res = []
    for t in json.loads(out or "[]"):
        if any(w in t.get("unit", "") for w in want):
            nxt = t.get("next")
            last = t.get("last")
            res.append({"unit": t["unit"],
                        "next": nxt / 1e6 if isinstance(nxt, (int, float)) and nxt else None,
                        "last": last / 1e6 if isinstance(last, (int, float)) and last else None})
    return res


def containers():
    if not shutil.which("docker"):
        return []
    code, out = sh(["docker", "ps", "-a", "--format", "{{json .}}"], 5)
    res = []
    for line in out.splitlines():
        try:
            c = json.loads(line)
        except ValueError:
            continue
        res.append({"name": c.get("Names"), "image": c.get("Image"), "state": c.get("State"),
                    "status": c.get("Status"), "ports": c.get("Ports", "")})
    return res


def tailscale():
    code, out = sh(["tailscale", "status", "--json"], 5)
    if code:
        return {}
    s = json.loads(out)
    self_ = s.get("Self", {})
    peers = [{"name": (p.get("DNSName") or p.get("HostName") or "").split(".")[0], "online": p.get("Online"), "os": p.get("OS")}
             for p in (s.get("Peer") or {}).values()]
    _, fun = sh(["tailscale", "funnel", "status", "--json"], 5)
    funnel_on = False
    try:
        fj = json.loads(fun)
        funnel_on = bool(fj.get("AllowFunnel"))
    except ValueError:
        pass
    return {"dns": self_.get("DNSName", "").rstrip("."), "ip": (self_.get("TailscaleIPs") or [""])[0],
            "online": self_.get("Online"), "peers": peers, "funnel": funnel_on}


def market():
    """Read the price tracker database through the tracker package."""
    sys.path.insert(0, str(REPO))
    from tracker import config as tcfg, db as tdb, stats as tstats  # noqa: E402
    if not tcfg.DB_PATH.exists():
        return {"ready": False, "note": "Waiting for eBay keys and the first price run."}
    con = tdb.connect()
    runs = con.execute("SELECT COUNT(*), MAX(ts), SUM(source='sample') FROM runs").fetchone()
    if not runs[0]:
        return {"ready": False, "note": "No price runs yet."}
    models = tcfg.load_models()["models"]
    reps = [tstats.model_report(con, m) for m in models]
    site = tcfg.SITE_URL
    rows = []
    deals = []
    for r in reps:
        c = r["current"]
        if not c:
            continue
        rows.append({"id": r["model"]["id"], "name": r["model"]["name"], "cat": r["model"]["cat"],
                     "median": c["median"], "chg7": r["chg_7d"], "chg30": r["chg_30d"],
                     "perGb": r.get("per_gb"), "spark": [p["median"] for p in r["series"][-30:]],
                     "url": f"{site}/{r['model']['id']}.html"})
        for d in r["deals"]:
            deals.append({"model": r["model"]["name"], "title": d["title"], "total": d["total"],
                          "under": round((1 - d["total"] / c["median"]) * 100), "url": d["url"]})
    deals.sort(key=lambda d: -d["under"])
    return {"ready": True, "demo": bool(runs[2]), "lastRun": runs[1], "rows": rows,
            "gpu7": tstats.market_index(reps, "gpu", "chg_7d"), "ram7": tstats.market_index(reps, "ram", "chg_7d"),
            "gpu30": tstats.market_index(reps, "gpu", "chg_30d"), "ram30": tstats.market_index(reps, "ram", "chg_30d"),
            "deals": deals[:8], "site": site}


def backups():
    conf = Path.home() / ".config" / "rclone" / "rclone.conf"
    if not conf.exists() or not shutil.which("rclone"):
        return {"configured": False}
    code, out = sh(["rclone", "--config", str(conf), "lsjson", "gcrypt:"], 180)
    if code:
        return {"configured": True, "error": out.strip()[-200:]}
    files = [f for f in json.loads(out) if not f.get("IsDir")]
    files.sort(key=lambda f: f.get("ModTime", ""), reverse=True)
    running = sh(["pgrep", "-f", "p.sh cloudrun"], 2)[0] == 0
    return {"configured": True, "running": running,
            "files": [{"name": f["Name"], "size": f["Size"], "time": f["ModTime"]} for f in files[:8]]}


def status():
    return {
        "services": cached("services", 5, services),
        "timers": cached("timers", 30, timers),
        "containers": cached("containers", 5, containers),
        "tailscale": cached("tailscale", 15, tailscale),
        "market": cached("market", 120, market),
        "backups": cached_bg("backups", 600, backups, {"configured": True, "loading": True}),
    }


# ---------------------------------------------------------------- actions (whitelist)
SUDO_SYSTEMCTL = ["sudo", "-n", "/usr/bin/systemctl"]


def act(body):
    a = body.get("action")
    target = body.get("target", "")
    if a in ("start", "stop", "restart"):
        if target not in UNITS or target == "picommand.service" and a == "stop":
            return 400, "unit not allowed"
        code, out = sh(SUDO_SYSTEMCTL + [a, target], 30)
    elif a == "container_restart":
        names = {c["name"] for c in containers()}
        if target not in names:
            return 400, "unknown container"
        code, out = sh(["docker", "restart", target], 60)
    elif a == "run_prices":
        code, out = sh(SUDO_SYSTEMCTL + ["start", "--no-block", "gpu-prices.service"], 10)
    elif a == "run_backup":
        code, out = sh(SUDO_SYSTEMCTL + ["start", "--no-block", "pi-cloud-backup.service"], 10)
    elif a == "funnel_on":
        code, out = sh(["sudo", "-n", "/usr/bin/tailscale", "funnel", "--bg", "8088"], 20)
    elif a == "funnel_off":
        code, out = sh(["sudo", "-n", "/usr/bin/tailscale", "funnel", "--https=443", "off"], 20)
    elif a == "update_app":
        code, out = sh(["git", "-C", str(REPO), "pull", "--ff-only", "-q"], 60)
        if code == 0:
            threading.Timer(1.0, lambda: sh(SUDO_SYSTEMCTL + ["restart", "picommand.service"], 30)).start()
    elif a == "reboot":
        threading.Timer(1.5, lambda: sh(SUDO_SYSTEMCTL + ["reboot"], 10)).start()
        code, out = 0, "rebooting"
    else:
        return 400, "unknown action"
    for k in ("services", "containers", "timers", "tailscale"):
        _cache.pop(k, None)
    return (200 if code == 0 else 500), out.strip()[-400:] or "ok"


def load_settings():
    try:
        s = json.loads(SETTINGS_FILE.read_text())
        return {**DEFAULT_SETTINGS, **s, "panels": {**DEFAULT_SETTINGS["panels"], **s.get("panels", {})}}
    except (OSError, ValueError):
        return DEFAULT_SETTINGS


def save_settings(new):
    s = load_settings()
    if new.get("accent") in ("cyan", "magenta", "lime", "amber", "violet"):
        s["accent"] = new["accent"]
    if isinstance(new.get("refresh"), (int, float)) and 1 <= new["refresh"] <= 30:
        s["refresh"] = int(new["refresh"])
    for k in ("compact", "reduceMotion"):
        if isinstance(new.get(k), bool):
            s[k] = new[k]
    for k, v in (new.get("panels") or {}).items():
        if k in s["panels"] and isinstance(v, bool):
            s["panels"][k] = v
    SETTINGS_FILE.write_text(json.dumps(s, indent=1))
    return s


# ---------------------------------------------------------------- http
SAMPLER = Sampler()
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css",
         ".json": "application/json", ".webmanifest": "application/manifest+json",
         ".svg": "image/svg+xml", ".png": "image/png"}


class Handler(BaseHTTPRequestHandler):
    server_version = "PiCommand/1"

    def log_message(self, fmt, *args):  # quiet
        pass

    def _authed(self):
        if not ALLOWED_LOGIN:
            return True
        return self.headers.get("Tailscale-User-Login", "").lower() == ALLOWED_LOGIN.lower()

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if not self._authed():
            return self._json(403, {"error": "not your tailnet identity"})
        path = urlparse(self.path).path
        if path == "/api/stream":
            return self._stream()
        if path == "/api/live":
            return self._json(200, SAMPLER.snapshot())
        if path == "/api/status":
            return self._json(200, status())
        if path == "/api/settings":
            return self._json(200, load_settings())
        if path == "/api/me":
            return self._json(200, {"login": self.headers.get("Tailscale-User-Login", "local"),
                                    "name": self.headers.get("Tailscale-User-Name", "")})
        f = (WEB / (path.lstrip("/") or "index.html")).resolve()
        if not str(f).startswith(str(WEB)) or not f.is_file():
            f = WEB / "index.html"
        data = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", TYPES.get(f.suffix, "application/octet-stream"))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):  # noqa: N802
        if not self._authed():
            return self._json(403, {"error": "not your tailnet identity"})
        if self.headers.get("X-PiCommand") != "1":  # blocks cross-site form posts
            return self._json(400, {"error": "missing header"})
        n = int(self.headers.get("Content-Length", "0") or 0)
        try:
            body = json.loads(self.rfile.read(min(n, 10000)) or b"{}")
        except ValueError:
            return self._json(400, {"error": "bad json"})
        path = urlparse(self.path).path
        if path == "/api/action":
            code, msg = act(body)
            return self._json(code, {"ok": code == 200, "message": msg})
        if path == "/api/settings":
            return self._json(200, save_settings(body))
        return self._json(404, {"error": "not found"})

    def _stream(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        interval = max(1, int(load_settings().get("refresh", 2)))
        try:
            while True:
                snap = SAMPLER.snapshot()
                snap.pop("history", None)
                self.wfile.write(f"data: {json.dumps(snap)}\n\n".encode())
                self.wfile.flush()
                time.sleep(interval)
        except (BrokenPipeError, ConnectionResetError):
            return


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    srv.daemon_threads = True
    print(f"Pi Command on http://127.0.0.1:{PORT}  allowed={ALLOWED_LOGIN or 'ANY (local test)'}")
    srv.serve_forever()
