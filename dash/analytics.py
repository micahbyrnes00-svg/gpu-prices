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
            bot = bool(BOTS.search(ua)) or not ua
            ip = (h.get("cf-connecting-ip") or h.get("x-forwarded-for") or [req.get("client_ip") or req.get("remote_ip", "")])[0].split(",")[0].strip()
            uri = req.get("uri", "/")
            path = urlparse(uri).path
            ts = e.get("ts", time.time())
            day = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")
            visitor = hashlib.sha256(f"{salt}{day}{ip}{ua}".encode()).hexdigest()[:16]  # rotates daily, no raw IPs kept
            ref = (h.get("referer") or [""])[0]
            ref_host = urlparse(ref).netloc if ref else ""
            if bot and e.get("status", 200) < 400:
                continue
            if path == "/c":  # affiliate click beacon from the site
                qd = parse_qs(urlparse(uri).query)
                model = qd.get("m", [""])[0][:60]
                ptype = re.sub(r"[^a-z]", "", qd.get("p", ["page"])[0])[:12] or "page"
                rows.append((ts, "/c/" + ptype, ref_host, visitor, e.get("status", 0), "click", model))
            elif e.get("status", 200) < 400 and not ASSET.search(path) and req.get("method") == "GET":
                rows.append((ts, path, ref_host, visitor, e.get("status", 200), "view", ""))
            elif 400 <= e.get("status", 200) < 500 and path not in ("/favicon.ico", "/robots.txt", "/apple-touch-icon.png"):
                rows.append((ts, path[:120], ref_host, visitor, e.get("status"), "err", ""))
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
    clicked = store.q("SELECT model, COUNT(*) n FROM hits WHERE kind='click' AND ts>? GROUP BY model ORDER BY n DESC LIMIT 6", (now - 30 * 86400,))
    by_page = store.q("SELECT REPLACE(path,'/c/','') pt, COUNT(*) n FROM hits WHERE kind='click' AND ts>? AND path LIKE '/c/%' GROUP BY path ORDER BY n DESC",
                      (now - 30 * 86400,))
    amz7 = one("SELECT COUNT(*) c FROM hits WHERE kind='click' AND model LIKE 'amz:%' AND ts>?", (now - 7 * 86400,))
    daily = store.q("SELECT CAST((ts/86400) AS INT) d, COUNT(DISTINCT visitor) u FROM hits WHERE kind='view' AND ts>? GROUP BY d ORDER BY d",
                    (now - 30 * 86400,))
    earn = earnings_summary()
    return {"today": today, "week": week, "clicks7": clicks.get("c", 0), "clicksToday": clicks_today.get("c", 0),
            "pages": pages, "refs": refs, "clicked": clicked, "dailyVisitors": [r["u"] for r in daily],
            "earnings": earn, "logFound": LOG.exists(), "amazonClicks7": amz7.get("c", 0), "clicksByPage": by_page}


def _env(key):
    """Read a setting from the environment or the repo's .env (the tracker's config file)."""
    if os.environ.get(key):
        return os.environ[key]
    try:
        for line in (Path(__file__).resolve().parent.parent / ".env").read_text().splitlines():
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def amazon_status():
    AMAZON_TAG, AMAZON_SIGNUP = _env("AMAZON_TAG"), _env("AMAZON_SIGNUP")  # Amazon needs 3 qualifying sales within 180 days of signup
    sales = store.q("SELECT COUNT(*) n FROM earnings WHERE source='amazon' AND amount>0")[0]["n"]
    out = {"tag": AMAZON_TAG, "sales": sales, "deadline": None, "daysLeft": None}
    if AMAZON_SIGNUP:
        try:
            dl = datetime.strptime(AMAZON_SIGNUP, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() + 180 * 86400
            out.update(deadline=dl, daysLeft=max(0, round((dl - time.time()) / 86400)))
        except ValueError:
            pass
    return out


def earnings_summary():
    now = time.time()
    def tot(where="", a=()):
        return round(store.q(f"SELECT COALESCE(SUM(amount),0) t FROM earnings {where}", a)[0]["t"], 2)
    recent = store.q("SELECT ts, amount, item, source FROM earnings ORDER BY ts DESC LIMIT 8")
    return {"total": tot(), "last30": tot("WHERE ts>?", (now - 30 * 86400,)),
            "ebay": tot("WHERE COALESCE(source,'ebay')='ebay'"), "amazon": tot("WHERE source='amazon'"),
            "recent": recent, "lastImport": store.get("earn_import"), "amazonStatus": amazon_status()}


def import_tdr(text: str):
    """Import an eBay Partner Network Transaction Detail Report CSV. Returns (new_rows, new_amount)."""
    text = text.lstrip("\ufeff")
    lines = text.splitlines()
    # Amazon Associates reports start with a title line ("Fee-Earnings reports from ...") before the header
    for i, l in enumerate(lines[:5]):
        if "ad fees" in l.lower() or "earnings" in l.lower() and "," in l and len(l.split(",")) > 3:
            lines = lines[i:]
            break
    text = "\n".join(lines)
    delim = "\t" if lines and lines[0].count("\t") > lines[0].count(",") else ","
    rdr = csv.DictReader(io.StringIO(text), delimiter=delim)
    cols = [c for c in (rdr.fieldnames or [])]
    lower = {c.lower(): c for c in cols}
    source = "amazon" if any("ad fee" in c for c in lower) or any("tracking id" in c for c in lower) else "ebay"
    amt_col = next((lower[c] for c in lower if "ad fee" in c), None) or \
        next((lower[c] for c in lower if "earning" in c and "currency" not in c), None) or \
        next((lower[c] for c in lower if "commission" in c and "currency" not in c and "rate" not in c), None)
    date_col = next((lower[c] for c in lower if "date shipped" in c or "event date" in c or "transaction date" in c or c == "date"), None) or \
        next((lower[c] for c in lower if "date" in c), None)
    item_col = next((lower[c] for c in lower if "item name" in c or "item title" in c or c == "name" or "item id" in c), None)
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
        store.x("INSERT INTO earnings (key, ts, amount, item, imported, source) VALUES (?,?,?,?,?,?)",
                (key, ts, amt, (row.get(item_col) or "")[:120] if item_col else "", now, source))
        new_rows += 1
        new_amt += amt
    store.put("earn_import", now)
    return new_rows, round(new_amt, 2), source


def _models():
    try:
        return json.loads((Path(__file__).resolve().parent.parent / "config" / "models.json").read_text())["models"]
    except (OSError, ValueError):
        return []


def _match_model(title, models):
    """Map a commission's item title to a tracked model (same 'must words' rule the tracker uses)."""
    t = " ".join((title or "").lower().split())
    c = t.replace(" ", "")
    best, score = None, 0
    for m in models:
        if all(w.lower() in t or w.lower().replace(" ", "") in c for w in m.get("must", [])):
            s = len("".join(m.get("must", [])))
            if s > score:
                best, score = m, s
    return best


def funnel(days=7):
    """Visitors -> clicks (eBay / Amazon) -> commissions, plus which models earn."""
    since = time.time() - days * 86400
    one = lambda sql, a=(): (store.q(sql, a) or [{}])[0]  # noqa: E731
    v = one("SELECT COUNT(DISTINCT visitor) u, COUNT(*) n FROM hits WHERE kind='view' AND ts>?", (since,))
    ce = one("SELECT COUNT(*) n FROM hits WHERE kind='click' AND ts>? AND model NOT LIKE 'amz:%' AND model!='discord'", (since,))
    ca = one("SELECT COUNT(*) n FROM hits WHERE kind='click' AND ts>? AND model LIKE 'amz:%'", (since,))
    se = one("SELECT COUNT(*) n, COALESCE(SUM(amount),0) t FROM earnings WHERE ts>? AND COALESCE(source,'ebay')='ebay'", (since,))
    sa = one("SELECT COUNT(*) n, COALESCE(SUM(amount),0) t FROM earnings WHERE ts>? AND source='amazon'", (since,))
    models = _models()
    names = {m["id"]: m["name"] for m in models}
    per = {}
    for r in store.q("SELECT model, COUNT(*) n FROM hits WHERE kind='click' AND ts>? GROUP BY model", (since,)):
        mid = (r["model"] or "").removeprefix("amz:")
        if mid in names:
            p = per.setdefault(mid, {"id": mid, "name": names[mid], "ebayClicks": 0, "amzClicks": 0, "sales": 0, "earned": 0.0})
            p["amzClicks" if r["model"].startswith("amz:") else "ebayClicks"] += r["n"]
    for e in store.q("SELECT item, amount FROM earnings WHERE ts>?", (since,)):
        m = _match_model(e["item"], models)
        key = m["id"] if m else "_other"
        p = per.setdefault(key, {"id": key, "name": m["name"] if m else "Other items", "ebayClicks": 0, "amzClicks": 0, "sales": 0, "earned": 0.0})
        p["sales"] += 1
        p["earned"] = round(p["earned"] + (e["amount"] or 0), 2)
    rows = sorted(per.values(), key=lambda p: (-p["earned"], -(p["ebayClicks"] + p["amzClicks"])))[:15]
    visitors = v.get("u") or 0
    clicks = (ce.get("n") or 0) + (ca.get("n") or 0)
    return {"days": days, "visitors": visitors, "views": v.get("n") or 0,
            "ebayClicks": ce.get("n") or 0, "amzClicks": ca.get("n") or 0,
            "ebaySales": se.get("n") or 0, "amzSales": sa.get("n") or 0,
            "ebayEarned": round(se.get("t") or 0, 2), "amzEarned": round(sa.get("t") or 0, 2),
            "clickRate": round(clicks / visitors * 100, 1) if visitors else None,
            "perVisitor": round(((se.get("t") or 0) + (sa.get("t") or 0)) / visitors, 3) if visitors else None,
            "models": rows}
