"""Self-built price history: the cheapest total we observe per card, per day.

Stored in state/price_history.json and committed back each run, so over time it
becomes a genuine daily time series of eBay-AU prices for your watchlist. This is
what powers "cheapest since <you started tracking>" and "new tracked low" — no
paid data source required, though it only knows history from when tracking began.

Shape:
  {
    "<card name>": {
      "first_tracked": "2025-07-26",
      "daily_low": { "2025-07-26": 245.0, "2025-07-27": 240.0, ... }
    }
  }

Storing one min-price per day keeps the file small (~365 entries/card/year) while
preserving enough resolution to answer "cheapest in the last N days".
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any


def _today() -> str:
    return date.today().isoformat()


def _fmt(iso_date: str) -> str:
    try:
        return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%-d %b %Y")
    except ValueError:
        return iso_date


def record(history: dict[str, Any], card: str, total: float) -> None:
    """Fold today's cheapest observed `total` for `card` into the history."""
    entry = history.setdefault(card, {"first_tracked": _today(), "daily_low": {}})
    entry.setdefault("first_tracked", _today())
    daily = entry.setdefault("daily_low", {})
    today = _today()
    if today not in daily or total < daily[today]:
        daily[today] = round(total, 2)


def summarize(prior_entry: dict[str, Any] | None, total: float, window_days: int = 90) -> tuple[str, str]:
    """Compare `total` against PRIOR history (before today's update).

    Returns (badge, detail):
      - badge: short emoji tag for a notable low ("" if unremarkable)
      - detail: one-line human context always safe to show
    Pass the card's history entry as it was *before* this run recorded anything,
    so "new low" isn't defeated by today's own value.
    """
    if not prior_entry or not prior_entry.get("daily_low"):
        return ("🆕 First time tracked", "No prior price history yet — building it from now.")

    daily: dict[str, float] = prior_entry["daily_low"]
    low_date = min(daily, key=lambda d: daily[d])
    low = daily[low_date]
    first = prior_entry.get("first_tracked", low_date)

    cutoff = (date.today() - timedelta(days=window_days)).isoformat()
    recent = [p for d, p in daily.items() if d >= cutoff]
    low_window = min(recent) if recent else None

    if total <= low:
        return (
            "🔻 Lowest since tracking began",
            f"Beats the previous tracked low of A${low:.2f} ({_fmt(low_date)}); "
            f"tracking since {_fmt(first)}.",
        )
    if low_window is not None and total <= low_window:
        return (
            f"📉 Cheapest in {window_days} days",
            f"All-time tracked low is A${low:.2f} ({_fmt(low_date)}).",
        )
    return ("", f"Tracked low: A${low:.2f} on {_fmt(low_date)} (since {_fmt(first)}).")
