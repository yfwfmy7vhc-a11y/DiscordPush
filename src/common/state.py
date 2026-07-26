"""JSON state persistence.

State is committed back to the repo by the GitHub Actions workflow after each
run, so these files act as a tiny "database" with no hosting required. Keep the
payloads small and prune old entries so the repo doesn't bloat over time.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Sorted keys => deterministic diffs => clean git history.
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")


def prune_older_than(data: dict[str, Any], max_age_days: float, key: str = "ts") -> dict[str, Any]:
    """Drop entries whose ``key`` timestamp (epoch seconds) is older than the cutoff."""
    cutoff = time.time() - max_age_days * 86400
    return {
        k: v
        for k, v in data.items()
        if not (isinstance(v, dict) and isinstance(v.get(key), (int, float)) and v[key] < cutoff)
    }
