"""Central configuration: env vars, paths, and config-file loading.

All secrets come from environment variables (set as GitHub repository secrets).
Config files live under config/, mutable state under state/.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"
STATE_DIR = REPO_ROOT / "state"

WATCHLIST_PATH = CONFIG_DIR / "watchlist.json"
FEEDS_PATH = CONFIG_DIR / "feeds.yaml"
POKEMON_STATE_PATH = STATE_DIR / "pokemon_seen.json"
NEWS_STATE_PATH = STATE_DIR / "news_seen.json"
# Our own accumulating daily-low price history (grows into a real time series).
PRICE_HISTORY_PATH = STATE_DIR / "price_history.json"

# ---------------------------------------------------------------------------
# Models / timezone
# ---------------------------------------------------------------------------
# Haiku is used everywhere: cheap, fast, plenty for verification + digests.
HAIKU_MODEL = "claude-haiku-4-5"
LOCAL_TZ = "Australia/Sydney"
DIGEST_HOUR_LOCAL = 7  # 7am Sydney


def _require(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            "Set it as a GitHub repository secret (see README)."
        )
    return val


def _optional(name: str) -> str:
    return os.environ.get(name, "").strip()


# ---------------------------------------------------------------------------
# Secrets (read lazily via functions so importing this module never crashes)
# ---------------------------------------------------------------------------
def anthropic_api_key() -> str:
    return _require("ANTHROPIC_API_KEY")


def ebay_credentials() -> tuple[str, str]:
    return _require("EBAY_APP_ID"), _require("EBAY_CERT_ID")


def ebay_marketplace() -> str:
    # Defaults to Australia; override with EBAY_MARKETPLACE_ID if desired.
    return _optional("EBAY_MARKETPLACE_ID") or "EBAY_AU"


def pricecharting_token() -> str:
    # Optional. When set, alerts are enriched with PriceCharting market values.
    return _optional("PRICECHARTING_TOKEN")


# Discord webhooks — one per stream. Missing ones are treated as "disabled".
def webhook(stream: str) -> str:
    env_name = {
        "cards": "DISCORD_WEBHOOK_CARDS",
        "cyber": "DISCORD_WEBHOOK_CYBER",
        "tech": "DISCORD_WEBHOOK_TECH",
        "ai": "DISCORD_WEBHOOK_AI",
        "urgent": "DISCORD_WEBHOOK_URGENT",
    }[stream]
    return _optional(env_name)


# ---------------------------------------------------------------------------
# Config-file loaders
# ---------------------------------------------------------------------------
def load_watchlist() -> dict[str, Any]:
    with WATCHLIST_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_feeds() -> dict[str, Any]:
    with FEEDS_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)
