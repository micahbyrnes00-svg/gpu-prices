"""Post deals, 90-day-low buy signals and the weekly report to Discord through channel webhooks
(no bot account needed). Each category can have its own channel webhook; anything without one goes to
DISCORD_WEBHOOK."""
import json
import os
import sys
import time
import urllib.error
import urllib.request

from . import config

COLORS = {"gpu": 0x76B900, "cpu": 0xED1C24, "ram": 0x2457D6, "ssd": 0x8E44AD, "monitor": 0x16A085, "console": 0x003791, "phone": 0x555555, "laptop": 0xE67E22, "mac": 0xA2AAAD, "handheld": 0x1A9FFF, "camera": 0xC0392B}
CHANNEL_KEY = {"gpu": "GPU", "cpu": "CPU", "ram": "RAMSSD", "ssd": "RAMSSD", "monitor": "MONITOR", "console": "CONSOLE", "phone": "PHONE", "handheld": "CONSOLE", "laptop": "LAPTOP", "mac": "LAPTOP", "camera": "CAMERA"}


def webhook(kind):
    """kind: a category id, 'report', or None for the main channel."""
    key = "REPORT" if kind == "report" else CHANNEL_KEY.get(kind or "", "")
    return (os.environ.get(f"DISCORD_WEBHOOK_{key}") if key else "") or config.DISCORD_WEBHOOK


def _footer():
    invite = os.environ.get("DISCORD_INVITE", "")
    text = f"{config.SITE_URL.split('//')[-1]} · affiliate links may earn a commission"
    if invite:
        text += f" · invite friends: discord.gg/{invite}"
    return {"text": text[:2000]}


def _send(payload, url=None):
    url = url or config.DISCORD_WEBHOOK
    if not url:
        return False
    req = urllib.request.Request(url, json.dumps(payload).encode(),
                                 {"Content-Type": "application/json", "User-Agent": "UsedTechPrices-DealBot/1"})
    for _ in range(3):
        try:
            urllib.request.urlopen(req, timeout=20).read()
            return True
        except urllib.error.HTTPError as e:
            if e.code == 429:  # rate limited: wait the time Discord asks for
                time.sleep(float(json.loads(e.read() or b"{}").get("retry_after", 2)) + 0.5)
                continue
            print(f"  ! discord: HTTP {e.code}", file=sys.stderr)
            return False
        except OSError as e:
            print(f"  ! discord: {e}", file=sys.stderr)
            return False
    return False


def _posted(con, key):
    con.execute("CREATE TABLE IF NOT EXISTS posted (item_id TEXT PRIMARY KEY, ts REAL)")
    return con.execute("SELECT 1 FROM posted WHERE item_id=?", (key,)).fetchone() is not None


def _mark(con, key):
    con.execute("INSERT OR IGNORE INTO posted VALUES (?,?)", (key, time.time()))


def post_deals(con, reports, limit=10):
    """Post each new deal once, to its category's channel. Returns how many were posted."""
    if not any(webhook(c) for c in CHANNEL_KEY):
        return 0
    new = []
    for r in reports:
        cur = r["current"]
        for d in r["deals"]:
            if not _posted(con, d["item_id"]):
                new.append((1 - d["total"] / cur["median"], r, d))
    new.sort(key=lambda x: -x[0])
    per, picked, rest = {}, [], []
    for x in new:  # at most 2 per model per run so one model can't fill the channel
        mid = x[1]["model"]["id"]
        (picked if per.get(mid, 0) < 2 else rest).append(x)
        per[mid] = per.get(mid, 0) + 1
    new = picked + rest
    chosen, skipped = new[:limit], new[limit:]
    groups = {}
    for x in chosen:
        groups.setdefault(webhook(x[1]["model"]["cat"]), []).append(x)
    posted = 0
    for url, items in groups.items():
        if not url:
            continue
        for i in range(0, len(items), 5):  # up to 5 embeds per message
            batch = items[i:i + 5]
            embeds = []
            for under, r, d in batch:
                m = r["model"]
                embeds.append({
                    "title": f"{m['name']} · ${d['total']:,.2f} ({under * 100:.0f}% under typical)"[:250],
                    "url": d["url"],
                    "description": f"{d['title'][:180]}\nTypical used: **${r['current']['median']:,.0f}** · seller {d['seller_pct'] or 0:.1f}% positive\n"
                                   f"[Price history]({config.SITE_URL}/{m['id']}.html)",
                    "color": COLORS.get(m["cat"], 0x2457D6),
                    "footer": _footer(),
                    **({"thumbnail": {"url": d["image"]}} if d.get("image") else {}),
                })
            if not _send({"username": config.SITE_NAME[:80], "embeds": embeds}, url):
                break
            for _, _, d in batch:
                _mark(con, d["item_id"])
            posted += len(embeds)
            time.sleep(1.5)
    for _, _, d in skipped:  # over the limit: skip so the channel isn't flooded later
        _mark(con, d["item_id"])
    con.commit()
    return posted


def post_signals(con, reports):
    """Buy signals: a model's typical price at its lowest in 90 days (once per model per day)."""
    n = 0
    for r in reports:
        cur = r["current"]
        if not cur or len(r["series"]) < 15:
            continue
        prior = [p["median"] for p in r["series"][-91:-1]]
        if not prior or cur["median"] > min(prior):
            continue
        key = f"low-{r['model']['id']}-{cur['day']}"
        url = webhook(r["model"]["cat"])
        if not url or _posted(con, key):
            continue
        m = r["model"]
        ok = _send({"username": config.SITE_NAME[:80], "embeds": [{
            "title": f"Buy signal: {m['name']} at a 90-day low",
            "url": f"{config.SITE_URL}/{m['id']}.html",
            "description": f"Typical used price **${cur['median']:,.0f}** (fair ${cur['p25']:,.0f}–${cur['p75']:,.0f}), "
                           f"the lowest in 90 days. 30-day change: {r['chg_30d'] or 0:+.1f}%.",
            "color": 0x13834F, "footer": _footer()}]}, url)
        if ok:
            _mark(con, key)
            n += 1
            time.sleep(1.5)
    con.commit()
    return n


def post_report(con, week, summary, drops, lows):
    """Post the weekly market report link once per ISO week."""
    url = webhook("report")
    key = f"report-{week}"
    if not url or _posted(con, key):
        return False
    lines = [f"**{r['model']['name']}** ${r['current']['median']:,.0f} (▼ {abs(r['chg_7d']):.1f}% this week)" for r in drops if r["chg_7d"] < 0][:5]
    lines += [f"**{r['model']['name']}** at a 90-day low: ${r['current']['median']:,.0f}" for r in lows][:3]
    desc = ((summary or "")[:600] + "\n\n" if summary else "") + "\n".join(lines)
    ok = _send({"username": config.SITE_NAME[:80], "embeds": [{
        "title": f"Used tech market report — week {week}", "url": f"{config.SITE_URL}/report.html",
        "description": desc[:3800] or "This week's price moves and deals.", "color": 0x2457D6, "footer": _footer()}]}, url)
    if ok:
        _mark(con, key)
        con.commit()
    return ok
