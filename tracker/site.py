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


def page(title, desc, body, path, demo=False, jsonld=None):
    canon = f"{config.SITE_URL}/{path}".replace("/index.html", "/")
    banner = '<div class="demo">DEMO DATA — not real prices</div>' if demo else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)}</title><meta name="description" content="{E(desc)}">
<link rel="canonical" href="{canon}"><link rel="icon" href="{FAVICON}">
{'<script type="application/ld+json">' + json.dumps(jsonld) + '</script>' if jsonld else ''}
<meta property="og:title" content="{E(title)}"><meta property="og:description" content="{E(desc)}"><meta property="og:type" content="website">
{'<meta name="robots" content="noindex">' if demo else ''}
<style>{CSS}</style></head><body>{banner}
<header><div class="wrap"><a class="brand" href="index.html">{E(config.SITE_NAME)}</a>
<nav><a href="index.html#gpu">GPUs</a><a href="index.html#ram">RAM</a><a href="about.html">About</a></nav></div></header>
<main class="wrap">{body}</main>
<footer class="wrap">Prices are eBay US fixed-price listings, including shipping, updated automatically.
As an eBay Partner Network affiliate, this site may earn a commission from qualifying purchases made through its links.
<a href="about.html">How prices are calculated</a>.</footer></body></html>"""


def model_page(rep, summary, demo):
    m, cur = rep["model"], rep["current"]
    name = m["name"]
    if not cur:
        body = f"<h1>Used {E(name)} price</h1><p class='sub'>Not enough listings yet. Check back after the next update.</p>"
        return page(f"Used {name} Price", f"Used {name} price tracker.", body, f"{m['id']}.html", demo)
    fair = f"{money(cur['p25'])}–{money(cur['p75'])}"
    per_gb = f'<div class="card"><div class="k">Price per GB</div><div class="v">{money(rep["per_gb"], 2)}</div></div>' if rep.get("per_gb") else ""
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
                 f'<td><a class="btn" href="{E(l["url"] or "#")}" rel="sponsored nofollow noopener" target="_blank">View</a></td></tr>')
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
<h2>Price history</h2><div class="chart">{chart_svg(rep['series'])}</div>
{f'<h2>Market read</h2><div class="ai">{E(summary)}</div>' if summary else ''}
<h2>Cheapest listings from well-rated sellers</h2>{listings}
{faq}"""
    desc = f"Used {name} price today: typically {money(cur['median'])} ({fair}). Price history, trend and the best current eBay listings."
    ld = {"@context": "https://schema.org", "@type": "Product", "name": name,
          "description": f"Used {name} market price tracked daily from eBay listings.",
          "offers": {"@type": "AggregateOffer", "priceCurrency": "USD", "lowPrice": cur["low"],
                     "highPrice": cur["p75"], "offerCount": cur["n"], "itemCondition": "https://schema.org/UsedCondition"}}
    return page(f"Used {name} Price Today — Fair Price & History", desc, body, f"{m['id']}.html", demo, ld)


def table(reports, cat):
    is_ram = cat == "ram"
    head = "<tr><th>Model</th><th>Typical used</th>" + ("<th>$/GB</th>" if is_ram else "") + "<th>7d</th><th>30d</th><th>Deals</th></tr>"
    rows = ""
    for r in reports:
        if r["model"]["cat"] != cat:
            continue
        c = r["current"]
        rows += (f'<tr><td><a href="{r["model"]["id"]}.html">{E(r["model"]["name"])}</a></td>'
                 f"<td>{money(c and c['median'])}</td>"
                 + (f"<td>{money(r.get('per_gb'), 2)}</td>" if is_ram else "")
                 + f"<td>{chg(r['chg_7d'])}</td><td>{chg(r['chg_30d'])}</td>"
                 f"<td>{len(r['deals']) or '—'}</td></tr>")
    return f'<div class="scroll"><table class="tbl">{head}{rows}</table></div>'


def index_page(reports, market, summary, demo):
    from .stats import market_index
    gpu7, gpu30 = market_index(reports, "gpu", "chg_7d"), market_index(reports, "gpu", "chg_30d")
    ram7, ram30 = market_index(reports, "ram", "chg_7d"), market_index(reports, "ram", "chg_30d")
    deals = sorted((d | {"model": r["model"], "median": r["current"]["median"]} for r in reports for d in r["deals"]),
                   key=lambda d: d["total"] / d["median"])[:8]
    deal_rows = "".join(
        f'<tr><td><a href="{d["model"]["id"]}.html">{E(d["model"]["name"])}</a><br><span class="k">{E(d["title"][:70])}</span></td>'
        f"<td>{money(d['total'], 2)}</td><td class='deal'>{(1 - d['total'] / d['median']) * 100:.0f}% under</td>"
        f'<td><a class="btn" href="{E(d["url"] or "#")}" rel="sponsored nofollow noopener" target="_blank">View</a></td></tr>'
        for d in deals)
    deals_html = (f'<div class="scroll"><table class="tbl"><tr><th>Deal</th><th>Total</th><th>vs typical</th><th></th></tr>{deal_rows}</table></div>'
                  if deal_rows else '<p class="sub">No standout deals right now.</p>')
    body = f"""<h1>Used GPU &amp; RAM prices, tracked daily</h1>
<p class="sub">What used graphics cards and memory actually cost right now, from thousands of eBay listings. Updated {E(market)}.</p>
<div class="cards">
<div class="card"><div class="k">GPU market · 7d</div><div class="v">{chg(gpu7)}</div></div>
<div class="card"><div class="k">GPU market · 30d</div><div class="v">{chg(gpu30)}</div></div>
<div class="card"><div class="k">RAM market · 7d</div><div class="v">{chg(ram7)}</div></div>
<div class="card"><div class="k">RAM market · 30d</div><div class="v">{chg(ram30)}</div></div>
</div>
{f'<h2>This week</h2><div class="ai">{E(summary)}</div>' if summary else ''}
<h2>Best deals right now</h2>{deals_html}
<h2 id="gpu">Graphics cards</h2>{table(reports, 'gpu')}
<h2 id="ram">Desktop RAM</h2>{table(reports, 'ram')}"""
    return page(f"{config.SITE_NAME} — Today's Used Prices & Deals",
                "Daily used GPU and RAM price tracker: fair prices, price history, trends and the best current deals.",
                body, "index.html", demo)


def about_page(demo):
    body = """<h1>How prices are calculated</h1>
<p>Every few hours we collect active fixed-price eBay US listings for each tracked model using eBay's official API.</p>
<p>We remove listings that aren't the actual working product (parts, boxes, bundles, laptops, other variants) and statistical outliers, then add shipping to each price.</p>
<ul><li><b>Typical used price</b>: the median of the remaining used and refurbished listings.</li>
<li><b>Fair range</b>: the middle 50% of listings (25th to 75th percentile).</li>
<li><b>Deal</b>: a listing at least 15% under the typical price from a seller with 98%+ positive feedback.</li>
<li><b>Market change</b>: the average change of the typical price across all tracked models.</li></ul>
<p>These are asking prices, not guaranteed sale prices. Always check the listing, seller and return policy before buying.</p>
<p><b>Affiliate disclosure:</b> links to eBay are affiliate links. If you buy through them, this site may earn a commission at no extra cost to you. It does not change which listings are shown.</p>"""
    return page(f"About — {config.SITE_NAME}", "How used GPU and RAM prices are calculated.", body, "about.html", demo)


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


def build(reports, summaries, demo):
    final = config.SITE_DIR
    out = final.parent / (final.name + ".building")
    if out.exists():
        shutil.rmtree(out)
    (out / "data").mkdir(parents=True)
    market_day = max((r["current"]["day"] for r in reports if r["current"]), default="—")
    (out / "index.html").write_text(index_page(reports, market_day, summaries.get("_market"), demo))
    (out / "about.html").write_text(about_page(demo))
    for r in reports:
        (out / f"{r['model']['id']}.html").write_text(model_page(r, summaries.get(r["model"]["id"]), demo))
        (out / "data" / f"{r['model']['id']}.json").write_text(json.dumps({
            "model": r["model"]["name"], "current": r["current"], "change_7d": r["chg_7d"],
            "change_30d": r["chg_30d"], "history": r["series"][-365:]}, indent=1))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls = ["", "about.html"] + [f"{r['model']['id']}.html" for r in reports]
    (out / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"<url><loc>{config.SITE_URL}/{u}</loc><lastmod>{now}</lastmod></url>\n" for u in urls)
        + "</urlset>\n")
    (out / "robots.txt").write_text(
        ("User-agent: *\nDisallow: /\n" if demo else f"User-agent: *\nAllow: /\nSitemap: {config.SITE_URL}/sitemap.xml\n"))
    (out / ".nojekyll").write_text("")
    (out / "404.html").write_text(page(f"Not found — {config.SITE_NAME}", "Page not found.",
        '<h1>Page not found</h1><p class="sub">That page doesn\'t exist. <a href="index.html">See all used GPU &amp; RAM prices</a>.</p>',
        "404.html", demo))
    _sync(out, final)
    shutil.rmtree(out)
