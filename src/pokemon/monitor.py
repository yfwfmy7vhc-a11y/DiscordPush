"""Pokémon card price monitor — entry point.

Flow per watchlist card:
  1. Search eBay AU (cheapest first).
  2. Keep listings whose TOTAL price (item + shipping) <= target_aud.
  3. Drop excluded-keyword noise and already-alerted listings (unless price dropped).
  4. Ask Claude Haiku to verify each remaining candidate is a legit deal.
  5. Enrich with our own price history + (optional) PriceCharting market value.
  6. Post a Discord embed per verified deal; record it in state to dedupe.

Run:  python -m src.pokemon.monitor
"""

from __future__ import annotations

import time
from typing import Any

from ..common import claude_client, config, discord, fx, state
from . import ebay, history, pricecharting

# Only re-alert a listing we've seen before if its total dropped by at least this much.
_REALERT_DROP_AUD = 5.0
# Forget listings we haven't re-seen in this many days.
_STATE_TTL_DAYS = 30


def _excluded(title: str, exclude: list[str]) -> bool:
    low = title.lower()
    return any(bad.lower() in low for bad in (exclude or []))


def _already_alerted(seen: dict[str, Any], item_id: str, total: float) -> bool:
    prev = seen.get(item_id)
    if not prev:
        return False
    prev_price = prev.get("price", float("inf"))
    return total >= prev_price - _REALERT_DROP_AUD


def _pricecharting_field(listing: dict[str, Any], pc: dict[str, Any]) -> dict[str, Any] | None:
    """Build a 'market value' field from PriceCharting data (USD -> AUD)."""
    lines: list[str] = []
    ungraded = pc.get("ungraded_usd")
    if ungraded is not None:
        aud = fx.usd_to(ungraded)
        if aud and aud > 0:
            discount = (1 - listing["total"] / aud) * 100
            verdict = (f"{discount:.0f}% under market" if discount >= 0
                       else f"{-discount:.0f}% over market")
            lines.append(f"Ungraded: US${ungraded:.2f} ≈ A${aud:.2f} · **{verdict}**")
        else:
            lines.append(f"Ungraded: US${ungraded:.2f}")
    psa10 = pc.get("psa10_usd")
    if psa10 is not None:
        aud10 = fx.usd_to(psa10)
        lines.append(f"PSA 10: US${psa10:.2f}" + (f" ≈ A${aud10:.2f}" if aud10 else ""))
    if pc.get("url"):
        lines.append(f"[PriceCharting ↗]({pc['url']})")
    if not lines:
        return None
    return {"name": "🏷️ Market value (PriceCharting)", "value": "\n".join(lines), "inline": False}


def _deal_embed(
    card_name: str,
    listing: dict[str, Any],
    verdict: dict[str, Any],
    *,
    hist_badge: str = "",
    hist_detail: str = "",
    pc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    concerns = verdict.get("concerns") or []
    fields = [
        {"name": "Total", "value": f"**${listing['total']:.2f} {listing['currency']}** "
                                   f"(item ${listing['price']:.2f} + ship ${listing['shipping']:.2f})",
         "inline": True},
        {"name": "Condition", "value": str(listing.get("condition", "?")), "inline": True},
        {"name": "Buying", "value": str(listing.get("buying_options") or "?"), "inline": True},
        {"name": "Seller", "value": f"{listing.get('seller')} "
                                    f"({listing.get('seller_feedback_pct')}%, "
                                    f"{listing.get('seller_feedback_score')})", "inline": True},
    ]
    # Historical context from our own accumulating daily-low series.
    if hist_detail:
        hist_value = (f"**{hist_badge}**\n{hist_detail}" if hist_badge else hist_detail)
        fields.append({"name": "📈 Price history", "value": hist_value[:1024], "inline": False})
    # Optional market value from PriceCharting.
    if pc:
        pc_field = _pricecharting_field(listing, pc)
        if pc_field:
            fields.append(pc_field)
    fields.append(
        {"name": "Claude verdict",
         "value": f"✅ {verdict.get('reason', '')[:900]} "
                  f"(confidence {float(verdict.get('confidence', 0)):.0%})",
         "inline": False},
    )
    if concerns:
        fields.append(
            {"name": "Heads up", "value": "• " + "\n• ".join(c[:200] for c in concerns[:5]),
             "inline": False}
        )
    # Surface a strong historical signal right in the title.
    title = f"💰 {card_name}"
    if hist_badge and "🔻" in hist_badge:
        title = f"🔻 {card_name} — lowest tracked!"
    return discord.make_embed(
        title=title,
        description=listing.get("title", "")[:400],
        url=listing.get("url") or None,
        color=discord.COLORS["cards"],
        fields=fields,
        thumbnail_url=listing.get("image") or None,
        footer="eBay AU • Pokémon price monitor",
    )


def run() -> int:
    watchlist = config.load_watchlist()
    cards = watchlist.get("cards", [])
    seen = state.load(config.POKEMON_STATE_PATH)
    price_history = state.load(config.PRICE_HISTORY_PATH)

    try:
        token = ebay.get_access_token()
    except Exception as exc:
        print(f"[fatal] could not obtain eBay token: {exc}")
        return 1

    total_alerts = 0
    for card in cards:
        name = card.get("name", card.get("query", "?"))
        query = card.get("query", "")
        target = float(card.get("target_aud", 0))
        exclude = card.get("exclude", [])
        if not query or target <= 0:
            continue

        print(f"\n== {name}  (target <= ${target:.2f} AUD)")
        try:
            listings = ebay.search(token, query, max_price=target, limit=25)
        except Exception as exc:
            print(f"  [warn] search failed: {exc}")
            continue

        # History comparisons must use the card's state BEFORE this run updates it,
        # so a "new low" isn't defeated by the value we're about to record.
        prior_entry = price_history.get(name)
        cheapest_seen: float | None = None  # market floor observed this run
        pc_info: dict[str, Any] | None = None  # lazy PriceCharting lookup

        embeds: list[dict[str, Any]] = []
        for listing in listings:
            if _excluded(listing["title"], exclude):
                continue
            # Track the cheapest non-junk listing (even above target) as the floor.
            if cheapest_seen is None or listing["total"] < cheapest_seen:
                cheapest_seen = listing["total"]

            if listing["total"] > target:
                continue  # only genuine at-or-below-target deals get alerted
            if _already_alerted(seen, listing["item_id"], listing["total"]):
                continue

            verdict = claude_client.verify_listing(name, listing)
            status = "PASS" if verdict.get("legit") else "reject"
            print(f"  [{status}] ${listing['total']:.2f} — {listing['title'][:70]}")
            # Record every candidate we evaluated so we don't re-verify it next run
            # unless the price drops further.
            seen[listing["item_id"]] = {"price": listing["total"], "ts": time.time()}

            if verdict.get("legit") and float(verdict.get("confidence", 0)) >= 0.5:
                if pc_info is None:  # look up market value once, only when alerting
                    pc_info = pricecharting.lookup(query) or {}
                badge, detail = history.summarize(prior_entry, listing["total"])
                embeds.append(
                    _deal_embed(
                        name, listing, verdict,
                        hist_badge=badge, hist_detail=detail, pc=pc_info or None,
                    )
                )

        if embeds:
            discord.send_embeds(config.webhook("cards"), embeds)
            total_alerts += len(embeds)

        # Fold this run's floor into the accumulating daily-low history.
        if cheapest_seen is not None:
            history.record(price_history, name, cheapest_seen)
            print(f"  tracked floor: ${cheapest_seen:.2f}")

    seen = state.prune_older_than(seen, _STATE_TTL_DAYS)
    state.save(config.POKEMON_STATE_PATH, seen)
    state.save(config.PRICE_HISTORY_PATH, price_history)  # keep full history
    print(f"\nDone. {total_alerts} alert(s) sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
