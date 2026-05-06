import pandas as pd

from src.normalizer import sector_percentile


def test_sector_percentile_never_falls_back_to_global_ranking():
    df = pd.DataFrame({
        "sector": ["A", "A", "B"],
        "metric": [10.0, 20.0, 1.0],
    })

    result = sector_percentile(df, "metric", ascending=True)

    assert result.iloc[0] == 0.5
    assert result.iloc[1] == 1.0
    assert result.iloc[2] == 1.0
