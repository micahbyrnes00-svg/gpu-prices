"""Privacy-friendly site analytics from Caddy's JSON access log, plus affiliate-click beacons and earnings."""
import csv
import hashlib
import io
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import store

LOG = Path(os.environ.get("SITE_LOG", "/home/pi/site-logs/access.log"))
BOTS = re.compile(r"bot|crawl|spider|slurp|preview|monitor|curl|wget|python|headless|lighthouse|facebookexternalhit", re.I)
ASSET = re.compile(r"\.(css|js|png|jpg|svg|ico|json|xml|txt|webmanifest|map)$")


def ingest():
    """Read new lines from the access log (handles rotation by inode/size)."""
    if not LOG.exists():
        return 0
    st = LOG.stat()
    state = store.get("log_state", {"ino": None, "pos": 0})
    pos = state["pos"] if state["ino"] == st.st_ino and state["pos"] <= st.st_size else 0
    salt = store.get("visitor_salt") or os.urandom(8).hex()
    store.put("visitor_salt", salt)
    rows = []
    with LOG.open("rb") as f:
        f.seek(pos)
        for raw in f:
            try:
                e = json.loads(raw)
            except ValueError:
                continue
            req = e.get("request", {})
            h = {k.lower(): v for k, v in (req.get("headers") or {}).items()}
            ua = (h.get("user-agent") or [""])[0]
            if BOTS.search(ua):
                continue
            ip = (h.get("x-forwarded-for") or [req.get("client_ip") or req.get("remote_ip", "")])[0].split(",")[0].strip()
            uri = req.get("uri", "/")
            path = urlparse(uri).path
            ts = e.get("ts", time.time())
            day = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")
            visitor = hashlib.sha256(f"{salt}{day}{ip}{ua}".encode()).hexdigest()[:16]  # rotates daily, no raw IPs kept
            ref = (h.get("referer") or [""])[0]
            ref_host = urlparse(ref).netloc if ref else ""
            if path == "/c":  # affiliate click beacon from the site
                model = parse_qs(urlparse(uri).query).get("m", [""])[0][:60]
                rows.append((ts, path, ref_host, visitor, e.get("status", 0), "click", model))
            elif e.get("status", 200) < 400 and not ASSET.search(path) and req.get("method") == "GET":
                rows.append((ts, path, ref_host, visitor, e.get("status", 200), "view", ""))
        new_pos = f.tell()
    if rows:
        store.many("INSERT INTO hits (ts, path, ref, visitor, status, kind, model) VALUES (?,?,?,?,?,?,?)", rows)
    store.put("log_state", {"ino": st.st_ino, "pos": new_pos})
    return len(rows)


def summary(own_host=""):
    now = time.time()
    day0 = now - 86400
    def one(sql, a=()):
        r = store.q(sql, a)
        return r[0] if r else {}
    today = one("SELECT COUNT(*) v, COUNT(DISTINCT visitor) u FROM hits WHERE kind='view' AND ts>?", (day0,))
    week = one("SELECT COUNT(*) v, COUNT(DISTINCT visitor) u FROM hits WHERE kind='view' AND ts>?", (now - 7 * 86400,))
    clicks = one("SELECT COUNT(*) c FROM hits WHERE kind='click' AND ts>?", (now - 7 * 86400,))
    clicks_today = one("SELECT COUNT(*) c FROM hits WHERE kind='click' AND ts>?", (day0,))
    pages = store.q("SELECT path, COUNT(*) n FROM hits WHERE kind='view' AND ts>? GROUP BY path ORDER BY n DESC LIMIT 8", (now - 7 * 86400,))
    refs = store.q("SELECT ref, COUNT(*) n FROM hits WHERE kind='view' AND ts>? AND ref!='' AND ref!=? GROUP BY ref ORDER BY n DESC LIMIT 6",
                   (now - 7 * 86400, own_host))
    clicked = store.q("SELECT model, COUNT(*) n FROM hits WHERE kind='click' AND ts>? GROUP BY model ORDER BY n DESC LIMIT 5", (now - 30 * 86400,))
    daily = store.q("SELECT CAST((ts/86400) AS INT) d, COUNT(DISTINCT visitor) u FROM hits WHERE kind='view' AND ts>? GROUP BY d ORDER BY d",
                    (now - 30 * 86400,))
    earn = earnings_summary()
    return {"today": today, "week": week, "clicks7": clicks.get("c", 0), "clicksToday": clicks_today.get("c", 0),
            "pages": pages, "refs": refs, "clicked": clicked, "dailyVisitors": [r["u"] for r in daily],
            "earnings": earn, "logFound": LOG.exists()}


def earnings_summary():
    now = time.time()
    tot = store.q("SELECT COALESCE(SUM(amount),0) t FROM earnings")[0]["t"]
    m30 = store.q("SELECT COALESCE(SUM(amount),0) t FROM earnings WHERE ts>?", (now - 30 * 86400,))[0]["t"]
    recent = store.q("SELECT ts, amount, item FROM earnings ORDER BY ts DESC LIMIT 6")
    return {"total": round(tot, 2), "last30": round(m30, 2), "recent": recent, "lastImport": store.get("earn_import")}


def import_tdr(text: str):
    """Import an eBay Partner Network Transaction Detail Report CSV. Returns (new_rows, new_amount)."""
    rdr = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    cols = [c for c in (rdr.fieldnames or [])]
    lower = {c.lower(): c for c in cols}
    amt_col = next((lower[c] for c in lower if "earning" in c and "currency" not in c), None) or \
        next((lower[c] for c in lower if "commission" in c and "currency" not in c and "rate" not in c), None)
    date_col = next((lower[c] for c in lower if "event date" in c or "transaction date" in c or c == "date"), None) or \
        next((lower[c] for c in lower if "date" in c), None)
    item_col = next((lower[c] for c in lower if "item name" in c or "item title" in c or "item id" in c), None)
    if not amt_col:
        raise ValueError(f"No earnings/commission column found. Columns: {', '.join(cols)[:300]}")
    new_rows, new_amt = 0, 0.0
    now = time.time()
    for i, row in enumerate(rdr):
        raw = (row.get(amt_col) or "").replace("$", "").replace(",", "").strip()
        try:
            amt = float(raw)
        except ValueError:
            continue
        ts = now
        dv = (row.get(date_col) or "").strip() if date_col else ""
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M", "%Y-%m-%dT%H:%M:%S"):
            try:
                ts = datetime.strptime(dv[:19], fmt).replace(tzinfo=timezone.utc).timestamp()
                break
            except ValueError:
                pass
        key = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()[:24]
        if store.q("SELECT 1 FROM earnings WHERE key=?", (key,)):
            continue
        store.x("INSERT INTO earnings VALUES (?,?,?,?,?)", (key, ts, amt, (row.get(item_col) or "")[:120] if item_col else "", now))
        new_rows += 1
        new_amt += amt
    store.put("earn_import", now)
    return new_rows, round(new_amt, 2)
