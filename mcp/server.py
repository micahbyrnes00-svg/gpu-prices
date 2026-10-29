"""Orbit MCP server: lets AI assistants look up used tech prices from orbitbymicah.com.

Remote MCP over Streamable HTTP (JSON responses, no SSE), Python standard library only.
Reads the aggregated JSON the price worker publishes (site/api/v1); never raw eBay listings.

  ORBIT_DATA   folder with models.json, categories.json, movers.json, models/<id>.json   (default /data)
  ORBIT_STATE  folder for keys.json (paid-tier API keys, {"key": "label"})              (default /state)
  PORT         listen port (default 8000)
  FREE_DAILY   tool calls per day per IP without a key (default 200)
  KEY_DAILY    tool calls per day per API key (default 10000)

Free tier: current prices, search, deal check, categories, movers, last 30 days of history.
API key (header "Authorization: Bearer <key>" or "X-Orbit-Key"): up to 365 days of history, higher limit.
"""
import json
import os
import re
import threading
import time
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DATA = Path(os.environ.get("ORBIT_DATA", "/data"))
STATE = Path(os.environ.get("ORBIT_STATE", "/state"))
SITE = os.environ.get("SITE_URL", "https://orbitbymicah.com").rstrip("/")
FREE_DAILY = int(os.environ.get("FREE_DAILY", "200"))
KEY_DAILY = int(os.environ.get("KEY_DAILY", "10000"))
VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
SOURCE = (f"Source: Orbit ({SITE}). Typical used asking prices from live eBay US listings, shipping included, USD. "
          "Asking prices, not sold prices.")
INSTRUCTIONS = ("Used tech price data (GPUs, CPUs, RAM, SSDs, monitors, consoles, iPhones, gaming laptops, MacBooks, "
                "handheld PCs, cameras). Use search_models to find a model id, then get_price, check_price or "
                f"get_price_history. When citing, name Orbit ({SITE}) and link the model's page.")

# ---------------------------------------------------------------- data (re-read when the worker publishes)
_cache = {}


def _load(name):
    p = DATA / name
    try:
        mt = p.stat().st_mtime
    except OSError:
        return None
    hit = _cache.get(name)
    if hit and hit[0] == mt:
        return hit[1]
    try:
        obj = json.loads(p.read_text())
    except (OSError, ValueError):
        return hit[1] if hit else None
    _cache[name] = (mt, obj)
    return obj


def _models():
    return (_load("models.json") or {}).get("models", [])


def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def _find(q):
    """Best model for an id or a free-text name; None if nothing plausible."""
    ms = _models()
    for m in ms:
        if m["id"] == q:
            return m
    qn = _norm(q)
    qt = set(qn.split())
    best, score = None, 0.0
    for m in ms:
        name = _norm(m["name"])
        toks = set(name.split()) | set(_norm(m["id"]).split())
        if qn == name:
            return m
        overlap = len(qt & toks)
        # every number in the query (3080, 128, 15) must appear: an RTX 3070 is not an RTX 3080
        if any(t.isdigit() or re.match(r"\d", t) for t in qt) and not all(t in toks for t in qt if re.match(r"\d", t)):
            continue
        s = overlap / max(len(qt), 1) + (0.5 if qn in name else 0)
        if s > score:
            best, score = m, s
    return best if score >= 0.5 else None


def _url(m):
    return f"{SITE}/{m['id']}.html"


def _summary(m):
    u = m.get("used") or {}
    return {"id": m["id"], "name": m["name"], "category": m.get("category"),
            "typical_used_usd": u.get("typical"), "fair_range_usd": [u.get("fair_low"), u.get("fair_high")],
            "lowest_listing_usd": u.get("lowest"), "listings": u.get("listings"), "as_of": u.get("date"),
            "typical_new_usd": (m.get("new") or {}).get("typical"),
            "change_7d_pct": m.get("change_7d_pct"), "change_30d_pct": m.get("change_30d_pct"),
            "low_90d_usd": m.get("low_90d"), "page": _url(m)}


def _money(v):
    return f"${v:,.0f}" if isinstance(v, (int, float)) else "n/a"


# ---------------------------------------------------------------- tools
def t_search(a, paid):
    q, cat = _norm(a.get("query", "")), a.get("category")
    out = []
    for m in _models():
        if cat and m.get("category") != cat:
            continue
        hay = _norm(m["name"]) + " " + _norm(m["id"])
        if not q or all(t in hay for t in q.split()):
            out.append({"id": m["id"], "name": m["name"], "category": m.get("category"),
                        "typical_used_usd": (m.get("used") or {}).get("typical")})
    if not out and q:
        m = _find(a.get("query", ""))
        out = [{"id": m["id"], "name": m["name"], "category": m.get("category"),
                "typical_used_usd": (m.get("used") or {}).get("typical")}] if m else []
    return {"results": out[:25], "count": len(out)}


def _need_model(a):
    m = _find(a.get("model", ""))
    if not m:
        raise ToolError(f"No tracked model matches '{a.get('model', '')}'. Use search_models to see tracked models.")
    return m


def t_price(a, paid):
    return _summary(_need_model(a))


def t_check(a, paid):
    m = _need_model(a)
    try:
        price = float(a["price"])
    except (KeyError, TypeError, ValueError):
        raise ToolError("price must be a number in USD (include shipping).")
    u = m.get("used") or {}
    lo, typ, hi = u.get("fair_low"), u.get("typical"), u.get("fair_high")
    if typ is None:
        raise ToolError(f"No current price data for {m['name']}.")
    pct = (price - typ) / typ * 100
    if lo is not None and price < lo * 0.7:
        verdict = "suspiciously low: far below the market; check for a broken, locked or fake item, or a scam"
    elif lo is not None and price < lo:
        verdict = "good deal: below the fair range"
    elif hi is not None and price <= hi:
        verdict = "fair: within the normal range"
    else:
        verdict = "high: above the fair range"
    return {"model": m["name"], "price_usd": price, "verdict": verdict, "vs_typical_pct": round(pct, 1),
            "typical_used_usd": typ, "fair_range_usd": [lo, hi], "as_of": u.get("date"), "page": _url(m)}


def t_category(a, paid):
    cat = a.get("category", "")
    d = _load(f"categories/{cat}.json")
    if not d:
        cats = [c["id"] for c in (_load("categories.json") or {}).get("categories", [])]
        raise ToolError(f"Unknown category '{cat}'. Categories: {', '.join(cats)}.")
    return {"category": cat, "models": [_summary(m) for m in d.get("models", [])], "page": f"{SITE}/{cat}.html"}


def t_categories(a, paid):
    return {"categories": (_load("categories.json") or {}).get("categories", [])}


def t_movers(a, paid):
    d = _load("movers.json") or {}
    drops, rises = [_summary(m) for m in d.get("drops_7d", [])], [_summary(m) for m in d.get("rises_7d", [])]
    note = None if drops or rises else "Not enough history yet for 7-day changes."
    return {"drops_7d": drops, "rises_7d": rises, "note": note, "report": f"{SITE}/report.html"}


def t_history(a, paid):
    m = _need_model(a)
    days = int(a.get("days") or 30)
    cap = 365 if paid else 30
    d = _load(f"models/{m['id']}.json") or {}
    hist = d.get("history", [])[-min(max(days, 1), cap):]
    out = {"model": m["name"], "days": len(hist), "history": hist, "page": _url(m)}
    if days > cap:
        out["note"] = (f"Free access returns the last {cap} days. Up to 365 days needs an Orbit API key "
                       f"({SITE}/api.html).")
    return out


S = lambda props, req=(): {"type": "object", "properties": props, "required": list(req)}
MODEL = {"type": "string", "description": "Model id (e.g. rtx-3080) or name (e.g. 'RTX 3080', 'iPhone 15 Pro 128GB')"}
CAT = {"type": "string", "description": "gpu, cpu, ram, ssd, monitor, console, phone, laptop, mac, handheld or camera"}
TOOLS = {
    "search_models": (t_search, "Find tracked models by name or category. Returns ids, names and typical used prices.",
                      S({"query": {"type": "string", "description": "Words to match, e.g. 'rtx 40', 'macbook air'"},
                         "category": CAT})),
    "get_price": (t_price, "Current typical used price, fair range, lowest listing, new price, 7/30-day change and "
                           "90-day low for one model.", S({"model": MODEL}, ["model"])),
    "check_price": (t_check, "Is this asking price a good deal? Compares a USD price (including shipping) with the "
                             "current used market for the model.",
                    S({"model": MODEL, "price": {"type": "number", "description": "Asking price in USD incl. shipping"}},
                      ["model", "price"])),
    "list_category": (t_category, "Current used prices for every tracked model in a category.", S({"category": CAT}, ["category"])),
    "list_categories": (t_categories, "Tracked categories and how many models each has.", S({})),
    "market_movers": (t_movers, "Biggest 7-day used price drops and rises.", S({})),
    "get_price_history": (t_history, "Daily typical used price and fair range for a model. Free: last 30 days; "
                                     "with an Orbit API key: up to 365 days.",
                          S({"model": MODEL, "days": {"type": "integer", "description": "Days of history (default 30)"}},
                            ["model"])),
}


class ToolError(Exception):
    pass


# ---------------------------------------------------------------- limits and keys
_lock = threading.Lock()
_used = {}  # (day, who) -> count


def _keys():
    try:
        return json.loads((STATE / "keys.json").read_text())
    except (OSError, ValueError):
        return {}


def _allow(who, limit):
    day = date.today().isoformat()
    with _lock:
        for k in [k for k in _used if k[0] != day]:
            del _used[k]
        n = _used.get((day, who), 0)
        if n >= limit:
            return False
        _used[(day, who)] = n + 1
        return True


def _log(who, tool, ok):
    try:
        with open(STATE / "usage.log", "a") as f:
            f.write(json.dumps({"ts": int(time.time()), "who": who, "tool": tool, "ok": ok}) + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------- JSON-RPC
def _result(rid, res):
    return {"jsonrpc": "2.0", "id": rid, "result": res}


def _error(rid, code, msg):
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": msg}}


def handle(msg, who, paid):
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or "method" not in msg:
        return _error(msg.get("id") if isinstance(msg, dict) else None, -32600, "Invalid request")
    rid, method, p = msg.get("id"), msg["method"], msg.get("params") or {}
    if rid is None:  # notification (e.g. notifications/initialized): no response
        return None
    if method == "initialize":
        v = p.get("protocolVersion")
        return _result(rid, {"protocolVersion": v if v in VERSIONS else VERSIONS[0],
                             "capabilities": {"tools": {"listChanged": False}},
                             "serverInfo": {"name": "orbit-used-tech-prices", "title": "Orbit used tech prices",
                                            "version": "1.0.0"},
                             "instructions": INSTRUCTIONS})
    if method == "ping":
        return _result(rid, {})
    if method == "tools/list":
        return _result(rid, {"tools": [{"name": n, "description": d, "inputSchema": s,
                                        "annotations": {"readOnlyHint": True, "openWorldHint": False}}
                                       for n, (_, d, s) in TOOLS.items()]})
    if method == "tools/call":
        name, args = p.get("name"), p.get("arguments") or {}
        if name not in TOOLS:
            return _error(rid, -32602, f"Unknown tool: {name}")
        limit = KEY_DAILY if paid else FREE_DAILY
        if not _allow(who, limit):
            _log(who, name, False)
            return _result(rid, {"isError": True, "content": [{"type": "text", "text":
                f"Daily limit of {limit} calls reached. Higher limits with an Orbit API key: {SITE}/api.html"}]})
        try:
            data = TOOLS[name][0](args, paid)
        except ToolError as e:
            _log(who, name, False)
            return _result(rid, {"isError": True, "content": [{"type": "text", "text": str(e)}]})
        data["source"] = SOURCE
        _log(who, name, True)
        return _result(rid, {"content": [{"type": "text", "text": json.dumps(data)}], "structuredContent": data})
    return _error(rid, -32601, f"Method not found: {method}")


class H(BaseHTTPRequestHandler):
    server_version = "orbit-mcp"
    sys_version = ""

    def _send(self, code, body=None, ctype="application/json"):
        raw = b"" if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
        self.send_response(code)
        if raw:
            self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.split("?")[0] in ("/mcp", "/mcp/"):
            self.send_response(405)
            self.send_header("Allow", "POST")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif self.path == "/healthz":
            self._send(200, {"ok": True, "models": len(_models())})
        else:
            self._send(404, {"error": "not found"})

    def do_DELETE(self):
        self._send(405)

    def do_POST(self):
        if self.path.split("?")[0] not in ("/mcp", "/mcp/"):
            return self._send(404, {"error": "not found"})
        n = int(self.headers.get("Content-Length") or 0)
        if n > 1_000_000:
            return self._send(413, _error(None, -32600, "Request too large"))
        try:
            msg = json.loads(self.rfile.read(n) or b"null")
        except ValueError:
            return self._send(400, _error(None, -32700, "Parse error"))
        auth = self.headers.get("Authorization", "")
        key = auth[7:].strip() if auth.lower().startswith("bearer ") else (self.headers.get("X-Orbit-Key") or "").strip()
        keys = _keys()
        if key and key not in keys:
            return self._send(401, _error(msg.get("id") if isinstance(msg, dict) else None, -32001, "Invalid API key"))
        paid = bool(key)
        who = f"key:{keys[key]}" if paid else "ip:" + (self.headers.get("CF-Connecting-IP") or self.client_address[0])
        if isinstance(msg, list):
            out = [r for r in (handle(m, who, paid) for m in msg) if r is not None]
            return self._send(200, out) if out else self._send(202)
        out = handle(msg, who, paid)
        self._send(202) if out is None else self._send(200, out)


if __name__ == "__main__":
    STATE.mkdir(parents=True, exist_ok=True)
    port = int(os.environ.get("PORT", "8000"))
    print(f"orbit-mcp on :{port}, data {DATA}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
