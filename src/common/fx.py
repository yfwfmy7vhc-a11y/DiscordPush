"""Tiny currency conversion helper.

PriceCharting values are in USD; eBay AU listings are in AUD. To compare them we
convert USD -> AUD using a free, no-key rates endpoint. Fails soft: if the rate
can't be fetched, callers just show the USD figure unconverted.
"""

from __future__ import annotations

from functools import lru_cache

import requests

_URL = "https://open.er-api.com/v6/latest/USD"
_TIMEOUT = 20


@lru_cache(maxsize=1)
def _rates() -> dict[str, float]:
    try:
        resp = requests.get(_URL, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json().get("rates", {}) or {}
    except Exception as exc:
        print(f"  [fx] rate fetch failed ({exc}); prices will show in USD.")
        return {}


def usd_to(amount_usd: float | None, code: str = "AUD") -> float | None:
    """Convert a USD amount to `code`, or None if unavailable."""
    if amount_usd is None:
        return None
    rate = _rates().get(code)
    if not rate:
        return None
    return round(amount_usd * rate, 2)
