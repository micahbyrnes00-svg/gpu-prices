"""Ask Orbit: read-only AI explanations of the Pi's state, via the Claude CLI already installed on the Pi.

The model only receives a text snapshot and answers in text. Tools are disabled, so it cannot run commands
or change anything; it can only explain and suggest.
"""
import json
import os
import shlex
import subprocess
import threading
import time
import uuid
from pathlib import Path

import store

REPO = Path(__file__).resolve().parent.parent
TIMEOUT = 90
MAX_PER_HOUR = 20
_jobs = {}          # id -> {"status", "answer", "error", "ts"}
_lock = threading.Lock()
_busy = threading.Semaphore(1)  # one Claude call at a time on a 4 GB Pi

SYSTEM = (
    "You are Orbit, the assistant inside a Raspberry Pi home-server control app. You get a snapshot of the Pi's "
    "current state and answer the owner's question in plain language for a smart non-expert. Be direct and short "
    "(under 180 words unless asked for detail). Use only the facts in the snapshot; say so if something isn't in it. "
    "You cannot run commands or change anything. If a fix needs a command, say what to run and where, and note the risk. "
    "No markdown headings; short paragraphs or a few bullets are fine."
)


def _cmd():
    base = os.environ.get("AI_CMD", "")
    if not base:
        for line in (REPO / ".env").read_text().splitlines() if (REPO / ".env").exists() else []:
            if line.startswith("AI_CMD="):
                base = line.split("=", 1)[1].strip()
    return shlex.split(base or "claude -p")


def _run(prompt):
    cmd = _cmd()
    attempts = [cmd + ["--tools", ""], cmd + ["--disallowedTools", "Bash", "Edit", "Write", "NotebookEdit", "WebFetch", "WebSearch"], cmd] \
        if os.path.basename(cmd[0]) == "claude" else [cmd]
    last = ""
    for c in attempts:
        try:
            r = subprocess.run(c, input=prompt, capture_output=True, text=True, timeout=TIMEOUT, cwd="/tmp")
        except subprocess.TimeoutExpired:
            raise RuntimeError("Claude took longer than 90 seconds. Try a shorter question.")
        except FileNotFoundError:
            raise RuntimeError("The Claude CLI isn't installed for this user on the Pi.")
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
        last = (r.stderr or r.stdout).strip()
        if "unknown option" not in last.lower() and "error: option" not in last.lower():
            break
    if "login" in last.lower() or "auth" in last.lower():
        raise RuntimeError("Claude on the Pi needs to be signed in again (run `claude` once in the Pi terminal).")
    raise RuntimeError(last[-200:] or "Claude returned nothing.")


def snapshot(status_fn, sampler, unit_logs=None):
    """Compact, factual context for the model."""
    live = sampler.snapshot()
    live.pop("history", None)
    root = next((d for d in live.get("disks", []) if d.get("mount") == "/"), {})
    s = {
        "time": time.strftime("%Y-%m-%d %H:%M %Z"),
        "pi": {"cpu_pct": round(live.get("cpu", 0)), "temp_c": live.get("temp"), "clock_mhz": live.get("clock"),
               "throttled": live.get("throttled"), "uptime_h": round(live.get("uptime", 0) / 3600, 1),
               "load": live.get("load"),
               "mem_used_pct": round((1 - live["mem"]["avail"] / live["mem"]["total"]) * 100) if live.get("mem") else None,
               "root_disk_used_pct": round((1 - root["free"] / root["total"]) * 100) if root.get("total") else None,
               "top_procs": [p["name"] for p in live.get("procs", [])[:5]]},
    }
    try:
        st = status_fn()
        s["services"] = [{"unit": u["unit"], "state": u.get("sub") or u.get("active")} for u in st.get("services", [])]
        s["containers"] = [{"name": c["name"], "state": c.get("state"), "status": c.get("status")} for c in st.get("containers", [])]
        s["timers"] = [{"unit": t["unit"], "last_run": t.get("last"), "next_run": t.get("next")} for t in st.get("timers", [])]
        m = st.get("market") or {}
        s["price_site"] = {"ready": m.get("ready"), "demo": m.get("demo"), "note": m.get("note"), "last_run": m.get("lastRun"),
                           "site": m.get("site"), "deals": len(m.get("deals", [])),
                           "categories": [{"name": c["label"], "chg7_pct": c.get("chg7")} for c in m.get("cats", [])]}
        ts = st.get("tailscale") or {}
        s["tailscale"] = {"funnel_public": ts.get("funnel"), "peers_online": len([p for p in ts.get("peers", []) if p.get("online")])}
    except Exception:  # noqa: BLE001
        pass
    try:
        import analytics, netradar, disks  # noqa: E401
        n = netradar.summary()
        s["internet"] = {"online": n["online"], "latency_ms": n["latency"], "uptime24_pct": n["uptime24"], "outages_24h": len(n["outages"]),
                         "last_speedtest": n["speed"][0] if n["speed"] else None}
        s["lan_devices"] = {"known": len(netradar.devices()), "new_untrusted": sum(1 for d in netradar.devices() if not d["trusted"])}
        mo = analytics.summary()
        s["site_traffic"] = {"visitors_24h": mo["today"].get("u"), "visitors_7d": mo["week"].get("u"), "clicks_7d": mo["clicks7"],
                             "earned_total_usd": mo["earnings"]["total"], "earned_30d_usd": mo["earnings"]["last30"],
                             "amazon": mo["earnings"].get("amazonStatus")}
        s["drives"] = [{k: d.get(k) for k in ("model", "passed", "temp", "hours", "error", "attrs")} for d in disks.cached().get("disks", [])]
    except Exception:  # noqa: BLE001
        pass
    s["recent_alerts"] = [{"when": time.strftime("%m-%d %H:%M", time.localtime(a["ts"])), "title": a["title"], "body": a["body"]}
                          for a in store.q("SELECT ts, title, body FROM alerts ORDER BY id DESC LIMIT 12")]
    if unit_logs:
        s["logs"] = unit_logs[-6000:]
    return s


def _allowed():
    hour = [t for t in store.get("ask_times", []) if t > time.time() - 3600]
    if len(hour) >= MAX_PER_HOUR:
        return False
    store.put("ask_times", hour + [time.time()])
    return True


def answer_now(question, context):
    prompt = f"{SYSTEM}\n\nSnapshot (JSON):\n{json.dumps(context, default=str)[:24000]}\n\nQuestion: {question.strip()[:1500]}"
    with _busy:
        return _run(prompt)


def start(question, context):
    if not question.strip():
        raise ValueError("Ask something first.")
    if not _allowed():
        raise ValueError(f"Limit is {MAX_PER_HOUR} questions an hour. Try again later.")
    jid = uuid.uuid4().hex[:12]
    with _lock:
        for k in [k for k, v in _jobs.items() if v["ts"] < time.time() - 3600]:
            _jobs.pop(k, None)
        _jobs[jid] = {"status": "running", "answer": None, "error": None, "ts": time.time()}

    def work():
        try:
            ans = answer_now(question, context)
            _jobs[jid].update(status="done", answer=ans)
        except Exception as e:  # noqa: BLE001
            _jobs[jid].update(status="error", error=str(e))

    threading.Thread(target=work, daemon=True).start()
    return jid


def job(jid):
    return _jobs.get(jid)
