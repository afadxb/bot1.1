"""CLI orchestration for the premarket workflow."""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd
import yaml
from pydantic import BaseModel, Field

from . import features, filters, loader_finviz, normalize, persist, ranker, utils
from .news_probe import probe as news_probe

LOGGER = logging.getLogger(__name__)


class WeightsModel(BaseModel):
    relvol: float
    gap: float
    avgvol: float
    float_band: float
    short_float: float
    after_hours: float
    change: float
    w52pos: float
    news_fresh: float
    analyst: float
    insider_inst: float


class PenaltiesModel(BaseModel):
    earnings_near: float
    pe_outlier: float


class CapsModel(BaseModel):
    max_single_negative: float


class PremarketModel(BaseModel):
    price_min: float
    price_max: float
    avg_vol_min: int
    rel_vol_min: float
    float_min: int
    earnings_exclude_window_days: int
    max_per_sector: float
    top_n: int
    exclude_exchanges: list[str] = Field(default_factory=list)
    exclude_countries: list[str] = Field(default_factory=list)
    weights: WeightsModel
    penalties: PenaltiesModel
    caps: CapsModel


class NewsModel(BaseModel):
    enabled: bool = False
    freshness_hours: int = 24


class StrategyConfig(BaseModel):
    premarket: PremarketModel
    news: NewsModel


def _load_config(path: Path) -> StrategyConfig:
    data = yaml.safe_load(path.read_text())
    return StrategyConfig.model_validate(data)


def _build_filter_config(cfg: PremarketModel) -> filters.FilterConfig:
    return filters.FilterConfig(
        price_min=cfg.price_min,
        price_max=cfg.price_max,
        avg_vol_min=cfg.avg_vol_min,
        rel_vol_min=cfg.rel_vol_min,
        float_min=cfg.float_min,
        earnings_exclude_window_days=cfg.earnings_exclude_window_days,
        exclude_exchanges=cfg.exclude_exchanges,
        exclude_countries=cfg.exclude_countries,
    )


def _build_ranker_config(cfg: PremarketModel) -> ranker.RankerConfig:
    return ranker.RankerConfig(
        weights=ranker.RankerWeights(**cfg.weights.model_dump()),
        penalties=ranker.RankerPenalties(**cfg.penalties.model_dump()),
        caps=ranker.RankerCaps(**cfg.caps.model_dump()),
        earnings_window_days=cfg.earnings_exclude_window_days,
    )


def _determine_output_dir(base_dir: Optional[str], today: str) -> Path:
    if base_dir:
        path = Path(base_dir)
    else:
        path = Path("data/watchlists") / today
    utils.ensure_directory(path)
    return path


def _determine_log_path(log_file: Optional[str], today: str) -> Path:
    if log_file:
        return Path(log_file)
    return Path("logs") / f"premarket_{today}.log"


def _news_scores(symbols: list[str], news_cfg: NewsModel) -> Dict[str, float]:
    if not news_cfg.enabled or not symbols:
        return {symbol: 0.0 for symbol in symbols}
    raw = news_probe(symbols, news_cfg)
    scores: Dict[str, float] = {}
    for symbol, payload in raw.items():
        freshness = payload.get("freshness_hours") if isinstance(payload, dict) else None
        if freshness is None:
            scores[symbol] = 0.0
        else:
            freshness = max(0.0, float(freshness))
            normalized = max(0.0, 1 - min(freshness, news_cfg.freshness_hours) / news_cfg.freshness_hours)
            scores[symbol] = float(np.clip(normalized, 0.0, 1.0))
    return scores


def _tags_for_row(row: pd.Series) -> list[str]:
    tags: list[str] = []
    float_shares = row.get("float_shares")
    if float_shares is not None and float_shares < 20_000_000:
        tags.append("LOW_FLOAT")
    gap_pct = row.get("gap_pct")
    if gap_pct is not None and gap_pct > 20:
        tags.append("EXTREME_GAP")
    earnings_date = row.get("earnings_date")
    if hasattr(earnings_date, "date"):
        if abs((earnings_date.date() - utils.now_eastern().date()).days) <= 1:
            tags.append("EARNINGS_TODAY")
    if row.get("f_52w_pos", 0.0) >= 0.80:
        tags.append("FIFTY_TWO_WEEK_BREAKOUT")
    return tags


def _build_feature_dict(row: pd.Series) -> Dict[str, float]:
    features_map: Dict[str, float] = {}
    for col in row.index:
        if not col.startswith("f_"):
            continue
        value = row[col]
        if value is None or (isinstance(value, float) and np.isnan(value)):
            features_map[col.replace("f_", "")] = 0.0
        else:
            features_map[col.replace("f_", "")] = float(value)
    return features_map


def run(
    cfg_path: str,
    out_dir: Optional[str],
    top_n: Optional[int],
    use_cache: bool,
    news_override: Optional[bool] = None,
    log_file: Optional[str] = None,
) -> int:
    """Execute the full workflow."""

    today = utils.now_eastern().date().isoformat()
    log_path = _determine_log_path(log_file, today)
    logger = utils.setup_logging(log_path)

    try:
        cfg = _load_config(Path(cfg_path))
    except Exception as exc:  # pragma: no cover - config errors
        logger.error("Failed to load config: %s", exc)
        return 1

    finviz_url = utils.env_str("FINVIZ_EXPORT_URL", "")
    if not finviz_url:
        logger.error("FINVIZ_EXPORT_URL is not set. Provide the export URL with auth token.")
        return 3

    news_enabled = news_override if news_override is not None else cfg.news.enabled
    news_cfg = cfg.news.copy()
    news_cfg.enabled = bool(news_enabled)

    output_dir = _determine_output_dir(out_dir, today)

    raw_csv_path = Path("data/raw") / today / "finviz_elite.csv"

    timings: Dict[str, float] = {}
    notes: list[str] = []

    start = time.perf_counter()
    try:
        csv_path = loader_finviz.download_csv(finviz_url, raw_csv_path, use_cache=use_cache)
    except RuntimeError:
        logger.error("Failed to download CSV and no cache available.")
        return 3
    timings["download"] = time.perf_counter() - start
    used_cached_csv = csv_path != raw_csv_path
    notes.append(f"used_cached_csv: {used_cached_csv}")

    start = time.perf_counter()
    df = loader_finviz.read_csv(csv_path)
    raw_rows = len(df)
    df = normalize.normalize_columns(df)
    df = normalize.coerce_types(df)
    timings["normalize"] = time.perf_counter() - start

    filter_cfg = _build_filter_config(cfg.premarket)
    qualified_df, rejected_df = filters.apply_hard_filters(df, filter_cfg)

    if qualified_df.empty:
        logger.warning("No candidates qualified after filters.")
        return 2

    start = time.perf_counter()
    symbols = qualified_df.get("ticker", pd.Series(dtype=str)).fillna("").astype(str).tolist()
    news_scores = _news_scores(symbols, news_cfg)
    qualified_df["news_fresh_score"] = [news_scores.get(sym, 0.0) for sym in symbols]

    featured_df = features.build_features(qualified_df, cfg)

    rank_cfg = _build_ranker_config(cfg.premarket)
    scores = ranker.compute_score(featured_df, rank_cfg)
    featured_df["score"] = scores
    featured_df["tier"] = ranker.assign_tiers(scores)
    timings["score"] = time.perf_counter() - start

    featured_df.sort_values(
        by=["score", "turnover_dollar", "ticker"], ascending=[False, False, True], inplace=True
    )

    top_n_value = top_n if top_n is not None else cfg.premarket.top_n
    diversified_df = ranker.apply_sector_diversity(
        featured_df, top_n=top_n_value, max_fraction=cfg.premarket.max_per_sector
    )

    if diversified_df.empty:
        logger.warning("No symbols selected after sector diversity constraint.")
        return 2

    diversified_df = diversified_df.head(top_n_value)
    diversified_df = diversified_df.copy()
    diversified_df["rank"] = range(1, len(diversified_df) + 1)
    diversified_df["tags"] = diversified_df.apply(_tags_for_row, axis=1)

    generated_at = utils.timestamp_iso()

    full_watchlist = []
    for _, row in featured_df.iterrows():
        features_dict = _build_feature_dict(row)
        item = {
            "symbol": row.get("ticker"),
            "company": row.get("company"),
            "sector": row.get("sector"),
            "industry": row.get("industry"),
            "exchange": row.get("exchange"),
            "market_cap": row.get("market_cap"),
            "pe": row.get("pe"),
            "price": row.get("price"),
            "change_pct": row.get("change_pct"),
            "gap_pct": row.get("gap_pct"),
            "volume": row.get("volume"),
            "avg_volume_3m": row.get("avg_volume_3m"),
            "rel_volume": row.get("rel_volume"),
            "float_shares": row.get("float_shares"),
            "short_float_pct": row.get("short_float_pct"),
            "after_hours_change_pct": row.get("after_hours_change_pct"),
            "week52_range": row.get("week52_range"),
            "week52_pos": row.get("f_52w_pos"),
            "earnings_date": row.get("earnings_date").isoformat()
            if hasattr(row.get("earnings_date"), "isoformat")
            else row.get("earnings_date"),
            "analyst_recom": row.get("analyst_recom"),
            "features": features_dict,
            "score": row.get("score"),
            "tier": row.get("tier"),
            "tags": _tags_for_row(row),
            "rejection_reasons": row.get("rejection_reasons", []),
            "generated_at": generated_at,
        }
        if "insider_transactions" in row:
            item["insider_transactions"] = row.get("insider_transactions")
        if "institutional_transactions" in row:
            item["institutional_transactions"] = row.get("institutional_transactions")
        if "week52_pos" in row:
            item["week52_pos"] = row.get("week52_pos")
        full_watchlist.append(item)

    start = time.perf_counter()
    persist.write_json(full_watchlist, output_dir / "full_watchlist.json")

    top_symbols = diversified_df[["ticker", "score"]].rename(columns={"ticker": "symbol"})
    top_symbols_list = top_symbols["symbol"].tolist()
    persist.write_json(
        {
            "generated_at": generated_at,
            "top_n": top_n_value,
            "symbols": top_symbols_list,
            "ranking": top_symbols.to_dict(orient="records"),
        },
        output_dir / "topN.json",
    )

    watchlist_table = diversified_df[
        ["rank", "ticker", "score", "tier", "gap_pct", "rel_volume", "tags"]
    ].rename(columns={"ticker": "symbol"})
    persist.write_csv(watchlist_table, output_dir / "watchlist.csv")
    timings["persist"] = time.perf_counter() - start

    tier_counts = diversified_df["tier"].value_counts().to_dict()

    run_summary = {
        "date": today,
        "raw_rows": int(raw_rows),
        "qualified": int(len(featured_df)),
        "top_n": int(len(diversified_df)),
        "filters": cfg.premarket.model_dump(),
        "timings_sec": {k: round(v, 3) for k, v in timings.items()},
        "notes": notes,
        "tiers": tier_counts,
    }
    persist.write_json(run_summary, output_dir / "run_summary.json")

    logger.info(
        "Qualified: %s | Top-%s done | Using cache: %s | Tiers %s | Out: %s",
        len(featured_df),
        top_n_value,
        used_cached_csv,
        tier_counts,
        output_dir,
    )

    return 0


def _parse_args(args: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Premarket Top-N watchlist generator")
    parser.add_argument("--config", required=True, help="Path to strategy YAML config")
    parser.add_argument("--out", required=False, help="Output directory")
    parser.add_argument("--top-n", type=int, required=False, help="Override Top-N value")
    parser.add_argument("--use-cache", type=lambda x: x.lower() == "true", default=True)
    parser.add_argument("--news", type=lambda x: x.lower() == "true", required=False)
    parser.add_argument("--log-file", required=False)
    return parser.parse_args(args=args)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    return run(
        cfg_path=args.config,
        out_dir=args.out,
        top_n=args.top_n,
        use_cache=args.use_cache,
        news_override=args.news,
        log_file=args.log_file,
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
