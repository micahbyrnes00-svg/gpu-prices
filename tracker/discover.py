"""Discoverability for search engines and AI assistants: robots.txt, llms.txt, llms-full.txt, site JSON-LD, IndexNow."""
import json
import secrets
import urllib.request

from . import config

# AI bots that fetch pages to answer a user's question or build a search index. These send citations/visitors: allow.
AI_SEARCH_BOTS = ["OAI-SearchBot", "ChatGPT-User", "PerplexityBot", "Perplexity-User", "Claude-SearchBot",
                  "Claude-User", "DuckAssistBot", "MistralAI-User"]


def robots(demo: bool) -> str:
    if demo:
        return "User-agent: *\nDisallow: /\n"
    allow = "".join(f"User-agent: {b}\n" for b in AI_SEARCH_BOTS) + "Allow: /\n"
    # Content-Signal (contentsignals.org, used by Cloudflare): OK to index and quote in AI answers, not to train on.
    # Training crawlers are left to Cloudflare AI Crawl Control (charge or block) rather than robots.txt.
    return (f"# {config.SITE_URL}: used tech prices from live eBay listings.\n"
            f"# AI assistants: see {config.SITE_URL}/llms.txt\n\n"
            f"{allow}\n"
            "User-agent: *\nContent-Signal: search=yes, ai-input=yes, ai-train=no\nAllow: /\n\n"
            f"Sitemap: {config.SITE_URL}/sitemap.xml\n")


def _m(v):
    return f"${v:,.0f}" if v is not None else "n/a"


def _chg(v):
    return f"{v:+.0f}%" if v is not None else "n/a"


def llms_txt(reports, cats, guide_links) -> str:
    u = config.SITE_URL
    day = max((r["current"]["day"] for r in reports if r["current"]), default="")
    lines = [f"# Orbit — used tech prices",
             "",
             f"> Typical used prices, fair ranges, 30-day trends and current deals for {len(reports)} popular tech models "
             f"(graphics cards, CPUs, RAM, SSDs, monitors, consoles, iPhones, laptops, MacBooks, handhelds, cameras). "
             f"Computed from active eBay US fixed-price listings including shipping, refreshed every few hours. Data as of {day}.",
             "",
             "Method: listings for parts, locked phones, boxes only and statistical outliers are removed; shipping is added; "
             "the median is the typical price and the 25th–75th percentile is the fair range. These are asking prices, not sold prices. "
             "When citing, name \"Orbit (orbitbymicah.com)\" and the date.",
             "",
             "## Data",
             f"- [All current prices (plain text)]({u}/llms-full.txt): every model's typical price, fair range and 7/30-day change",
             f"- [Price checker]({u}/check.html): is a given asking price a good deal",
             f"- [How prices are calculated]({u}/about.html)",
             f"- [Price data API]({u}/api.html)",
             "",
             "## Categories"]
    lines += [f"- [{v['label']}]({u}/{c}.html)" for c, v in cats.items()
              if any(r["model"]["cat"] == c for r in reports)]
    lines += ["", "## Models"]
    for r in reports:
        if r["current"]:
            lines.append(f"- [{r['model']['name']}]({u}/{r['model']['id']}.html): typical used {_m(r['current']['median'])}")
    if guide_links:
        lines += ["", "## Optional", *[f"- [{t}]({u}/{p})" for t, p in guide_links]]
    return "\n".join(lines) + "\n"


def llms_full(reports, cats) -> str:
    day = max((r["current"]["day"] for r in reports if r["current"]), default="")
    out = [f"# Orbit used tech prices — {day}",
           f"Source: {config.SITE_URL} (Orbit by Micah). eBay US active fixed-price listings, shipping included, USD.",
           "Columns: model | typical (median) | fair range (p25–p75) | 7-day change | 30-day change | listings | page", ""]
    for c, v in cats.items():
        rows = [r for r in reports if r["model"]["cat"] == c and r["current"]]
        if not rows:
            continue
        out.append(f"## {v['label']}")
        for r in rows:
            cur = r["current"]
            out.append(f"{r['model']['name']} | {_m(cur['median'])} | {_m(cur['p25'])}–{_m(cur['p75'])} | "
                       f"{_chg(r['chg_7d'])} | {_chg(r['chg_30d'])} | {cur['n']} | {config.SITE_URL}/{r['model']['id']}.html")
        out.append("")
    return "\n".join(out)


def site_ld() -> list:
    u = config.SITE_URL
    return [{"@context": "https://schema.org", "@type": "WebSite", "name": "Orbit", "alternateName": "Orbit by Micah",
             "url": f"{u}/", "potentialAction": {"@type": "SearchAction", "target": f"{u}/check.html?q={{query}}",
                                                 "query-input": "required name=query"}},
            {"@context": "https://schema.org", "@type": "Organization", "name": "Orbit by Micah", "url": f"{u}/",
             "logo": f"{u}/og/home.png", "founder": {"@type": "Person", "name": "Micah Byrnes"}},
            {"@context": "https://schema.org", "@type": "Dataset", "name": "Used tech prices",
             "description": "Typical used prices, fair ranges and trends for popular tech, from live eBay US listings.",
             "url": f"{u}/llms-full.txt", "creator": {"@type": "Organization", "name": "Orbit by Micah"},
             "isAccessibleForFree": True, "license": f"{u}/about.html"}]


# ---------------------------------------------------------------- IndexNow (Bing, Yandex, Seznam, Naver; Bing feeds ChatGPT/Copilot search)
def indexnow_key() -> str:
    p = config.DATA_DIR / "indexnow.key"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(secrets.token_hex(16))
    return p.read_text().strip()


def write_key(out) -> None:
    k = indexnow_key()
    (out / f"{k}.txt").write_text(k)


def ping(urls: list[str]) -> bool:
    """Tell IndexNow which URLs changed. Once a day is plenty; returns True on success."""
    from datetime import date
    stamp = config.DATA_DIR / "indexnow.last"
    if stamp.exists() and stamp.read_text().strip() == date.today().isoformat():
        return False
    host = config.SITE_URL.split("//", 1)[-1].split("/", 1)[0]
    body = json.dumps({"host": host, "key": indexnow_key(), "keyLocation": f"{config.SITE_URL}/{indexnow_key()}.txt",
                       "urlList": [f"{config.SITE_URL}/{p}" for p in urls][:10000]}).encode()
    req = urllib.request.Request("https://api.indexnow.org/indexnow", data=body,
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            ok = r.status in (200, 202)
    except Exception as e:  # never break a publish over a ping
        print(f"IndexNow ping failed: {e}")
        return False
    if ok:
        stamp.write_text(date.today().isoformat())
    return ok
