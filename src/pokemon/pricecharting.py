"""PriceCharting API client (optional market-value context).

PriceCharting's product endpoint returns the *current* guide values for a card
(ungraded + graded tiers) in US-cent integers. It does NOT return a full daily
history, so "cheapest since 2022" is built from our own accumulating history
(see src/pokemon/history.py) — this module supplies present-day market value so
an alert can say "X% under market".

Requires a PriceCharting API token (paid plan) in PRICECHARTING_TOKEN. When the
token is absent, lookup() returns None and enrichment is silently skipped.

Docs: https://www.pricecharting.com/api-documentation
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

import requests

from ..common import config

_URL = "https://www.pricecharting.com/api/product"
_TIMEOUT = 30


def _cents_to_usd(value: Any) -> float | None:
    try:
        return round(int(value) / 100, 2)
    except (TypeError, ValueError):
        return None


def lookup(query: str) -> dict[str, Any] | None:
    """Look up a card's current PriceCharting values. None if disabled/failed.

    Returned dict (USD):
      {name, set, ungraded_usd, grade9_usd, grade95_usd, psa10_usd, url}
    Any individual price may be None if PriceCharting doesn't publish that tier.
    """
    token = config.pricecharting_token()
    if not token:
        return None
    try:
        resp = requests.get(_URL, params={"t": token, "q": query}, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"  [pricecharting] lookup failed: {exc}")
        return None
    if data.get("status") != "success":
        return None

    # PriceCharting trading-card column -> field mapping (best effort; tiers vary
    # by product). We surface whatever is present and label conservatively.
    return {
        "name": data.get("product-name"),
        "set": data.get("console-name"),
        "ungraded_usd": _cents_to_usd(data.get("loose-price")),
        "grade9_usd": _cents_to_usd(data.get("graded-price")),
        "grade95_usd": _cents_to_usd(data.get("box-only-price")),
        "psa10_usd": _cents_to_usd(data.get("manual-only-price")),
        "url": f"https://www.pricecharting.com/search-products?q={quote_plus(query)}&type=prices",
    }
