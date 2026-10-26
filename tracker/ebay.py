"""eBay Browse API client (official API; client-credentials OAuth). Standard library only."""
import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from . import config

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
SCOPE = "https://api.ebay.com/oauth/api_scope"

NEW_IDS = {"1000", "1500", "1750"}  # New, New other, New with defects


class EbayClient:
    def __init__(self):
        if not (config.EBAY_CLIENT_ID and config.EBAY_CLIENT_SECRET):
            raise RuntimeError("EBAY_CLIENT_ID / EBAY_CLIENT_SECRET not set (see .env.example)")
        self._token = None
        self._token_exp = 0.0

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        creds = f"{config.EBAY_CLIENT_ID}:{config.EBAY_CLIENT_SECRET}".encode()
        req = urllib.request.Request(
            TOKEN_URL,
            data=urllib.parse.urlencode({"grant_type": "client_credentials", "scope": SCOPE}).encode(),
            headers={
                "Authorization": "Basic " + base64.b64encode(creds).decode(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            body = json.load(r)
        self._token = body["access_token"]
        self._token_exp = time.time() + int(body.get("expires_in", 7200))
        return self._token

    def search(self, query: str, category_id: str, pmin: float, pmax: float, pages: int = 2) -> list[dict]:
        """Fixed-price US listings in a price window. Returns normalized dicts."""
        headers = {
            "Authorization": "Bearer " + self._get_token(),
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        }
        if config.EPN_CAMPAIGN_ID:
            headers["X-EBAY-C-ENDUSERCTX"] = (
                f"affiliateCampaignId={config.EPN_CAMPAIGN_ID},affiliateReferenceId={config.EPN_REFERENCE_ID}"
            )
        flt = (
            f"buyingOptions:{{FIXED_PRICE}},price:[{pmin:.0f}..{pmax:.0f}],priceCurrency:USD,"
            "deliveryCountry:US,itemLocationCountry:US"
        )
        out = []
        for page in range(pages):
            params = {"q": query, "category_ids": category_id, "filter": flt, "limit": 200, "offset": page * 200}
            req = urllib.request.Request(SEARCH_URL + "?" + urllib.parse.urlencode(params), headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    body = json.load(r)
            except urllib.error.HTTPError as e:
                raise RuntimeError(f"eBay search failed for {query!r}: {e.code} {e.read()[:300]!r}") from e
            items = body.get("itemSummaries", [])
            out.extend(_normalize(i) for i in items)
            if len(items) < 200:
                break
            time.sleep(0.5)
        return [i for i in out if i]


def _normalize(it: dict) -> dict | None:
    try:
        price = float(it["price"]["value"])
    except (KeyError, ValueError, TypeError):
        return None
    ship = None
    for opt in it.get("shippingOptions") or []:
        cost = (opt.get("shippingCost") or {}).get("value")
        if cost is not None:
            ship = float(cost)
            break
    seller = it.get("seller") or {}
    return {
        "item_id": it.get("itemId"),
        "title": it.get("title", ""),
        "bucket": "new" if str(it.get("conditionId")) in NEW_IDS else "used",
        "price": price,
        "shipping": ship,
        "total": price + (ship or 0.0),
        "url": it.get("itemAffiliateWebUrl") or it.get("itemWebUrl"),
        "image": (it.get("image") or {}).get("imageUrl"),
        "seller_pct": float(seller["feedbackPercentage"]) if seller.get("feedbackPercentage") else None,
        "seller_score": int(seller["feedbackScore"]) if seller.get("feedbackScore") is not None else None,
    }
