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


def _openrouter(prompt: str) -> str | None:
    import urllib.request
    body = json.dumps({"model": config.AI_MODEL, "max_tokens": 400, "temperature": 0.3,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=body, headers={
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}", "Content-Type": "application/json",
        "HTTP-Referer": config.SITE_URL, "X-Title": "Orbit used tech prices"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.load(r)
        return clean(d["choices"][0]["message"]["content"])
    except Exception as e:  # never break a build over a summary
        print(f"OpenRouter failed: {str(e)[:120]}")
        return None


def _ask(prompt: str) -> str | None:
    if config.OPENROUTER_API_KEY:
        return _openrouter(prompt)
    if not config.AI_CMD:
        return None
    try:
        r = subprocess.run(shlex.split(config.AI_CMD), input=prompt, capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return clean(r.stdout) if r.returncode == 0 else None


# Phrases that mean the model talked to us instead of writing for readers.
_META = ("---", "```", "_pct", "_usd", "the data", "the prompt", "length limit", "i wrote", "i used", "i've ", "i have ",
         "you might", "let me", "here's", "here is", "null", "json", "as an ai")


def clean(text: str | None) -> str | None:
    """Return reader-facing text, or None if the model added notes, markdown or field names."""
    text = (text or "").strip()
    if not text or len(text) > 900 or "\n\n" in text:
        return None
    low = text.lower()
    if any(m in low for m in _META):
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


RULES = ("Write plain sentences for a price-tracker website. Use only the numbers given; do not invent facts, "
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
        if old and old["day"] > cutoff and not force and clean(old["text"]) and _same(old.get("basis"), (rep["current"] or {}).get("median")):
            out[mid] = old["text"]
            continue
        if not rep["current"]:
            continue
        text = _ask(f"Write 2-3 sentences. {RULES}\n\nData:\n{json.dumps(_facts(rep))}") or _template(rep)
        con.execute("INSERT OR REPLACE INTO summaries (model_id, day, text, basis) VALUES (?,?,?,?)",
                    (mid, today, text, rep["current"]["median"]))
        out[mid] = text
    old = existing.get("_market")
    meds = [r["current"]["median"] for r in reports if r["current"]]
    level = sum(meds) / len(meds) if meds else None
    if old and old["day"] > cutoff and not force and clean(old["text"]) and _same(old.get("basis"), level):
        out["_market"] = old["text"]
    else:
        facts = [_facts(r) for r in reports if r["current"]]
        slim = [{k: f[k] for k in ("model", "typical_used_usd", "change_7d_pct", "change_30d_pct")} for f in facts]
        has_trend = any(f["change_7d_pct"] is not None or f["change_30d_pct"] is not None for f in slim)
        task = ("Name the biggest movers (null change means no data yet; skip those models). " if has_trend else
                "No trend data exists yet: do not mention movers, trends or changes; describe the current price range only. ")
        text = _ask("Write a 3-sentence weekly used tech market report for a price-tracker homepage. " + task + RULES
                    + " Output only the report text for readers: no notes, no commentary about the data or instructions."
                    + f"\n\nData:\n{json.dumps(slim)}")
        if text:
            con.execute("INSERT OR REPLACE INTO summaries (model_id, day, text, basis) VALUES (?,?,?,?)",
                        ("_market", today, text, level))
            out["_market"] = text
    con.commit()
    return out
