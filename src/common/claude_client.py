"""Thin wrapper around the Anthropic SDK (Claude Haiku).

Three jobs:
  - verify_listing:  judge whether an eBay listing is a legit deal worth pinging.
  - summarize_digest: turn a batch of headlines into a concise Discord brief.
  - classify_urgent:  decide if a single article is a major AU cyber incident.

All calls use claude-haiku-4-5. Verification and classification use structured
outputs (json_schema) so we always get parseable JSON.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

import anthropic

from . import config


@lru_cache(maxsize=1)
def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=config.anthropic_api_key())


def _structured(prompt: str, schema: dict[str, Any], max_tokens: int = 512) -> dict[str, Any]:
    """Run Haiku with a JSON-schema-constrained response and return parsed dict."""
    resp = _client().messages.create(
        model=config.HAIKU_MODEL,
        max_tokens=max_tokens,
        output_config={"format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": prompt}],
    )
    text = next((b.text for b in resp.content if b.type == "text"), "{}")
    return json.loads(text)


# ---------------------------------------------------------------------------
# Pokémon listing verification
# ---------------------------------------------------------------------------
_VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "legit": {"type": "boolean"},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
        "concerns": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["legit", "confidence", "reason", "concerns"],
    "additionalProperties": False,
}


def verify_listing(card_name: str, listing: dict[str, Any]) -> dict[str, Any]:
    """Ask Haiku whether an eBay listing is a genuine deal for the target card.

    Returns dict: {legit, confidence (0-1), reason, concerns[]}.
    """
    prompt = (
        "You are vetting eBay Australia listings for a Pokemon card collector before "
        "sending them a price-drop alert. Only genuine singles of the ACTUAL card at a "
        "genuinely good price should pass.\n\n"
        f"Target card the collector wants: {card_name}\n\n"
        "Listing under review:\n"
        f"- Title: {listing.get('title')}\n"
        f"- Price (item): {listing.get('price')} {listing.get('currency')}\n"
        f"- Shipping: {listing.get('shipping')} {listing.get('currency')}\n"
        f"- Total: {listing.get('total')} {listing.get('currency')}\n"
        f"- Condition: {listing.get('condition')}\n"
        f"- Seller: {listing.get('seller')} "
        f"(feedback {listing.get('seller_feedback_pct')}%, "
        f"{listing.get('seller_feedback_score')} reviews)\n"
        f"- Buying option: {listing.get('buying_options')}\n"
        f"- Location: {listing.get('location')}\n\n"
        "Reject (legit=false) if the listing is: a proxy/fake/custom/orica/replica, a "
        "digital or code card, a lot/bundle when a single is wanted, the wrong card or "
        "wrong set/number, a damaged card sold as mint with no disclosure, an obvious "
        "scam (price far too good, brand-new seller with zero feedback), a graded slab "
        "priced like a raw card mismatch, an empty box/wrapper, or a poster/sticker/jumbo "
        "novelty. Be strict but fair: a normal raw or graded single of the right card at "
        "or below the collector's target is legit=true.\n\n"
        "Give confidence 0-1, a one-sentence reason, and any concerns as short strings."
    )
    try:
        return _structured(prompt, _VERIFY_SCHEMA)
    except Exception as exc:  # never let a model hiccup crash the run
        return {
            "legit": False,
            "confidence": 0.0,
            "reason": f"verification error: {exc}",
            "concerns": ["Could not verify with Claude; suppressed to avoid a bad ping."],
        }


# ---------------------------------------------------------------------------
# Daily news digest
# ---------------------------------------------------------------------------
_CATEGORY_BRIEF = {
    "cyber": "cyber security (breaches, vulnerabilities, threat actors, notable CVEs, "
    "ransomware, and anything materially affecting Australian orgs)",
    "tech": "general technology and IT (major product, platform, infra, and industry news)",
    "ai": "artificial intelligence (model releases, research, tooling, policy, and industry moves)",
}


def summarize_digest(category: str, items: list[dict[str, Any]]) -> str:
    """Summarise a list of {title, source, link, summary} into a Discord-ready brief."""
    focus = _CATEGORY_BRIEF.get(category, category)
    lines = []
    for i, it in enumerate(items, 1):
        lines.append(
            f"{i}. [{it.get('source', '?')}] {it.get('title', '').strip()}\n"
            f"   {(it.get('summary') or '').strip()[:400]}"
        )
    corpus = "\n".join(lines)

    prompt = (
        f"You are writing a concise morning briefing on {focus} for a busy IT/security "
        "professional in Australia. Below are the last ~24h of headlines pulled from RSS.\n\n"
        "Write a tight brief for Discord using Markdown:\n"
        "- Start with a one-line 'vibe of the day' summary.\n"
        "- Then 4-8 bullet points ranked by importance. Each bullet: bold a 3-6 word hook, "
        "then one crisp sentence on what happened and why it matters. Prefer Australian-"
        "relevant items where present.\n"
        "- Merge duplicate stories. Skip fluff, listicles, and pure marketing.\n"
        "- Do NOT invent facts or links; only use what's provided. Keep it under ~1800 characters.\n\n"
        f"Headlines:\n{corpus}"
    )
    resp = _client().messages.create(
        model=config.HAIKU_MODEL,
        max_tokens=1400,
        messages=[{"role": "user", "content": prompt}],
    )
    return next((b.text for b in resp.content if b.type == "text"), "").strip()


# ---------------------------------------------------------------------------
# Urgent AU cyber classification
# ---------------------------------------------------------------------------
_URGENT_SCHEMA = {
    "type": "object",
    "properties": {
        "is_urgent_au_cyber": {"type": "boolean"},
        "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
        "headline": {"type": "string"},
        "why": {"type": "string"},
    },
    "required": ["is_urgent_au_cyber", "severity", "headline", "why"],
    "additionalProperties": False,
}


def classify_urgent(item: dict[str, Any]) -> dict[str, Any]:
    """Decide whether an article is a major, time-sensitive Australian cyber incident."""
    prompt = (
        "Decide whether this news item is a MAJOR, time-sensitive cyber security incident "
        "relevant to Australia and worth an immediate push alert.\n\n"
        f"Source: {item.get('source')}\n"
        f"Title: {item.get('title')}\n"
        f"Summary: {(item.get('summary') or '')[:800]}\n\n"
        "is_urgent_au_cyber = true ONLY for things like: an active breach/attack on a notable "
        "Australian organisation or government body; a widely-exploited critical vulnerability "
        "affecting AU orgs; a national-scale outage caused by a cyber incident; an ACSC/ASD "
        "alert or advisory; large-scale data theft affecting Australians. \n"
        "false for: routine vendor patches with no active exploitation, opinion/analysis, "
        "overseas-only incidents with no AU angle, product marketing, or old/rehashed news.\n\n"
        "Set severity (low/medium/high/critical), a short punchy headline, and a one-sentence why."
    )
    try:
        return _structured(prompt, _URGENT_SCHEMA)
    except Exception as exc:
        return {
            "is_urgent_au_cyber": False,
            "severity": "low",
            "headline": item.get("title", "")[:120],
            "why": f"classification error: {exc}",
        }
