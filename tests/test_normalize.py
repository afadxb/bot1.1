import pandas as pd

from premarket import normalize


def test_normalize_columns_and_types():
    df = pd.DataFrame(
        {
            "Ticker": ["AAA"],
            "Relative Vol.": ["1.8"],
            "Average Volume (3M)": ["1,500,000"],
            "Change": ["5%"],
            "52-Week Range": ["10 - 20"],
            "Price": ["18.5"],
            "Previous Close": ["17.5"],
        }
    )

    normalized = normalize.normalize_columns(df)
    assert "rel_volume" in normalized.columns

    coerced = normalize.coerce_types(normalized)
    assert coerced.loc[0, "rel_volume"] == 1.8
    assert coerced.loc[0, "avg_volume_3m"] == 1_500_000
    assert round(coerced.loc[0, "change_pct"], 2) == 5.0
    assert round(coerced.loc[0, "gap_pct"], 2) == round((18.5 - 17.5) / 17.5 * 100, 2)

    week_pos = normalize.compute_week52_pos(coerced)
    assert 0.0 <= week_pos.iloc[0] <= 1.0
