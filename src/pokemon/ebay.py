"""eBay Browse API client (OAuth client-credentials flow, EBAY_AU marketplace).

Docs: https://developer.ebay.com/api-docs/buy/browse/resources/item_summary/methods/search
Requires an eBay developer application (App ID + Cert ID) — see README.
"""

from __future__ import annotations

import base64
from typing import Any

import requests

from ..common import config

_OAUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"
_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
_SCOPE = "https://api.ebay.com/oauth/api_scope"
_TIMEOUT = 30


def get_access_token() -> str:
    """Client-credentials OAuth token (valid ~2h). Fetched fresh each run."""
    app_id, cert_id = config.ebay_credentials()
    basic = base64.b64encode(f"{app_id}:{cert_id}".encode()).decode()
    resp = requests.post(
        _OAUTH_URL,
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"grant_type": "client_credentials", "scope": _SCOPE},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _money(node: dict[str, Any] | None) -> float:
    if not node:
        return 0.0
    try:
        return float(node.get("value", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _shipping_cost(item: dict[str, Any]) -> float:
    options = item.get("shippingOptions") or []
    for opt in options:
        node = opt.get("shippingCost")
        # Free shipping shows value "0.0"; treat any present cost as authoritative.
        if node is not None:
            return _money(node)
    return 0.0


def search(
    token: str,
    query: str,
    *,
    max_price: float | None = None,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Search item summaries on the AU marketplace, sorted cheapest first.

    Returns a list of normalized dicts with item + shipping + total price.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": config.ebay_marketplace(),
        "Content-Type": "application/json",
    }
    filters = ["buyingOptions:{FIXED_PRICE|AUCTION|BEST_OFFER}"]
    if max_price is not None:
        # Guard against absurd matches; give headroom above target for shipping.
        filters.append(f"price:[..{max_price * 1.5:.2f}],priceCurrency:AUD")

    params = {
        "q": query,
        "limit": str(min(limit, 50)),
        "sort": "price",
        "filter": ",".join(filters),
    }
    resp = requests.get(_SEARCH_URL, headers=headers, params=params, timeout=_TIMEOUT)
    if resp.status_code == 204:  # no matches
        return []
    resp.raise_for_status()
    data = resp.json()

    results: list[dict[str, Any]] = []
    for item in data.get("itemSummaries", []) or []:
        price = _money(item.get("price"))
        if price <= 0:
            continue
        shipping = _shipping_cost(item)
        seller = item.get("seller") or {}
        results.append(
            {
                "item_id": item.get("itemId", ""),
                "title": item.get("title", ""),
                "price": round(price, 2),
                "shipping": round(shipping, 2),
                "total": round(price + shipping, 2),
                "currency": (item.get("price") or {}).get("currency", "AUD"),
                "condition": item.get("condition", "Unspecified"),
                "url": item.get("itemWebUrl", ""),
                "image": (item.get("image") or {}).get("imageUrl", ""),
                "seller": seller.get("username", "?"),
                "seller_feedback_pct": seller.get("feedbackPercentage", "?"),
                "seller_feedback_score": seller.get("feedbackScore", "?"),
                "buying_options": ", ".join(item.get("buyingOptions", []) or []),
                "location": ((item.get("itemLocation") or {}).get("country", "?")),
            }
        )
    return results
