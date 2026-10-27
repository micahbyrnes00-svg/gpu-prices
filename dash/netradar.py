"""Network radar: LAN devices, internet reachability, speed tests. Standard library only."""
import concurrent.futures
import ipaddress
import re
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

import store

OUI_FILES = ["/usr/share/ieee-data/oui.txt", "/usr/share/arp-scan/ieee-oui.txt", "/var/lib/ieee-data/oui.txt"]
_oui = None


def _load_oui():
    global _oui
    if _oui is not None:
        return _oui
    _oui = {}
    for f in OUI_FILES:
        p = Path(f)
        if not p.exists():
            continue
        for line in p.read_text(errors="ignore").splitlines():
            m = re.match(r"^([0-9A-F]{2})-([0-9A-F]{2})-([0-9A-F]{2})\s+\(hex\)\s+(.+)$", line.strip())
            if m:
                _oui["".join(m.groups()[:3])] = m.group(4).strip()
            else:
                m = re.match(r"^([0-9A-F]{6})\t(.+)$", line.strip())
                if m:
                    _oui[m.group(1)] = m.group(2).strip()
        if _oui:
            break
    return _oui


def vendor(mac: str) -> str:
    key = mac.replace(":", "").upper()[:6]
    if int(key[1], 16) & 2:  # locally administered bit: phones with private Wi-Fi addresses
        return "Private address (phone/tablet)"
    return _load_oui().get(key, "")


def _local_nets():
    out = subprocess.run(["ip", "-4", "-o", "addr"], capture_output=True, text=True).stdout
    nets = {}
    for line in out.splitlines():
        f = line.split()
        iface, cidr = f[1], f[3]
        if iface.startswith(("eth", "wlan", "en", "wl")):
            net = ipaddress.ip_interface(cidr).network
            if net.prefixlen >= 22:
                nets[str(net)] = iface
    return nets


def _ping(ip, timeout=1):
    r = subprocess.run(["ping", "-c", "1", "-W", str(timeout), "-q", ip], capture_output=True, text=True)
    m = re.search(r"= [\d.]+/([\d.]+)/", r.stdout)
    return r.returncode == 0, float(m.group(1)) if m else None


def scan():
    """Ping-sweep local subnets, then read the kernel neighbour table. Returns list of new MACs."""
    nets = _local_nets()
    hosts = []
    for n in nets:
        hosts += [str(h) for h in ipaddress.ip_network(n).hosts()]
    with concurrent.futures.ThreadPoolExecutor(64) as ex:
        list(ex.map(lambda h: _ping(h, 1), hosts))
    out = subprocess.run(["ip", "-4", "neigh"], capture_output=True, text=True).stdout
    now = time.time()
    first_run = not store.q("SELECT 1 FROM devices LIMIT 1")
    new = []
    for line in out.splitlines():
        m = re.match(r"^(\S+) dev (\S+) lladdr (\S+) (\S+)", line)
        if not m or m.group(4) in ("FAILED", "INCOMPLETE"):
            continue
        ip, iface, mac = m.group(1), m.group(2), m.group(3).lower()
        try:
            host = socket.gethostbyaddr(ip)[0]
        except OSError:
            host = ""
        row = store.q("SELECT * FROM devices WHERE mac=?", (mac,))
        if row:
            store.x("UPDATE devices SET ip=?, host=COALESCE(NULLIF(?,''),host), last_seen=?, iface=? WHERE mac=?",
                    (ip, host, now, iface, mac))
        else:
            store.x("INSERT INTO devices (mac, ip, host, vendor, name, trusted, first_seen, last_seen, iface) "
                    "VALUES (?,?,?,?,?,?,?,?,?)", (mac, ip, host, vendor(mac), "", 1 if first_run else 0, now, now, iface))
            if not first_run:
                new.append({"mac": mac, "ip": ip, "host": host, "vendor": vendor(mac)})
    store.put("net_last_scan", now)
    return new


def devices():
    now = time.time()
    rows = store.q("SELECT * FROM devices ORDER BY trusted, last_seen DESC")
    for r in rows:
        r["online"] = now - (r["last_seen"] or 0) < 900
    return rows


def internet_check():
    """Ping two anycast resolvers; internet is 'up' if either answers."""
    best = None
    ok = False
    for target in ("1.1.1.1", "8.8.8.8"):
        good, ms = _ping(target, 2)
        if good:
            ok = True
            best = ms if best is None else min(best, ms)
    store.x("INSERT OR REPLACE INTO netping VALUES (?,?,?)", (time.time(), int(ok), best))
    store.x("DELETE FROM netping WHERE ts < ?", (time.time() - 8 * 86400,))
    return ok, best


def speedtest(down_bytes=20_000_000, up_bytes=5_000_000):
    """Download/upload test against Cloudflare's speed endpoints."""
    ua = {"User-Agent": "Orbit/1"}
    try:
        t0 = time.time()
        urllib.request.urlopen(urllib.request.Request("https://speed.cloudflare.com/__down?bytes=0", headers=ua), timeout=10).read()
        ping = (time.time() - t0) * 1000
        t0 = time.time()
        with urllib.request.urlopen(urllib.request.Request(f"https://speed.cloudflare.com/__down?bytes={down_bytes}", headers=ua), timeout=60) as r:
            n = 0
            while chunk := r.read(65536):
                n += len(chunk)
        down = n * 8 / (time.time() - t0) / 1e6
        data = b"0" * up_bytes
        t0 = time.time()
        urllib.request.urlopen(urllib.request.Request("https://speed.cloudflare.com/__up", data=data, headers=ua, method="POST"), timeout=60).read()
        up = up_bytes * 8 / (time.time() - t0) / 1e6
        store.x("INSERT INTO speed VALUES (?,?,?,?,?)", (time.time(), round(down, 1), round(up, 1), round(ping, 1), None))
        return {"down": round(down, 1), "up": round(up, 1), "ping": round(ping, 1)}
    except Exception as e:  # noqa: BLE001
        store.x("INSERT INTO speed VALUES (?,?,?,?,?)", (time.time(), None, None, None, str(e)[:200]))
        return {"error": str(e)[:200]}


def summary():
    now = time.time()
    day = store.q("SELECT ok, ms, ts FROM netping WHERE ts > ? ORDER BY ts", (now - 86400,))
    week = store.q("SELECT AVG(ok)*100 AS up FROM netping WHERE ts > ?", (now - 7 * 86400,))
    tests = store.q("SELECT * FROM speed ORDER BY ts DESC LIMIT 12")
    last = day[-1] if day else None
    return {
        "online": bool(last and last["ok"]),
        "latency": last and last["ms"],
        "uptime24": round(sum(r["ok"] for r in day) / len(day) * 100, 2) if day else None,
        "uptime7": round(week[0]["up"], 2) if week and week[0]["up"] is not None else None,
        "latencySeries": [r["ms"] or 0 for r in day[-120:]],
        "outages": _outages(day),
        "speed": tests,
        "lastScan": store.get("net_last_scan"),
    }


def _outages(rows):
    out, start = [], None
    for r in rows:
        if not r["ok"] and start is None:
            start = r["ts"]
        elif r["ok"] and start is not None:
            out.append({"start": start, "end": r["ts"]})
            start = None
    if start is not None:
        out.append({"start": start, "end": None})
    return out[-10:]
