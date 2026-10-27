"""Status of every outside service the price site and Orbit use, for Settings > Integrations."""
import json
import subprocess
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

import store

REPO = Path(__file__).resolve().parent.parent
ENV = REPO / ".env"
UA = {"User-Agent": "Orbit/1"}
DISCORD_KEYS = [("DISCORD_WEBHOOK", "#deals (main)"), ("DISCORD_WEBHOOK_GPU", "#gpu-deals"), ("DISCORD_WEBHOOK_CPU", "#cpu-deals"),
                ("DISCORD_WEBHOOK_RAMSSD", "#ram-ssd-deals"), ("DISCORD_WEBHOOK_MONITOR", "#monitor-deals"),
                ("DISCORD_WEBHOOK_CONSOLE", "#console-deals"), ("DISCORD_WEBHOOK_PHONE", "#iphone-deals"),
                ("DISCORD_WEBHOOK_REPORT", "#market-report")]


def env_get(key):
    try:
        for line in ENV.read_text().splitlines():
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def env_set(key, val):
    lines = ENV.read_text().splitlines() if ENV.exists() else []
    lines = [l for l in lines if not l.startswith(key + "=")] + [f"{key}={val}"]
    ENV.write_text("\n".join(lines) + "\n")
    ENV.chmod(0o600)


def _sh(cmd, timeout=10):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def discord_counts(force=False):
    """Member and online counts from the public invite endpoint (no login needed). Cached 10 minutes."""
    code = env_get("DISCORD_INVITE").rsplit("/", 1)[-1]
    if not code:
        return None
    c = store.get("discord_counts")
    if c and c.get("code") == code and time.time() - c["ts"] < 600 and not force:
        return c
    try:
        req = urllib.request.Request(f"https://discord.com/api/v10/invites/{code}?with_counts=true", headers=UA)
        d = json.loads(urllib.request.urlopen(req, timeout=10).read())
        c = {"code": code, "ts": time.time(), "members": d.get("approximate_member_count"),
             "online": d.get("approximate_presence_count"), "server": (d.get("guild") or {}).get("name"), "error": None}
    except urllib.error.HTTPError as e:
        c = {"code": code, "ts": time.time(), "members": None, "online": None, "server": None,
             "error": "Invite not found or expired" if e.code == 404 else f"HTTP {e.code}"}
    except OSError as e:
        c = {"code": code, "ts": time.time(), "members": None, "online": None, "server": None, "error": str(e)[:80]}
    store.put("discord_counts", c)
    if c["members"] is not None:
        hist = store.get("discord_hist", {})
        hist[date.today().isoformat()] = c["members"]
        store.put("discord_hist", dict(sorted(hist.items())[-120:]))
    return c


def discord_growth():
    hist = store.get("discord_hist", {})
    if not hist:
        return None
    days = sorted(hist)
    now = hist[days[-1]]
    week = next((hist[d] for d in reversed(days) if d <= date.fromordinal(date.today().toordinal() - 7).isoformat()), hist[days[0]])
    return {"members": now, "week": now - week, "series": [hist[d] for d in days[-30:]]}


def site_check(url, force=False):
    c = store.get("site_up")
    if c and c.get("url") == url and time.time() - c["ts"] < 300 and not force:
        return c
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=UA, method="HEAD"), timeout=10)
        c = {"url": url, "ts": time.time(), "ok": r.status < 400, "code": r.status}
    except urllib.error.HTTPError as e:
        c = {"url": url, "ts": time.time(), "ok": False, "code": e.code}
    except OSError as e:
        c = {"url": url, "ts": time.time(), "ok": False, "code": None, "error": str(e)[:80]}
    store.put("site_up", c)
    return c


def prices_job():
    out = _sh(["systemctl", "show", "gpu-prices.service", "-p", "Result", "-p", "ExecMainExitTimestamp", "--value"])
    parts = out.splitlines()
    return {"result": parts[0] if parts else "", "last": parts[1] if len(parts) > 1 else ""}


def status(amazon_status, widget_has_token):
    site = env_get("SITE_URL")
    items = []
    keys = bool(env_get("EBAY_CLIENT_ID")) and bool(env_get("EBAY_CLIENT_SECRET"))
    job = prices_job()
    ran = job["last"] and job["last"] != "n/a"
    items.append({"id": "ebay", "name": "eBay API keys",
                  "state": ("on" if job["result"] == "success" else "warn") if keys and ran else ("warn" if keys else "off"),
                  "detail": (f"Last price run: {job['result']} · {job['last']}" if ran else "Keys saved, waiting for the first price run") if keys
                  else "Waiting on eBay developer approval. Then run bash p.sh keys and golive.",
                  "link": "https://developer.ebay.com/my/keys", "test": keys})
    epn = env_get("EPN_CAMPAIGN_ID")
    items.append({"id": "epn", "name": "eBay Partner Network", "state": "on" if epn else "off",
                  "detail": f"Campaign {epn} · add payout + tax info in EPN" if epn else "No campaign ID", "link": "https://partnernetwork.ebay.com/"})
    a = amazon_status
    items.append({"id": "amazon", "name": "Amazon Associates", "state": "on" if a.get("tag") else "off",
                  "detail": (f"{a['tag']} · {min(a['sales'], 3)} of 3 sales" + (f" · {a['daysLeft']} days left" if a.get("daysLeft") is not None and a["sales"] < 3 else "")) if a.get("tag") else "Not connected",
                  "link": "https://affiliate-program.amazon.com/home"})
    dc = discord_counts()
    invite = env_get("DISCORD_INVITE")
    hooks = [{"key": k, "label": lbl, "set": bool(env_get(k))} for k, lbl in DISCORD_KEYS]
    items.append({"id": "discord", "name": "Discord deals server",
                  "state": "on" if any(h["set"] for h in hooks) and invite and dc and not dc.get("error") else ("warn" if any(h["set"] for h in hooks) else "off"),
                  "detail": (f"{dc['members']} members · {dc['online']} online" if dc and dc.get("members") is not None else (dc or {}).get("error") or "Add the invite code below")
                  + f" · {sum(h['set'] for h in hooks)} of {len(hooks)} channels connected",
                  "link": f"https://discord.gg/{invite}" if invite else "https://discord.com/app", "test": any(h["set"] for h in hooks)})
    cf = _sh(["systemctl", "is-active", "cloudflared.service"])
    up = site_check(site + "/") if site.startswith("https://") else None
    items.append({"id": "cloudflare", "name": "Cloudflare Tunnel", "state": "on" if cf == "active" and up and up["ok"] else ("warn" if cf == "active" else "off"),
                  "detail": f"cloudflared {cf or 'not installed'} · {site.split('//')[-1] or 'no site URL'} " + (f"answers {up['code']}" if up and up.get("code") else "unreachable" if up else ""),
                  "link": "https://one.dash.cloudflare.com/", "test": bool(site)})
    items.append({"id": "gsc", "name": "Google Search Console", "state": "on" if site else "off",
                  "detail": "Verified · submit the sitemap after go-live", "link": "https://search.google.com/search-console"})
    ads = env_get("ADSENSE_CLIENT")
    items.append({"id": "adsense", "name": "Google AdSense", "state": "on" if ads else "off",
                  "detail": ads or "Apply after a few weeks of real traffic", "link": "https://adsense.google.com/"})
    nl = env_get("NEWSLETTER_URL")
    items.append({"id": "newsletter", "name": "Price-drop emails", "state": "on" if nl else "off",
                  "detail": "Signup form live on the site" if nl else "Make a free Buttondown account, then paste its form URL", "link": "https://buttondown.com/"})
    items.append({"id": "widget", "name": "iPhone widget", "state": "on" if widget_has_token else "off",
                  "detail": "Scriptable · works over Tailscale", "link": None})
    return {"items": items, "discordHooks": hooks, "discordInvite": invite, "discordCounts": dc, "discordGrowth": discord_growth(),
            "amazonTag": a.get("tag"), "siteUrl": site}


def test_discord(key):
    url = env_get(key)
    if not url:
        return False, "That channel isn't connected"
    req = urllib.request.Request(url, json.dumps({"content": "✅ Test from Orbit: this channel is connected."}).encode(),
                                 {"Content-Type": "application/json", "User-Agent": "UsedTechPrices-DealBot/1"})
    try:
        urllib.request.urlopen(req, timeout=15).read()
        return True, "Test message sent"
    except Exception as e:  # noqa: BLE001
        return False, f"Discord rejected it: {str(e)[:60]}"


def test_ebay():
    r = subprocess.run(["python3", "-c", "from tracker.ebay import EbayClient; EbayClient()._get_token(); print('ok')"],
                       cwd=str(REPO), capture_output=True, text=True, timeout=40)
    return ("ok" in r.stdout), ("eBay accepted the keys" if "ok" in r.stdout else (r.stderr.strip().splitlines() or ["failed"])[-1][:120])
