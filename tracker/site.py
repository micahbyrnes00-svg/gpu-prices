"""Static site generator. Writes HTML/JSON/sitemap into SITE_DIR (docs/ for GitHub Pages)."""
import html
import json
import shutil
from datetime import datetime, timezone

from . import config

E = html.escape

CSS = """
:root{--bg:#f7f7f5;--card:#fff;--ink:#16181d;--mute:#5d636e;--line:#e3e4e8;--accent:#2457d6;--up:#c0392b;--down:#13834f;--band:rgba(36,87,214,.12)}
@media (prefers-color-scheme:dark){:root{--bg:#0f1115;--card:#171a21;--ink:#e8eaee;--mute:#99a0ab;--line:#2a2f39;--accent:#7aa2ff;--up:#ff7b6b;--down:#4fd18b;--band:rgba(122,162,255,.16)}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.wrap{max-width:1040px;margin:0 auto;padding:0 16px}
header{border-bottom:1px solid var(--line);background:var(--card)}header .wrap{display:flex;gap:20px;align-items:center;height:56px}
.brand{font-weight:700;color:var(--ink)}nav a{color:var(--mute);margin-right:16px}
h1{font-size:28px;margin:28px 0 6px}h2{font-size:20px;margin:32px 0 12px}.sub{color:var(--mute);margin:0 0 20px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.k{color:var(--mute);font-size:13px}.v{font-size:24px;font-weight:700;font-variant-numeric:tabular-nums}
.tbl{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden;font-variant-numeric:tabular-nums}
.tbl th,.tbl td{padding:10px 12px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
.tbl th:first-child,.tbl td:first-child{text-align:left;white-space:normal}.tbl th{font-size:13px;color:var(--mute);font-weight:600}
.scroll{overflow-x:auto}.up{color:var(--up)}.down{color:var(--down)}.flat{color:var(--mute)}
.chart{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}
.chart svg{width:100%;height:auto;display:block}.ai{background:var(--card);border-left:3px solid var(--accent);padding:12px 16px;border-radius:6px}
.btn{display:inline-block;background:var(--accent);color:#fff;padding:6px 12px;border-radius:6px;font-size:14px}.btn:hover{text-decoration:none;opacity:.9}
.demo{background:#ffe08a;color:#3a2d00;text-align:center;padding:8px;font-weight:600}
footer{margin:48px 0 0;padding:20px 0 40px;border-top:1px solid var(--line);color:var(--mute);font-size:13px}
.deal{color:var(--down);font-weight:600}
@media (prefers-color-scheme:dark){.btn{color:#0f1115}}
nav{display:flex;overflow-x:auto;white-space:nowrap;scrollbar-width:none;flex:1}nav::-webkit-scrollbar{display:none}
.btn.alt{background:transparent;color:var(--accent);border:1px solid var(--accent)}
.pill{display:inline-block;padding:6px 12px;border:1px solid var(--line);border-radius:99px;margin:0 6px 8px 0;color:var(--ink);background:var(--card)}
.verdict{font-size:26px;font-weight:800;margin:4px 0}.great{color:var(--down)}.good{color:var(--down)}.fair{color:var(--accent)}.high{color:var(--up)}
.form{display:grid;gap:10px;max-width:560px}.form input,.form select,.form textarea{font:inherit;padding:10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink);width:100%}
.bar{position:relative;height:12px;border-radius:6px;background:linear-gradient(90deg,var(--down),var(--accent) 50%,var(--up));margin:18px 0 6px}
.crumbs{font-size:13px;color:var(--mute);margin:16px 0 -14px}.crumbs a{color:var(--mute)}
.news{margin:24px 0}.newsf{display:flex;gap:8px;flex-wrap:wrap}.newsf input[type=email]{flex:1;min-width:200px;font:inherit;padding:8px 10px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--ink)}
.newsf button{border:0;cursor:pointer;font:inherit}
.flinks{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:4px 16px;margin-bottom:16px}.flinks b{display:block;color:var(--ink);margin:8px 0 4px}.flinks a{display:block;color:var(--mute);padding:2px 0}
.vs{display:grid;grid-template-columns:1fr 1fr;gap:12px}.vs .card h3{margin:0 0 6px;font-size:17px}
.rank{counter-reset:r}.rank .card{display:flex;gap:14px;align-items:center;margin-bottom:10px}.rank .card:before{counter-increment:r;content:counter(r);font:800 22px system-ui;color:var(--accent);min-width:28px}
.rank .grow{flex:1;min-width:0}.rank .card .btn{white-space:nowrap}
@media (max-width:600px){.vs{grid-template-columns:1fr}.rank .card{flex-wrap:wrap}}
.bar i{position:absolute;top:-5px;width:4px;height:22px;background:var(--ink);border-radius:2px}
@media (max-width:600px){.cards{grid-template-columns:1fr 1fr}.hide-sm{display:none}.tbl th,.tbl td{padding:8px}h1{font-size:24px}}
"""


def money(v, d=0):
    return "—" if v is None else f"${v:,.{d}f}"


def chg(v):
    if v is None:
        return '<span class="flat">—</span>'
    cls = "up" if v > 0.5 else "down" if v < -0.5 else "flat"
    arrow = "▲" if v > 0.5 else "▼" if v < -0.5 else "•"
    return f'<span class="{cls}">{arrow} {abs(v):.1f}%</span>'


def chart_svg(series: list[dict], w=800, h=260) -> str:
    pts = series[-90:]
    if len(pts) < 2:
        return '<p class="sub">Chart appears after two days of data.</p>'
    pad_l, pad_r, pad_t, pad_b = 56, 12, 12, 28
    lo = min(p["p25"] for p in pts) * 0.97
    hi = max(p["p75"] for p in pts) * 1.03
    xs = lambda i: pad_l + i * (w - pad_l - pad_r) / (len(pts) - 1)
    ys = lambda v: pad_t + (hi - v) * (h - pad_t - pad_b) / (hi - lo)
    band = " ".join(f"{xs(i):.1f},{ys(p['p75']):.1f}" for i, p in enumerate(pts))
    band += " " + " ".join(f"{xs(i):.1f},{ys(p['p25']):.1f}" for i, p in reversed(list(enumerate(pts))))
    line = " ".join(f"{xs(i):.1f},{ys(p['median']):.1f}" for i, p in enumerate(pts))
    grid = ""
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        y = ys(v)
        grid += f'<line x1="{pad_l}" x2="{w-pad_r}" y1="{y:.1f}" y2="{y:.1f}" stroke="var(--line)"/>'
        grid += f'<text x="{pad_l-8}" y="{y+4:.1f}" text-anchor="end" font-size="12" fill="var(--mute)">${v:,.0f}</text>'
    labels = ""
    for i in sorted({0, len(pts) // 2, len(pts) - 1}):
        anchor = "start" if i == 0 else "end" if i == len(pts) - 1 else "middle"
        labels += f'<text x="{xs(i):.1f}" y="{h-8}" text-anchor="{anchor}" font-size="12" fill="var(--mute)">{pts[i]["day"][5:]}</text>'
    return (
        f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Used price history">{grid}'
        f'<polygon points="{band}" fill="var(--band)"/>'
        f'<polyline points="{line}" fill="none" stroke="var(--accent)" stroke-width="2.5"/>{labels}</svg>'
        '<p class="k" style="margin:6px 0 0">Line = median used price incl. shipping. Band = middle 50% of listings.</p>'
    )


FAVICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
           "%3Crect width='32' height='32' rx='7' fill='%232457d6'/%3E%3Cpath d='M7 22l6-7 5 4 7-9' "
           "stroke='white' stroke-width='3' fill='none' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E")


NAV = ""
CATS = {}
FOOTER_LINKS = ""
RELATED = {}       # model id -> html block: similar models and comparisons
CAT_GUIDES = {}    # category -> html list of guides/comparisons
HOME_GUIDES = ""   # homepage guides block
OG = {}            # page key -> og image path
LAST_WEEK = None

# Accessory searches that pair with each category (Amazon, only when AMAZON_TAG is set)
ACCESSORIES = {
    "gpu": [("850W power supply", "850W ATX 3.0 power supply"), ("PCIe 16-pin power cable", "12VHPWR 16 pin cable"), ("GPU support bracket", "GPU support bracket")],
    "cpu": [("CPU air cooler", "CPU air cooler"), ("Thermal paste", "thermal paste"), ("AM5 / LGA1700 motherboards", "AM5 LGA1700 motherboard")],
    "ram": [("Desktop RAM (new)", "DDR5 32GB desktop memory kit")],
    "ssd": [("NVMe enclosure (USB-C)", "NVMe SSD enclosure USB C"), ("M.2 heatsink", "M.2 SSD heatsink"), ("SATA cable & bracket", "2.5 inch SSD bracket SATA cable")],
    "monitor": [("Monitor arm", "monitor arm"), ("DisplayPort 1.4 cable", "DisplayPort 1.4 cable")],
    "console": [("Extra controller", "PS5 DualSense Xbox wireless controller"), ("Storage expansion", "PS5 NVMe SSD Xbox storage expansion card"), ("Charging station", "controller charging station")],
    "phone": [("iPhone case", "iPhone case MagSafe"), ("USB-C / MagSafe charger", "MagSafe charger 20W USB C"), ("Screen protector", "iPhone tempered glass screen protector")],
}


def ebay_search_url(query):
    """eBay search link carrying the EPN campaign id (paid on any qualifying purchase in the session)."""
    from urllib.parse import urlencode
    q = {"_nkw": query, "LH_ItemCondition": "3000", "LH_BIN": "1"}
    if config.EPN_CAMPAIGN_ID:
        q.update({"mkcid": "1", "mkrid": "711-53200-19255-0", "siteid": "0", "campid": config.EPN_CAMPAIGN_ID,
                  "customid": config.EPN_REFERENCE_ID, "toolid": "10001", "mkevt": "1"})
    return "https://www.ebay.com/sch/i.html?" + urlencode(q)


def amazon_search(q):
    from urllib.parse import quote_plus
    return f"https://www.amazon.com/s?k={quote_plus(q)}&tag={quote_plus(config.AMAZON_TAG)}"


def aff(url, label, beacon, cls="btn"):
    return f'<a class="{cls}" data-m="{E(beacon)}" href="{E(url)}" rel="sponsored nofollow noopener" target="_blank">{label}</a>'


def accessories_html(cat):
    if not config.AMAZON_TAG or cat not in ACCESSORIES:
        return ""
    links = "".join(f'<a class="pill" data-m="amz:acc-{cat}" href="{E(amazon_search(q))}" rel="sponsored nofollow noopener" target="_blank">{E(n)} ↗</a>'
                    for n, q in ACCESSORIES[cat])
    return f'<h2>Often bought with it</h2><p>{links}</p><p class="k">Amazon links (new items).</p>'


def newsletter_html(m=None):
    if not config.NEWSLETTER_URL:
        return ""
    what = f"the {E(m['name'])}" if m else "the models you care about"
    return f"""<div class="card news"><b>Get price-drop emails</b><p class="k" style="margin:4px 0 10px">A short email when prices on {what} fall. Unsubscribe anytime.</p>
<form action="{E(config.NEWSLETTER_URL)}" method="post" target="_blank" class="newsf"><input type="email" name="email" required placeholder="you@example.com" aria-label="Email">
<input type="hidden" name="tag" value="{E(m['id'] if m else 'site')}"><button class="btn" type="submit">Subscribe</button></form></div>"""


def amazon_url(m):
    from urllib.parse import quote_plus
    return f"https://www.amazon.com/s?k={quote_plus(m.get('amazon') or m['name'])}&tag={quote_plus(config.AMAZON_TAG)}"


def per_unit(rep):
    unit = CATS.get(rep["model"]["cat"], {}).get("per")
    if not unit or not rep.get("per_gb"):
        return None, None
    return unit, rep["per_gb"] * (1000 if unit == "TB" else 1)


def page(title, desc, body, path, demo=False, jsonld=None, crumbs=None, og=None, pt="page"):
    canon = f"{config.SITE_URL}/{path}".replace("/index.html", "/")
    banner = '<div class="demo">DEMO DATA — not real prices</div>' if demo else ""
    lds = jsonld if isinstance(jsonld, list) else ([jsonld] if jsonld else [])
    crumb_html = ""
    if crumbs:
        trail = [("Home", "index.html")] + crumbs
        crumb_html = '<nav class="crumbs" aria-label="Breadcrumb">' + ' <span aria-hidden="true">›</span> '.join(
            f'<a href="{E(u)}">{E(n)}</a>' if u else f"<span>{E(n)}</span>" for n, u in trail) + "</nav>"
        lds.append({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": n, "item": f"{config.SITE_URL}/{u or path}".replace("/index.html", "/")}
            for i, (n, u) in enumerate(trail)]})
    body = crumb_html + body
    og_tags = (f'<meta property="og:image" content="{config.SITE_URL}/{og}"><meta property="og:image:width" content="1200">'
               f'<meta property="og:image:height" content="630"><meta name="twitter:card" content="summary_large_image">') if og else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)}</title><meta name="description" content="{E(desc)}">
<link rel="canonical" href="{canon}"><link rel="icon" href="{FAVICON}">
{"".join('<script type="application/ld+json">' + json.dumps(x) + '</script>' for x in lds)}
<meta property="og:title" content="{E(title)}">{og_tags}<meta property="og:url" content="{canon}"><meta property="og:description" content="{E(desc)}"><meta property="og:type" content="website">
{'<meta name="robots" content="noindex">' if demo else ''}
{f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={E(config.ADSENSE_CLIENT)}" crossorigin="anonymous"></script>' if config.ADSENSE_CLIENT and not demo else ''}
<style>{CSS}</style></head><body data-pt="{pt}">{banner}
<header><div class="wrap"><a class="brand" href="index.html">{E(config.SITE_NAME)}</a>
<nav>{NAV}<a href="guides.html">Guides</a><a href="report.html">Report</a><a href="check.html">Price check</a></nav></div></header>
<main class="wrap">{body}</main>
<footer class="wrap">{FOOTER_LINKS}Prices are eBay US fixed-price listings, including shipping, updated automatically.
As an eBay Partner Network affiliate, this site may earn a commission from qualifying purchases made through its links.
{'As an Amazon Associate I earn from qualifying purchases. ' if config.AMAZON_TAG else ''}
<a href="about.html">How prices are calculated</a> · <a href="privacy.html">Privacy</a>.</footer>
<script>document.addEventListener("click",function(e){{var a=e.target.closest&&e.target.closest("a[data-m]");if(a&&navigator.sendBeacon)navigator.sendBeacon("/c?m="+encodeURIComponent(a.dataset.m)+"&p="+(document.body.dataset.pt||"page"))}});</script></body></html>"""


def model_page(rep, summary, demo):
    m, cur = rep["model"], rep["current"]
    name = m["name"]
    if not cur:
        body = f"<h1>Used {E(name)} price</h1><p class='sub'>Not enough listings yet. Check back after the next update.</p>"
        return page(f"Used {name} Price", f"Used {name} price tracker.", body, f"{m['id']}.html", demo)
    fair = f"{money(cur['p25'])}–{money(cur['p75'])}"
    unit, per = per_unit(rep)
    per_gb = f'<div class="card"><div class="k">Price per {unit}</div><div class="v">{money(per, 2)}</div></div>' if per else ""
    amazon = (f'<a class="btn alt" data-m="amz:{E(m["id"])}" href="{E(amazon_url(m))}" rel="sponsored nofollow noopener" target="_blank">Compare new on Amazon</a> '
              if config.AMAZON_TAG else "")
    ebay_all = aff(ebay_search_url(m.get("query") or name), f"See all used {E(name)} on eBay", m["id"])
    actions = f'<p>{ebay_all} {amazon}<a class="btn alt" href="check.html?m={E(m["id"])}">Is my price good?</a></p>'
    cards = f"""<div class="cards">
<div class="card"><div class="k">Typical used price</div><div class="v">{money(cur['median'])}</div></div>
<div class="card"><div class="k">Fair range</div><div class="v" style="font-size:20px">{fair}</div></div>
<div class="card"><div class="k">7 days</div><div class="v" style="font-size:20px">{chg(rep['chg_7d'])}</div></div>
<div class="card"><div class="k">30 days</div><div class="v" style="font-size:20px">{chg(rep['chg_30d'])}</div></div>
{per_gb}
<div class="card"><div class="k">New (median)</div><div class="v" style="font-size:20px">{money((rep['new_current'] or {}).get('median'))}</div></div>
</div>"""
    rows = ""
    for l in rep["listings"]:
        is_deal = l["total"] <= cur["median"] * config.DEAL_RATIO
        tag = ' <span class="deal">Deal</span>' if is_deal else ""
        rows += (f"<tr><td>{E(l['title'][:90])}{tag}</td><td>{money(l['total'], 2)}</td>"
                 f"<td class='hide-sm'>{l['seller_pct'] or 0:.1f}%</td>"
                 f'<td><a class="btn" data-m="{E(rep["model"]["id"])}" href="{E(l["url"] or "#")}" rel="sponsored nofollow noopener" target="_blank">View</a></td></tr>')
    listings = (f'<div class="scroll"><table class="tbl"><tr><th>Listing</th><th>Total</th><th class="hide-sm">Seller</th><th></th></tr>{rows}</table></div>'
                if rows else '<p class="sub">No listings from well-rated sellers right now.</p>')
    buy_under = money(cur["p25"])
    faq = f"""<h2>Common questions</h2>
<p><b>How much is a used {E(name)} worth?</b> Most used {E(name)} listings sell between {fair} including shipping; the typical price is {money(cur['median'])}.</p>
<p><b>What is a good price for a used {E(name)}?</b> Anything under about {buy_under} from a well-rated seller is below most of the market.</p>
<p><b>Are prices going up or down?</b> Over the last 30 days the typical used price changed {chg(rep['chg_30d'])}.</p>"""
    body = f"""<h1>Used {E(name)} price</h1>
<p class="sub">Updated {E(cur['day'])} · based on {cur['n']} current eBay listings</p>
{cards}
{actions}
<h2>Price history</h2><div class="chart">{chart_svg(rep['series'])}</div>
{f'<h2>Market read</h2><div class="ai">{E(summary)}</div>' if summary else ''}
<h2>Cheapest listings from well-rated sellers</h2>{listings}
{faq}
{RELATED.get(m["id"], "")}
{accessories_html(m["cat"])}
{newsletter_html(m)}"""
    desc = f"Used {name} price today: typically {money(cur['median'])} ({fair}). Price history, trend and the best current eBay listings."
    ld = {"@context": "https://schema.org", "@type": "Product", "name": name,
          "description": f"Used {name} market price tracked daily from eBay listings.",
          "offers": {"@type": "AggregateOffer", "priceCurrency": "USD", "lowPrice": cur["low"],
                     "highPrice": cur["p75"], "offerCount": cur["n"], "itemCondition": "https://schema.org/UsedCondition"}}
    faq_ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": f"How much is a used {name} worth?",
         "acceptedAnswer": {"@type": "Answer", "text": f"Most used {name} listings sell between {fair} including shipping; the typical price is {money(cur['median'])}."}},
        {"@type": "Question", "name": f"What is a good price for a used {name}?",
         "acceptedAnswer": {"@type": "Answer", "text": f"Anything under about {buy_under} from a well-rated seller is below most of the market."}}]}
    crumbs = [(CATS.get(m["cat"], {}).get("label", "Prices"), f"{m['cat']}.html"), (name, None)]
    return page(f"Used {name} Price Today: {money(cur['median'])} — Fair Price & History", desc, body, f"{m['id']}.html", demo,
                [ld, faq_ld], crumbs, OG.get(m["id"]), "model")


def table(reports, cat):
    unit = CATS.get(cat, {}).get("per")
    is_ram = bool(unit)
    head = "<tr><th>Model</th><th>Typical used</th>" + (f"<th>$/{unit}</th>" if unit else "") + "<th>7d</th><th>30d</th><th>Deals</th></tr>"
    rows = ""
    for r in reports:
        if r["model"]["cat"] != cat:
            continue
        c = r["current"]
        rows += (f'<tr><td><a href="{r["model"]["id"]}.html">{E(r["model"]["name"])}</a></td>'
                 f"<td>{money(c and c['median'])}</td>"
                 + (f"<td>{money(per_unit(r)[1], 2)}</td>" if is_ram else "")
                 + f"<td>{chg(r['chg_7d'])}</td><td>{chg(r['chg_30d'])}</td>"
                 f"<td>{len(r['deals']) or '—'}</td></tr>")
    return f'<div class="scroll"><table class="tbl">{head}{rows}</table></div>'


def index_page(reports, market, summary, demo):
    from .stats import market_index
    deals = sorted((d | {"model": r["model"], "median": r["current"]["median"]} for r in reports for d in r["deals"]),
                   key=lambda d: d["total"] / d["median"])[:10]
    deal_rows = "".join(
        f'<tr><td><a href="{d["model"]["id"]}.html">{E(d["model"]["name"])}</a><br><span class="k">{E(d["title"][:70])}</span></td>'
        f"<td>{money(d['total'], 2)}</td><td class='deal'>{(1 - d['total'] / d['median']) * 100:.0f}% under</td>"
        f'<td><a class="btn" data-m="{E(d["model"]["id"])}" href="{E(d["url"] or "#")}" rel="sponsored nofollow noopener" target="_blank">View</a></td></tr>'
        for d in deals)
    deals_html = (f'<div class="scroll"><table class="tbl"><tr><th>Deal</th><th>Total</th><th>vs typical</th><th></th></tr>{deal_rows}</table></div>'
                  if deal_rows else '<p class="sub">No standout deals right now.</p>')
    cards = "".join(f'<a class="card" href="{c}.html" style="color:inherit"><div class="k">{E(v["label"])} · 30d</div><div class="v">{chg(market_index(reports, c, "chg_30d"))}</div></a>'
                    for c, v in CATS.items() if any(r["model"]["cat"] == c for r in reports))
    sections = "".join(f'<h2 id="{c}"><a href="{c}.html" style="color:inherit">{E(v["label"])}</a></h2>{table(reports, c)}'
                       for c, v in CATS.items() if any(r["model"]["cat"] == c for r in reports))
    body = f"""<h1>What used tech actually costs today</h1>
<p class="sub">Typical used prices for graphics cards, CPUs, RAM, SSDs, monitors, consoles and iPhones, from thousands of live eBay listings. Updated {E(market)}.</p>
<p><a class="btn" href="check.html">Check a price</a></p>
<div class="cards">{cards}</div>
{f'<h2>This week</h2><div class="ai">{E(summary)}</div>' if summary else ''}
<h2>Best deals right now</h2>{deals_html}
{HOME_GUIDES}
{sections}
{newsletter_html()}"""
    return page(f"{config.SITE_NAME} — Today's Used Prices & Deals",
                "Daily used price tracker for GPUs, CPUs, RAM, SSDs, monitors, consoles and iPhones: fair prices, history, trends and the best current deals.",
                body, "index.html", demo, og=OG.get("home"), pt="home")


def category_page(cat, reports, demo):
    from .stats import market_index
    info = CATS[cat]
    reps = [r for r in reports if r["model"]["cat"] == cat]
    deals = sorted((d | {"model": r["model"], "median": r["current"]["median"]} for r in reps for d in r["deals"]),
                   key=lambda d: d["total"] / d["median"])[:8]
    deal_rows = "".join(
        f'<tr><td><a href="{d["model"]["id"]}.html">{E(d["model"]["name"])}</a><br><span class="k">{E(d["title"][:70])}</span></td>'
        f"<td>{money(d['total'], 2)}</td><td class='deal'>{(1 - d['total'] / d['median']) * 100:.0f}% under</td>"
        f'<td><a class="btn" data-m="{E(d["model"]["id"])}" href="{E(d["url"] or "#")}" rel="sponsored nofollow noopener" target="_blank">View</a></td></tr>'
        for d in deals)
    body = f"""<h1>Used {E(info['label'].lower() if cat != 'phone' else 'iPhone')} prices</h1>
<p class="sub">{E(info.get('intro', ''))} Typical market change: 7 days {chg(market_index(reports, cat, 'chg_7d'))} · 30 days {chg(market_index(reports, cat, 'chg_30d'))}.</p>
{table(reports, cat)}
<h2>Best {E(info['short'])} deals right now</h2>
{f'<div class="scroll"><table class="tbl"><tr><th>Deal</th><th>Total</th><th>vs typical</th><th></th></tr>{deal_rows}</table></div>' if deal_rows else '<p class="sub">No standout deals right now.</p>'}
<p><a class="btn alt" href="check.html">Check a price</a></p>
{CAT_GUIDES.get(cat, "")}
{accessories_html(cat)}
{newsletter_html()}"""
    title = f"Used {info['short']} Prices Today — Fair Prices, History & Deals" if cat != "phone" else "Used iPhone Prices Today — Unlocked iPhone Values & Deals"
    return page(title, f"What used {info['label'].lower()} cost right now: typical prices, trends and deals from live eBay listings.",
                body, f"{cat}.html", demo, crumbs=[(info["label"], None)], og=OG.get("cat-" + cat), pt="category")


def check_page(demo):
    body = r"""<h1>Is this a good price?</h1>
<p class="sub">Paste a listing title or pick a model, enter the total price including shipping, and see how it compares to the live used market.</p>
<div class="form">
<textarea id="t" rows="2" placeholder="Paste a listing title, e.g. ASUS TUF RTX 3080 10GB OC"></textarea>
<select id="m"><option value="">Pick a model…</option></select>
<input id="p" type="number" inputmode="decimal" placeholder="Total price incl. shipping ($)">
</div>
<div id="out" style="margin-top:20px"></div>
<script>
(function(){var D=null,$=function(i){return document.getElementById(i)};
function norm(s){return s.toLowerCase().replace(/\s+/g," ")}
function match(t){t=norm(t);var c=t.replace(/ /g,""),best=null,score=0;D.models.forEach(function(m){
 if(!m.must.every(function(w){w=w.toLowerCase();return t.indexOf(w)>=0||c.indexOf(w.replace(/ /g,""))>=0}))return;
 if(m.exclude.some(function(w){return new RegExp("(^|[^a-z0-9])"+w.toLowerCase().replace(/[.*+?^${}()|[\]\\]/g,"\\$&")+"s?($|[^a-z0-9])").test(t)}))return;
 var s=m.must.join("").length;if(s>score){score=s;best=m}});return best}
function money(v){return "$"+Math.round(v).toLocaleString()}
function run(){var id=$("m").value,p=parseFloat($("p").value),m=D.models.find(function(x){return x.id===id});
 if(!m){$("out").innerHTML="";return}
 if(!m.cur){$("out").innerHTML="<p class='sub'>Not enough data for this model yet.</p>";return}
 var c=m.cur,h='<div class="card"><div class="k">'+m.name+' · typical used</div><div class="v">'+money(c.median)+'</div><div class="k">fair range '+money(c.p25)+'–'+money(c.p75)+(m.low90?' · 90-day low '+money(m.low90):'')+'</div></div>';
 if(p>0){var v,cl;if(p<=c.median*0.85){v="Great deal";cl="great"}else if(p<=c.p25){v="Good price";cl="good"}else if(p<=c.p75){v="Fair price";cl="fair"}else{v="Above market";cl="high"}
  var lo=c.p25-(c.p75-c.p25),hi=c.p75+(c.p75-c.p25),pos=Math.max(0,Math.min(100,(p-lo)/(hi-lo)*100)),d=(p-c.median)/c.median*100;
  h='<div class="verdict '+cl+'">'+v+'</div><p>'+money(p)+' is '+Math.abs(d).toFixed(0)+'% '+(d<0?'below':'above')+' the typical used price.</p>'
   +'<div class="bar"><i style="left:calc('+pos+'% - 2px)"></i></div><div class="k" style="display:flex;justify-content:space-between"><span>cheap</span><span>typical</span><span>expensive</span></div>'+h
   +'<p class="k">Check the seller rating, photos and return policy before buying. Prices well under market can be scams.</p>';
  history.replaceState(null,"","?m="+id+"&p="+p)}
 h+='<p><a class="btn" href="'+m.id+'.html">Price history &amp; best listings</a></p>';$("out").innerHTML=h}
fetch("data/index.json").then(function(r){return r.json()}).then(function(d){D=d;
 var g={};d.models.forEach(function(m){(g[m.cat]=g[m.cat]||[]).push(m)});
 Object.keys(g).forEach(function(k){var og=document.createElement("optgroup");og.label=d.cats[k];g[k].forEach(function(m){var o=document.createElement("option");o.value=m.id;o.textContent=m.name;og.appendChild(o)});$("m").appendChild(og)});
 var q=new URLSearchParams(location.search);if(q.get("m"))$("m").value=q.get("m");if(q.get("p"))$("p").value=q.get("p");run()});
$("t").addEventListener("input",function(){var m=match($("t").value);if(m){$("m").value=m.id;run()}});
$("m").addEventListener("change",run);$("p").addEventListener("input",run);})();
</script>"""
    return page(f"Used Price Checker — Is It a Good Deal? | {config.SITE_NAME}",
                "Check if a used GPU, CPU, RAM kit, SSD, monitor, console or iPhone is a good price, compared to live eBay market data.",
                body, "check.html", demo, crumbs=[("Price check", None)], pt="check")


def privacy_page(demo):
    contact = f' Contact: <a href="mailto:{E(config.CONTACT_EMAIL)}">{E(config.CONTACT_EMAIL)}</a>.' if config.CONTACT_EMAIL else ""
    body = f"""<h1>Privacy</h1>
<p>This site has no accounts and no sign-up. Our web server keeps standard access logs (page requested, time, browser type, referring site) to count visits and keep the site secure. Visitor counts use a one-way hash that changes daily; IP addresses are not stored in our statistics.</p>
<p><b>Affiliate links.</b> Links to eBay{' and Amazon' if config.AMAZON_TAG else ''} are affiliate links. When you click one, that store may set cookies to credit this site for a purchase, under its own privacy policy.</p>
{'<p><b>Advertising.</b> This site uses Google AdSense. Google and its partners use cookies to serve ads based on your visits to this and other websites. You can opt out of personalized advertising at <a href="https://adssettings.google.com" rel="noopener">Google Ads Settings</a>. See <a href="https://policies.google.com/technologies/partner-sites" rel="noopener">how Google uses data from partner sites</a>.</p>' if config.ADSENSE_CLIENT else '<p><b>Advertising.</b> If ads are added, they may be served by Google AdSense, which uses cookies; this page will be updated with details and opt-out links.</p>'}
<p>We don't sell personal information.{contact}</p>"""
    return page(f"Privacy — {config.SITE_NAME}", "Privacy policy.", body, "privacy.html", demo)


def about_page(demo):
    body = """<h1>How prices are calculated</h1>
<p>Every few hours we collect active fixed-price eBay US listings for each tracked model using eBay's official API.</p>
<p>We remove listings that aren't the actual working product (for parts, locked phones, empty boxes, bundles, other variants) and statistical outliers, then add shipping to each price. iPhone prices are for unlocked phones only.</p>
<ul><li><b>Typical used price</b>: the median of the remaining used and refurbished listings.</li>
<li><b>Fair range</b>: the middle 50% of listings (25th to 75th percentile).</li>
<li><b>Deal</b>: a listing at least 15% under the typical price from a seller with 98%+ positive feedback.</li>
<li><b>Market change</b>: the average change of the typical price across all tracked models.</li></ul>
<p>These are asking prices, not guaranteed sale prices. Always check the listing, seller and return policy before buying.</p>
<p><b>Affiliate disclosure:</b> links to eBay are affiliate links. If you buy through them, this site may earn a commission at no extra cost to you. It does not change which listings are shown.</p>"""
    return page(f"About — {config.SITE_NAME}", "How used tech prices are calculated.", body, "about.html", demo)


def _share_images(out, reports, og, pages):
    """Open Graph cards for the home, category, model and comparison pages (skipped if Pillow is missing)."""
    OG.clear()
    (out / "og").mkdir(exist_ok=True)
    host = config.SITE_URL.split("//")[-1]
    brand = f"{config.SITE_NAME} · {host}"
    by = {r["model"]["id"]: r for r in reports}
    live = [r for r in reports if r["current"]]
    if not og.card(out / "og" / "home.png", "What used tech costs today", f"{len(live)} models",
                   "GPUs · CPUs · RAM · SSDs · monitors · consoles · iPhones — updated daily", None, brand):
        return
    OG["home"] = "og/home.png"
    for c, v in CATS.items():
        reps = [r for r in live if r["model"]["cat"] == c]
        if reps:
            lo, hi = min(r["current"]["median"] for r in reps), max(r["current"]["median"] for r in reps)
            og.card(out / "og" / f"cat-{c}.png", f"Used {v['label']} prices", f"{money(lo)}–{money(hi)}",
                    f"{len(reps)} models tracked · typical used prices incl. shipping", None, brand)
            OG["cat-" + c] = f"og/cat-{c}.png"
    for r in live:
        m, cur = r["model"], r["current"]
        og.card(out / "og" / f"{m['id']}.png", f"Used {m['name']}", money(cur["median"]),
                f"typical used · fair {money(cur['p25'])}–{money(cur['p75'])} · {cur['day']}",
                [p["median"] for p in r["series"][-90:]], brand, r["chg_30d"])
        OG[m["id"]] = f"og/{m['id']}.png"
    for a, b in pages.PAIRS:
        if a in by and b in by and by[a]["current"] and by[b]["current"]:
            pid = pages.pair_id(a, b)
            og.card(out / "og" / f"vs-{pid}.png", f"{by[a]['model']['name']} vs {by[b]['model']['name']}",
                    f"{money(by[a]['current']['median'])} vs {money(by[b]['current']['median'])}", "typical used prices incl. shipping", None, brand)
            OG["vs-" + pid] = f"og/vs-{pid}.png"


def _sync(src, dst):
    """Replace dst's contents with src's without removing dst itself (it may be a bind mount)."""
    dst.mkdir(parents=True, exist_ok=True)
    for child in list(dst.iterdir()):
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
    for child in src.iterdir():
        shutil.move(str(child), str(dst / child.name))


def build(reports, summaries, demo, models=None):
    global NAV, CATS
    CATS = (models or config.load_models())["categories"]
    NAV = "".join(f'<a href="{c}.html">{E(v["short"])}</a>' for c, v in CATS.items() if any(r["model"]["cat"] == c for r in reports))
    final = config.SITE_DIR
    out = final.parent / (final.name + ".building")
    if out.exists():
        shutil.rmtree(out)
    (out / "data").mkdir(parents=True)
    from . import og, pages
    _share_images(out, reports, og, pages)
    pages.prepare(reports)
    market_day = max((r["current"]["day"] for r in reports if r["current"]), default="—")
    (out / "index.html").write_text(index_page(reports, market_day, summaries.get("_market"), demo))
    (out / "about.html").write_text(about_page(demo))
    (out / "check.html").write_text(check_page(demo))
    (out / "privacy.html").write_text(privacy_page(demo))
    cats_used = [c for c in CATS if any(r["model"]["cat"] == c for r in reports)]
    for c in cats_used:
        (out / f"{c}.html").write_text(category_page(c, reports, demo))
    (out / "data" / "index.json").write_text(json.dumps({
        "cats": {c: CATS[c]["label"] for c in cats_used},
        "models": [{"id": r["model"]["id"], "name": r["model"]["name"], "cat": r["model"]["cat"],
                    "must": r["model"].get("must", []), "exclude": r["model"].get("exclude", []) + CATS[r["model"]["cat"]].get("exclude", []),
                    "cur": r["current"] and {k: r["current"][k] for k in ("median", "p25", "p75", "low", "n", "day")},
                    "low90": min((p["median"] for p in r["series"][-90:]), default=None)} for r in reports]}, separators=(",", ":")))
    if config.ADSENSE_CLIENT:
        (out / "ads.txt").write_text(f"google.com, {config.ADSENSE_CLIENT.replace('ca-', '')}, DIRECT, f08c47fec0942fa0\n")
    for r in reports:
        (out / f"{r['model']['id']}.html").write_text(model_page(r, summaries.get(r["model"]["id"]), demo))
        (out / "data" / f"{r['model']['id']}.json").write_text(json.dumps({
            "model": r["model"]["name"], "current": r["current"], "change_7d": r["chg_7d"],
            "change_30d": r["chg_30d"], "history": r["series"][-365:]}, indent=1))
    extra, week = pages.write_all(out, reports, summaries, demo)
    global LAST_WEEK
    LAST_WEEK = week
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls = ["", "check.html", "about.html", "privacy.html"] + [f"{c}.html" for c in cats_used] + [f"{r['model']['id']}.html" for r in reports] + extra
    (out / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"<url><loc>{config.SITE_URL}/{u}</loc><lastmod>{now}</lastmod></url>\n" for u in urls)
        + "</urlset>\n")
    (out / "robots.txt").write_text(
        ("User-agent: *\nDisallow: /\n" if demo else f"User-agent: *\nAllow: /\nSitemap: {config.SITE_URL}/sitemap.xml\n"))
    (out / ".nojekyll").write_text("")
    (out / "404.html").write_text(page(f"Not found — {config.SITE_NAME}", "Page not found.",
        '<h1>Page not found</h1><p class="sub">That page doesn\'t exist. <a href="index.html">See all used prices</a>.</p>',
        "404.html", demo))
    _sync(out, final)
    shutil.rmtree(out)
