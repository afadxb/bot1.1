"""Utility helpers for the premarket pipeline."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from dateutil import tz
from rich.logging import RichHandler
from urllib.parse import parse_qsl, urlsplit, urlunsplit

DEFAULT_TZ_NAME = "America/New_York"
EASTERN = tz.gettz(DEFAULT_TZ_NAME)


def configure_timezone(tz_name: str) -> None:
    """Configure the default timezone used across the project."""

    global EASTERN
    resolved = tz.gettz(tz_name)
    EASTERN = resolved if resolved is not None else tz.gettz(DEFAULT_TZ_NAME)


def ensure_directory(path: Path) -> None:
    """Ensure that a directory exists."""
    path.mkdir(parents=True, exist_ok=True)


def now_eastern() -> datetime:
    """Return the current time in US Eastern time."""
    return datetime.now(tz=EASTERN)


def timestamp_iso(dt: Optional[datetime] = None) -> str:
    """Return an ISO8601 string for the given datetime (defaults to now)."""
    if dt is None:
        dt = now_eastern()
    return dt.isoformat()


def setup_logging(log_file: Optional[Path] = None) -> logging.Logger:
    """Configure logging with Rich formatting."""
    handlers: list[logging.Handler] = [RichHandler(rich_tracebacks=True)]
    if log_file is not None:
        ensure_directory(log_file.parent)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
        )
        handlers.append(file_handler)

    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=handlers,
        force=True,
    )
    return logging.getLogger("premarket")


def safe_float(value: Any) -> Optional[float]:
    """Parse a value into float where possible."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, bool):
            return float(value)
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped or stripped.upper() in {"N/A", "NA", "-"}:
            return None
        stripped = stripped.replace(",", "").replace("$", "")
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def safe_percent(value: Any) -> Optional[float]:
    """Parse percent values (with % sign) into floats."""
    if isinstance(value, str):
        value = value.replace("%", "")
    result = safe_float(value)
    if result is None:
        return None
    return result


def safe_int(value: Any) -> Optional[int]:
    """Parse integers with commas and symbols."""
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip().replace(",", "")
        if not stripped or stripped.upper() in {"N/A", "NA", "-"}:
            return None
        try:
            return int(float(stripped))
        except ValueError:
            return None
    return None


def parse_range(range_str: Any) -> Optional[tuple[float, float]]:
    """Parse a range string like '15 - 28'."""
    if not isinstance(range_str, str):
        return None
    parts = [p.strip() for p in range_str.split("-") if p.strip()]
    if len(parts) != 2:
        return None
    low = safe_float(parts[0])
    high = safe_float(parts[1])
    if low is None or high is None or high == low:
        return None
    return low, high


def read_json(path: Path) -> Any:
    """Read a JSON file."""
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def redact_token(url: str) -> str:
    """Redact sensitive query parameters from a URL for logging."""

    if not url:
        return url

    try:
        parsed = urlsplit(url)
    except ValueError:
        return url

    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    if not query_pairs:
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", parsed.fragment))

    masked_pairs: list[str] = []
    for key, value in query_pairs:
        if key.lower() == "auth":
            masked_pairs.append(f"{key}=***")
        else:
            placeholder = "<redacted>" if value else ""
            masked_pairs.append(f"{key}={placeholder}" if placeholder else key)

    masked_query = "&".join(masked_pairs)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, masked_query, parsed.fragment))


def env_str(key: str, default: Optional[str] = None) -> Optional[str]:
    """Read an environment variable with optional default."""
    return os.environ.get(key, default)


def ensure_iterable(obj: Optional[Iterable[str]]) -> list[str]:
    """Return a list from an iterable, ignoring None."""
    if obj is None:
        return []
    return [item for item in obj]
