"""Optional lightweight news probing (stub implementation)."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable

from . import utils


def probe(symbols: Iterable[str], cfg) -> Dict[str, dict]:
    """Return empty news signals for the provided symbols.

    This lightweight implementation keeps the interface ready for future
    expansion without performing network activity. It returns neutral scores
    (0 freshness) so that ranking remains deterministic.
    """

    now = utils.now_eastern()
    return {
        symbol: {"freshness_hours": None, "category": None, "timestamp": now}
        for symbol in symbols
    }
