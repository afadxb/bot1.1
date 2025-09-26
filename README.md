# Premarket Top-N Watchlist

A lightweight Python 3.11 project that pulls a Finviz Elite export, applies deterministic filters and scoring, and produces a ranked pre-market Top-N watchlist.

## Quickstart

1. Create and populate a `.env` file (or export variables in your shell):

```bash
export FINVIZ_EXPORT_URL="https://elite.finviz.com/export.ashx?...&auth=..."
export CACHE_TTL_MIN=60  # optional
```

2. Install dependencies:

```bash
pip install -e .[dev]
```

3. Run the pipeline (example):

```bash
python -m premarket.orchestrate \
  --config config/strategy.yaml \
  --out data/watchlists/$(date +%F) \
  --top-n 20 \
  --use-cache true
```

On success, the following files will appear under the output directory:

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

Override the Top-N size via CLI or edit `premarket.top_n` in the config.

## Testing

Run unit tests with coverage:

```bash
pytest -q
```

Coverage reports target ≥90% for core modules.

## Troubleshooting

- **Auth errors**: verify `FINVIZ_EXPORT_URL` includes a valid `auth=` token and has not expired. Tokens are never logged; any errors will show a redacted URL.
- **Header drift**: the normalizer maps multiple header synonyms. If Finviz introduces new names, update `premarket/normalize.py` with additional aliases.
- **Missing columns**: the pipeline degrades gracefully—absent data defaults to neutral scores. Review `run_summary.json` for notes and adjust config thresholds if the dataset is sparse.
- **Download failures**: the loader falls back to the most recent cached CSV when available. Increase `CACHE_TTL_MIN` if the service rate-limits frequent requests.

## Logging & Observability

Logs are written using Rich formatting. By default a log file is created under `logs/premarket_<date>.log`. The CLI also prints a concise completion summary showing qualified counts, tier distribution, cache usage, and output paths.
