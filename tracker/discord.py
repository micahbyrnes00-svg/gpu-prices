"""Post new deals to a Discord channel through a webhook (no bot account or server needed)."""
import json
import sys
import time
import urllib.error
import urllib.request

from . import config

COLORS = {"gpu": 0x76B900, "cpu": 0xED1C24, "ram": 0x2457D6, "ssd": 0x8E44AD, "monitor": 0x16A085, "console": 0x003791, "phone": 0x555555}


def _send(payload):
    req = urllib.request.Request(config.DISCORD_WEBHOOK, json.dumps(payload).encode(),
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


def post_deals(con, reports, limit=10):
    """Post each new deal once. Returns how many were posted."""
    if not config.DISCORD_WEBHOOK:
        return 0
    con.execute("CREATE TABLE IF NOT EXISTS posted (item_id TEXT PRIMARY KEY, ts REAL)")
    new = []
    for r in reports:
        cur = r["current"]
        for d in r["deals"]:
            if not con.execute("SELECT 1 FROM posted WHERE item_id=?", (d["item_id"],)).fetchone():
                new.append((1 - d["total"] / cur["median"], r, d))
    new.sort(key=lambda x: -x[0])
    per, picked, rest = {}, [], []
    for x in new:  # at most 2 per model per run so one model can't fill the channel
        mid = x[1]["model"]["id"]
        (picked if per.get(mid, 0) < 2 else rest).append(x)
        per[mid] = per.get(mid, 0) + 1
    new = picked + rest
    posted = 0
    for i in range(0, min(len(new), limit), 5):  # up to 5 embeds per message
        embeds = []
        for under, r, d in new[i:i + 5]:
            m = r["model"]
            embeds.append({
                "title": f"{m['name']} · ${d['total']:,.2f} ({under * 100:.0f}% under typical)"[:250],
                "url": d["url"],
                "description": f"{d['title'][:180]}\nTypical used: **${r['current']['median']:,.0f}** · seller {d['seller_pct'] or 0:.1f}% positive\n"
                               f"[Price history]({config.SITE_URL}/{m['id']}.html)",
                "color": COLORS.get(m["cat"], 0x2457D6),
                **({"thumbnail": {"url": d["image"]}} if d.get("image") else {}),
            })
        ok = _send({"username": config.SITE_NAME[:80], "embeds": embeds,
                    "content": "" if i else "New deals (affiliate links: the site may earn a commission)"})
        if not ok:
            break
        for _, _, d in new[i:i + 5]:
            con.execute("INSERT OR IGNORE INTO posted VALUES (?,?)", (d["item_id"], time.time()))
        posted += len(embeds)
        time.sleep(1.5)
    # deals not posted this run (over the limit) are skipped so the channel isn't flooded later
    for _, _, d in new[limit:]:
        con.execute("INSERT OR IGNORE INTO posted VALUES (?,?)", (d["item_id"], time.time()))
    con.commit()
    return posted


def post_report(con, week, summary, drops, lows):
    """Post the weekly market report link once per ISO week."""
    if not config.DISCORD_WEBHOOK:
        return False
    con.execute("CREATE TABLE IF NOT EXISTS posted (item_id TEXT PRIMARY KEY, ts REAL)")
    key = f"report-{week}"
    if con.execute("SELECT 1 FROM posted WHERE item_id=?", (key,)).fetchone():
        return False
    lines = [f"**{r['model']['name']}** ${r['current']['median']:,.0f} (▼ {abs(r['chg_7d']):.1f}% this week)" for r in drops if r["chg_7d"] < 0][:5]
    lines += [f"**{r['model']['name']}** at a 90-day low: ${r['current']['median']:,.0f}" for r in lows][:3]
    desc = ((summary or "")[:600] + "\n\n" if summary else "") + "\n".join(lines)
    ok = _send({"username": config.SITE_NAME[:80], "embeds": [{
        "title": f"Used tech market report — week {week}", "url": f"{config.SITE_URL}/report.html",
        "description": desc[:3800] or "This week's price moves and deals.", "color": 0x2457D6}]})
    if ok:
        con.execute("INSERT OR IGNORE INTO posted VALUES (?,?)", (key, time.time()))
        con.commit()
    return ok
