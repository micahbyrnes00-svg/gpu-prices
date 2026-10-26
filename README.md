# Used GPU & RAM Prices

A Raspberry Pi pulls used GPU and desktop RAM listings from eBay's official Browse API every 6 hours. It calculates fair prices, trends and deals, writes short AI summaries, and publishes a static site to GitHub Pages from `docs/`. The Pi only makes outbound connections. No ports are opened at home.

```
eBay Browse API ─► Pi: run.py collect ─► SQLite (DATA_DIR)
                                      └► run.py build ─► docs/ ─► git push ─► GitHub Pages
```

## Files
| Path | What it does |
|---|---|
| `config/models.json` | Tracked models, search terms, title filters, price windows |
| `tracker/ebay.py` | eBay OAuth and search (standard library only) |
| `tracker/filters.py` | Drops parts, boxes, bundles, laptops, wrong variants |
| `tracker/stats.py` | Median, fair range, 7/30-day change, deals, $/GB |
| `tracker/ai.py` | Weekly summaries through `AI_CMD` (`claude -p`), with template fallback |
| `tracker/site.py` | HTML pages, JSON data, sitemap, robots.txt |
| `deploy/` | `update.sh` and the systemd service and timer |

No pip packages are needed. It uses Python 3.11+ standard library only.

## Test with fake data (no keys needed)
```
python3 run.py demo --days 60 --no-ai     # builds demo-site/ from a separate demo database
```
Demo builds carry a banner, are set to noindex, and `update.sh` refuses to publish them.

## Pi setup (Pi-hosted, current)
Everything runs and is served from the Pi. `p.sh` wraps each step:
```bash
cd ~/gpu-prices && git pull
bash p.sh prep      # .env defaults, systemd timer installed, checks Claude CLI + Tailscale name
bash p.sh keys      # prompts for eBay production keys (secret hidden) and tests them
bash p.sh golive    # first real build -> /home/pi/site, Caddy on localhost:8088, Tailscale Funnel, 6-hour timer
```
Funnel needs HTTPS certificates and the Funnel attribute enabled for this device in the Tailscale admin console. No router ports are opened.

To publish on GitHub Pages instead, set `PUBLISH=github` and `SITE_DIR=docs` in `.env`, add a write deploy key, and enable Pages from `main` `/docs`.

Other helpers: `p.sh web` (serve demo or real site), `p.sh status`, `p.sh diag`, `p.sh cloudsetup` / `cloudrun` (encrypted weekly OS backup to Google Drive).

## Adding a model
Add an entry to `config/models.json`. `must` words must all appear in the title, `exclude` words reject it, and `min`/`max` set the plausible USD window. RAM entries take `gb` for price per GB.

## Notes
- Before going public, read the eBay API License Agreement and the eBay Partner Network rules on displaying listing data.
- Prices are asking prices for active listings, not sold prices.
