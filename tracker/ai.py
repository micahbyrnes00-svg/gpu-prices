"""Short market summaries. Uses a local AI CLI (Claude Code / Gemini CLI) on the Pi; falls back to a template."""
import json
import shlex
import subprocess
from datetime import date, timedelta

from . import config


def _template(rep: dict) -> str:
    cur = rep["current"]
    if not cur:
        return ""
    name = rep["model"]["name"]
    c30 = rep["chg_30d"]
    trend = ("roughly flat" if c30 is None or abs(c30) < 2 else
             f"up {c30:.0f}%" if c30 > 0 else f"down {abs(c30):.0f}%")
    return (f"Used {name} listings are typically ${cur['median']:,.0f} including shipping, "
            f"{trend} over the last 30 days. Most sell between ${cur['p25']:,.0f} and ${cur['p75']:,.0f}; "
            f"under ${cur['p25']:,.0f} from a well-rated seller is a good buy.")


def _ask(prompt: str) -> str | None:
    if not config.AI_CMD:
        return None
    try:
        r = subprocess.run(shlex.split(config.AI_CMD), input=prompt, capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = r.stdout.strip()
    if r.returncode != 0 or not text or len(text) > 900:
        return None
    return text


def _facts(rep: dict) -> dict:
    cur = rep["current"] or {}
    return {
        "model": rep["model"]["name"], "typical_used_usd": cur.get("median"),
        "fair_range_usd": [cur.get("p25"), cur.get("p75")], "change_7d_pct": rep["chg_7d"],
        "change_30d_pct": rep["chg_30d"], "price_per_gb": rep.get("per_gb"),
        "new_median_usd": (rep["new_current"] or {}).get("median"),
        "recent_daily_medians": [p["median"] for p in rep["series"][-30:]],
    }


def _same(basis, median, tol=0.05) -> bool:
    """True if the cached summary was written from about the same price (within 5%)."""
    return bool(basis and median) and abs(median - basis) / basis <= tol


RULES = ("Write 2-3 plain sentences for a price-tracker website. Use only the numbers given; do not invent facts, "
         "news, or reasons. No hype, no emojis, no headings. Say whether now looks like a good time to buy used, "
         "based only on the trend and range.")


def refresh(con, reports: list[dict], force: bool = False) -> dict:
    """Return {model_id or '_market': text}; regenerates entries older than AI_REFRESH_DAYS."""
    today = date.today().isoformat()
    cutoff = (date.today() - timedelta(days=config.AI_REFRESH_DAYS)).isoformat()
    existing = {r["model_id"]: dict(r) for r in con.execute("SELECT * FROM summaries")}
    out = {}
    for rep in reports:
        mid = rep["model"]["id"]
        old = existing.get(mid)
        if old and old["day"] > cutoff and not force and _same(old.get("basis"), (rep["current"] or {}).get("median")):
            out[mid] = old["text"]
            continue
        if not rep["current"]:
            continue
        text = _ask(f"{RULES}\n\nData:\n{json.dumps(_facts(rep))}") or _template(rep)
        con.execute("INSERT OR REPLACE INTO summaries (model_id, day, text, basis) VALUES (?,?,?,?)",
                    (mid, today, text, rep["current"]["median"]))
        out[mid] = text
    old = existing.get("_market")
    meds = [r["current"]["median"] for r in reports if r["current"]]
    level = sum(meds) / len(meds) if meds else None
    if old and old["day"] > cutoff and not force and _same(old.get("basis"), level):
        out["_market"] = old["text"]
    else:
        facts = [_facts(r) for r in reports if r["current"]]
        slim = [{k: f[k] for k in ("model", "typical_used_usd", "change_7d_pct", "change_30d_pct")} for f in facts]
        text = _ask("Write a 3-4 sentence weekly used tech market report (graphics cards, CPUs, RAM, SSDs, monitors, consoles, iPhones) for a price-tracker homepage. "
                    "Name the biggest movers. " + RULES + f"\n\nData:\n{json.dumps(slim)}")
        if text:
            con.execute("INSERT OR REPLACE INTO summaries (model_id, day, text, basis) VALUES (?,?,?,?)",
                        ("_market", today, text, level))
            out["_market"] = text
    con.commit()
    return out
