# Premarket Top-N Watchlist

A lightweight Python 3.11 project that pulls a Finviz Elite export, applies deterministic filters and scoring, and produces a ranked pre-market Top-N watchlist.

## Quickstart

1. Copy the sample environment file and populate your values:

```bash
cp .env.example .env
# edit .env to add your Finviz export URL and optional overrides
```

2. Install dependencies:

```bash
pip install -e .[dev]
```

3. Execute the workflow:

```bash
python -m premarket
```

CLI flags are optional—any provided values override `.env` settings.

On success, the following files appear under `PREMARKET_OUT_DIR/<YYYY-MM-DD>`:

- `full_watchlist.json`: detailed data with features, scores, and tags.
- `topN.json`: compact ranking summary for automation.
- `watchlist.csv`: human-friendly table for quick review.
- `run_summary.json`: structured metrics, timings, and notes.

Raw CSV exports are stored under `data/raw/<date>/finviz_elite.csv`.

## Configuration

Strategy defaults live in `config/strategy.yaml`. Tune the thresholds and weights to match your risk tolerance. Fields are validated via Pydantic and include:

- Hard filters (`price_min`, `avg_vol_min`, `earnings_exclude_window_days`, etc.).
- Feature weights and penalty caps.
- Sector diversification ratio (`max_per_sector`).
- Optional news settings (disabled by default).

Override the Top-N size via `.env` (`PREMARKET_TOP_N`) or edit `premarket.top_n` in the config.

### `.env` example

```dotenv
# Required Finviz export URL (auth token is automatically redacted in logs)
FINVIZ_EXPORT_URL="https://elite.finviz.com/export.ashx?...&auth=..."

# Runtime overrides (all optional)
PREMARKET_CONFIG_PATH="config/strategy.yaml"
PREMARKET_OUT_DIR="data/watchlists"      # YYYY-MM-DD is auto-appended
PREMARKET_TOP_N=20                        # override YAML top_n
PREMARKET_USE_CACHE=true                  # reuse downloads within CACHE_TTL_MIN
PREMARKET_NEWS_ENABLED=false              # force news probe on/off
PREMARKET_MAX_PER_SECTOR=0.4              # optional sector cap override
PREMARKET_LOG_FILE="logs/premarket.log"  # defaults to logs/premarket_<date>.log
PREMARKET_DATE=2025-10-01                 # backfill run date (timezone aware)
PREMARKET_FAIL_ON_EMPTY=false             # return success even if no rows qualify
PREMARKET_TZ="America/New_York"          # timezone for scheduling & logging
```

## Testing

Run unit tests with coverage:

```bash
pytest -q
```

Coverage reports target ≥90% for core modules.

## Troubleshooting

| Exit code | Meaning | Common fixes |
|-----------|---------|--------------|
| `0` | Success (check `row_counts.topN` in `run_summary.json` to see how many symbols qualified). | No action required. If `topN` is zero, relax filters or keep `PREMARKET_FAIL_ON_EMPTY=false` to treat empty runs as expected. |
| `2` | No symbols met the filters or were trimmed by sector caps. | Review `run_summary.json` (`row_counts`, `sector_cap_applied`) and adjust thresholds or caps. Ensure `PREMARKET_MAX_PER_SECTOR` is not overly restrictive. |
| `3` | Failed to download or authenticate the Finviz export. | Verify `FINVIZ_EXPORT_URL` (token still valid), network connectivity, or run with `PREMARKET_USE_CACHE=true` to reuse cached data. |

## Logging & Observability

- Logs are written with Rich formatting, and the Finviz URL is redacted to host + query keys (with `auth=` masked).
- `run_summary.json` records `env_overrides_used`, `weights_version`, `csv_hash`, `row_counts`, `used_cached_csv`, `sector_cap_applied`, and `week52_warning_count` for easier auditing.
- `watchlist.csv` includes a `Why` column plus `TopFeature1`–`TopFeature5` showing the primary drivers behind each pick.
- The console summary prints a single line containing date, requested Top-N, tier counts, sector-cap status, cache usage, and output path.

