"""Tailscale management for Orbit: tailnet devices, connection paths, serve/Funnel, ping, netcheck,
and (optional) the Tailscale admin API for client updates, key expiry and device approval.

Local data comes from the `tailscale` CLI (no sudo). The admin API is used only when
TAILSCALE_API_KEY is set in .env (an API access token from login.tailscale.com/admin/settings/keys).
Every lookup is cached and single-flight, so page loads and the alert watcher never fork the CLI
more than once per TTL. Standard library only.
"""
import json
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request

import integrations

API = "https://api.tailscale.com/api/v2"
_cache = {}
_locks = {}
_guard = threading.Lock()


def _sh(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, "", str(e)


def _memo(key, ttl, fn, force=False):
    """Cache fn() for ttl seconds; concurrent callers wait for one call instead of each forking."""
    hit = _cache.get(key)
    if hit and not force and time.time() - hit[0] < ttl:
        return hit[1]
    with _guard:
        lock = _locks.setdefault(key, threading.Lock())
    with lock:
        hit = _cache.get(key)
        if hit and not force and time.time() - hit[0] < ttl:
            return hit[1]
        try:
            val = fn()
        except Exception as e:  # noqa: BLE001
            val = {"error": str(e)[:200]}
        _cache[key] = (time.time(), val)
        return val


def _bg_memo(key, ttl, fn, placeholder=None):
    """Like _memo, but a stale value is refreshed in a background thread; callers never wait."""
    hit = _cache.get(key)
    if not hit or time.time() - hit[0] > ttl:
        with _guard:
            busy = _locks.setdefault(key + ":bg", threading.Lock())
        if busy.acquire(blocking=False):
            def run():
                try:
                    _memo(key, 0, fn, force=True)
                finally:
                    busy.release()
            threading.Thread(target=run, daemon=True).start()
    return hit[1] if hit else placeholder


def invalidate(*keys):
    for k in keys or list(_cache):
        _cache.pop(k, None)


def _ts(value):
    """RFC 3339 from tailscaled -> unix seconds (None for zero/unset times)."""
    if not value or value.startswith("0001-"):
        return None
    from datetime import datetime
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _node(p, users):
    dns = (p.get("DNSName") or "").rstrip(".")
    relay = p.get("Relay") or ""
    cur = p.get("CurAddr") or ""
    online = bool(p.get("Online"))
    user = users.get(str(p.get("UserID")), {})
    return {
        "id": p.get("ID") or "",
        "name": dns.split(".")[0] or p.get("HostName") or "",
        "host": p.get("HostName") or "",
        "dns": dns,
        "ip": next((ip for ip in p.get("TailscaleIPs") or [] if "." in ip), ""),
        "os": p.get("OS") or "",
        "online": online,
        "active": bool(p.get("Active")),
        "lastSeen": _ts(p.get("LastSeen")),
        # direct = WireGuard peer-to-peer; relay = traffic goes through a Tailscale DERP server
        "path": ("direct" if cur else f"relay · {relay}" if relay else "idle") if online else "offline",
        "rx": p.get("RxBytes") or 0,
        "tx": p.get("TxBytes") or 0,
        "exitNode": bool(p.get("ExitNode")),
        "exitNodeOption": bool(p.get("ExitNodeOption")),
        "tags": p.get("Tags") or [],
        "keyExpiry": _ts(p.get("KeyExpiry")),
        "ssh": bool(p.get("sshHostKeys") or p.get("SSH_HostKeys")),
        "owner": user.get("LoginName", ""),
    }


def _status():
    code, out, err = _sh(["tailscale", "status", "--json"], 6)
    if code:
        return {"error": (err or "tailscale not running").strip()[:200]}
    s = json.loads(out)
    users = s.get("User") or {}
    me = _node(s.get("Self") or {}, users)
    me["online"] = s.get("BackendState") == "Running"
    peers = sorted((_node(p, users) for p in (s.get("Peer") or {}).values()),
                   key=lambda n: (not n["online"], n["name"]))
    cv = s.get("ClientVersion") or {}
    return {"backend": s.get("BackendState"), "version": (s.get("Version") or "").split("-")[0],
            "latest": cv.get("LatestVersion") or None, "updateAvailable": cv.get("RunningLatest") is False,
            "tailnet": (s.get("CurrentTailnet") or {}).get("Name") or "",
            "magicDNS": (s.get("CurrentTailnet") or {}).get("MagicDNSSuffix") or "",
            "health": s.get("Health") or [], "self": me, "peers": peers}


def status(force=False):
    return _memo("status", 10, _status, force)


def peer(name):
    """Find a peer by short name, MagicDNS name, hostname or Tailscale IP."""
    name = (name or "").lower().rstrip(".")
    for p in status().get("peers", []):
        if name in (p["name"].lower(), p["host"].lower(), p["dns"].lower(), p["ip"]):
            return p
    return None


def resolve(name, fallback=""):
    """Tailscale IPv4 for a device name; keeps working if the address ever changes."""
    p = peer(name)
    return (p or {}).get("ip") or fallback


def _serve():
    code, out, err = _sh(["tailscale", "serve", "status", "--json"], 6)
    if code:
        return {"error": (err or out).strip()[:200]}
    cfg = json.loads(out or "{}") or {}
    funnel = cfg.get("AllowFunnel") or {}
    routes = []
    for hostport, web in (cfg.get("Web") or {}).items():
        port = hostport.rsplit(":", 1)[-1]
        for path, h in (web.get("Handlers") or {}).items():
            target = h.get("Proxy") or h.get("Path") or ("text" if h.get("Text") else "")
            routes.append({"port": port, "path": path, "target": target, "public": bool(funnel.get(hostport))})
    for port, tcp in (cfg.get("TCP") or {}).items():
        if tcp.get("TCPForward"):
            routes.append({"port": str(port), "path": "tcp", "target": tcp["TCPForward"], "public": False})
    routes.sort(key=lambda r: (r["port"], r["path"]))
    return {"routes": routes, "funnel": any(funnel.values())}


def serve(force=False):
    """`tailscale serve` and Funnel config in one call (Funnel state is part of the serve config)."""
    return _memo("serve", 30, _serve, force)


def _netcheck():
    code, out, err = _sh(["tailscale", "netcheck", "--format=json"], 25)
    if code:
        return {"error": (err or out).strip()[:200]}
    n = json.loads(out)
    lat = n.get("RegionLatency") or {}
    pref = str(n.get("PreferredDERP") or "")
    return {"ts": time.time(), "udp": bool(n.get("UDP")), "ipv4": bool(n.get("IPv4")), "ipv6": bool(n.get("IPv6")),
            "hardNAT": bool(n.get("MappingVariesByDestIP")), "upnp": bool(n.get("UPnP")),
            "derp": pref, "derpMs": round(lat[pref] / 1e6) if pref in lat else None,
            "global": n.get("GlobalV4") or ""}


def netcheck():
    """DERP latency and NAT type. Slow (several seconds), so refreshed in the background every 15 min."""
    return _bg_memo("netcheck", 900, _netcheck, {"loading": True})


PONG = re.compile(r"pong from (\S+) \(([^)]+)\) (?:via (DERP\(\w+\)|\S+) )?in ([\d.]+)ms")


def ping(name):
    """`tailscale ping` (disco, not ICMP): shows whether the path is direct or relayed, and latency."""
    p = peer(name)
    if not p:
        raise ValueError("Not a device on your tailnet")
    if not p["online"]:
        raise ValueError(f"{p['name']} is offline")
    code, out, err = _sh(["tailscale", "ping", "-c", "4", "--timeout", "3s", p["ip"]], 20)
    pongs = PONG.findall(out)
    if not pongs:
        raise ValueError((err or out).strip().splitlines()[-1][:160] if (err or out).strip() else "no reply")
    ms = [float(x[3]) for x in pongs]
    via = pongs[-1][2]
    invalidate("status")
    return {"peer": p["name"], "ms": round(min(ms), 1), "avg": round(sum(ms) / len(ms), 1),
            "via": "relay " + via[5:-1] if via.startswith("DERP") else "direct " + via if via else "direct",
            "direct": not via.startswith("DERP")}


# ---------------------------------------------------------------- admin API (optional)
def _api(method, path, body=None, timeout=15):
    key = integrations.env_get("TAILSCALE_API_KEY")
    if not key:
        raise PermissionError("TAILSCALE_API_KEY not set")
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                                          "User-Agent": "Orbit/1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return json.loads(raw) if raw else {}


def _tailnet_name():
    return integrations.env_get("TAILSCALE_TAILNET") or "-"


def _devices():
    data = _api("GET", f"/tailnet/{_tailnet_name()}/devices?fields=all")
    out = {}
    for d in data.get("devices", []):
        out[d.get("nodeId") or d.get("id")] = {
            "apiId": d.get("id"), "name": (d.get("name") or "").split(".")[0], "authorized": d.get("authorized", True),
            "updateAvailable": bool(d.get("updateAvailable")), "clientVersion": (d.get("clientVersion") or "").split("-")[0],
            "expires": _ts(d.get("expires")), "keyExpiryDisabled": bool(d.get("keyExpiryDisabled")),
            "blocksIncoming": bool(d.get("blocksIncomingConnections")), "external": bool(d.get("isExternal"))}
    return {"ts": time.time(), "devices": out}


def api_enabled():
    return bool(integrations.env_get("TAILSCALE_API_KEY"))


def devices(force=False):
    """Admin-API device details, refreshed in the background every 10 minutes."""
    if not api_enabled():
        return {"enabled": False}
    if force:
        invalidate("api")
    return {"enabled": True, **(_bg_memo("api", 600, _devices, {"loading": True}) or {})}


def test_api():
    try:
        n = len(_devices()["devices"])
        invalidate("api")
        return True, f"Tailscale API OK · {n} devices"
    except urllib.error.HTTPError as e:
        return False, f"Tailscale API rejected the key (HTTP {e.code})"
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:120]


def _api_device(node_id):
    d = (devices().get("devices") or {}).get(node_id)
    if not d:
        raise ValueError("Unknown device (refresh the tailnet list)")
    return d


def authorize(node_id):
    d = _api_device(node_id)
    _api("POST", f"/device/{d['apiId']}/authorized", {"authorized": True})
    invalidate("api", "status")
    return f"{d['name']} approved"


def disable_key_expiry(node_id):
    d = _api_device(node_id)
    _api("POST", f"/device/{d['apiId']}/key", {"keyExpiryDisabled": True})
    invalidate("api", "status")
    return f"Key expiry disabled for {d['name']}"


# ---------------------------------------------------------------- views
def summary():
    """Compact view for /api/status (same keys the app and Ask Orbit already read)."""
    s = status()
    if s.get("error"):
        return {}
    me = s["self"]
    return {"dns": me["dns"], "ip": me["ip"], "online": me["online"], "funnel": serve().get("funnel", False),
            "peers": [{"name": p["name"], "online": p["online"], "os": p["os"]} for p in s["peers"]],
            "updateAvailable": s["updateAvailable"], "version": s["version"]}


def full():
    """Everything the Tailnet panel shows; admin API fields merged into each device when available."""
    s = status()
    api = devices()
    extra = api.get("devices") or {}
    if not s.get("error"):
        for n in [s["self"], *s["peers"]]:
            n.update({k: v for k, v in (extra.get(n["id"]) or {}).items() if k not in ("name",)})
    return {**s, "serve": serve(), "netcheck": netcheck(),
            "api": {"enabled": api.get("enabled", False), "loading": api.get("loading", False),
                    "error": api.get("error"), "ts": api.get("ts")}}
