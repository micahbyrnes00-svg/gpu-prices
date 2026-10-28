"""Extra site sections: Buy new, What's my part worth (sell), Discord channels + sharing, and the price data API."""
import json
from urllib.parse import quote, quote_plus

from . import config

# Where each trade-in service is worth suggesting (eBay takes everything).
SELL_FOR = {
    "swappa": {"phone", "laptop", "mac", "console", "handheld", "camera", "gpu"},
    "backmarket": {"phone", "laptop", "mac", "console", "handheld"},
    "decluttr": {"phone", "mac", "console"},
}
SELL_NAMES = {"ebay": "eBay (sell it yourself)", "swappa": "Swappa", "backmarket": "Back Market trade-in", "decluttr": "Decluttr"}
SELL_NOTES = {"ebay": "Most money, most effort: you list, ship and handle buyers.",
              "swappa": "Marketplace with lower fees than eBay; you ship to the buyer.",
              "backmarket": "Instant quote and free shipping label; usually below private-sale prices.",
              "decluttr": "Fast fixed-price trade-in; lowest effort, lowest payout."}
CHANNELS = [  # (channel, what it posts, categories)
    ("#deals", "Every deal across all categories as it appears", None),
    ("#gpu-deals", "Used graphics cards priced below the typical market", "gpu"),
    ("#cpu-deals", "Used processors below market", "cpu"),
    ("#ram-ssd-deals", "Desktop RAM and SSD deals, with price per GB/TB", "ram"),
    ("#monitor-deals", "Gaming monitor deals", "monitor"),
    ("#console-deals", "PlayStation, Xbox, Switch, Steam Deck and ROG Ally deals", "console"),
    ("#iphone-deals", "Unlocked iPhone deals (no locks, no finance)", "phone"),
    ("#market-report", "Weekly report: biggest price drops and 90-day lows", None),
]


def amazon(q, sort=None):
    s = f"&s={sort}" if sort else ""
    return f"https://www.amazon.com/s?k={quote_plus(q)}{s}&tag={quote_plus(config.AMAZON_TAG)}"


def _aff(url, label, beacon, cls="btn"):
    from .site import E
    return f'<a class="{cls}" data-m="{E(beacon)}" href="{E(url)}" rel="sponsored nofollow noopener" target="_blank">{label}</a>'


# ---------------- Buy new ----------------
def buy_new_html(rep):
    """Model-page section: cheapest new listings from well-rated eBay sellers + top-rated on Amazon."""
    from .site import E, money, ebay_search_url
    m, newcur = rep["model"], rep.get("new_current")
    q = m.get("amazon") or m["name"]
    cards = "".join(
        f'<div class="card listing"><div><div class="t">{E(l["title"][:110])}</div>'
        f'<div class="meta">new · {"free shipping" if not l.get("shipping") else money(l["shipping"], 2) + " shipping"} · seller {l["seller_pct"] or 0:.1f}% positive'
        + (f' <span class="save">{(1 - l["total"] / newcur["median"]) * 100:.0f}% under typical new</span>' if newcur and l["total"] <= newcur["median"] * 0.92 else "")
        + f'</div></div><div class="p">{money(l["total"], 2)}</div>{_aff(l["url"] or "#", "View on eBay", "new:" + m["id"])}</div>'
        for l in rep.get("new_listings", [])[:3])
    amz = (_aff(amazon(q, "review-rank"), "Top-rated on Amazon", "amz:top-" + m["id"], "btn alt")
           + _aff(amazon(q), "All new on Amazon", "amz:" + m["id"], "btn ghost")) if config.AMAZON_TAG else ""
    ebay_new = _aff(ebay_search_url((m.get("query") or m["name"]) + " new"), "See all new on eBay", "new:" + m["id"], "btn ghost")
    head = f"Typical new price on eBay: <b>{money(newcur['median'])}</b>. " if newcur else ""
    return (f'<h2 id="new">Buy it new</h2><p class="sub">{head}New comes with a full warranty and return window; '
            f'compare it with the used price above.</p>'
            + (f'<div class="lgrid">{cards}</div>' if cards else "")
            + f'<div class="actions" style="margin-top:10px">{amz}{ebay_new}</div>'
            + ('<p class="k">"Top-rated" opens Amazon sorted by average customer review.</p>' if amz else ""))


def new_page(reports, demo):
    """/new.html: best new-condition deals across every category, plus top-rated links."""
    from .site import CATS, E, ICONS, money, page
    sections = ""
    for c, info in CATS.items():
        reps = [r for r in reports if r["model"]["cat"] == c and r.get("new_current")]
        if not reps:
            continue
        deals = sorted(((r, d) for r in reps for d in r.get("new_deals", [])),
                       key=lambda x: x[1]["total"] / x[0]["new_current"]["median"])[:4]
        dcards = "".join(
            f'<div class="card dealcard"><a href="{r["model"]["id"]}.html#new"><b>{E(r["model"]["name"])}</b></a>'
            f'<div class="tt">{E(d["title"][:90])}</div><div class="row"><span class="p">{money(d["total"], 0)}</span>'
            f'<span class="save">{(1 - d["total"] / r["new_current"]["median"]) * 100:.0f}% under typical new</span></div>'
            f'<div class="k">new · seller {d.get("seller_pct") or 0:.1f}% positive · incl. shipping</div>'
            f'{_aff(d["url"] or "#", "View on eBay", "new:" + r["model"]["id"])}</div>' for r, d in deals)
        rows = "".join(
            f'<tr><td><a href="{r["model"]["id"]}.html#new">{E(r["model"]["name"])}</a></td><td>{money(r["new_current"]["median"])}</td>'
            f'<td>{money(r["current"] and r["current"]["median"])}</td>'
            f'<td>{_aff(amazon(r["model"].get("amazon") or r["model"]["name"], "review-rank"), "Top-rated ↗", "amz:top-" + r["model"]["id"], "pill") if config.AMAZON_TAG else "—"}</td></tr>'
            for r in reps)
        sections += (f'<h2>{ICONS.get(c, "")} {E(info["label"])}</h2>'
                     + (f'<div class="dgrid">{dcards}</div>' if dcards else '<p class="sub">No new-condition deals right now.</p>')
                     + f'<div class="scroll"><table class="tbl"><tr><th>Model</th><th>Typical new</th><th>Typical used</th><th>Amazon</th></tr>{rows}</table></div>')
    body = (f'<h1>Best deals on new tech</h1><p class="sub">New-condition listings priced below the typical new price, '
            f'from well-rated eBay sellers, updated with every price check. Each table shows new vs used, and links to the '
            f'top-rated options on Amazon.</p>{sections}')
    return page("Best Deals on New GPUs, MacBooks, Steam Decks & More — Updated Daily",
                "New-condition tech deals below the typical new price, updated daily, with new vs used prices side by side.",
                body, "new.html", demo, crumbs=[("New deals", None)], pt="new")


# ---------------- What's my part worth ----------------
def sell_page(rep, demo):
    from .site import CATS, E, money, page
    m, cur = rep["model"], rep["current"]
    name = m["name"]
    crumbs = [("What's it worth", "sell.html"), (name, None)]
    if not cur:
        return page(f"What's my {name} worth?", f"Used {name} value.", f"<h1>What's my {E(name)} worth?</h1><p class='sub'>Not enough listings yet.</p>",
                    f"sell-{m['id']}.html", demo, crumbs=crumbs, pt="sell")
    quick = cur["p25"] * 0.92
    links = "".join(
        f'<div class="card"><b>{E(SELL_NAMES[k])}</b><p class="k" style="margin:4px 0 10px">{E(SELL_NOTES[k])}</p>'
        f'<a class="btn ghost" data-m="sell:{k}-{E(m["id"])}" href="{E(url)}" rel="nofollow noopener" target="_blank">Get a price ↗</a></div>'
        for k, url in config.SELL_LINKS.items() if k == "ebay" or m["cat"] in SELL_FOR.get(k, set()))
    upgrades = sorted((r for r in REPORTS if r["model"]["cat"] == m["cat"] and r is not rep and r["current"]
                       and r["current"]["median"] > cur["median"]), key=lambda r: r["current"]["median"])[:3]
    up = "".join(f'<a class="pill" href="{r["model"]["id"]}.html">{E(r["model"]["name"])} · {money(r["current"]["median"])} used</a>' for r in upgrades)
    body = f"""<h1>What's my used {E(name)} worth?</h1>
<p class="sub">Based on {cur['n']} current eBay listings, updated {E(cur['day'])}, including shipping.</p>
<div class="grid3">
<div class="card"><div class="k">Sell fast</div><div class="v">{money(quick)}</div><p class="k">Priced to sell within days.</p></div>
<div class="card main"><div class="k">Fair market value</div><div class="v big">{money(cur['p25'])}–{money(cur['median'])}</div><p class="k">What most buyers pay.</p></div>
<div class="card"><div class="k">Top dollar</div><div class="v">{money(cur['p75'])}</div><p class="k">Mint condition, box and accessories, patient sale.</p></div>
</div>
<p>Buyers pay these prices <b>including shipping</b>, so if you sell on eBay, list a little lower and add shipping, or price with free shipping built in. Selling fees usually take 10–15%.</p>
<h2>Where to sell it</h2><div class="grid3">{links}</div>
<p class="k">Trade-in sites quote instantly but pay below private-sale prices. Check each site accepts your exact model.</p>
{f'<h2>Upgrading?</h2><p>Used prices for the next step up: {up}</p>' if up else ''}
<p><a href="{m['id']}.html">See the full {E(name)} price history and current deals ›</a></p>"""
    desc = f"What is a used {name} worth? Fair value {money(cur['p25'])}–{money(cur['median'])} from live eBay listings, updated daily, plus where to sell it."
    ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": f"How much is my used {name} worth?",
          "acceptedAnswer": {"@type": "Answer", "text": f"About {money(cur['p25'])}–{money(cur['median'])} including shipping, based on current eBay listings. Priced to sell fast: about {money(quick)}."}}]}
    return page(f"What's My {name} Worth? Used Value {money(cur['median'])} — Updated Daily", desc, body,
                f"sell-{m['id']}.html", demo, ld, crumbs, pt="sell")


def sell_index(reports, demo):
    from .site import CATS, E, ICONS, money, page
    groups = ""
    for c, info in CATS.items():
        reps = [r for r in reports if r["model"]["cat"] == c and r["current"]]
        if reps:
            groups += (f'<h2>{ICONS.get(c, "")} {E(info["label"])}</h2><div class="scroll"><table class="tbl"><tr><th>Model</th><th>Worth about</th><th></th></tr>'
                       + "".join(f'<tr><td>{E(r["model"]["name"])}</td><td>{money(r["current"]["p25"])}–{money(r["current"]["median"])}</td>'
                                 f'<td><a href="sell-{r["model"]["id"]}.html">Details ›</a></td></tr>' for r in reps) + "</table></div>")
    body = ('<h1>What\'s my used tech worth?</h1><p class="sub">Selling or trading in? See what your used GPU, CPU, iPhone, MacBook, '
            'console or camera is worth today, from live eBay listings, and where to sell it.</p>' + groups)
    return page("What's My Used Tech Worth? GPU, iPhone, MacBook & Console Values Today",
                "Free used-tech value checker: what your GPU, iPhone, MacBook, Steam Deck or camera is worth today, updated daily.",
                body, "sell.html", demo, crumbs=[("What's it worth", None)], pt="sell")


# ---------------- Discord + sharing ----------------
def share_html(url, text, label="Share"):
    from .site import E, ICONS
    u, t = quote(url, safe=""), quote(text, safe="")
    return (f'<div class="share" data-url="{E(url)}" data-text="{E(text)}"><button class="btn ghost sharebtn" type="button">{ICONS["share"]}{E(label)}</button>'
            f'<a class="pill" target="_blank" rel="noopener" href="https://twitter.com/intent/tweet?url={u}&text={t}">X</a>'
            f'<a class="pill" target="_blank" rel="noopener" href="https://www.facebook.com/sharer/sharer.php?u={u}">Facebook</a>'
            f'<a class="pill" target="_blank" rel="noopener" href="https://www.reddit.com/submit?url={u}&title={t}">Reddit</a>'
            f'<a class="pill" href="sms:?&body={t}%20{u}">Text</a>'
            f'<button class="pill copybtn" type="button">Copy link</button></div>')


SHARE_JS = """document.addEventListener('click',async e=>{const s=e.target.closest('.share');if(!s)return;const url=s.dataset.url,text=s.dataset.text;
if(e.target.closest('.sharebtn')){if(navigator.share){try{await navigator.share({title:text,text,url})}catch{}}else{try{await navigator.clipboard.writeText(url);e.target.closest('.sharebtn').lastChild.textContent='Link copied'}catch{}}}
if(e.target.closest('.copybtn')){try{await navigator.clipboard.writeText(url);e.target.closest('.copybtn').textContent='Copied ✓'}catch{}}});"""


def discord_page(demo):
    from .site import E, ICONS, page, discord_url
    inv = discord_url()
    if not inv:
        return None
    rows = "".join(f'<div class="card"><b>{E(ch)}</b><p class="k" style="margin:4px 0 0">{E(what)}</p></div>' for ch, what, _ in CHANNELS)
    text = "Free Discord that posts used GPU, iPhone, console & tech deals the moment they drop below market price"
    body = f"""<h1>{ICONS["discord"]} The Used Tech Deals Discord</h1>
<p class="sub">Free. A bot checks live eBay listings all day and posts anything priced below the typical market into the right channel, so you see deals before they sell.</p>
<p><a class="btn" data-m="discord" href="{E(inv)}" target="_blank" rel="noopener">Join the Discord</a></p>
<h2>Channels</h2><div class="grid3">{rows}</div>
<h2>Know someone building a PC or hunting a deal?</h2><p>Share the server; it's free for everyone.</p>
{share_html(inv, text, "Share the Discord")}
<p class="k">Deals link to eBay; as an eBay Partner Network affiliate this site may earn a commission, at no cost to you.</p>
<script>{SHARE_JS}</script>"""
    return page("Used Tech Deals Discord — Free GPU, iPhone & Console Deal Alerts", text, body, "discord.html", demo,
                crumbs=[("Discord", None)], pt="discord")


# ---------------- Price data API ----------------
API_VERSION = "v1"


def _model_summary(r):
    c, n = r["current"], r.get("new_current")
    return {"id": r["model"]["id"], "name": r["model"]["name"], "category": r["model"]["cat"],
            "used": c and {"typical": c["median"], "fair_low": c["p25"], "fair_high": c["p75"], "lowest": c["low"],
                           "listings": c["n"], "date": c["day"]},
            "new": n and {"typical": n["median"], "listings": n.get("n")},
            "change_7d_pct": r["chg_7d"], "change_30d_pct": r["chg_30d"], "low_90d": r["low_90d"]}


def write_api(out, reports):
    """Aggregated statistics only (computed here); never raw eBay listing content."""
    from .site import CATS
    if not config.RAPIDAPI_PROXY_SECRET:
        return []
    base = out / "api" / API_VERSION
    (base / "models").mkdir(parents=True)
    (base / "categories").mkdir(parents=True)
    live = [r for r in reports if r["current"]]
    dump = lambda p, o: p.write_text(json.dumps(o, separators=(",", ":")))
    meta = {"source": "Aggregated from live eBay listings including shipping; asking prices, not sold prices.",
            "currency": "USD", "updated": max((r["current"]["day"] for r in live), default=None)}
    dump(base / "categories.json", {**meta, "categories": [{"id": c, "name": v["label"],
         "models": sum(1 for r in live if r["model"]["cat"] == c)} for c, v in CATS.items() if any(r["model"]["cat"] == c for r in live)]})
    dump(base / "models.json", {**meta, "models": [_model_summary(r) for r in live]})
    for c in CATS:
        reps = [r for r in live if r["model"]["cat"] == c]
        if reps:
            dump(base / "categories" / f"{c}.json", {**meta, "category": c, "models": [_model_summary(r) for r in reps]})
    for r in live:
        dump(base / "models" / f"{r['model']['id']}.json", {**meta, **_model_summary(r), "history": [
            {"date": p["day"], "typical": p["median"], "fair_low": p["p25"], "fair_high": p["p75"]} for p in r["series"][-365:]]})
    moves = [r for r in live if r["chg_7d"] is not None]
    dump(base / "movers.json", {**meta, "drops_7d": [_model_summary(r) for r in sorted(moves, key=lambda r: r["chg_7d"])[:10]],
                                "rises_7d": [_model_summary(r) for r in sorted(moves, key=lambda r: -r["chg_7d"])[:10]]})
    (out / "openapi.json").write_text(json.dumps(openapi(), indent=1))
    return []


def openapi():
    model = {"type": "object", "properties": {
        "id": {"type": "string"}, "name": {"type": "string"}, "category": {"type": "string"},
        "used": {"type": "object", "nullable": True, "properties": {k: {"type": "number"} for k in ("typical", "fair_low", "fair_high", "lowest", "listings")}},
        "new": {"type": "object", "nullable": True, "properties": {"typical": {"type": "number"}}},
        "change_7d_pct": {"type": "number", "nullable": True}, "change_30d_pct": {"type": "number", "nullable": True},
        "low_90d": {"type": "number", "nullable": True}}}
    get = lambda summary, desc, params=None: {"get": {"summary": summary, "description": desc, "parameters": params or [],
                                                     "responses": {"200": {"description": "OK", "content": {"application/json": {"schema": {"type": "object"}}}}}}}
    pid = [{"name": "id", "in": "path", "required": True, "schema": {"type": "string"}, "description": "Model id from /models.json, e.g. rtx-3080"}]
    pcat = [{"name": "category", "in": "path", "required": True, "schema": {"type": "string"}, "description": "gpu, cpu, ram, ssd, monitor, console, phone, laptop, mac, handheld, camera"}]
    return {"openapi": "3.0.3", "info": {"title": "Used Tech Price API", "version": API_VERSION,
            "description": "Daily used-market prices for GPUs, CPUs, RAM, SSDs, monitors, consoles, iPhones, gaming laptops, MacBooks, handheld PCs and cameras: typical price, fair range, trends and up to a year of history. Aggregated from live eBay listings including shipping (asking prices, not sold prices). Updated several times a day."},
            "servers": [{"url": f"{config.SITE_URL}/api/{API_VERSION}"}],
            "paths": {"/models.json": get("All models with current prices", "Typical used and new price, fair range, 7/30-day change and 90-day low for every tracked model."),
                      "/models/{id}.json": get("One model with price history", "Current prices plus up to 365 days of daily typical price and fair range.", pid),
                      "/categories.json": get("Categories", "Tracked categories and model counts."),
                      "/categories/{category}.json": get("Models in a category", "Current prices for every model in one category.", pcat),
                      "/movers.json": get("Biggest 7-day movers", "Top 10 price drops and rises over the last 7 days.")},
            "components": {"schemas": {"Model": model}}}


def api_page(demo):
    from .site import E, page
    if not config.RAPIDAPI_PROXY_SECRET:
        return None
    sub = (f'<p><a class="btn" href="{E(config.RAPIDAPI_URL)}" target="_blank" rel="noopener">Get an API key on RapidAPI</a></p>'
           if config.RAPIDAPI_URL else "<p class='sub'>API keys coming soon.</p>")
    eps = [("/models.json", "Every model: typical used & new price, fair range, 7/30-day change, 90-day low"),
           ("/models/{id}.json", "One model plus up to 365 days of daily price history"),
           ("/categories.json", "Tracked categories"), ("/categories/{category}.json", "All models in one category"),
           ("/movers.json", "Biggest 7-day price drops and rises")]
    rows = "".join(f"<tr><td><code>GET {E(p)}</code></td><td>{E(d)}</td></tr>" for p, d in eps)
    body = f"""<h1>Used Tech Price API</h1>
<p class="sub">Daily used-market prices for 75+ models across GPUs, CPUs, RAM, SSDs, monitors, consoles, iPhones, gaming laptops, MacBooks, handhelds and cameras, as clean JSON.</p>
{sub}
<h2>Endpoints</h2><div class="scroll"><table class="tbl"><tr><th>Endpoint</th><th>Returns</th></tr>{rows}</table></div>
<h2>Example</h2><pre class="card" style="overflow:auto">{{"id":"rtx-3080","name":"NVIDIA RTX 3080","category":"gpu",
 "used":{{"typical":412.5,"fair_low":380,"fair_high":455,"lowest":329,"listings":118,"date":"2026-10-28"}},
 "new":{{"typical":699}},"change_7d_pct":-2.1,"change_30d_pct":-4.8,"low_90d":398}}</pre>
<p class="k">Aggregated from live eBay listings including shipping. These are asking prices, not sold prices. Built for price checkers, resellers, repair shops and content creators. OpenAPI spec: <a href="openapi.json">openapi.json</a>.</p>"""
    return page("Used Tech Price API — GPU, iPhone & Console Price Data (JSON)", "Daily used-market price data API for GPUs, iPhones, consoles, MacBooks and more.",
                body, "api.html", demo, crumbs=[("API", None)], pt="api")


REPORTS = []


def write_all(out, reports, demo):
    """Write every extra page. Returns URLs for the sitemap."""
    global REPORTS
    REPORTS = reports
    urls = ["new.html", "sell.html"]
    (out / "new.html").write_text(new_page(reports, demo))
    (out / "sell.html").write_text(sell_index(reports, demo))
    for r in reports:
        (out / f"sell-{r['model']['id']}.html").write_text(sell_page(r, demo))
        if r["current"]:
            urls.append(f"sell-{r['model']['id']}.html")
    d = discord_page(demo)
    if d:
        (out / "discord.html").write_text(d)
        urls.append("discord.html")
    a = api_page(demo)
    if a:
        (out / "api.html").write_text(a)
        urls.append("api.html")
    write_api(out, reports)
    return urls
