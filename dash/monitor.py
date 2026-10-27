"""Background jobs + alert rules. Every rule is toggleable with thresholds; alerts are stored and pushed."""
import json
import subprocess
import threading
import time
import traceback
from datetime import datetime

import analytics
import disks
import netradar
import security
import sitemon
import store
import webpush

RULES = {
    # key: (label, level, default enabled, default params, description)
    "temp":      ("Pi overheating", "warning", True, {"limit": 75}, "CPU temperature at or above the limit for 2 checks in a row."),
    "power":     ("Power problem", "critical", True, {}, "Under-voltage or throttling reported by the Pi firmware."),
    "service":   ("Service stopped", "warning", True, {}, "A watched service or timer that was running stops or fails."),
    "container": ("Container stopped", "warning", True, {}, "A Docker container that was running stops."),
    "disk_full": ("Disk filling up", "warning", True, {"limit": 90}, "Root disk usage at or above the limit (%)."),
    "smart":     ("Drive health", "critical", True, {"temp": 55}, "SMART failure, new bad/pending sectors, or drive temperature above the limit (°C)."),
    "backup":    ("Cloud backup", "info", True, {}, "Weekly encrypted Google Drive backup finished or failed."),
    "prices":    ("Price update failed", "warning", True, {}, "The 6-hour price update job failed."),
    "deal":      ("Watchlist deal", "info", True, {}, "A listing hits a target price on your watchlist."),
    "money":     ("Money made", "info", True, {}, "New affiliate commission imported from eBay Partner Network."),
    "amazon":    ("Amazon deadline", "warning", True, {}, "Reminders at 60, 30 and 7 days left if Amazon Associates still needs its 3 qualifying sales."),
    "discord":   ("New Discord members", "info", True, {}, "People joined your deals Discord (checked every 30 minutes, at most one alert a day)."),
    "click":     ("Affiliate click", "info", False, {}, "Someone clicked through to eBay from your site (can be chatty)."),
    "traffic":   ("Traffic spike", "info", True, {"visitors": 50}, "Unique site visitors in the last 24h reach the threshold."),
    "device":    ("New device on network", "warning", True, {}, "An unknown device joins your home network."),
    "internet":  ("Internet outage", "critical", True, {}, "Internet unreachable for 3 checks in a row, plus a recovery notice."),
    "speed":     ("Slow internet", "warning", False, {"down": 50}, "Scheduled speed test below the download limit (Mbps)."),
    "site":      ("Website down", "critical", True, {}, "A monitored website fails 2 checks in a row (error, timeout or HTTP 4xx/5xx), plus a recovery notice."),
    "slow":      ("Website slow", "warning", False, {"ms": 3000}, "A monitored website responds slower than the limit (milliseconds)."),
    "cert":      ("Certificate expiring", "warning", True, {"days": 14}, "A monitored site's HTTPS certificate expires within the limit (days)."),
    "buy":       ("Buy signal", "info", True, {}, "A tracked model's typical price drops to its lowest level in 90 days."),
    "reboot":    ("Restart needed", "warning", True, {}, "Installed updates (usually the kernel) need a reboot to take effect."),
    "updates":   ("Updates waiting", "info", False, {}, "Package updates are pending (security updates install automatically)."),
    "ssh":       ("SSH login", "info", True, {}, "Someone signed in to the Pi over SSH."),
    "sshfail":   ("SSH attack", "warning", True, {"fails": 5}, "Failed SSH logins in 10 minutes reach the limit."),
    "probe":     ("Site probing", "warning", True, {"hits": 20}, "One visitor triggers this many error pages in 10 minutes (bots scanning for weaknesses)."),
    "digest":    ("Weekly AI digest", "info", False, {"hour": 9}, "Sunday morning: Claude on the Pi summarizes the week's health, traffic, money and prices."),
    "daily":     ("Daily summary", "info", False, {"hour": 8}, "One morning summary: health, visitors, clicks, deals."),
}
SCHEDULE = {"net_scan_min": 10, "speedtest_hours": 6, "smart_min": 30, "site_min": 5, "security_hours": 6}


def config():
    c = store.get("alert_cfg", {})
    rules = {}
    for k, (label, level, on, params, desc) in RULES.items():
        r = c.get("rules", {}).get(k, {})
        rules[k] = {"label": label, "level": level, "desc": desc, "enabled": r.get("enabled", on),
                    "params": {**params, **{p: v for p, v in r.get("params", {}).items() if p in params}}}
    return {"rules": rules, "quiet": c.get("quiet", {"enabled": False, "start": 23, "end": 7}),
            "watchlist": c.get("watchlist", []), "schedule": {**SCHEDULE, **c.get("schedule", {})}}


def save_config(new):
    c = store.get("alert_cfg", {})
    rules = c.get("rules", {})
    for k, v in (new.get("rules") or {}).items():
        if k not in RULES:
            continue
        cur = rules.get(k, {})
        if isinstance(v.get("enabled"), bool):
            cur["enabled"] = v["enabled"]
        for p, val in (v.get("params") or {}).items():
            if p in RULES[k][3] and isinstance(val, (int, float)):
                cur.setdefault("params", {})[p] = val
        rules[k] = cur
    c["rules"] = rules
    if isinstance(new.get("quiet"), dict):
        q = new["quiet"]
        c["quiet"] = {"enabled": bool(q.get("enabled")), "start": int(q.get("start", 23)) % 24, "end": int(q.get("end", 7)) % 24}
    if isinstance(new.get("watchlist"), list):
        c["watchlist"] = [{"model": str(w.get("model"))[:60], "max": float(w.get("max"))}
                          for w in new["watchlist"] if w.get("model") and isinstance(w.get("max"), (int, float))][:40]
    if isinstance(new.get("schedule"), dict):
        s = c.get("schedule", {})
        for k, v in new["schedule"].items():
            if k in SCHEDULE and isinstance(v, (int, float)) and v > 0:
                s[k] = v
        c["schedule"] = s
    store.put("alert_cfg", c)
    return config()


def _quiet_now(cfg):
    q = cfg["quiet"]
    if not q["enabled"]:
        return False
    h = datetime.now().hour
    return (q["start"] <= h or h < q["end"]) if q["start"] > q["end"] else (q["start"] <= h < q["end"])


_last_fire = {}


def fire(rule, title, body, url="/", key=None, cooldown=3600, force=False):
    """Record an alert and push it (respects enable flag, cooldown and quiet hours)."""
    cfg = config()
    r = cfg["rules"].get(rule)
    if not force and (not r or not r["enabled"]):
        return False
    k = key or rule
    if not force and time.time() - _last_fire.get(k, 0) < cooldown:
        return False
    _last_fire[k] = time.time()
    level = r["level"] if r else "info"
    pushed = 0
    if force or not (_quiet_now(cfg) and level != "critical"):
        pushed = sum(1 for s in webpush.broadcast(title, body, url, level, tag=k) if s in (200, 201))
    store.x("INSERT INTO alerts (ts, rule, level, title, body, url, pushed) VALUES (?,?,?,?,?,?,?)",
            (time.time(), rule, level, title, body, url, pushed))
    store.x("DELETE FROM alerts WHERE id NOT IN (SELECT id FROM alerts ORDER BY id DESC LIMIT 300)")
    return True


def history(limit=60):
    return store.q("SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,))


# ---------------------------------------------------------------- the watcher
class Watcher:
    def __init__(self, sampler, status_fn):
        self.sampler = sampler
        self.status_fn = status_fn
        self.state = store.get("watch_state", {})
        self.hot = 0
        self.net_fail = 0
        self.net_down_since = None
        self.next = {"scan": 0, "speed": time.time() + 600, "smart": 0, "net": 0, "log": 0, "daily": 0, "site": 0, "sec": 60}
        threading.Thread(target=self._loop, daemon=True).start()

    def _save(self):
        store.put("watch_state", self.state)

    def _loop(self):
        time.sleep(15)
        while True:
            for job in (self._system, self._units, self._jobs, self._net, self._scan, self._smart,
                        self._speed, self._traffic, self._deals, self._sites, self._security, self._buy, self._amazon, self._discord, self._digest, self._daily):
                try:
                    job()
                except Exception:  # noqa: BLE001
                    traceback.print_exc()
            self._save()
            time.sleep(30)

    def _system(self):
        cfg = config()["rules"]
        d = self.sampler.snapshot()
        t = d.get("temp")
        if t is not None and t >= cfg["temp"]["params"]["limit"]:
            self.hot += 1
            if self.hot == 2:
                fire("temp", "Pi is running hot", f"CPU at {t:.1f} °C (limit {cfg['temp']['params']['limit']} °C).")
        else:
            self.hot = 0
        thr = d.get("throttled")
        if thr and thr != "0x0":
            bits = int(thr, 16)
            now_bad = bits & 0xF
            if now_bad:
                why = "under-voltage" if bits & 1 else "throttling"
                fire("power", "Pi power problem", f"Firmware reports {why} ({thr}). Check the power supply.", key="power")
        for disk in d.get("disks", []):
            if disk["mount"] == "/" and disk["total"]:
                pct = (1 - disk["free"] / disk["total"]) * 100
                if pct >= cfg["disk_full"]["params"]["limit"]:
                    fire("disk_full", "Disk almost full", f"Root disk at {pct:.0f}%.", cooldown=6 * 3600)

    def _units(self):
        st = self.status_fn()
        prev = self.state.get("units", {})
        cur = {}
        for u in st.get("services", []):
            cur[u["unit"]] = u["active"]
            if prev.get(u["unit"]) == "active" and u["active"] in ("inactive", "failed"):
                fire("service", f"{u['unit']} stopped", f"{u['desc']} is now {u['active']}.", url="/#control", key="svc-" + u["unit"])
        self.state["units"] = cur
        prevc = self.state.get("containers", {})
        curc = {}
        for c in st.get("containers", []):
            curc[c["name"]] = c["state"]
            if prevc.get(c["name"]) == "running" and c["state"] != "running":
                fire("container", f"Container {c['name']} stopped", c.get("status", ""), url="/#control", key="ctr-" + c["name"])
        self.state["containers"] = curc

    def _unit_result(self, unit):
        out = subprocess.run(["systemctl", "show", unit, "-p", "Result,ExecMainExitTimestampMonotonic,ExecMainStatus,ActiveState"],
                             capture_output=True, text=True).stdout
        return dict(l.split("=", 1) for l in out.splitlines() if "=" in l)

    def _jobs(self):
        for unit, rule in (("pi-cloud-backup.service", "backup"), ("gpu-prices.service", "prices")):
            r = self._unit_result(unit)
            stamp = r.get("ExecMainExitTimestampMonotonic", "0")
            key = "job-" + unit
            if stamp in ("0", "") or r.get("ActiveState") == "activating":
                continue
            if self.state.get(key) is None:
                self.state[key] = stamp  # first look: remember, don't alert
                continue
            if stamp != self.state.get(key):
                self.state[key] = stamp
                ok = r.get("Result") == "success" and r.get("ExecMainStatus") == "0"
                if rule == "backup":
                    fire("backup", "Cloud backup " + ("finished" if ok else "FAILED"),
                         "Encrypted system backup uploaded to Google Drive." if ok else "Check logs in Orbit → Control.",
                         url="/#control", key=key, cooldown=60)
                elif not ok:
                    fire("prices", "Price update failed", "The tracker job failed. Open its logs in Orbit.", url="/#control", key=key, cooldown=60)

    def _net(self):
        if time.time() < self.next["net"]:
            return
        self.next["net"] = time.time() + 60
        ok, _ = netradar.internet_check()
        if ok:
            if self.net_down_since and self.net_fail >= 3:
                mins = (time.time() - self.net_down_since) / 60
                fire("internet", "Internet is back", f"Outage lasted about {mins:.0f} min.", key="net-up", cooldown=60)
            self.net_fail, self.net_down_since = 0, None
        else:
            self.net_fail += 1
            self.net_down_since = self.net_down_since or time.time()
            if self.net_fail == 3:  # stored now, pushed when a path out exists again
                fire("internet", "Internet outage", "The Pi can't reach the internet.", key="net-down", cooldown=60)

    def _scan(self):
        mins = config()["schedule"]["net_scan_min"]
        if time.time() < self.next["scan"]:
            return
        self.next["scan"] = time.time() + mins * 60
        for d in netradar.scan():
            label = d["host"] or d["vendor"] or "Unknown device"
            fire("device", "New device on your network", f"{label} · {d['ip']} · {d['mac']}", url="/#network", key="dev-" + d["mac"], cooldown=86400)

    def _smart(self):
        if time.time() < self.next["smart"]:
            return
        self.next["smart"] = time.time() + config()["schedule"]["smart_min"] * 60
        lim = config()["rules"]["smart"]["params"]["temp"]
        prev = self.state.get("smart", {})
        cur = {}
        for d in disks.read_all():
            if d.get("error"):
                continue
            k = d.get("serial") or d["dev"]
            bad = sum(v for n, v in d["attrs"].items() if n in ("Reallocated sectors", "Pending sectors", "Offline uncorrectable"))
            cur[k] = bad
            if d.get("passed") is False:
                fire("smart", "Drive failing", f"{d['model']} reports SMART FAILED. Back up now.", url="/#system", key="smart-fail-" + k, cooldown=6 * 3600)
            elif k in prev and bad > prev[k]:
                fire("smart", "Drive developing bad sectors", f"{d['model']}: {bad} bad/pending sectors (was {prev[k]}).", url="/#system", key="smart-bad-" + k)
            if d.get("temp") and d["temp"] >= lim:
                fire("smart", "Drive running hot", f"{d['model']} at {d['temp']} °C.", url="/#system", key="smart-temp-" + k, cooldown=3 * 3600)
        self.state["smart"] = cur

    def _speed(self):
        hours = config()["schedule"]["speedtest_hours"]
        if time.time() < self.next["speed"]:
            return
        self.next["speed"] = time.time() + hours * 3600
        r = netradar.speedtest()
        lim = config()["rules"]["speed"]["params"]["down"]
        if r.get("down") is not None and r["down"] < lim:
            fire("speed", "Internet is slow", f"Speed test: {r['down']} Mbps down / {r['up']} up (limit {lim}).", url="/#network", cooldown=6 * 3600)

    def _traffic(self):
        if time.time() < self.next["log"]:
            return
        self.next["log"] = time.time() + 120
        before = store.q("SELECT COALESCE(MAX(id),0) m FROM hits")[0]["m"]
        analytics.ingest()
        for c in store.q("SELECT * FROM hits WHERE kind='click' AND id>?", (before,)):
            fire("click", "Affiliate click", f"Someone clicked through to eBay: {c['model'] or 'a listing'}.", url="/#market", key=f"click-{c['id']}", cooldown=0)
        lim = config()["rules"]["traffic"]["params"]["visitors"]
        u = store.q("SELECT COUNT(DISTINCT visitor) u FROM hits WHERE kind='view' AND ts>?", (time.time() - 86400,))[0]["u"]
        if u >= lim:
            fire("traffic", "Traffic spike", f"{u} unique visitors in the last 24 hours.", url="/#market", key="traffic", cooldown=86400)

    def _deals(self):
        wl = config()["watchlist"]
        if not wl:
            return
        m = self.status_fn().get("market") or {}
        if not m.get("ready") or m.get("demo"):
            return
        seen = set(self.state.get("deal_seen", []))
        for w in wl:
            for d in m.get("allListings", []):
                if d["modelId"] == w["model"] and d["total"] <= w["max"] and d["url"] not in seen:
                    seen.add(d["url"])
                    fire("deal", f"{d['model']} under ${w['max']:.0f}", f"${d['total']:.2f} · {d['title'][:80]}", url=d["url"], key="deal-" + d["url"][-40:], cooldown=0)
        self.state["deal_seen"] = list(seen)[-500:]

    def _sites(self):
        if time.time() < self.next["site"] or not sitemon.sites():
            return
        self.next["site"] = time.time() + config()["schedule"]["site_min"] * 60
        rules = config()["rules"]
        fails = self.state.setdefault("site_fails", {})
        names = {x["url"]: x["name"] for x in sitemon.sites()}
        for r in sitemon.check_all():
            u, name = r["url"], names.get(r["url"], r["url"])
            if not r["ok"]:
                fails[u] = fails.get(u, 0) + 1
                if fails[u] == 2:
                    why = f"HTTP {r['code']}" if r["code"] else (r["err"] or "no response")
                    fire("site", f"{name} is down", f"{why} · {u}", url="/#network", key="site-" + u, cooldown=0)
            else:
                if fails.get(u, 0) >= 2:
                    fire("site", f"{name} is back up", f"Responding in {r['ms']} ms.", url="/#network", key="siteup-" + u, cooldown=0)
                fails[u] = 0
                if r["ms"] > rules["slow"]["params"]["ms"]:
                    fire("slow", f"{name} is slow", f"{r['ms']} ms response (limit {rules['slow']['params']['ms']} ms).", url="/#network", key="slow-" + u, cooldown=3 * 3600)
            if r["certDays"] is not None and r["certDays"] <= rules["cert"]["params"]["days"]:
                fire("cert", f"{name} certificate expiring", f"HTTPS certificate expires in {r['certDays']:.0f} days.", url="/#network", key="cert-" + u, cooldown=86400)

    def _security(self):
        rules = config()["rules"]
        now = time.time()
        since = self.state.get("ssh_since", now - 600)
        ev = security.ssh_events(since)
        self.state["ssh_since"] = now
        if ev:
            log = store.get("ssh_log", []) + ev
            store.put("ssh_log", [e for e in log if e["ts"] > now - 7 * 86400][-300:])
            for e in ev:
                if e["ok"]:
                    fire("ssh", "SSH login", f"{e['user']} signed in from {e['ip']} ({e['method']}).", url="/#control", key=f"ssh-{e['ts']}", cooldown=0)
        recent_fail = sum(1 for e in store.get("ssh_log", []) if not e["ok"] and e["ts"] > now - 600)
        if recent_fail >= rules["sshfail"]["params"]["fails"]:
            fire("sshfail", "Failed SSH logins", f"{recent_fail} failed SSH logins in 10 minutes.", url="/#control", key="sshfail", cooldown=3600)
        lim = rules["probe"]["params"]["hits"]
        for p in store.q("SELECT visitor, COUNT(*) n FROM hits WHERE kind='err' AND ts>? GROUP BY visitor HAVING n>=?", (now - 600, lim)):
            fire("probe", "Site is being probed", f"One visitor hit {p['n']} error pages in 10 minutes (scanning for weaknesses). The site is static, so there's nothing to exploit.",
                 url="/#control", key="probe-" + p["visitor"], cooldown=6 * 3600)
        if now < self.next["sec"]:
            return
        self.next["sec"] = now + config()["schedule"]["security_hours"] * 3600
        up = security.updates()
        if up["pending"]:
            fire("updates", "Updates waiting", f"{up['pending']} package updates ({up['security']} security).", url="/#control", key="updates", cooldown=86400)
        if security.summary()["reboot"]:
            fire("reboot", "Pi needs a restart", "Updates were installed that need a reboot to take effect.", url="/#control", key="reboot", cooldown=86400)

    def _buy(self):
        m = self.status_fn().get("market") or {}
        if not m.get("ready") or m.get("demo"):
            return
        seen = self.state.setdefault("buy_seen", {})
        for r in m.get("rows", []):
            if r.get("signal") and seen.get(r["id"]) != r.get("day"):
                seen[r["id"]] = r.get("day")
                fire("buy", f"Buy signal: {r['name']}", f"Typical used price ${r['median']:.0f}, the lowest in 90 days.",
                     url=r["url"], key="buy-" + r["id"], cooldown=0)

    def _amazon(self):
        a = analytics.amazon_status()
        if a["daysLeft"] is None or a["sales"] >= 3:
            return
        for mark in (60, 30, 7):
            if a["daysLeft"] <= mark and self.state.get("amz_mark", 999) > mark:
                self.state["amz_mark"] = mark
                fire("amazon", f"Amazon: {a['daysLeft']} days left", f"{a['sales']} of 3 qualifying sales so far. Without 3 sales by the deadline, Amazon closes the Associates account.",
                     url="/#market", key=f"amz-{mark}", cooldown=0)
                break

    def _discord(self):
        if time.time() < self.next.get("discord", 0):
            return
        self.next["discord"] = time.time() + 1800
        import integrations
        c = integrations.discord_counts(force=True)
        if not c or c.get("members") is None:
            return
        last = self.state.get("dc_members")
        self.state["dc_members"] = c["members"]
        if last is not None and c["members"] > last:
            n = c["members"] - last
            fire("discord", f"+{n} Discord member{'s' if n != 1 else ''}", f"Your deals server now has {c['members']} members ({c['online']} online).",
                 url="/#market", key="discord-join", cooldown=86400)

    def _digest(self):
        r = config()["rules"]["digest"]
        now = datetime.now()
        week = now.strftime("%G-%V")
        if not r["enabled"] or now.weekday() != 6 or now.hour != int(r["params"]["hour"]) or self.state.get("digest") == week:
            return
        self.state["digest"] = week

        def work():
            import ask
            try:
                text = ask.answer_now("Write my weekly digest: Pi health, internet, site traffic, clicks and money, notable price moves, "
                                      "and anything I should do this week. Under 90 words, plain sentences.",
                                      ask.snapshot(self.status_fn, self.sampler))
            except Exception as e:  # noqa: BLE001
                text = f"Digest unavailable: {e}"
            fire("digest", "Your weekly Orbit digest", text[:900], url="/#alerts", key="digest-" + week, cooldown=0)
        threading.Thread(target=work, daemon=True).start()

    def _daily(self):
        r = config()["rules"]["daily"]
        if not r["enabled"]:
            return
        today = datetime.now().strftime("%Y-%m-%d")
        if datetime.now().hour != int(r["params"]["hour"]) or self.state.get("daily") == today:
            return
        self.state["daily"] = today
        d = self.sampler.snapshot()
        a = analytics.summary()
        n = netradar.summary()
        body = (f"Temp {d.get('temp')} °C · up {d.get('uptime', 0) / 86400:.1f} d · internet {n.get('uptime24') or '--'}% · "
                f"{a['today'].get('u', 0)} visitors · {a['clicksToday']} clicks · ${a['earnings']['last30']:.2f} earned (30d)")
        fire("daily", "Orbit daily summary", body, key="daily", cooldown=3600)
