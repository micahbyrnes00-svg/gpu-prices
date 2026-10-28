"""Settings: loaded from environment and an optional .env file in the repo root."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if not os.environ.get(key):  # .env fills anything unset or empty (a parent process may pass empty values)
            os.environ[key] = val


_load_dotenv(ROOT / ".env")

EBAY_CLIENT_ID = os.environ.get("EBAY_CLIENT_ID", "")
EBAY_CLIENT_SECRET = os.environ.get("EBAY_CLIENT_SECRET", "")
EPN_CAMPAIGN_ID = os.environ.get("EPN_CAMPAIGN_ID", "")  # eBay Partner Network campaign id
EPN_REFERENCE_ID = os.environ.get("EPN_REFERENCE_ID", "site")

DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "data"))
DB_PATH = DATA_DIR / "prices.db"
SITE_DIR = Path(os.environ.get("SITE_DIR", ROOT / "docs"))  # GitHub Pages serves /docs

SITE_NAME = os.environ.get("SITE_NAME", "Used Tech Prices")
SITE_URL = os.environ.get("SITE_URL", "https://micahbyrnes00-svg.github.io/gpu-prices").rstrip("/")

AMAZON_TAG = os.environ.get("AMAZON_TAG", "")            # Amazon Associates tracking id, e.g. yourtag-20
ADSENSE_CLIENT = os.environ.get("ADSENSE_CLIENT", "")    # e.g. ca-pub-1234567890123456 (only after AdSense approval)
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")  # Discord channel webhook URL for deal posts
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "")
DISCORD_INVITE = os.environ.get("DISCORD_INVITE", "").rsplit("/", 1)[-1]  # invite code, e.g. AbCd123
NEWSLETTER_URL = os.environ.get("NEWSLETTER_URL", "")    # newsletter provider's embed form action (e.g. Buttondown), optional

# Price data API (sold through RapidAPI). Files under /api/v1 are only built when the proxy secret is set,
# and Caddy refuses /api/* requests that don't carry it, so the data can't be pulled for free around RapidAPI.
RAPIDAPI_PROXY_SECRET = os.environ.get("RAPIDAPI_PROXY_SECRET", "")
RAPIDAPI_URL = os.environ.get("RAPIDAPI_URL", "")          # public RapidAPI listing page, shown on api.html
# "What's my part worth?" trade-in links. Plain links work; paste affiliate/referral URLs to earn on them.
SELL_LINKS = {
    "ebay": os.environ.get("SELL_EBAY_URL", "https://www.ebay.com/sl/sell"),
    "backmarket": os.environ.get("SELL_BACKMARKET_URL", "https://www.backmarket.com/en-us/buyback/home"),
    "decluttr": os.environ.get("SELL_DECLUTTR_URL", "https://www.decluttr.com/"),
    "swappa": os.environ.get("SELL_SWAPPA_URL", "https://swappa.com/sell"),
}

# Command used for AI summaries; prompt is passed on stdin. Empty = template text only.
AI_CMD = os.environ.get("AI_CMD", "claude -p")
AI_REFRESH_DAYS = int(os.environ.get("AI_REFRESH_DAYS", "7"))

# Deal rules
DEAL_RATIO = float(os.environ.get("DEAL_RATIO", "0.85"))  # listing <= 85% of fair price
MIN_FEEDBACK_PCT = float(os.environ.get("MIN_FEEDBACK_PCT", "98"))
MIN_FEEDBACK_SCORE = int(os.environ.get("MIN_FEEDBACK_SCORE", "20"))


def load_models() -> dict:
    return json.loads((ROOT / "config" / "models.json").read_text())
