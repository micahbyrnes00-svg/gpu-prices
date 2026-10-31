"""Ask Orbit: read-only AI answers about the Pi, themachine, the tailnet, the site and the market.

Everything is automatic. Each question is routed (no AI call needed for routing) to:
  - a mode, which decides which facts go into the prompt (smaller prompt = faster, better answers),
  - a model tier: "fast" for status questions, "deep" for troubleshooting and log reading,
  - log sources, picked from units/containers the question names or that are failing.
Follow-up questions without their own topic keep the previous mode.

The model only receives text and answers in text; tools are disabled, so it cannot run commands.
Fallback chain: Claude CLI with the tier's model -> Claude CLI default model -> OpenRouter (if a key is set).
"""
import json
import os
import re
import shlex
import subprocess
import threading
import time
import urllib.request
import uuid
from pathlib import Path

import store

REPO = Path(__file__).resolve().parent.parent
MAX_PER_HOUR = 30
TIMEOUT = {"fast": 75, "deep": 160}
_jobs = {}
_lock = threading.Lock()
_busy = threading.Semaphore(1)  # one model call at a time on the Pi

SYSTEM = (
    "You are Orbit, the assistant inside Micah's home-lab control app. The lab is a Raspberry Pi (runs Orbit, the "
    "used-tech price site orbitbymicah.com, cloud backups) and 'themachine' (Ubuntu server: apps, 2 TB data drive, "
    "4 TB backup drive), joined by Tailscale. You get a JSON snapshot focused on the question's topic. Answer in plain "
    "language for a smart non-expert. Use only facts in the snapshot and say when something isn't in it. You cannot run "
    "commands or change anything; if a fix needs a command, give the exact command, where to run it, and the risk. "
    "No markdown headings; short paragraphs or a few bullets."
)
STYLE = {"fast": "Be brief: under 120 words.",
         "deep": "Work out the most likely cause from the evidence (logs, states, timings) before answering. "
                 "Lead with the cause and the fix, then the evidence. Under 220 words."}

# ---------------------------------------------------------------- routing
MODES = {
    "network": ["internet", "wifi", "wi-fi", "speed", "latency", "outage", "router", "lan", "network", "dns", "ping",
                "tailscale", "tailnet", "funnel", "vpn", "derp", "relay", "iphone", "macbook", "peer", "device", "ip address",
                "website down", "site down", "certificate", "cert"],
    "themachine": ["themachine", "the machine", "server", "ubuntu", "celeron", "data drive", "backup drive", "2 tb", "4 tb",
                   "2tb", "4tb", "nas", "share", "samba", "worker"],
    "money": ["money", "earn", "revenue", "commission", "affiliate", "click", "visitor", "traffic", "amazon", "epn",
              "income", "paid", "payout", "discord", "subscriber", "growth", "seo", "google"],
    "market": ["price", "gpu", "rtx", "radeon", "deal", "market", "buy", "worth", "sell", "listing", "cheap", "iphone 1",
               "macbook air", "macbook pro", "console", "ps5", "xbox", "switch", "monitor", "ssd", "ram ", "ddr", "steam deck",
               "camera", "laptop", "cpu price", "ryzen", "intel"],
    "pi": ["pi", "raspberry", "temp", "hot", "cpu", "memory", "ram usage", "disk", "storage", "uptime",
           "throttl", "power", "voltage", "fan", "reboot", "load", "swap", "update", "security", "ssh", "sd card", "usb"],
    # last, so a specific topic wins a tie ("is everything ok on themachine" -> themachine)
    "overview": ["everything", "overall", "all good", "summary", "summarize", "status", "anything", "lab", "home lab", "today",
                 "this week", "health check"],
}
ALERT_MODES = {"prices": "pi", "backup": "pi", "service": "pi", "container": "pi", "temp": "pi", "power": "pi", "disk_full": "pi",
               "smart": "pi", "reboot": "pi", "updates": "pi", "ssh": "pi", "sshfail": "pi", "machine": "themachine",
               "peer": "network", "tskey": "network", "tsupdate": "network", "internet": "network", "speed": "network",
               "site": "network", "slow": "network", "cert": "network", "device": "network", "probe": "network",
               "money": "money", "traffic": "money", "click": "money", "amazon": "money", "discord": "money",
               "deal": "market", "buy": "market"}
TROUBLE = ["why", "fail", "error", "broken", "down", "not working", "isn't working", "doesn't", "won't", "can't", "cannot",
           "fix", "log", "crash", "stopped", "stuck", "slow", "wrong", "problem", "issue", "debug", "diagnos", "alert", "warning",
           "investigate", "explain these"]
ALIASES = {  # words people use -> log source
    "price update": "unit:gpu-prices.service", "prices": "unit:gpu-prices.service", "tracker": "unit:gpu-prices.service",
    "ebay": "unit:gpu-prices.service", "backup": "unit:pi-cloud-backup.service", "google drive": "unit:pi-cloud-backup.service",
    "orbit": "unit:picommand.service", "dashboard": "unit:picommand.service", "app": "unit:picommand.service",
    "tailscale": "unit:tailscaled.service", "funnel": "unit:tailscaled.service", "tunnel": "unit:cloudflared.service",
    "cloudflare": "unit:cloudflared.service", "docker": "unit:docker.service", "vnc": "unit:wayvnc.service",
    "cockpit": "unit:cockpit.socket", "airplay": "unit:shairport-sync.service",
}
ALERT_UNITS = {"prices": "unit:gpu-prices.service", "backup": "unit:pi-cloud-backup.service"}


_rx = {}


def _has(text, words, whole=False):
    """Count words that start a word in text (whole=True: must also end there), so 'app' never matches 'happen'."""
    n = 0
    for w in words:
        key = (w, whole)
        if key not in _rx:
            _rx[key] = re.compile(r"(?<![a-z0-9])" + re.escape(w.strip()) + (r"(?![a-z0-9])" if whole else ""))
        n += bool(_rx[key].search(text))
    return n


def route(question, history, st, alerts):
    """Pick mode, tier and log sources from the question text and current state. Deterministic and instant."""
    q = " " + question.lower() + " "
    scores = {m: _has(q, words) for m, words in MODES.items()}
    best = max(scores, key=scores.get)
    mode = best if scores[best] else None
    trouble = _has(q, TROUBLE) > 0
    about_alert = _has(q, ["alert", "notification", "warning"]) > 0
    if mode is None and about_alert and alerts:
        mode = ALERT_MODES.get(alerts[0].get("rule"), "pi")
    sources = []

    def add(src):
        if src and src not in sources and len(sources) < 2:
            sources.append(src)

    units = [u["unit"] for u in st.get("services", [])] + ["gpu-prices.service", "pi-cloud-backup.service", "picommand.service"]
    for u in units:
        base = u.rsplit(".", 1)[0].lower()
        if _has(q, [base, base.replace("-", " ")], whole=True):
            add("unit:" + u)
    for c in st.get("containers", []):
        if c.get("name") and _has(q, [c["name"].lower()], whole=True):
            add("container:" + c["name"])
    named = bool(sources)
    for word, src in ALIASES.items():
        if mode == "themachine" and src == "unit:pi-cloud-backup.service":
            continue  # themachine has its own local backup; its status is in the snapshot
        if _has(q, [word], whole=True):
            add(src)
    if mode is None and (named or sources):
        mode = "pi"  # a Pi service or container was named
    if mode is None and history:
        mode = history[-1].get("mode")  # follow-up like "and what about yesterday?"
    if mode is None:
        mode = "overview"
    if trouble:
        if (about_alert or _has(q, ["log", "last"])) and alerts and mode not in ("themachine", "market", "money"):
            a = alerts[0]
            add(ALERT_UNITS.get(a.get("rule")))
            m = re.search(r"([\w@.-]+\.(?:service|timer|socket))", a.get("title", ""))
            if m:
                add("unit:" + m.group(1).replace(".timer", ".service"))
            m = re.search(r"Container (\S+)", a.get("title", ""))
            if m:
                add("container:" + m.group(1))
        if not sources and mode in ("overview", "pi", "network"):  # "anything broken?": read whatever is failing
            for u in st.get("services", []):
                if u.get("active") == "failed":
                    add("unit:" + u["unit"])
            for c in st.get("containers", []):
                if c.get("state") not in (None, "running"):
                    add("container:" + c["name"])
    if sources:
        trouble = True
    return {"mode": mode, "tier": "deep" if trouble else "fast", "logs": sources}


# ---------------------------------------------------------------- context per mode
def _pi(sampler):
    live = sampler.snapshot()
    root = next((d for d in live.get("disks", []) if d.get("mount") == "/"), {})
    return {"cpu_pct": round(live.get("cpu", 0)), "temp_c": live.get("temp"), "clock_mhz": live.get("clock"),
            "throttled": live.get("throttled"), "uptime_h": round(live.get("uptime", 0) / 3600, 1), "load": live.get("load"),
            "mem_used_pct": round((1 - live["mem"]["avail"] / live["mem"]["total"]) * 100) if live.get("mem") else None,
            "root_disk_used_pct": round((1 - root["free"] / root["total"]) * 100) if root.get("total") else None,
            "top_procs": [f"{p['name']} {p['cpu']}%" for p in live.get("procs", [])[:5]]}


def _machine(fleet):
    if not fleet:
        return None
    r = fleet.remote_state()
    d = r.get("metrics") or {}
    mem = d.get("mem") or {}
    return {"online": r.get("online"), "status": r.get("status"), "tailnet": r.get("tailnet"),
            "cpu_pct": d.get("cpu"), "temp_c": d.get("temp"), "load": d.get("load"),
            "uptime_h": round(d["uptime"] / 3600, 1) if d.get("uptime") else None,
            "mem_used_pct": round((1 - mem["avail"] / mem["total"]) * 100) if mem.get("total") else None,
            "disks": [{"label": x.get("label"), "mount": x.get("mount"), "mounted": x.get("mounted"),
                       "used_pct": round((1 - x["free"] / x["total"]) * 100) if x.get("total") else None} for x in d.get("disks", [])],
            "drive_health": [{k: v for k, v in x.items() if k in ("label", "status", "temperature", "powerOnHours", "errors", "message")}
                             for x in (d.get("driveHealth") or {}).get("drives", [])],
            "backup": d.get("backup"), "top_procs": [p.get("name") for p in d.get("procs", [])[:5]]}


def _tailnet():
    import tailnet
    s = tailnet.status()
    if s.get("error"):
        return {"error": s["error"]}
    return {"version": s["version"], "update_available": s["updateAvailable"], "health": s["health"],
            "funnel_public": tailnet.serve().get("funnel"), "serve_routes": tailnet.serve().get("routes"),
            "netcheck": {k: v for k, v in tailnet.netcheck().items() if k != "ts"},
            "devices": [{"name": n["name"], "os": n["os"], "online": n["online"], "path": n["path"],
                         "last_seen": time.strftime("%m-%d %H:%M", time.localtime(n["lastSeen"])) if n.get("lastSeen") else None,
                         "key_expires_days": round((n["keyExpiry"] - time.time()) / 86400) if n.get("keyExpiry") else None}
                        for n in [s["self"], *s["peers"]]]}


def _market(st, question):
    m = st.get("market") or {}
    if not m.get("ready"):
        return {"ready": False, "note": m.get("note") or m.get("error")}
    words = [w for w in re.findall(r"[a-z0-9]+", question.lower()) if len(w) > 1]
    asked = [r for r in m.get("rows", []) if sum(w in r["name"].lower() for w in words) >= 2 or
             any(w in r["id"].replace("-", "") for w in words if any(ch.isdigit() for ch in w))]
    movers = sorted((r for r in m.get("rows", []) if r.get("chg7") is not None), key=lambda r: abs(r["chg7"]), reverse=True)[:10]
    slim = lambda r: {"model": r["name"], "typical_usd": r["median"], "chg7_pct": r["chg7"], "chg30_pct": r["chg30"],  # noqa: E731
                      "buy_signal": r["signal"], "price_day": r["day"]}
    return {"demo_data": m.get("demo"), "last_run": m.get("lastRun"),
            "categories": [{"name": c["label"], "chg7_pct": c.get("chg7")} for c in m.get("cats", [])],
            "asked_models": [slim(r) for r in asked[:8]], "biggest_7d_moves": [slim(r) for r in movers],
            "buy_signals": [r["name"] for r in m.get("rows", []) if r.get("signal")][:15],
            "top_deals": [{k: d[k] for k in ("model", "total", "under", "title")} for d in m.get("deals", [])[:6]]}


def _services(st):
    return {"services": [{"unit": u["unit"], "state": u.get("sub") or u.get("active")} for u in st.get("services", [])],
            "containers": [{"name": c["name"], "state": c.get("state"), "status": c.get("status")} for c in st.get("containers", [])],
            "timers": [{"unit": t["unit"], "last": _when(t.get("last")), "next": _when(t.get("next"))} for t in st.get("timers", [])]}


def _when(ts):
    return time.strftime("%m-%d %H:%M", time.localtime(ts)) if ts else None


def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception as e:  # noqa: BLE001
        return {"unavailable": str(e)[:120]}


def build_context(route_, question, p):
    """p: providers dict from server.py (status, sampler, fleet, logs)."""
    st = _safe(p["status"])
    mode = route_["mode"]
    ctx = {"time": time.strftime("%Y-%m-%d %H:%M %Z"), "mode": mode}
    alerts = [{"when": _when(a["ts"]), "title": a["title"], "body": a["body"]}
              for a in store.q("SELECT ts, title, body FROM alerts ORDER BY id DESC LIMIT 15")]
    if mode in ("pi", "overview") or route_["tier"] == "deep":
        ctx["pi"] = _safe(_pi, p["sampler"])
        ctx.update(_safe(_services, st))
    if mode in ("themachine", "overview"):
        ctx["themachine"] = _safe(_machine, p.get("fleet"))
    if mode == "pi":
        import disks
        ctx["pi_drives"] = _safe(lambda: [{k: d.get(k) for k in ("model", "passed", "temp", "hours", "error")}
                                          for d in disks.cached().get("disks", [])])
        import security
        ctx["security"] = _safe(security.summary)
    if mode in ("network", "overview"):
        import netradar
        n = _safe(netradar.summary)
        ctx["internet"] = {k: n.get(k) for k in ("online", "latency", "uptime24", "uptime7")} | {
            "outages_24h": len(n.get("outages") or []), "last_speedtest": (n.get("speed") or [None])[0]}
        if mode == "network":
            devs = _safe(netradar.devices)
            ctx["lan_devices"] = {"count": len(devs) if isinstance(devs, list) else None,
                                  "untrusted": [d.get("host") or d.get("vendor") or d.get("ip") for d in devs if not d.get("trusted")][:10]
                                  if isinstance(devs, list) else []}
            import sitemon
            ctx["websites"] = _safe(sitemon.summary)
        ctx["tailnet"] = _safe(_tailnet)
    if mode in ("money", "overview"):
        import analytics
        mo = _safe(analytics.summary)
        if "unavailable" in mo:
            ctx["site_traffic"] = mo
        else:
            ctx["site_traffic"] = {"visitors_24h": mo["today"].get("u"), "visitors_7d": mo["week"].get("u"),
                                   "clicks_today": mo.get("clicksToday"), "clicks_7d": mo.get("clicks7"),
                                   "earned_total_usd": mo["earnings"]["total"], "earned_30d_usd": mo["earnings"]["last30"],
                                   "amazon": mo["earnings"].get("amazonStatus")}
        if mode == "money":
            ctx["funnel_7d"] = _safe(analytics.funnel, 7)
            import integrations
            ctx["discord"] = _safe(integrations.discord_growth)
    if mode in ("market", "overview"):
        ctx["market"] = _safe(_market, st, question) if mode == "market" else {
            k: v for k, v in _safe(_market, st, question).items() if k in ("demo_data", "last_run", "categories", "buy_signals")}
    ctx["recent_alerts"] = alerts[:15 if route_["tier"] == "deep" else 6]
    for src in route_["logs"]:
        kind, name = src.split(":", 1)
        code, out = p["logs"]({kind: [name], "n": ["120"]})
        if code == 200:
            ctx.setdefault("logs", {})[name] = out[-5000:]
    return ctx


# ---------------------------------------------------------------- model calls
def _env(key, default=""):
    try:
        import integrations
        return os.environ.get(key) or integrations.env_get(key) or default
    except Exception:  # noqa: BLE001
        return os.environ.get(key, default)


def _cmd():
    return shlex.split(_env("AI_CMD", "claude -p") or "claude -p")


_learned = {"flags": None, "bad_models": {}}  # remembered so later questions skip known-failing attempts


def _claude(prompt, tier):
    cmd = _cmd()
    is_claude = os.path.basename(cmd[0]) == "claude"
    model = _env("AI_FAST_MODEL", "haiku") if tier == "fast" else _env("AI_DEEP_MODEL", "sonnet")
    if time.time() - _learned["bad_models"].get(model, 0) < 6 * 3600:
        model = None
    models = [model, None] if is_claude and model and "--model" not in cmd else [None]
    tool_flags = [["--tools", ""], ["--disallowedTools", "Bash", "Edit", "Write", "NotebookEdit", "WebFetch", "WebSearch"], []] \
        if is_claude else [[]]
    if _learned["flags"] is not None and _learned["flags"] in tool_flags:
        tool_flags = [_learned["flags"]]
    last = ""
    for m in models:
        for flags in tool_flags:
            c = cmd + (["--model", m] if m else []) + flags
            try:
                r = subprocess.run(c, input=prompt, capture_output=True, text=True, timeout=TIMEOUT[tier], cwd="/tmp")
            except subprocess.TimeoutExpired:
                raise RuntimeError(f"No answer within {TIMEOUT[tier]} seconds.")
            except FileNotFoundError:
                raise RuntimeError("The Claude CLI isn't installed for this user on the Pi.")
            if r.returncode == 0 and r.stdout.strip():
                _learned["flags"] = flags
                return r.stdout.strip(), m or "claude default"
            last = (r.stderr or r.stdout).strip()
            low = last.lower()
            if "unknown option" in low or "error: option" in low or "unknown argument" in low:
                continue  # older CLI: try the next tool flag style
            break
        low = last.lower()
        if m and "model" in low:
            _learned["bad_models"][m] = time.time()
            continue  # tier model not available on this plan/CLI: retry with the default model
        break
    low = last.lower()
    if "login" in low or "auth" in low or "credential" in low:
        raise RuntimeError("Claude on the Pi needs to be signed in again (run `claude` once in the Pi terminal).")
    raise RuntimeError(last[-200:] or "Claude returned nothing.")


def _openrouter(prompt, tier):
    key = _env("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("no OpenRouter key")
    model = _env("AI_MODEL", "reflection/beam-1.0-501b-a23b")
    body = json.dumps({"model": model, "max_tokens": 700, "temperature": 0.2,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=body, headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json", "X-Title": "Orbit"})
    with urllib.request.urlopen(req, timeout=TIMEOUT[tier]) as r:
        return json.load(r)["choices"][0]["message"]["content"].strip(), model.split("/")[-1]


def _run(prompt, tier):
    try:
        return _claude(prompt, tier)
    except RuntimeError as first:
        try:
            return _openrouter(prompt, tier)
        except Exception:  # noqa: BLE001
            raise first


def _prompt(question, ctx, tier, history):
    convo = "".join(f"\nEarlier question: {h['q'][:300]}\nYour earlier answer: {h['a'][:600]}\n" for h in history[-2:] if h.get("a"))
    return (f"{SYSTEM} {STYLE[tier]}\n\nSnapshot (JSON):\n{json.dumps(ctx, default=str)[:22000]}\n{convo}\n"
            f"Question: {question.strip()[:1500]}")


# ---------------------------------------------------------------- public API
def snapshot(status_fn, sampler, unit_logs=None):
    """Overview context (kept for the weekly digest)."""
    ctx = build_context({"mode": "overview", "tier": "fast", "logs": []}, "",
                        {"status": status_fn, "sampler": sampler, "fleet": None, "logs": lambda q: (404, "")})
    if unit_logs:
        ctx["logs"] = unit_logs[-6000:]
    return ctx


def answer_now(question, context, tier="fast"):
    with _busy:
        return _run(_prompt(question, context, tier, []), tier)[0]


def _allowed():
    hour = [t for t in store.get("ask_times", []) if t > time.time() - 3600]
    if len(hour) >= MAX_PER_HOUR:
        return False
    store.put("ask_times", hour + [time.time()])
    return True


LABELS = {"overview": "Overview", "pi": "Pi", "themachine": "themachine", "network": "Network",
          "money": "Money", "market": "Market"}


def start(question, history, providers):
    """Route, gather context and answer in the background; returns a job id immediately."""
    question = (question or "").strip()
    if not question:
        raise ValueError("Ask something first.")
    if not _allowed():
        raise ValueError(f"Limit is {MAX_PER_HOUR} questions an hour. Try again later.")
    history = [h for h in (history or []) if isinstance(h, dict)][-3:]
    jid = uuid.uuid4().hex[:12]
    with _lock:
        for k in [k for k, v in _jobs.items() if v["ts"] < time.time() - 3600]:
            _jobs.pop(k, None)
        _jobs[jid] = {"status": "running", "answer": None, "error": None, "ts": time.time(), "stage": "Reading your lab…"}

    def work():
        job = _jobs[jid]
        try:
            st = _safe(providers["status"])
            alerts = store.q("SELECT rule, title FROM alerts ORDER BY id DESC LIMIT 1")
            r = route(question, history, st if isinstance(st, dict) else {}, alerts)
            job.update(mode=r["mode"], modeLabel=LABELS.get(r["mode"], r["mode"]), tier=r["tier"],
                       logs=[s.split(":", 1)[1] for s in r["logs"]],
                       stage=("Reading logs and thinking it through…" if r["tier"] == "deep" else "Thinking…"))
            ctx = build_context(r, question, providers)
            with _busy:
                answer, model = _run(_prompt(question, ctx, r["tier"], history), r["tier"])
            job.update(status="done", answer=answer, model=model, secs=round(time.time() - job["ts"]))
        except Exception as e:  # noqa: BLE001
            job.update(status="error", error=str(e))

    threading.Thread(target=work, daemon=True).start()
    return jid


def job(jid):
    return _jobs.get(jid)
