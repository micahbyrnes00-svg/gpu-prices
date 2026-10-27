"""Website monitor: availability, response time and TLS certificate expiry for any URLs you add."""
import socket
import ssl
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

import store

UA = {"User-Agent": "Orbit-SiteMonitor/1 (+uptime check)"}


def sites():
    return store.get("sites", [])


def save_sites(lst):
    clean, seen = [], set()
    for s in lst[:20]:
        url = str(s.get("url", "")).strip()
        if not url:
            continue
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        u = urlparse(url)
        if not u.hostname or url in seen:
            continue
        seen.add(url)
        clean.append({"url": url, "name": str(s.get("name") or u.hostname)[:40]})
    store.put("sites", clean)
    return clean


def cert_days(host, port=443):
    ctx = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=10) as raw:
        with ctx.wrap_socket(raw, server_hostname=host) as t:
            return round((ssl.cert_time_to_seconds(t.getpeercert()["notAfter"]) - time.time()) / 86400, 1)


def check(url):
    t0 = time.time()
    code, err = None, None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15) as r:
            code = r.status
            r.read(65536)
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception as e:  # noqa: BLE001  (DNS, TLS, timeout, refused)
        err = (getattr(e, "reason", None) or e).__str__()[:160]
    ms = round((time.time() - t0) * 1000)
    ok = code is not None and code < 400
    u = urlparse(url)
    days = None
    if u.scheme == "https":
        cache = store.get("cert_cache", {})
        c = cache.get(u.hostname)
        if c and time.time() - c["ts"] < 6 * 3600:
            days = c["days"] - (time.time() - c["ts"]) / 86400
        else:
            try:
                days = cert_days(u.hostname, u.port or 443)
                cache[u.hostname] = {"ts": time.time(), "days": days}
                store.put("cert_cache", cache)
            except Exception as e:  # noqa: BLE001
                err = err or f"TLS: {str(e)[:140]}"
                ok = False
    store.x("INSERT INTO sitechecks (ts, url, ok, code, ms, err) VALUES (?,?,?,?,?,?)",
            (time.time(), url, int(ok), code, ms if code else None, err))
    return {"url": url, "ok": ok, "code": code, "ms": ms, "err": err, "certDays": None if days is None else round(days, 1)}


def check_all():
    out = [check(s["url"]) for s in sites()]
    store.x("DELETE FROM sitechecks WHERE ts < ?", (time.time() - 8 * 86400,))
    store.put("site_last", {r["url"]: r for r in out} | {"_ts": time.time()})
    return out


def summary():
    now = time.time()
    last = store.get("site_last", {})
    res = []
    for s in sites():
        rows = store.q("SELECT ok, ms FROM sitechecks WHERE url=? AND ts>? ORDER BY ts", (s["url"], now - 86400))
        wk = store.q("SELECT AVG(ok)*100 u FROM sitechecks WHERE url=? AND ts>?", (s["url"], now - 7 * 86400))[0]["u"]
        ms = [r["ms"] for r in rows if r["ms"]]
        res.append({**s, "last": last.get(s["url"]),
                    "uptime24": round(sum(r["ok"] for r in rows) / len(rows) * 100, 2) if rows else None,
                    "uptime7": round(wk, 2) if wk is not None else None,
                    "avgMs": round(sum(ms) / len(ms)) if ms else None, "series": ms[-48:]})
    return {"sites": res, "checked": last.get("_ts")}
