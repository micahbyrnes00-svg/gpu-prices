"""Static site generator. Writes HTML/JSON/sitemap into SITE_DIR (docs/ for GitHub Pages)."""
import html
import json
import shutil
from datetime import datetime, timezone

from . import config, extra

E = html.escape

CSS = """
:root{--bg:#f3f6fc;--card:#fff;--ink:#101935;--mute:#56607a;--line:#dfe4f0;--soft:#eaeefa;--accent:#3d5afe;--accent-ink:#fff;--up:#c8362e;--down:#0b8a5f;
 --gold:#c98a00;--goldbg:#fff4d6;--band:rgba(61,90,254,.12);--r:14px;--disp:"Bricolage Grotesque",ui-sans-serif,system-ui,sans-serif}
@media (prefers-color-scheme:dark){:root{--bg:#0b1020;--card:#141b31;--ink:#e6eaf5;--mute:#9aa4c2;--line:#26304d;--soft:#1b2440;--accent:#8c9dff;--accent-ink:#0b1020;
 --up:#ff7a70;--down:#34d399;--gold:#ffc94d;--goldbg:#3a2f12;--band:rgba(140,157,255,.16)}}
*{box-sizing:border-box}html{scroll-padding-top:80px}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;font-variant-numeric:tabular-nums}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline;text-underline-offset:3px}
:focus-visible{outline:3px solid var(--accent);outline-offset:2px;border-radius:6px}
.wrap{max-width:1120px;margin:0 auto;padding:0 20px}
h1,h2,h3,.disp{font-family:var(--disp);letter-spacing:-.01em}
h1{font-size:clamp(28px,4.4vw,44px);line-height:1.08;margin:28px 0 10px;font-weight:800}
h2{font-size:22px;line-height:1.2;margin:40px 0 14px;font-weight:700}h3{font-size:18px;margin:0 0 6px}
.sub{color:var(--mute);margin:0 0 20px;max-width:68ch}
.k{color:var(--mute);font-size:13px}.v{font:800 26px/1.15 var(--disp)}
.up{color:var(--up)}.down{color:var(--down)}.flat{color:var(--mute)}
.demo{background:var(--goldbg);color:var(--ink);text-align:center;padding:7px;font-size:14px}
/* header */
.top{position:sticky;top:0;z-index:20;background:color-mix(in srgb,var(--bg) 88%,transparent);backdrop-filter:saturate(1.4) blur(10px);-webkit-backdrop-filter:saturate(1.4) blur(10px);border-bottom:1px solid var(--line)}
.top .wrap{display:flex;align-items:center;gap:14px;height:64px}
.brand{display:flex;align-items:center;gap:9px;color:var(--ink);flex:none}.brand:hover{text-decoration:none}
.brand svg{width:34px;height:34px}.brand b{font:800 21px/1 var(--disp);letter-spacing:-.02em}.brand small{display:block;font-size:11.5px;color:var(--mute);margin-top:2px;letter-spacing:0}
.search{position:relative;flex:1;max-width:420px;margin-left:auto}
.search input{width:100%;font:inherit;font-size:15px;padding:9px 12px 9px 36px;border:1px solid var(--line);border-radius:999px;background:var(--card);color:var(--ink)}
.search svg{position:absolute;left:12px;top:50%;transform:translateY(-50%);width:16px;height:16px;color:var(--mute)}
.results{position:absolute;left:0;right:0;top:calc(100% + 6px);background:var(--card);border:1px solid var(--line);border-radius:12px;box-shadow:0 12px 40px rgba(16,25,53,.16);padding:6px;display:none;max-height:60vh;overflow:auto}
.results.open{display:block}.results a{display:flex;justify-content:space-between;gap:10px;padding:9px 10px;border-radius:8px;color:var(--ink)}
.results a:hover,.results a.sel{background:var(--soft);text-decoration:none}.results small{color:var(--mute)}
.navlinks{display:flex;gap:4px;align-items:center}.navlinks a{color:var(--ink);padding:8px 10px;border-radius:999px;font-size:15px;white-space:nowrap}.navlinks a:hover{background:var(--soft);text-decoration:none}
.menubtn svg{width:20px;height:20px}.menubtn{flex:none;display:flex;align-items:center;gap:6px;font:inherit;font-size:15px;background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:999px;padding:8px 14px;cursor:pointer}
.navcta{background:#5865f2;color:#fff!important}.navcta:hover{background:#4752c4!important}
.sheet{position:fixed;inset:0;z-index:30;background:rgba(9,14,30,.45);display:none}.sheet.open{display:block}
.sheet .panel{position:absolute;right:0;top:0;bottom:0;width:min(380px,92vw);background:var(--card);padding:18px 20px 30px;overflow:auto;box-shadow:-20px 0 60px rgba(0,0,0,.2)}
.sheet .panel h3{font-size:13px;color:var(--mute);font-family:inherit;font-weight:600;margin:20px 0 6px;letter-spacing:0}
.sheet .panel a{display:flex;align-items:center;gap:10px;padding:10px 8px;border-radius:10px;color:var(--ink);font-size:16px}.sheet .panel a:hover{background:var(--soft);text-decoration:none}
.sheet .panel a svg{width:20px;height:20px;color:var(--accent);flex:none}
.closebtn{float:right;font:inherit;background:none;border:1px solid var(--line);border-radius:999px;width:36px;height:36px;color:var(--ink);cursor:pointer}
/* cards, buttons */
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:16px 18px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
.btn{display:inline-flex;align-items:center;gap:6px;background:var(--accent);color:var(--accent-ink);padding:9px 16px;border-radius:999px;font-size:15px;font-weight:600;border:1px solid var(--accent);white-space:nowrap}
.btn:hover{text-decoration:none;filter:brightness(1.08)}.btn.alt{background:transparent;color:var(--accent)}
.btn.ghost{background:var(--soft);border-color:transparent;color:var(--ink)}
.actions{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}
.pill{display:inline-block;padding:7px 13px;border:1px solid var(--line);border-radius:999px;margin:0 6px 8px 0;color:var(--ink);background:var(--card);font-size:14.5px}
.pill:hover{border-color:var(--accent);text-decoration:none}
.term{border-bottom:1px dotted var(--mute);cursor:help;position:relative}
.term:hover:after,.term:focus:after{content:attr(data-tip);position:absolute;left:0;top:calc(100% + 8px);width:min(260px,70vw);background:var(--ink);color:var(--bg);font:13px/1.45 system-ui;padding:9px 11px;border-radius:9px;z-index:5;white-space:normal}
/* the signature: price track */
.track{position:relative;height:34px;margin:6px 0 4px}
.track .rail{position:absolute;left:0;right:0;top:15px;height:4px;border-radius:2px;background:var(--line)}
.track .fair{position:absolute;top:11px;height:12px;border-radius:6px;background:var(--band);border:1px solid color-mix(in srgb,var(--accent) 40%,transparent)}
.track .zone{position:absolute;top:13px;height:8px;left:0;border-radius:4px;background:color-mix(in srgb,var(--down) 22%,transparent)}
.track .dot{position:absolute;top:8px;width:18px;height:18px;margin-left:-9px;border-radius:50%;background:var(--accent);box-shadow:0 0 0 4px var(--card),0 0 0 5px color-mix(in srgb,var(--accent) 45%,transparent)}
.track .you{position:absolute;top:2px;width:3px;height:30px;margin-left:-1.5px;background:var(--ink);border-radius:2px}
.tlabels{display:flex;justify-content:space-between;font-size:12.5px;color:var(--mute)}
/* hero */
.hero{display:grid;grid-template-columns:1.25fr .9fr;gap:36px;align-items:center;padding:30px 0 10px}
.hero h1{font-size:clamp(34px,5.6vw,60px);margin-top:0}
.qcheck{display:grid;grid-template-columns:1fr 140px auto;gap:8px;background:var(--card);border:1px solid var(--line);border-radius:18px;padding:8px;max-width:640px}
.qcheck input{font:inherit;border:0;background:transparent;color:var(--ink);padding:10px 12px;min-width:0}.qcheck input+input{border-left:1px solid var(--line)}
.orbitcard{position:relative;padding:22px 22px 18px;overflow:hidden}
.orbitcard .ring{position:absolute;right:-60px;top:-70px;width:220px;height:220px;border:1.5px dashed color-mix(in srgb,var(--accent) 35%,transparent);border-radius:50%;pointer-events:none}
.steps{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;counter-reset:s;margin:8px 0 0;padding:0;list-style:none}
.steps li{position:relative;padding:14px 16px 14px 50px;background:var(--card);border:1px solid var(--line);border-radius:var(--r);font-size:14.5px;color:var(--mute)}
.steps li b{display:block;color:var(--ink);font-size:15.5px}
.steps li:before{counter-increment:s;content:counter(s);position:absolute;left:14px;top:14px;width:26px;height:26px;border-radius:50%;background:var(--soft);color:var(--accent);font:800 14px/26px var(--disp);text-align:center}
.catgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px}
.cat{display:flex;gap:14px;align-items:flex-start;color:var(--ink)}.cat:hover{border-color:var(--accent);text-decoration:none}
.cat .ic{flex:none;width:44px;height:44px;border-radius:12px;background:var(--soft);display:grid;place-items:center;color:var(--accent)}.cat .ic svg{width:24px;height:24px}
.cat b{font:700 17px var(--disp)}.cat .k{display:block}
/* model rows */
.mlist{background:var(--card);border:1px solid var(--line);border-radius:var(--r);overflow:hidden}
.mrow{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(0,1.3fr) 110px 90px;gap:16px;align-items:center;padding:12px 18px;border-top:1px solid var(--line);color:var(--ink)}
.mrow:first-child{border-top:0}.mrow:hover{background:var(--soft);text-decoration:none}
.mrow .nm{font-weight:600}.mrow .nm small{display:block;font-weight:400;color:var(--mute);font-size:13px}
.mrow .pr{font:800 19px var(--disp);text-align:right}.mrow .ch{text-align:right;font-size:14px}
.mrow .track{height:22px;margin:0}.mrow .track .rail{top:9px}.mrow .track .fair{top:6px;height:10px}.mrow .track .dot{top:4px;width:14px;height:14px;margin-left:-7px;box-shadow:0 0 0 3px var(--card)}
.mrow .track .zone{top:8px;height:6px}
.mhead{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(0,1.3fr) 110px 90px;gap:16px;padding:10px 18px;font-size:13px;color:var(--mute);border-bottom:1px solid var(--line)}
.mhead span:nth-child(n+3){text-align:right}
/* deal + listing cards */
.dgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}
.grid3{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;margin:12px 0}
.grid3 .card .v{font:800 26px/1.1 var(--disp)}.grid3 .card .v.big{font-size:32px}.grid3 .card.main{border-color:var(--accent)}
.share{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:12px 0}.share .sharebtn svg{width:16px;height:16px;margin-right:6px;vertical-align:-3px}
button.pill{cursor:pointer;font:inherit}
h1 svg,h2 svg,.card b svg,.pill svg{width:1.05em;height:1.05em;vertical-align:-.15em;margin-right:.25em;display:inline-block}
.dealcard{display:flex;flex-direction:column;gap:6px}
.deal{color:var(--down);font-weight:700}
.dealcard .tt{font-size:14px;color:var(--mute);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;min-height:2.9em}
.dealcard .row{display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin-top:auto}
.dealcard .p{font:800 24px var(--disp)}.save{display:inline-block;background:color-mix(in srgb,var(--down) 14%,transparent);color:var(--down);font-weight:700;font-size:13px;padding:3px 9px;border-radius:999px}
.dealcard .btn{justify-content:center;margin-top:6px}
.signal{display:inline-flex;align-items:center;gap:6px;background:var(--goldbg);color:var(--gold);font-weight:700;font-size:13.5px;padding:4px 11px;border-radius:999px}
/* model summary */
.summary{display:grid;grid-template-columns:1.2fr 1fr;gap:16px;align-items:stretch}
.summary .main .big{font:800 clamp(44px,7vw,64px)/1 var(--disp);letter-spacing:-.03em}
.verdict-line{font-size:16px;margin:12px 0 0}.verdict-line b{font-family:var(--disp)}
.facts{display:grid;grid-template-columns:1fr 1fr;gap:10px;align-content:start}.facts .card{padding:12px 14px}.facts .v{font-size:20px}
.chart{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:14px 16px}
.chart svg{width:100%;height:auto;display:block;overflow:visible}.chart .tabs{display:flex;gap:6px;margin-bottom:8px}
.chart .tabs button{font:inherit;font-size:13.5px;border:1px solid var(--line);background:var(--card);color:var(--ink);padding:4px 12px;border-radius:999px;cursor:pointer}
.chart .tabs button[aria-pressed=true]{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.tip{position:absolute;pointer-events:none;background:var(--ink);color:var(--bg);font-size:13px;padding:6px 9px;border-radius:8px;white-space:nowrap;transform:translate(-50%,-120%);display:none}
.ai{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--accent);padding:14px 18px;border-radius:var(--r);max-width:80ch}
.lgrid{display:grid;gap:10px}
.listing{display:grid;grid-template-columns:1fr auto auto;gap:14px;align-items:center}
.listing .t{font-weight:600;font-size:15px}.listing .meta{font-size:13px;color:var(--mute)}.listing .p{font:800 20px var(--disp);text-align:right}
/* tables kept for guides etc. */
.tbl{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:var(--r);overflow:hidden}
.tbl th,.tbl td{padding:10px 14px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}.tbl th:first-child,.tbl td:first-child{text-align:left;white-space:normal}
.tbl th{font-size:13px;color:var(--mute);font-weight:600}.scroll{overflow-x:auto}
/* forms */
.form{display:grid;gap:10px;max-width:620px}.form input,.form select,.form textarea{font:inherit;padding:12px;border:1px solid var(--line);border-radius:12px;background:var(--card);color:var(--ink);width:100%}
.verdict{font:800 34px/1.1 var(--disp);margin:6px 0}.great,.good{color:var(--down)}.fair{color:var(--accent)}.high{color:var(--up)}
/* guides / compare */
.vs{display:grid;grid-template-columns:1fr 1fr;gap:12px}.vs .card h3{font-size:18px}
.rank{counter-reset:r}.rank .card{display:flex;gap:16px;align-items:center;margin-bottom:10px}
.rank .card:before{counter-increment:r;content:counter(r);font:800 26px var(--disp);color:var(--accent);min-width:30px}
.rank .grow{flex:1;min-width:0}
.crumbs{font-size:13.5px;color:var(--mute);margin:18px 0 -16px}.crumbs a{color:var(--mute)}
.news,.dcta{margin:28px 0}.dcta{border-left:4px solid #5865f2}
.newsf{display:flex;gap:8px;flex-wrap:wrap}.newsf input[type=email]{flex:1;min-width:200px;font:inherit;padding:9px 12px;border:1px solid var(--line);border-radius:999px;background:var(--bg);color:var(--ink)}.newsf button{cursor:pointer;font:inherit}
.bar{position:relative;height:12px;border-radius:6px;background:linear-gradient(90deg,var(--down),var(--accent) 50%,var(--up));margin:18px 0 6px}
.bar i{position:absolute;top:-5px;width:4px;height:22px;background:var(--ink);border-radius:2px}
/* footer */
footer{margin:64px 0 0;border-top:1px solid var(--line);background:var(--card)}footer .wrap{padding:28px 20px 40px;color:var(--mute);font-size:14px}
.flinks{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:6px 24px;margin-bottom:22px}
.flinks b{display:block;color:var(--ink);margin:8px 0 6px;font-family:var(--disp)}.flinks a{display:block;color:var(--mute);padding:3px 0}
.disclose{font-size:13px;max-width:90ch}
@media (max-width:900px){.hero{grid-template-columns:1fr}.steps{grid-template-columns:1fr 1fr}.navlinks{display:none}.summary{grid-template-columns:1fr}}
@media (max-width:640px){.wrap{padding:0 16px}.top .wrap{gap:10px;height:58px}.brand small{display:none}.brand b{font-size:19px}
 .search{max-width:none}.search input{padding-left:32px}.menubtn span{display:none}
 .qcheck{grid-template-columns:1fr 1fr;border-radius:16px}.qcheck input:first-child{grid-column:1/-1;border-bottom:1px solid var(--line)}.qcheck input+input{border-left:0}
 .steps{grid-template-columns:1fr}.mhead{display:none}.mrow{grid-template-columns:1fr auto;gap:4px 12px;padding:12px 14px}
 .mrow .track{grid-column:1/-1;grid-row:2}.mrow .ch{grid-column:2;grid-row:1;display:none}
 .summary .actions .btn{flex:1 1 100%;justify-content:center}.listing{grid-template-columns:1fr auto}.listing .btn{grid-column:1/-1;justify-content:center}
 .vs{grid-template-columns:1fr}.rank .card{display:grid;grid-template-columns:auto minmax(0,1fr);gap:4px 14px}.rank .card .btn{grid-column:1/-1;justify-content:center;margin-top:6px}.facts{grid-template-columns:1fr 1fr}.cards{grid-template-columns:1fr 1fr}}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
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


LOGO = ('<svg viewBox="0 0 40 40" aria-hidden="true"><defs><linearGradient id="og" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#5ad1ff"/><stop offset="1" stop-color="#3d5afe"/></linearGradient></defs>'
        '<circle cx="20" cy="20" r="9" fill="url(#og)"/>'
        '<ellipse cx="20" cy="20" rx="17" ry="6.5" fill="none" stroke="currentColor" stroke-width="2" opacity=".55" transform="rotate(-20 20 20)"/>'
        '<circle cx="35" cy="14.5" r="2.6" fill="#f2a900"/></svg>')
FAVICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 40 40'%3E%3Ccircle cx='20' cy='20' r='9' fill='%233d5afe'/%3E"
           "%3Cellipse cx='20' cy='20' rx='17' ry='6.5' fill='none' stroke='%23101935' stroke-width='2.4' transform='rotate(-20 20 20)'/%3E"
           "%3Ccircle cx='35' cy='14.5' r='3' fill='%23f2a900'/%3E%3C/svg%3E")
_I = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{}</svg>'
ICONS = {
    "gpu": _I.format('<rect x="2" y="6" width="20" height="11" rx="2"/><circle cx="8" cy="11.5" r="2.6"/><circle cx="15.5" cy="11.5" r="2.6"/><path d="M4 17v2M7 17v2"/>'),
    "cpu": _I.format('<rect x="6" y="6" width="12" height="12" rx="2"/><rect x="9.5" y="9.5" width="5" height="5" rx="1"/><path d="M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3"/>'),
    "ram": _I.format('<rect x="2" y="7" width="20" height="9" rx="1.5"/><path d="M6 10v3M10 10v3M14 10v3M18 10v3M5 16v2M19 16v2"/>'),
    "ssd": _I.format('<rect x="2" y="8" width="20" height="8" rx="1.5"/><path d="M6 11h7M6 13h4"/><circle cx="18" cy="12" r="1"/>'),
    "monitor": _I.format('<rect x="2" y="4" width="20" height="13" rx="2"/><path d="M8 21h8M12 17v4"/>'),
    "console": _I.format('<path d="M7 8h10a5 5 0 0 1 4.6 7l-.6 1.4a2.5 2.5 0 0 1-4.3.5L15 15H9l-1.7 1.9a2.5 2.5 0 0 1-4.3-.5L2.4 15A5 5 0 0 1 7 8z"/><path d="M7 11v3M5.5 12.5h3M16 12h.01M18 13.5h.01"/>'),
    "phone": _I.format('<rect x="6.5" y="2" width="11" height="20" rx="2.5"/><path d="M11 18.5h2"/>'),
    "laptop": _I.format('<rect x="4" y="5" width="16" height="11" rx="1.5"/><path d="M2 19h20"/>'),
    "mac": _I.format('<rect x="4" y="5" width="16" height="11" rx="1.5"/><path d="M2 19h20M10 8.5h4"/>'),
    "handheld": _I.format('<rect x="2" y="7" width="20" height="10" rx="3"/><rect x="8" y="9" width="8" height="6" rx="1"/><path d="M5 11v2M4 12h2M19 11h.01M19 13h.01"/>'),
    "camera": _I.format('<path d="M4 8h3l2-2h6l2 2h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z"/><circle cx="12" cy="13" r="3.5"/>'),
    "new": _I.format('<path d="M12 3l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.3 6.8 19.1l1-5.8L3.5 9.2l5.9-.9z"/>'),
    "sell": _I.format('<path d="M3 12l9-9h7v7l-9 9z"/><circle cx="15.5" cy="7.5" r="1.4"/>'),
    "api": _I.format('<path d="M8 8l-4 4 4 4M16 8l4 4-4 4M13.5 5l-3 14"/>'),
    "share": _I.format('<circle cx="18" cy="5" r="2.5"/><circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="19" r="2.5"/><path d="M8.2 10.8l7.6-4.4M8.2 13.2l7.6 4.4"/>'),
    "search": _I.format('<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>'),
    "menu": _I.format('<path d="M4 7h16M4 12h16M4 17h16"/>'),
    "guide": _I.format('<path d="M4 5h11a3 3 0 0 1 3 3v12H7a3 3 0 0 1-3-3z"/><path d="M8 9h6M8 13h6"/>'),
    "report": _I.format('<path d="M4 19V5M4 19h16M8 15l3-4 3 2 4-6"/>'),
    "check": _I.format('<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.7 2.5L16 9.5"/>'),
    "discord": _I.format('<path d="M8 7c2.7-.8 5.3-.8 8 0l1.4 1.2c1.2 2.5 1.8 5.1 1.6 7.8-1.4 1.1-2.9 1.8-4.5 2.2l-.9-1.6M7 7L5.6 8.2C4.4 10.7 3.8 13.3 4 16c1.4 1.1 2.9 1.8 4.5 2.2l.9-1.6"/><circle cx="9.5" cy="13" r="1"/><circle cx="14.5" cy="13" r="1"/>'),
}



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
    "laptop": [("Laptop cooling pad", "gaming laptop cooling pad"), ("USB-C dock", "USB C docking station laptop"), ("Laptop backpack", "17 inch gaming laptop backpack")],
    "mac": [("USB-C hub", "USB C hub MacBook"), ("MacBook case", "MacBook Air Pro hard shell case"), ("Laptop stand", "aluminum laptop stand")],
    "handheld": [("Carrying case", "Steam Deck ROG Ally carrying case"), ("microSD card (1TB)", "1TB microSD card A2"), ("Docking station", "Steam Deck ROG Ally docking station")],
    "camera": [("Extra battery", "Sony NP-FZ100 Canon LP-E6NH battery"), ("SD card (V60/V90)", "SD card V90 UHS-II"), ("Camera bag", "mirrorless camera bag")],
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


def discord_url():
    return f"https://discord.gg/{config.DISCORD_INVITE}" if config.DISCORD_INVITE else ""


def discord_cta(where="block"):
    if not config.DISCORD_INVITE:
        return ""
    a = f'href="{E(discord_url())}" data-m="discord" rel="noopener" target="_blank"'
    if where == "nav":
        return f'<a class="navcta" {a}>Join Discord</a>'
    if where == "inline":
        return f'<a class="pill" {a}>Get deals like these in the Discord</a>'
    return (f'<div class="card dcta"><b>Get new deals the moment they appear</b><p class="k" style="margin:4px 0 10px">'
            f'Join the free deals Discord: a channel for each category, posted automatically from live listings.</p>'
            f'<a class="btn" {a}>Join the deals Discord</a></div>')


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


SITE_JS = r"""(function(){
document.addEventListener("click",function(e){var a=e.target.closest&&e.target.closest("a[data-m]");if(a&&navigator.sendBeacon)navigator.sendBeacon("/c?m="+encodeURIComponent(a.dataset.m)+"&p="+(document.body.dataset.pt||"page"))});
var sh=document.getElementById("menu"),mb=document.getElementById("menubtn");
function setMenu(o){sh.classList.toggle("open",o);mb.setAttribute("aria-expanded",o);if(o)sh.querySelector("a,button").focus();}
mb.onclick=function(){setMenu(true)};sh.onclick=function(e){if(e.target===sh||e.target.closest(".closebtn"))setMenu(false)};
document.addEventListener("keydown",function(e){if(e.key==="Escape")setMenu(false)});
var q=document.getElementById("q"),res=document.getElementById("res"),D=null,sel=-1,hits=[];
function money(v){return "$"+Math.round(v).toLocaleString()}
function show(){var t=q.value.toLowerCase().trim();if(!t||!D){res.classList.remove("open");return}
 var w=t.split(/\s+/);hits=D.models.filter(function(m){var n=(m.name+" "+(D.cats[m.cat]||"")).toLowerCase();return w.every(function(x){return n.indexOf(x)>=0})}).slice(0,8);
 sel=hits.length?0:-1;res.innerHTML=hits.length?hits.map(function(m,i){return '<a href="'+m.id+'.html" class="'+(i===sel?"sel":"")+'"><span>'+m.name+'</span><small>'+(m.cur?money(m.cur.median):"")+'</small></a>'}).join(""):'<a href="check.html?q='+encodeURIComponent(q.value)+'"><span>Check “'+q.value.replace(/</g,"")+'” with the price checker</span></a>';
 res.classList.add("open")}
function load(){if(!D)fetch("data/index.json").then(function(r){return r.json()}).then(function(d){D=d;show()})}
q.addEventListener("focus",load);q.addEventListener("input",function(){load();show()});
q.addEventListener("keydown",function(e){var a=res.querySelectorAll("a");if(e.key==="ArrowDown"||e.key==="ArrowUp"){e.preventDefault();sel=(sel+(e.key==="ArrowDown"?1:-1)+a.length)%a.length;a.forEach(function(x,i){x.classList.toggle("sel",i===sel)})}
 if(e.key==="Enter"&&a[sel]){e.preventDefault();location.href=a[sel].getAttribute("href")}});
document.addEventListener("click",function(e){if(!e.target.closest(".search"))res.classList.remove("open")});
})();"""


def page(title, desc, body, path, demo=False, jsonld=None, crumbs=None, og=None, pt="page"):
    canon = f"{config.SITE_URL}/{path}".replace("/index.html", "/")
    banner = '<div class="demo">Preview with sample data. Real prices appear after the first live update.</div>' if demo else ""
    lds = jsonld if isinstance(jsonld, list) else ([jsonld] if jsonld else [])
    crumb_html = ""
    if crumbs:
        trail = [("Home", "index.html")] + crumbs
        crumb_html = '<nav class="crumbs" aria-label="Breadcrumb">' + ' <span aria-hidden="true">/</span> '.join(
            f'<a href="{E(u)}">{E(n)}</a>' if u else f'<span aria-current="page">{E(n)}</span>' for n, u in trail) + "</nav>"
        lds.append({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": n, "item": f"{config.SITE_URL}/{u or path}".replace("/index.html", "/")}
            for i, (n, u) in enumerate(trail)]})
    og_tags = (f'<meta property="og:image" content="{config.SITE_URL}/{og}"><meta property="og:image:width" content="1200">'
               f'<meta property="og:image:height" content="630"><meta name="twitter:card" content="summary_large_image">') if og else ""
    dc = discord_url()
    menu_cats = "".join(f'<a href="{c}.html">{ICONS.get(c, "")}{E(v["label"])}</a>' for c, v in CATS.items() if c in CATS_USED)
    menu = (f'<div class="sheet" id="menu" role="dialog" aria-modal="true" aria-label="Menu"><div class="panel">'
            f'<button class="closebtn" aria-label="Close menu">✕</button><h3>Prices</h3>{menu_cats}'
            f'<h3>Tools</h3><a href="check.html">{ICONS["check"]}Price checker</a><a href="guides.html">{ICONS["guide"]}Buying guides &amp; comparisons</a>'
            f'<a href="report.html">{ICONS["report"]}Weekly market report</a>'
            f'<a href="new.html">{ICONS["new"]}Best deals on new</a><a href="sell.html">{ICONS["sell"]}What\'s my part worth?</a>'
            + (f'<a href="api.html">{ICONS["api"]}Price data API</a>' if config.RAPIDAPI_PROXY_SECRET else "")
            + (f'<a href="discord.html">{ICONS["discord"]}Deals Discord</a>' if dc else "")
            + '<h3>About</h3><a href="about.html">How prices are calculated</a><a href="privacy.html">Privacy</a></div></div>')
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#3d5afe">
<title>{E(title)}</title><meta name="description" content="{E(desc)}">
<link rel="canonical" href="{canon}"><link rel="icon" href="{FAVICON}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,700;12..96,800&display=swap" rel="stylesheet">
{"".join('<script type="application/ld+json">' + json.dumps(x) + '</script>' for x in lds)}
<meta property="og:title" content="{E(title)}">{og_tags}<meta property="og:url" content="{canon}"><meta property="og:description" content="{E(desc)}"><meta property="og:type" content="website">
{'<meta name="robots" content="noindex">' if demo else ''}
{f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={E(config.ADSENSE_CLIENT)}" crossorigin="anonymous"></script>' if config.ADSENSE_CLIENT and not demo else ''}
<style>{CSS}</style></head><body data-pt="{pt}">{banner}
<header class="top"><div class="wrap">
<a class="brand" href="index.html" aria-label="Orbit, used tech prices: home">{LOGO}<span><b>Orbit</b><small>used tech prices</small></span></a>
<div class="search" role="search">{ICONS["search"]}<input id="q" type="search" placeholder="Search a GPU, MacBook, Steam Deck…" aria-label="Search models" autocomplete="off"><div class="results" id="res"></div></div>
<nav class="navlinks" aria-label="Main"><a href="check.html">Price check</a><a href="guides.html">Guides</a>{discord_cta("nav")}</nav>
<button class="menubtn" id="menubtn" aria-expanded="false" aria-controls="menu">{ICONS["menu"]}<span>Browse</span></button>
</div></header>{menu}
<main class="wrap">{crumb_html}{body}</main>
<footer><div class="wrap">{discord_cta()}{FOOTER_LINKS}
<p class="disclose">Prices are eBay US fixed-price listings including shipping, refreshed every few hours. They're asking prices, so check the seller and return policy before buying.
As an eBay Partner Network affiliate, this site may earn a commission from qualifying purchases made through its links.
{'As an Amazon Associate I earn from qualifying purchases. ' if config.AMAZON_TAG else ''}Commissions never change which listings are shown.</p>
<p class="disclose">Orbit by Micah · <a href="about.html">How prices are calculated</a> · <a href="privacy.html">Privacy</a></p></div></footer>
<script>{SITE_JS}</script></body></html>"""


TERMS = {
    "typical": "The median used price of current eBay listings, including shipping. Half of listings cost less, half cost more.",
    "fair": "The middle half of current listings (25th to 75th percentile). Paying inside this range is normal.",
    "deal": f"A listing at least {round((1 - config.DEAL_RATIO) * 100)}% under the typical price, from a seller with {config.MIN_FEEDBACK_PCT:g}%+ positive feedback.",
}


def term(key, text):
    return f'<span class="term" tabindex="0" data-tip="{E(TERMS[key])}">{text}</span>'


def _scale(cur):
    iqr = max(cur["p75"] - cur["p25"], cur["median"] * 0.04)
    lo = max(0, min(cur["low"], cur["p25"] - iqr, cur["median"] * config.DEAL_RATIO * 0.96))
    hi = cur["p75"] + iqr * 1.1
    return lo, hi


def track(cur, you=None, labels=True):
    """Signature component: where the typical price sits inside the fair range, with the deal zone shaded."""
    lo, hi = _scale(cur)
    if you is not None:
        lo, hi = min(lo, you * 0.97), max(hi, you * 1.03)
    pct = lambda v: max(0.0, min(100.0, (v - lo) / (hi - lo) * 100))  # noqa: E731
    deal = pct(cur["median"] * config.DEAL_RATIO)
    t = (f'<div class="track" role="img" aria-label="Typical {money(cur["median"])}, fair range {money(cur["p25"])} to {money(cur["p75"])}">'
         f'<div class="rail"></div><div class="zone" style="width:{deal:.1f}%"></div>'
         f'<div class="fair" style="left:{pct(cur["p25"]):.1f}%;width:{pct(cur["p75"]) - pct(cur["p25"]):.1f}%"></div>'
         f'<div class="dot" style="left:{pct(cur["median"]):.1f}%"></div>'
         + (f'<div class="you" style="left:{pct(you):.1f}%"></div>' if you is not None else "") + "</div>")
    if labels:
        t += (f'<div class="tlabels"><span class="deal">deals under {money(cur["median"] * config.DEAL_RATIO)}</span>'
              f'<span>fair {money(cur["p25"])}–{money(cur["p75"])}</span></div>')
    return t


def model_row(r):
    m, c = r["model"], r["current"]
    unit, per = per_unit(r)
    sub = f"{money(per, 2)}/{unit}" if per else (f"{len(r['deals'])} deal{'s' if len(r['deals']) != 1 else ''} now" if r["deals"] else "")
    if not c:
        return f'<a class="mrow" href="{m["id"]}.html"><span class="nm">{E(m["name"])}<small>not enough listings yet</small></span><span></span><span class="pr">—</span><span class="ch"></span></a>'
    return (f'<a class="mrow" href="{m["id"]}.html"><span class="nm">{E(m["name"])}<small>{sub}</small></span>'
            f'{track(c, labels=False)}<span class="pr">{money(c["median"])}</span><span class="ch">{chg(r["chg_30d"])}</span></a>')


def model_list(reports, cat):
    rows = "".join(model_row(r) for r in reports if r["model"]["cat"] == cat)
    return (f'<div class="mlist"><div class="mhead"><span>Model</span><span>{term("fair", "Fair range")} and {term("typical", "typical")}</span>'
            f'<span>Typical</span><span>30 days</span></div>{rows}</div>')


def deal_card(d):
    under = (1 - d["total"] / d["median"]) * 100
    return (f'<div class="card dealcard"><a href="{d["model"]["id"]}.html"><b>{E(d["model"]["name"])}</b></a>'
            f'<div class="tt">{E(d["title"])}</div>'
            f'<div class="row"><span class="p">{money(d["total"], 0)}</span><span class="save">{under:.0f}% under typical</span></div>'
            f'<div class="k">typical {money(d["median"])} · seller {d.get("seller_pct") or 0:.1f}% positive · incl. shipping</div>'
            f'{aff(d["url"] or "#", "View on eBay", d["model"]["id"])}</div>')


def deals_block(deals, empty="No standout deals right now. They appear here when a listing drops well under the typical price."):
    return f'<div class="dgrid">{"".join(deal_card(d) for d in deals)}</div>' if deals else f'<p class="sub">{empty}</p>'


CATS_USED = set()


CHART_JS = r"""(function(){var el=document.getElementById("chart");if(!el)return;
var S=JSON.parse(document.getElementById("series").textContent),box=el.querySelector(".plot"),tip=el.querySelector(".tip");
function m(v){return "$"+Math.round(v).toLocaleString()}
function draw(n){var p=n?S.slice(-n):S;if(p.length<2)return;var W=800,H=260,L=58,R=14,T=14,B=30;
 var lo=Math.min.apply(null,p.map(function(d){return d[2]}))*0.97,hi=Math.max.apply(null,p.map(function(d){return d[3]}))*1.03;
 function x(i){return L+i*(W-L-R)/(p.length-1)}function y(v){return T+(hi-v)*(H-T-B)/(hi-lo)}
 var g="";for(var k=0;k<5;k++){var v=lo+(hi-lo)*k/4;g+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+y(v)+'" y2="'+y(v)+'" stroke="var(--line)"/><text x="'+(L-10)+'" y="'+(y(v)+4)+'" text-anchor="end" font-size="12" fill="var(--mute)">'+m(v)+'</text>'}
 var band=p.map(function(d,i){return x(i)+","+y(d[3])}).join(" ")+" "+p.map(function(d,i){return x(i)+","+y(d[2])}).reverse().join(" ");
 var line=p.map(function(d,i){return x(i)+","+y(d[1])}).join(" ");
 var lab=[0,Math.floor(p.length/2),p.length-1].map(function(i,j){return '<text x="'+x(i)+'" y="'+(H-8)+'" font-size="12" fill="var(--mute)" text-anchor="'+["start","middle","end"][j]+'">'+p[i][0].slice(5)+'</text>'}).join("");
 box.innerHTML='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="Used price history">'+g+'<polygon points="'+band+'" fill="var(--band)"/><polyline points="'+line+'" fill="none" stroke="var(--accent)" stroke-width="2.6" stroke-linejoin="round"/>'+lab+'<line class="hl" y1="'+T+'" y2="'+(H-B)+'" stroke="var(--ink)" stroke-dasharray="3 4" opacity="0"/><circle class="hc" r="5" fill="var(--accent)" stroke="var(--card)" stroke-width="2" opacity="0"/><rect x="'+L+'" y="0" width="'+(W-L-R)+'" height="'+H+'" fill="transparent"/></svg>';
 var svg=box.querySelector("svg"),hl=svg.querySelector(".hl"),hc=svg.querySelector(".hc");
 function mv(e){var r=svg.getBoundingClientRect(),cx=(e.touches?e.touches[0].clientX:e.clientX)-r.left,sx=cx*W/r.width,i=Math.round((sx-L)/(W-L-R)*(p.length-1));
  if(i<0||i>=p.length)return;var d=p[i];hl.setAttribute("x1",x(i));hl.setAttribute("x2",x(i));hl.setAttribute("opacity",".5");hc.setAttribute("cx",x(i));hc.setAttribute("cy",y(d[1]));hc.setAttribute("opacity","1");
  tip.style.display="block";tip.style.left=(x(i)*r.width/W)+"px";tip.style.top=(y(d[1])*r.height/H)+"px";tip.textContent=d[0]+": "+m(d[1])+" (fair "+m(d[2])+"–"+m(d[3])+")"}
 function out(){tip.style.display="none";hl.setAttribute("opacity","0");hc.setAttribute("opacity","0")}
 svg.addEventListener("mousemove",mv);svg.addEventListener("touchmove",mv,{passive:true});svg.addEventListener("mouseleave",out);svg.addEventListener("touchend",out)}
el.querySelectorAll(".tabs button").forEach(function(b){b.onclick=function(){el.querySelectorAll(".tabs button").forEach(function(o){o.setAttribute("aria-pressed",o===b)});draw(+b.dataset.n)}});
draw(90)})();"""


def verdict(rep):
    cur, ser = rep["current"], rep["series"]
    prior = [p["median"] for p in ser[-91:-1]]
    if len(ser) >= 15 and prior and cur["median"] <= min(prior):
        return '<span class="signal">★ Buy signal</span> <b>Good time to buy:</b> the typical price is the lowest in 90 days.'
    c30 = rep["chg_30d"]
    if c30 is not None and c30 <= -3:
        return f'<b>Prices are falling</b> ({abs(c30):.1f}% in 30 days). Buying now is reasonable; waiting may save a little more.'
    if c30 is not None and c30 >= 3:
        return f'<b>Prices are rising</b> ({c30:.1f}% in 30 days). Look for a listing in the deal zone rather than paying typical.'
    return "<b>Prices are steady.</b> Anything in the deal zone from a well-rated seller is a good buy."


def listing_card(l, rep):
    cur = rep["current"]
    under = (1 - l["total"] / cur["median"]) * 100
    ship = "free shipping" if not l.get("shipping") else f"{money(l['shipping'], 2)} shipping"
    badge = f' <span class="save">{under:.0f}% under typical</span>' if l["total"] <= cur["median"] * config.DEAL_RATIO else ""
    return (f'<div class="card listing"><div><div class="t">{E(l["title"][:110])}</div>'
            f'<div class="meta">{ship} · seller {l["seller_pct"] or 0:.1f}% positive{badge}</div></div>'
            f'<div class="p">{money(l["total"], 2)}</div>{aff(l["url"] or "#", "View on eBay", rep["model"]["id"])}</div>')


def model_page(rep, summary, demo):
    m, cur = rep["model"], rep["current"]
    name = m["name"]
    crumbs = [(CATS.get(m["cat"], {}).get("label", "Prices"), f"{m['cat']}.html"), (name, None)]
    if not cur:
        body = f"<h1>Used {E(name)} price</h1><p class='sub'>Not enough listings yet. Check back after the next update.</p>"
        return page(f"Used {name} Price", f"Used {name} price tracker.", body, f"{m['id']}.html", demo, crumbs=crumbs, pt="model")
    fair = f"{money(cur['p25'])}–{money(cur['p75'])}"
    unit, per = per_unit(rep)
    newp = (rep["new_current"] or {}).get("median")
    amazon = aff(amazon_url(m), "Compare new on Amazon", "amz:" + m["id"], "btn alt") if config.AMAZON_TAG else ""
    ebay_all = aff(ebay_search_url(m.get("query") or name), "See all used on eBay", m["id"])
    facts = "".join(f'<div class="card"><div class="k">{k}</div><div class="v">{v}</div></div>' for k, v in [
        ("7 days", chg(rep["chg_7d"])), ("30 days", chg(rep["chg_30d"])),
        (f"Price per {unit}" if per else "New (median)", money(per, 2) if per else money(newp)),
        ("Listings checked", str(cur["n"]))])
    series = json.dumps([[p["day"], p["median"], p["p25"], p["p75"]] for p in rep["series"][-365:]], separators=(",", ":"))
    listings = "".join(listing_card(l, rep) for l in rep["listings"])
    buy_under = money(cur["p25"])
    faq = f"""<h2>Common questions</h2>
<p><b>How much is a used {E(name)} worth?</b> Most used {E(name)} listings sell between {fair} including shipping. The typical price is {money(cur['median'])}.</p>
<p><b>What is a good price for a used {E(name)}?</b> Anything under about {buy_under} from a well-rated seller is below most of the market, and under {money(cur['median'] * config.DEAL_RATIO)} is a deal.</p>
<p><b>Are prices going up or down?</b> Over the last 30 days the typical used price changed {chg(rep['chg_30d'])}.</p>"""
    body = f"""<h1>Used {E(name)} price</h1>
<p class="sub">Updated {E(cur['day'])} from {cur['n']} current eBay listings, including shipping.</p>
<div class="summary"><div class="card main"><div class="k">{term("typical", "Typical used price")}</div>
<div class="big">{money(cur['median'])}</div>{track(cur)}
<p class="verdict-line">{verdict(rep)}</p>
<div class="actions">{ebay_all}{amazon}<a class="btn ghost" href="check.html?m={E(m["id"])}">Check a listing's price</a></div></div>
<div class="facts">{facts}</div></div>
<h2>Price history</h2>
<div class="chart" id="chart"><div class="tabs" role="group" aria-label="Range"><button data-n="30" aria-pressed="false">30 days</button><button data-n="90" aria-pressed="true">90 days</button><button data-n="365" aria-pressed="false">1 year</button></div>
<div style="position:relative"><div class="plot">{chart_svg(rep['series'])}</div><div class="tip"></div></div>
<p class="k" style="margin:8px 0 0">Line: typical price. Shaded band: fair range. Hover or drag to see a day.</p></div>
<script type="application/json" id="series">{series}</script><script>{CHART_JS}</script>
{f'<h2>Market read</h2><div class="ai">{E(summary)}</div>' if summary else ''}
<h2>Cheapest listings from well-rated sellers</h2>
{f'<div class="lgrid">{listings}</div>' if listings else '<p class="sub">No listings from well-rated sellers right now.</p>'}
<p>{discord_cta("inline")}</p>
{extra.buy_new_html(rep)}
<p><a class="pill" href="sell-{E(m["id"])}.html">{ICONS["sell"]}Selling one? See what your {E(name)} is worth</a></p>
{extra.share_html(f"{config.SITE_URL}/{m['id']}.html", f"Used {name} is going for about {money(cur['median'])} right now", "Share this price")}
<script>{extra.SHARE_JS}</script>
{RELATED.get(m["id"], "")}
{faq}
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
    from . import discover
    from .stats import market_index
    live = [r for r in reports if r["current"]]
    deals = sorted((d | {"model": r["model"], "median": r["current"]["median"]} for r in reports for d in r["deals"]),
                   key=lambda d: d["total"] / d["median"])[:8]
    # featured card: the model with the deepest current deal, else the first GPU
    feat = next((r for r in live if deals and r["model"]["id"] == deals[0]["model"]["id"]), live[0] if live else None)
    featured = ""
    if feat:
        fc = feat["current"]
        featured = (f'<a class="card orbitcard" href="{feat["model"]["id"]}.html" style="color:inherit;text-decoration:none"><div class="ring"></div>'
                    f'<div class="k">Example: {E(feat["model"]["name"])}</div><div class="v" style="font-size:40px;margin:4px 0 6px">{money(fc["median"])}</div>'
                    f'{track(fc)}<p class="k" style="margin:10px 0 0">The dot is the {term("typical", "typical price")}. The blue band is the '
                    f'{term("fair", "fair range")}. Anything in the green zone is a {term("deal", "deal")}.</p></a>')
    cats = []
    for c, v in CATS.items():
        reps = [r for r in live if r["model"]["cat"] == c]
        if not reps:
            continue
        lo, hi = min(r["current"]["median"] for r in reps), max(r["current"]["median"] for r in reps)
        cats.append(f'<a class="card cat" href="{c}.html"><span class="ic">{ICONS.get(c, "")}</span><span><b>{E(v["label"])}</b>'
                    f'<span class="k">{len(reps)} models · {money(lo)}–{money(hi)}</span><span class="k">30 days {chg(market_index(reports, c, "chg_30d"))}</span></span></a>')
    body = f"""<section class="hero"><div>
<h1>What used tech really costs, today.</h1>
<p class="sub" style="font-size:18px">Typical used prices for graphics cards, CPUs, RAM, SSDs, monitors, consoles and iPhones, from live eBay listings. Updated {E(market)}.</p>
<form class="qcheck" action="check.html" method="get" role="search" aria-label="Check a price">
<input name="q" placeholder="Paste a listing title, e.g. RTX 3080 10GB" aria-label="Listing title or model" required>
<input name="p" type="number" inputmode="decimal" placeholder="Price $" aria-label="Total price including shipping">
<button class="btn" type="submit">Check price</button></form>
<p class="k" style="margin-top:10px">Or <a href="#browse">browse every category</a>, see <a href="guides.html">buying guides</a>, or read this week's <a href="report.html">market report</a>.</p>
</div>{featured}</section>
<h2>How it works</h2>
<ol class="steps"><li><b>Collect</b>Every few hours, active eBay listings for {len(live)} popular models.</li>
<li><b>Clean</b>Parts, locked phones, empty boxes and outliers are removed. Shipping is added.</li>
<li><b>Price</b>The middle of the market becomes the typical price and fair range.</li>
<li><b>Flag</b>Listings well under typical, from trusted sellers, become deals.</li></ol>
<h2 id="browse">Browse by category</h2><div class="catgrid">{"".join(cats)}</div>
<div class="grid3">
<a class="card" href="new.html"><b>{ICONS["new"]} Best deals on new</b><p class="k" style="margin:4px 0 0">New-condition listings below the typical new price, plus top-rated picks.</p></a>
<a class="card" href="sell.html"><b>{ICONS["sell"]} What's my part worth?</b><p class="k" style="margin:4px 0 0">Selling or trading in? See today's value and where to sell.</p></a>
{f'<a class="card" href="discord.html"><b>{ICONS["discord"]} Deals Discord</b><p class="k" style="margin:4px 0 0">Free channels that post deals the moment they appear.</p></a>' if config.DISCORD_INVITE else ""}
</div>
<h2>Best deals right now</h2>{deals_block(deals)}<p style="margin-top:12px">{discord_cta("inline")}</p>
{f'<h2>This week in used tech</h2><div class="ai">{E(summary)}</div>' if summary else ''}
{HOME_GUIDES}
{newsletter_html()}"""
    return page(f"{config.SITE_NAME} — Today's Used Prices & Deals",
                "What used GPUs, CPUs, RAM, SSDs, monitors, consoles and iPhones really cost: typical prices, fair ranges, history and the best current deals from live eBay listings.",
                body, "index.html", demo, jsonld=(None if demo else discover.site_ld()), og=OG.get("home"), pt="home")


def category_page(cat, reports, demo):
    from .stats import market_index
    info = CATS[cat]
    reps = [r for r in reports if r["model"]["cat"] == cat]
    deals = sorted((d | {"model": r["model"], "median": r["current"]["median"]} for r in reps for d in r["deals"]),
                   key=lambda d: d["total"] / d["median"])[:8]
    short = info["short"]
    singular = short[:-1] if short.endswith("s") else short
    if singular in ("Monitor", "Console"):
        singular = "gaming monitor" if singular == "Monitor" else "game console"
    body = f"""<h1>Used {E(singular)} prices</h1>
<p class="sub">{E(info.get('intro', ''))} The market moved {chg(market_index(reports, cat, 'chg_7d'))} this week and {chg(market_index(reports, cat, 'chg_30d'))} over 30 days.</p>
{model_list(reports, cat)}
<h2>Best {E(info['short'])} deals right now</h2>{deals_block(deals)}
<p style="margin-top:12px">{discord_cta("inline")}</p>
<div class="actions"><a class="btn ghost" href="check.html">Check a listing's price</a></div>
{CAT_GUIDES.get(cat, "")}
{accessories_html(cat)}
{newsletter_html()}"""
    title = f"Used {info['short']} Prices Today — Fair Prices, History & Deals" if cat != "phone" else "Used iPhone Prices Today — Unlocked iPhone Values & Deals"
    return page(title, f"What used {info['label'].lower()} cost right now: typical prices, trends and deals from live eBay listings.",
                body, f"{cat}.html", demo, crumbs=[(info["label"], None)], og=OG.get("cat-" + cat), pt="category")


def check_page(demo):
    body = r"""<h1>Is this a good price?</h1>
<p class="sub">Paste a listing title or pick a model, add the total price including shipping, and see where it lands in today's used market.</p>
<div class="form card">
<label class="k" for="t">Listing title</label>
<textarea id="t" rows="2" placeholder="e.g. ASUS TUF RTX 3080 10GB OC graphics card"></textarea>
<label class="k" for="m">Model</label>
<select id="m"><option value="">Pick a model…</option></select>
<label class="k" for="p">Total price including shipping</label>
<input id="p" type="number" inputmode="decimal" placeholder="$">
</div>
<div id="out" style="margin-top:22px" aria-live="polite"></div>
<script>
(function(){var D=null,DR=__DR__,$=function(i){return document.getElementById(i)};
function norm(s){return s.toLowerCase().replace(/\s+/g," ")}
function match(t){t=norm(t);var c=t.replace(/ /g,""),best=null,score=0;D.models.forEach(function(m){
 if(!m.must.every(function(w){w=w.toLowerCase();return t.indexOf(w)>=0||c.indexOf(w.replace(/ /g,""))>=0}))return;
 if(m.exclude.some(function(w){return new RegExp("(^|[^a-z0-9])"+w.toLowerCase().replace(/[.*+?^${}()|[\]\\]/g,"\\$&")+"s?($|[^a-z0-9])").test(t)}))return;
 var s=m.must.join("").length;if(s>score){score=s;best=m}});return best}
function money(v){return "$"+Math.round(v).toLocaleString()}
function track(c,you){var iqr=Math.max(c.p75-c.p25,c.median*0.04),lo=Math.max(0,Math.min(c.low,c.p25-iqr,c.median*DR*0.96)),hi=c.p75+iqr*1.1;
 if(you){lo=Math.min(lo,you*0.97);hi=Math.max(hi,you*1.03)}function q(v){return Math.max(0,Math.min(100,(v-lo)/(hi-lo)*100))}
 return '<div class="track"><div class="rail"></div><div class="zone" style="width:'+q(c.median*DR)+'%"></div><div class="fair" style="left:'+q(c.p25)+'%;width:'+(q(c.p75)-q(c.p25))+'%"></div><div class="dot" style="left:'+q(c.median)+'%"></div>'+(you?'<div class="you" style="left:'+q(you)+'%"></div>':'')+'</div>'
  +'<div class="tlabels"><span class="deal">deals under '+money(c.median*DR)+'</span><span>fair '+money(c.p25)+'–'+money(c.p75)+'</span></div>'}
function run(){var id=$("m").value,p=parseFloat($("p").value),m=D.models.find(function(x){return x.id===id});
 if(!m){$("out").innerHTML="";return}
 if(!m.cur){$("out").innerHTML="<p class='sub'>Not enough data for this model yet.</p>";return}
 var c=m.cur,h='<div class="card">';
 if(p>0){var v,cl,d=(p-c.median)/c.median*100;if(p<=c.median*DR){v="Great deal";cl="great"}else if(p<=c.p25){v="Good price";cl="good"}else if(p<=c.p75){v="Fair price";cl="fair"}else{v="Above market";cl="high"}
  h+='<div class="verdict '+cl+'">'+v+'</div><p style="margin:0 0 6px">'+money(p)+' is '+Math.abs(d).toFixed(0)+'% '+(d<0?'below':'above')+' the typical used price of '+money(c.median)+' for the '+m.name+'. The black line is your price.</p>'+track(c,p)
   +'<p class="k">Before buying, check the seller rating, the photos and the return policy. Prices far under market can be scams.</p>';
  history.replaceState(null,"","?m="+id+"&p="+p)}
 else h+='<div class="k">'+m.name+'</div><div class="v">'+money(c.median)+' typical</div>'+track(c)+'<p class="k">Enter a price to get a verdict.</p>';
 h+='<div class="actions"><a class="btn" href="'+m.id+'.html">Price history and best listings</a></div></div>';$("out").innerHTML=h}
fetch("data/index.json").then(function(r){return r.json()}).then(function(d){D=d;
 var g={};d.models.forEach(function(m){(g[m.cat]=g[m.cat]||[]).push(m)});
 Object.keys(g).forEach(function(k){var og=document.createElement("optgroup");og.label=d.cats[k];g[k].forEach(function(m){var o=document.createElement("option");o.value=m.id;o.textContent=m.name;og.appendChild(o)});$("m").appendChild(og)});
 var q=new URLSearchParams(location.search);if(q.get("q")){$("t").value=q.get("q");var mm=match(q.get("q"));if(mm)$("m").value=mm.id}
 if(q.get("m"))$("m").value=q.get("m");if(q.get("p"))$("p").value=q.get("p");run()});
$("t").addEventListener("input",function(){var m=match($("t").value);if(m){$("m").value=m.id;run()}});
$("m").addEventListener("change",run);$("p").addEventListener("input",run);})();
</script>""".replace("__DR__", str(config.DEAL_RATIO))
    body += discord_cta()
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


LAST_URLS: list = []


def build(reports, summaries, demo, models=None):
    global NAV, CATS
    CATS = (models or config.load_models())["categories"]
    CATS_USED.clear()
    CATS_USED.update(r["model"]["cat"] for r in reports)
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
    more, week = pages.write_all(out, reports, summaries, demo)
    more += extra.write_all(out, reports, demo)
    global LAST_WEEK
    LAST_WEEK = week
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls = ["", "check.html", "about.html", "privacy.html"] + [f"{c}.html" for c in cats_used] + [f"{r['model']['id']}.html" for r in reports] + more
    (out / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"<url><loc>{config.SITE_URL}/{u}</loc><lastmod>{now}</lastmod></url>\n" for u in urls)
        + "</urlset>\n")
    from . import discover
    (out / "robots.txt").write_text(discover.robots(demo))
    if not demo:
        glinks = [(g["title"], f"{g['id']}.html") for g in pages.GUIDES if f"{g['id']}.html" in more]
        (out / "llms.txt").write_text(discover.llms_txt(reports, CATS, glinks))
        (out / "llms-full.txt").write_text(discover.llms_full(reports, CATS))
        discover.write_key(out)
    global LAST_URLS
    LAST_URLS = urls
    (out / ".nojekyll").write_text("")
    (out / "404.html").write_text(page(f"Not found — {config.SITE_NAME}", "Page not found.",
        '<h1>Page not found</h1><p class="sub">That page doesn\'t exist. <a href="index.html">See all used prices</a>.</p>',
        "404.html", demo))
    _sync(out, final)
    shutil.rmtree(out)
