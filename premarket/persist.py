"""Persistence utilities for writing outputs."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Sequence, Tuple

import pandas as pd

from . import utils


SQLITE_DB_PATH = Path("premarket.db")


def write_json(obj: Any, path: Path) -> None:
    """Write a JSON object to disk."""
    utils.ensure_directory(path.parent)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)


def write_csv(df: pd.DataFrame, path: Path) -> None:
    """Write a DataFrame to CSV."""
    utils.ensure_directory(path.parent)
    df.to_csv(path, index=False)


def _ensure_table(conn: sqlite3.Connection, table: str) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table} (
            run_date TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            payload TEXT NOT NULL
        )
        """
    )


def _clear_table(conn: sqlite3.Connection, table: str, run_date: str) -> None:
    conn.execute(f"DELETE FROM {table} WHERE run_date = ?", (run_date,))


def _as_json_rows(
    run_date: str, generated_at: str, records: Sequence[Dict[str, Any]]
) -> list[Tuple[str, str, str]]:
    rows: list[Tuple[str, str, str]] = []
    for record in records:
        payload = json.dumps(record, ensure_ascii=False)
        rows.append((run_date, generated_at, payload))
    return rows


def write_sqlite_outputs(
    run_date: str,
    generated_at: str,
    full_watchlist: list[Dict[str, Any]],
    top_n_records: list[Dict[str, Any]],
    watchlist_records: list[Dict[str, Any]],
    run_summary: Dict[str, Any],
    db_path: Path | str | None = None,
) -> None:
    """Persist run artifacts into a SQLite database for easy sharing."""

    path = Path(db_path) if db_path is not None else SQLITE_DB_PATH
    utils.ensure_directory(path.parent)

    full_rows = _as_json_rows(run_date, generated_at, full_watchlist)
    top_rows = _as_json_rows(run_date, generated_at, top_n_records)
    watch_rows = _as_json_rows(run_date, generated_at, watchlist_records)
    summary_row = (run_date, generated_at, json.dumps(run_summary, ensure_ascii=False))

    with sqlite3.connect(path) as conn:
        _ensure_table(conn, "full_watchlist")
        _ensure_table(conn, "top_n")
        _ensure_table(conn, "watchlist")
        _ensure_table(conn, "run_summary")

        _clear_table(conn, "full_watchlist", run_date)
        if full_rows:
            conn.executemany(
                "INSERT INTO full_watchlist (run_date, generated_at, payload) VALUES (?, ?, ?)",
                full_rows,
            )

        _clear_table(conn, "top_n", run_date)
        if top_rows:
            conn.executemany(
                "INSERT INTO top_n (run_date, generated_at, payload) VALUES (?, ?, ?)",
                top_rows,
            )

        _clear_table(conn, "watchlist", run_date)
        if watch_rows:
            conn.executemany(
                "INSERT INTO watchlist (run_date, generated_at, payload) VALUES (?, ?, ?)",
                watch_rows,
            )

        _clear_table(conn, "run_summary", run_date)
        conn.execute(
            "INSERT INTO run_summary (run_date, generated_at, payload) VALUES (?, ?, ?)",
            summary_row,
        )
