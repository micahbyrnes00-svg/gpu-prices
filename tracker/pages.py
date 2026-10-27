"""Search landing pages (buying guides), head-to-head comparisons, the weekly market report, and share images.

Everything is generated from the tracker's own data on each build. Nothing here invents prices: when a guide has
no qualifying models it says so.
"""
import html
import json
import shutil
from datetime import date, datetime, timezone

from . import config, site
from .site import E, aff, chg, ebay_search_url, money, page

# Approximate relative performance, from public benchmark averages, used only to rank within a budget.
# GPUs: 1440p raster average, RTX 3060 12GB = 100. CPUs: gaming average with a fast GPU, Ryzen 5 5600X = 100.
PERF = {
    "rtx-3060-12gb": 100, "rtx-3060-ti": 120, "rtx-3070": 135, "rtx-3080": 170, "rtx-3090": 190,
    "rtx-4060": 105, "rtx-4070": 165, "rtx-4070-super": 190, "rtx-4080": 255, "rtx-4090": 320,
    "rx-6700-xt": 125, "rx-6800-xt": 175, "rx-7800-xt": 190, "rx-7900-xtx": 270,
    "ryzen-5-5600x": 100, "ryzen-7-5800x3d": 130, "ryzen-5-7600x": 125, "ryzen-7-7800x3d": 150, "ryzen-7-9800x3d": 165,
    "ryzen-9-7950x": 135, "core-i5-12600k": 115, "core-i7-12700k": 122, "core-i7-13700k": 140, "core-i9-13900k": 148,
}
PERF_NOTE = {
    "gpu": "Performance index: approximate 1440p gaming average from public benchmarks, RTX 3060 12GB = 100. A guide for ranking, not a benchmark.",
    "cpu": "Performance index: approximate gaming average with a fast graphics card, from public benchmarks, Ryzen 5 5600X = 100. A guide for ranking, not a benchmark.",
}

GUIDES = (
    [{"id": f"best-used-gpu-under-{b}", "kind": "budget", "cat": "gpu", "max": b, "title": f"Best used GPU under ${b}"} for b in (200, 300, 400, 500, 700)]
    + [{"id": f"best-used-cpu-for-gaming-under-{b}", "kind": "budget", "cat": "cpu", "max": b, "title": f"Best used CPU for gaming under ${b}"} for b in (150, 250, 400)]
    + [{"id": f"cheapest-{g}gb-ram", "kind": "gb", "cat": "ram", "gb": g, "title": f"Cheapest {g}GB desktop RAM (used)"} for g in (32, 64)]
    + [{"id": "best-used-ssd-per-tb", "kind": "per", "cat": "ssd", "title": "Best used SSD value per TB"}]
)

PAIRS = [
    ("rtx-3080", "rx-6800-xt"), ("rtx-4070", "rx-7800-xt"), ("rtx-3070", "rx-6700-xt"), ("rtx-4070-super", "rtx-3090"),
    ("rtx-4080", "rx-7900-xtx"), ("ryzen-7-7800x3d", "ryzen-7-9800x3d"), ("ryzen-7-5800x3d", "ryzen-7-7800x3d"),
    ("core-i5-12600k", "ryzen-5-7600x"), ("core-i7-13700k", "ryzen-7-7800x3d"), ("samsung-990-pro-2tb", "wd-sn850x-2tb"),
    ("ps5-disc", "xbox-series-x"), ("ps5-digital", "xbox-series-s"), ("switch-oled", "switch-2"), ("ps5-disc", "ps5-pro"),
    ("iphone-14-pro-128", "iphone-15-128"), ("iphone-15-pro-128", "iphone-16-pro-128"), ("iphone-13-128", "iphone-14-128"),
]


def pair_id(a, b):
    return f"{a}-vs-{b}"


def _month(reports):
    d = max((r["current"]["day"] for r in reports if r["current"]), default=date.today().isoformat())
    return datetime.fromisoformat(d).strftime("%B %Y")


def _cheapest(rep):
    ls = rep["listings"]
    return ls[0] if ls else None


def _value(rep):
    p = PERF.get(rep["model"]["id"])
    return round(p / rep["current"]["median"] * 100, 1) if p and rep["current"] else None


# ---------------------------------------------------------------- shared blocks
def prepare(reports):
    """Fill the cross-links the regular pages show (related models, comparisons, guides)."""
    by = {r["model"]["id"]: r for r in reports}
    live_pairs = [(a, b) for a, b in PAIRS if a in by and b in by and by[a]["current"] and by[b]["current"]]
    guides = [g for g in GUIDES if any(r["model"]["cat"] == g["cat"] for r in reports)]
    for r in reports:
        m, cur = r["model"], r["current"]
        if not cur:
            continue
        sims = sorted((x for x in reports if x["model"]["cat"] == m["cat"] and x is not r and x["current"]),
                      key=lambda x: abs(x["current"]["median"] - cur["median"]))[:4]
        comps = [(a, b) for a, b in live_pairs if m["id"] in (a, b)]
        g = [x for x in guides if x["cat"] == m["cat"] and (x["kind"] != "budget" or cur["median"] <= x["max"])][:3]
        parts = []
        if comps:
            parts.append("<h2>Compare</h2><p>" + "".join(
                f'<a class="pill" href="{pair_id(a, b)}.html">{E(by[a]["model"]["name"])} vs {E(by[b]["model"]["name"])}</a>' for a, b in comps) + "</p>")
        if sims:
            parts.append("<h2>Similar models</h2><p>" + "".join(
                f'<a class="pill" href="{x["model"]["id"]}.html">{E(x["model"]["name"])} · {money(x["current"]["median"])}</a>' for x in sims) + "</p>")
        if g:
            parts.append("<h2>Buying guides</h2><p>" + "".join(f'<a class="pill" href="{x["id"]}.html">{E(x["title"])}</a>' for x in g) + "</p>")
        site.RELATED[m["id"]] = "\n".join(parts)
    for c in site.CATS:
        g = [x for x in guides if x["cat"] == c]
        comps = [(a, b) for a, b in live_pairs if by[a]["model"]["cat"] == c]
        if g or comps:
            site.CAT_GUIDES[c] = "<h2>Guides &amp; comparisons</h2><p>" + "".join(
                f'<a class="pill" href="{x["id"]}.html">{E(x["title"])}</a>' for x in g) + "".join(
                f'<a class="pill" href="{pair_id(a, b)}.html">{E(by[a]["model"]["name"])} vs {E(by[b]["model"]["name"])}</a>' for a, b in comps) + "</p>"
    site.HOME_GUIDES = ("<h2>Buying guides</h2><p>" + "".join(f'<a class="pill" href="{x["id"]}.html">{E(x["title"])}</a>' for x in guides[:8])
                        + '<a class="pill" href="guides.html">All guides &amp; comparisons →</a></p>') if guides else ""
    cats = "".join(f'<a href="{c}.html">{E(v["label"])}</a>' for c, v in site.CATS.items() if any(r["model"]["cat"] == c for r in reports))
    gl = "".join(f'<a href="{x["id"]}.html">{E(x["title"])}</a>' for x in guides[:6])
    cl = "".join(f'<a href="{pair_id(a, b)}.html">{E(by[a]["model"]["name"])} vs {E(by[b]["model"]["name"])}</a>' for a, b in live_pairs[:6])
    site.FOOTER_LINKS = (f'<div class="flinks"><div><b>Prices</b>{cats}</div><div><b>Guides</b>{gl}<a href="guides.html">All guides</a></div>'
                         f'<div><b>Comparisons</b>{cl}</div><div><b>More</b><a href="report.html">Weekly market report</a>'
                         '<a href="check.html">Price checker</a><a href="about.html">How it works</a><a href="privacy.html">Privacy</a></div></div>')
    return guides, live_pairs


# ---------------------------------------------------------------- guides
def guide_page(g, reports, demo, month):
    reps = [r for r in reports if r["model"]["cat"] == g["cat"] and r["current"]]
    note = ""
    if g["kind"] == "budget":
        pick = sorted((r for r in reps if r["current"]["median"] <= g["max"] and PERF.get(r["model"]["id"])),
                      key=lambda r: (-PERF[r["model"]["id"]], r["current"]["median"]))
        near = sorted((r for r in reps if g["max"] < r["current"]["median"] <= g["max"] * 1.15), key=lambda r: r["current"]["median"])
        how = (f"Every model whose typical used price (including shipping) is under ${g['max']} today, ranked by performance. "
               f"{PERF_NOTE[g['cat']]}")
    elif g["kind"] == "gb":
        pick = sorted((r for r in reps if r["model"].get("gb") == g["gb"]), key=lambda r: r["current"]["median"])
        near, how = [], f"Every tracked {g['gb']}GB desktop kit, cheapest typical used price first, with price per GB."
    else:
        pick = sorted((r for r in reps if r.get("per_gb")), key=lambda r: r["per_gb"])
        near, how = [], "Every tracked SSD, ranked by typical used price per terabyte (lower is better value)."

    def card(r):
        m, cur = r["model"], r["current"]
        unit, per = site.per_unit(r)
        extra = []
        if PERF.get(m["id"]):
            extra.append(f"performance {PERF[m['id']]} · {_value(r)} per $100")
        if per:
            extra.append(f"{money(per, 2)}/{unit}")
        c = _cheapest(r)
        buy = aff(c["url"], f"Cheapest: {money(c['total'], 0)}", m["id"]) if c and c.get("url") else ""
        return (f'<div class="card"><div class="grow"><a href="{m["id"]}.html"><b>{E(m["name"])}</b></a>{site.track(cur, labels=False)}'
                f'<div class="k">typical {money(cur["median"])} · fair {money(cur["p25"])}–{money(cur["p75"])} · 30d {chg(r["chg_30d"])}</div>'
                f'{"<div class=k>" + " · ".join(extra) + "</div>" if extra else ""}</div>{buy}</div>')

    title = f"{g['title']} ({month})"
    top = pick[0] if pick else None
    if top:
        lead = (f"<p><b>Top pick right now: <a href=\"{top['model']['id']}.html\">{E(top['model']['name'])}</a></b> at a typical "
                f"{money(top['current']['median'])} used, including shipping.</p>")
    else:
        lead = "<p class='sub'>Nothing we track fits this right now. Check the models just above it below, or come back after the next update.</p>"
    body = f"""<h1>{E(title)}</h1>
<p class="sub">{E(how)} Updated from live eBay listings.</p>
{lead}
<div class="rank">{''.join(card(r) for r in pick)}</div>
{('<h2>Just above budget</h2><div class="rank">' + ''.join(card(r) for r in near) + '</div>') if near else ''}
<p>{aff(ebay_search_url(site.CATS[g['cat']]['label'] + ' used'), 'Browse all used ' + E(site.CATS[g['cat']]['short']) + ' on eBay', 'guide-ebay')}
 <a class="btn alt" href="check.html">Check a listing's price</a></p>
{site.accessories_html(g['cat'])}
{site.newsletter_html()}"""
    faq = []
    if top:
        faq.append({"@type": "Question", "name": f"What is the {g['title'].lower()}?",
                    "acceptedAnswer": {"@type": "Answer", "text": f"Right now it's the {top['model']['name']}, typically {money(top['current']['median'])} used including shipping."}})
    ld = [{"@context": "https://schema.org", "@type": "ItemList", "name": title, "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "url": f"{config.SITE_URL}/{r['model']['id']}.html", "name": r["model"]["name"]}
        for i, r in enumerate(pick[:10])]}]
    if faq:
        ld.append({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": faq})
    desc = (f"{g['title']}: {top['model']['name']} at a typical {money(top['current']['median'])} used. "
            if top else f"{g['title']}: ") + "Ranked from live eBay prices, updated daily."
    return page(f"{title} — Live Prices", desc, body, f"{g['id']}.html", demo, ld,
                [("Guides", "guides.html"), (g["title"], None)], site.OG.get("guide-" + g["id"]), "guide")


# ---------------------------------------------------------------- comparisons
def _two_line_svg(a, b, w=800, h=260):
    sa = {p["day"]: p["median"] for p in a["series"][-90:]}
    sb = {p["day"]: p["median"] for p in b["series"][-90:]}
    days = sorted(set(sa) | set(sb))
    if len(days) < 2:
        return '<p class="sub">Chart appears after two days of data.</p>'
    vals = list(sa.values()) + list(sb.values())
    lo, hi = min(vals) * 0.95, max(vals) * 1.05
    pl, pr, pt, pb = 56, 12, 12, 28
    x = lambda i: pl + i * (w - pl - pr) / (len(days) - 1)  # noqa: E731
    y = lambda v: pt + (hi - v) * (h - pt - pb) / (hi - lo)  # noqa: E731
    line = lambda s: " ".join(f"{x(i):.1f},{y(s[d]):.1f}" for i, d in enumerate(days) if d in s)  # noqa: E731
    grid = "".join(f'<line x1="{pl}" x2="{w - pr}" y1="{y(lo + (hi - lo) * k / 4):.1f}" y2="{y(lo + (hi - lo) * k / 4):.1f}" stroke="var(--line)"/>'
                   f'<text x="{pl - 8}" y="{y(lo + (hi - lo) * k / 4) + 4:.1f}" text-anchor="end" font-size="12" fill="var(--mute)">${lo + (hi - lo) * k / 4:,.0f}</text>' for k in range(5))
    lab = (f'<text x="{pl}" y="{h - 8}" font-size="12" fill="var(--mute)">{days[0][5:]}</text>'
           f'<text x="{w - pr}" y="{h - 8}" text-anchor="end" font-size="12" fill="var(--mute)">{days[-1][5:]}</text>')
    return (f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Used price history comparison">{grid}'
            f'<polyline points="{line(sa)}" fill="none" stroke="var(--accent)" stroke-width="2.5"/>'
            f'<polyline points="{line(sb)}" fill="none" stroke="#e8771b" stroke-width="2.5" stroke-dasharray="6 4"/>{lab}</svg>'
            f'<p class="k" style="margin:6px 0 0"><span style="color:var(--accent)">━</span> {E(a["model"]["name"])} &nbsp; '
            f'<span style="color:#e8771b">╍</span> {E(b["model"]["name"])} · typical used price incl. shipping, last 90 days</p>')


def compare_page(a, b, demo, month):
    ma, mb, ca, cb = a["model"], b["model"], a["current"], b["current"]
    diff = cb["median"] - ca["median"]
    cheaper, dearer = (a, b) if diff > 0 else (b, a)
    pct = abs(diff) / max(ca["median"], cb["median"]) * 100
    verdict = (f"Used, the <b>{E(cheaper['model']['name'])}</b> is typically <b>{money(abs(diff))} cheaper</b> ({pct:.0f}%) "
               f"than the {E(dearer['model']['name'])}." if abs(diff) >= 1 else "Used, both typically cost about the same right now.")
    va, vb = _value(a), _value(b)
    if va and vb:
        better = a if va > vb else b
        verdict += (f" Per dollar, the <b>{E(better['model']['name'])}</b> gives more performance "
                    f"({max(va, vb)} vs {min(va, vb)} performance points per $100). {E(PERF_NOTE[ma['cat']])}")

    def side(r):
        m, cur = r["model"], r["current"]
        c = _cheapest(r)
        amz = aff(site.amazon_url(m), "New on Amazon", "amz:" + m["id"], "btn alt") if config.AMAZON_TAG else ""
        return (f'<div class="card"><h3><a href="{m["id"]}.html">{E(m["name"])}</a></h3>'
                f'<div class="v">{money(cur["median"])}</div>{site.track(cur)}'
                f'<div class="k">7d {chg(r["chg_7d"])} · 30d {chg(r["chg_30d"])}{" · performance " + str(PERF[m["id"]]) if PERF.get(m["id"]) else ""}</div>'
                f'<p style="margin:10px 0 0">{aff(c["url"], "Cheapest " + money(c["total"]), m["id"]) + " " if c and c.get("url") else ""}'
                f'{aff(ebay_search_url(m.get("query") or m["name"]), "All on eBay", m["id"], "btn alt")} {amz}</p></div>')

    title = f"{ma['name']} vs {mb['name']}: Used Price Comparison ({month})"
    body = f"""<h1>{E(ma['name'])} vs {E(mb['name'])} — used prices</h1>
<p class="sub">Live typical used prices from eBay listings, including shipping.</p>
<p>{verdict}</p>
<div class="vs">{side(a)}{side(b)}</div>
<h2>Price history</h2><div class="chart">{_two_line_svg(a, b)}</div>
{site.accessories_html(ma['cat'])}
{site.newsletter_html()}"""
    faq = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": f"Is the {ma['name']} or {mb['name']} cheaper used?",
         "acceptedAnswer": {"@type": "Answer", "text": html.unescape(verdict.replace("<b>", "").replace("</b>", ""))}}]}
    desc = f"{ma['name']} vs {mb['name']} used: {money(ca['median'])} vs {money(cb['median'])} typical. Price history, value and the best live deals."
    return page(title, desc, body, f"{pair_id(ma['id'], mb['id'])}.html", demo, faq,
                [("Guides", "guides.html"), (f"{ma['name']} vs {mb['name']}", None)], site.OG.get("vs-" + pair_id(ma["id"], mb["id"])), "compare")


def guides_index(guides, pairs, by, demo):
    g = "".join(f'<a class="pill" href="{x["id"]}.html">{E(x["title"])}</a>' for x in guides)
    c = "".join(f'<a class="pill" href="{pair_id(a, b)}.html">{E(by[a]["model"]["name"])} vs {E(by[b]["model"]["name"])}</a>' for a, b in pairs)
    body = f"""<h1>Buying guides &amp; comparisons</h1>
<p class="sub">Generated from live used prices every few hours, so the picks change as the market moves.</p>
<h2>Best value by budget</h2><p>{g}</p><h2>Head-to-head comparisons</h2><p>{c}</p>"""
    return page(f"Used Tech Buying Guides & Comparisons — {config.SITE_NAME}",
                "Best used GPUs, CPUs, RAM and SSDs by budget, plus head-to-head used price comparisons, from live eBay data.",
                body, "guides.html", demo, crumbs=[("Guides", None)], pt="guides")


# ---------------------------------------------------------------- weekly report
def report_html(reports, summary, week, demo, archive_links=""):
    live = [r for r in reports if r["current"] and r["chg_7d"] is not None]
    drops = sorted(live, key=lambda r: r["chg_7d"])[:6]
    rises = sorted(live, key=lambda r: -r["chg_7d"])[:6]
    lows = [r for r in reports if r["current"] and len(r["series"]) >= 15
            and r["current"]["median"] <= min(p["median"] for p in r["series"][-91:-1])]
    deals = sorted((d | {"model": r["model"], "median": r["current"]["median"]} for r in reports for d in r["deals"]),
                   key=lambda d: d["total"] / d["median"])[:6]
    from .stats import market_index
    li = lambda r: f'<li><a href="{r["model"]["id"]}.html">{E(r["model"]["name"])}</a> {money(r["current"]["median"])} {chg(r["chg_7d"])}</li>'  # noqa: E731
    cats = "".join(f'<div class="card"><div class="k">{E(v["label"])} · 7d</div><div class="v">{chg(market_index(reports, c, "chg_7d"))}</div></div>'
                   for c, v in site.CATS.items() if any(r["model"]["cat"] == c for r in reports))
    body = f"""<h1>Used tech market report — week {E(week)}</h1>
<p class="sub">What changed in used prices this week, from live eBay listings.</p>
{f'<div class="ai">{E(summary)}</div>' if summary else ''}
<h2>By category</h2><div class="cards">{cats}</div>
<h2>Biggest price drops</h2><ul>{''.join(li(r) for r in drops if r['chg_7d'] < 0) or '<li>None this week.</li>'}</ul>
<h2>Biggest price rises</h2><ul>{''.join(li(r) for r in rises if r['chg_7d'] > 0) or '<li>None this week.</li>'}</ul>
<h2>At a 90-day low</h2><ul>{''.join(f'<li><a href="{r["model"]["id"]}.html">{E(r["model"]["name"])}</a> {money(r["current"]["median"])}</li>' for r in lows) or '<li>None this week.</li>'}</ul>
<h2>Best deals right now</h2><ul>{''.join(f'<li><a href="{d["model"]["id"]}.html">{E(d["model"]["name"])}</a>: {aff(d["url"], money(d["total"], 2), d["model"]["id"], "deal")} ({(1 - d["total"] / d["median"]) * 100:.0f}% under typical)</li>' for d in deals if d.get("url")) or '<li>None right now.</li>'}</ul>
{('<h2>Past reports</h2><p>' + archive_links + '</p>') if archive_links else ''}
{site.newsletter_html()}"""
    return body, {"drops": drops, "lows": lows}


def write_all(out, reports, summaries, demo):
    """Write guides, comparisons, guides index and the weekly report. Returns new sitemap paths."""
    by = {r["model"]["id"]: r for r in reports}
    guides, pairs = prepare(reports)
    month = _month(reports)
    paths = ["guides.html", "report.html"]
    for g in guides:
        (out / f"{g['id']}.html").write_text(guide_page(g, reports, demo, month))
        paths.append(f"{g['id']}.html")
    for a, b in pairs:
        (out / f"{pair_id(a, b)}.html").write_text(compare_page(by[a], by[b], demo, month))
        paths.append(f"{pair_id(a, b)}.html")
    (out / "guides.html").write_text(guides_index(guides, pairs, by, demo))
    # weekly report: latest at report.html, one archived copy per ISO week kept in DATA_DIR
    day = max((r["current"]["day"] for r in reports if r["current"]), default=date.today().isoformat())
    week = date.fromisoformat(day).strftime("%G-W%V")
    arch_dir = config.DATA_DIR / "reports"
    arch_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted((p.stem for p in arch_dir.glob("*.html")), reverse=True)
    links = "".join(f'<a class="pill" href="reports/{w}.html">Week {w}</a>' for w in existing if w != week)
    body, _ = report_html(reports, summaries.get("_market"), week, demo, links)
    rep_page = page(f"Used Tech Market Report — Week {week}", f"This week's used GPU, CPU, RAM, SSD, monitor, console and iPhone price moves, 90-day lows and best deals.",
                    body, "report.html", demo, crumbs=[("Market report", None)], og=site.OG.get("home"), pt="report")
    (out / "report.html").write_text(rep_page)
    archived = page(f"Used Tech Market Report — Week {week}", f"Used tech price moves for week {week}.",
                    body, f"reports/{week}.html", demo, crumbs=[("Market report", "report.html"), (f"Week {week}", None)], pt="report")
    archived = archived.replace("<head>", '<head><base href="../">', 1)  # archive lives one folder down
    (arch_dir / f"{week}.html").write_text(archived)
    (out / "reports").mkdir(exist_ok=True)
    for p in arch_dir.glob("*.html"):
        shutil.copy(p, out / "reports" / p.name)
        paths.append(f"reports/{p.name}")
    return paths, week
