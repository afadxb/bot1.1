"""Finviz Elite CSV loader with caching and retries."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

import pandas as pd
import requests
from tenacity import RetryError, retry, stop_after_attempt, wait_exponential

from . import utils

LOGGER = logging.getLogger(__name__)


def _cache_ttl_minutes() -> int:
    value = utils.env_str("CACHE_TTL_MIN")
    if value is None:
        return 60
    try:
        return int(value)
    except ValueError:
        return 60


def _fetch_with_requests(url: str) -> str:
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    return response.text


def _fetch_with_urllib(url: str) -> str:
    try:
        with urllib_request.urlopen(url, timeout=15) as response:  # type: ignore[arg-type]
            status = getattr(response, "status", 200)
            if status and status >= 400:
                raise requests.RequestException(f"HTTP {status}")
            headers = getattr(response, "headers", None)
            if headers is not None:
                encoding = headers.get_content_charset() or "utf-8"
            else:
                encoding = "utf-8"
            content = response.read()
            return content.decode(encoding, errors="replace")
    except (HTTPError, URLError, OSError) as exc:  # pragma: no cover - defensive
        raise requests.RequestException(str(exc)) from exc


def _is_stub_network_error(exc: Exception) -> bool:
    return "Network access disabled" in str(exc)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def _http_get(url: str) -> str:
    try:
        return _fetch_with_requests(url)
    except requests.RequestException as exc:
        if _is_stub_network_error(exc):
            LOGGER.info("requests stub detected, retrying download via urllib")
            return _fetch_with_urllib(url)
        raise


def _latest_cached_file(base_dir: Path) -> Optional[Path]:
    if not base_dir.exists():
        return None
    candidates = sorted(base_dir.glob("*/finviz_elite.csv"))
    if not candidates:
        return None
    return candidates[-1]


def download_csv(url: str, out_path: Path, use_cache: bool) -> Path:
    """Download the CSV, falling back to cache if necessary."""
    utils.ensure_directory(out_path.parent)

    if use_cache and out_path.exists():
        ttl = timedelta(minutes=_cache_ttl_minutes())
        modified = datetime.fromtimestamp(out_path.stat().st_mtime, tz=timezone.utc)
        if datetime.now(timezone.utc) - modified < ttl:
            LOGGER.info("Using cached CSV at %s", out_path)
            return out_path

    try:
        LOGGER.info("Downloading Finviz CSV from %s", utils.redact_token(url))
        content = _http_get(url)
        out_path.write_text(content, encoding="utf-8")
        return out_path
    except (requests.RequestException, RetryError) as exc:
        LOGGER.warning("Download failed: %s", exc)
        fallback = _latest_cached_file(out_path.parent.parent)
        if fallback is None:
            raise RuntimeError("Download failed and no cached CSV available") from exc
        LOGGER.warning("Falling back to cached CSV at %s", fallback)
        return fallback


def read_csv(path: Path) -> pd.DataFrame:
    """Read a CSV file into a DataFrame."""
    return pd.read_csv(path)
