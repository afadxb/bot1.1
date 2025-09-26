import json
from pathlib import Path

import pandas as pd

from premarket import orchestrate


def _sample_csv(path: Path) -> None:
    rows = [
        {
            "Ticker": "AAA",
            "Company": "Alpha",
            "Sector": "Technology",
            "Industry": "Software",
            "Exchange": "NASDAQ",
            "Country": "USA",
            "Market Cap": "1,500,000,000",
            "P/E": "25",
            "Price": "25",
            "Change": "5%",
            "Gap": "4%",
            "Volume": "500000",
            "Average Volume (3m)": "2000000",
            "Relative Volume": "2.0",
            "Float": "50000000",
            "Short Float": "10%",
            "After-Hours Change": "1%",
            "52-Week Range": "10 - 30",
            "Earnings Date": "2099-01-01",
            "Analyst Recom.": "Buy",
            "Insider Transactions": "1%",
            "Institutional Transactions": "2%",
            "Previous Close": "24",
        },
        {
            "Ticker": "BBB",
            "Company": "Beta",
            "Sector": "Healthcare",
            "Industry": "Biotech",
            "Exchange": "NYSE",
            "Country": "USA",
            "Market Cap": "2,000,000,000",
            "P/E": "30",
            "Price": "45",
            "Change": "3%",
            "Gap": "2%",
            "Volume": "600000",
            "Average Volume (3m)": "3000000",
            "Relative Volume": "1.6",
            "Float": "15000000",
            "Short Float": "12%",
            "After-Hours Change": "0.5%",
            "52-Week Range": "20 - 60",
            "Earnings Date": "2099-01-01",
            "Analyst Recom.": "Strong Buy",
            "Insider Transactions": "0%",
            "Institutional Transactions": "3%",
            "Previous Close": "44",
        },
        {
            "Ticker": "CCC",
            "Company": "Gamma",
            "Sector": "Technology",
            "Industry": "Hardware",
            "Exchange": "OTC",
            "Country": "USA",
            "Market Cap": "500,000,000",
            "P/E": "15",
            "Price": "10",
            "Change": "1%",
            "Gap": "0.5%",
            "Volume": "300000",
            "Average Volume (3m)": "1500000",
            "Relative Volume": "1.7",
            "Float": "5000000",
            "Short Float": "5%",
            "After-Hours Change": "0.1%",
            "52-Week Range": "5 - 12",
            "Earnings Date": "2099-01-01",
            "Analyst Recom.": "Hold",
            "Insider Transactions": "-1%",
            "Institutional Transactions": "-2%",
            "Previous Close": "9.5",
        },
    ]
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)


def test_orchestrate_end_to_end(tmp_path, monkeypatch):
    csv_path = tmp_path / "finviz.csv"
    _sample_csv(csv_path)

    monkeypatch.setenv("FINVIZ_EXPORT_URL", "https://example.com/export")
    monkeypatch.setenv("CACHE_TTL_MIN", "1440")

    monkeypatch.setattr(orchestrate.loader_finviz, "download_csv", lambda url, out_path, use_cache: csv_path)

    out_dir = tmp_path / "out"
    code = orchestrate.run(
        cfg_path="config/strategy.yaml",
        out_dir=str(out_dir),
        top_n=2,
        use_cache=True,
        news_override=False,
        log_file=str(tmp_path / "run.log"),
    )

    assert code == 0
    assert (out_dir / "full_watchlist.json").exists()
    assert (out_dir / "topN.json").exists()
    assert (out_dir / "watchlist.csv").exists()
    assert (out_dir / "run_summary.json").exists()

    topn = json.loads((out_dir / "topN.json").read_text())
    assert topn["top_n"] == 2
    assert len(topn["symbols"]) == 2
