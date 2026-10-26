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

## Pi setup
```bash
cd ~ && git clone https://github.com/micahbyrnes00-svg/gpu-prices.git && cd gpu-prices

# 1. Deploy key so the Pi can push only to this repo
ssh-keygen -t ed25519 -N "" -f ~/.ssh/gpu_prices_deploy -C gpu-prices-pi
cat ~/.ssh/gpu_prices_deploy.pub   # GitHub repo -> Settings -> Deploy keys -> Add, tick "Allow write access"
cat >> ~/.ssh/config <<'EOF'
Host github-gpu
  HostName github.com
  IdentityFile ~/.ssh/gpu_prices_deploy
  IdentitiesOnly yes
EOF
git remote set-url origin git@github-gpu:micahbyrnes00-svg/gpu-prices.git
git config user.name "gpu-prices bot"; git config user.email "micahbyrnes00@gmail.com"

# 2. Keys
cp .env.example .env && chmod 600 .env && nano .env

# 3. First real run
python3 run.py all && ./deploy/update.sh

# 4. Schedule every 6 hours
sudo cp deploy/gpu-prices.service deploy/gpu-prices.timer /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now gpu-prices.timer
systemctl list-timers gpu-prices.timer
```
GitHub repo → Settings → Pages → Source: **Deploy from a branch**, branch `main`, folder `/docs`.

## Adding a model
Add an entry to `config/models.json`. `must` words must all appear in the title, `exclude` words reject it, and `min`/`max` set the plausible USD window. RAM entries take `gb` for price per GB.

## Notes
- Before going public, read the eBay API License Agreement and the eBay Partner Network rules on displaying listing data.
- Prices are asking prices for active listings, not sold prices.
