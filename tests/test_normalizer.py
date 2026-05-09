import pandas as pd
import numpy as np

from src.normalizer import sector_percentile


def test_sector_percentile_never_falls_back_to_global_ranking():
    df = pd.DataFrame({
        "sector": ["A", "A", "A", "B"],
        "metric": [10.0, 20.0, 30.0, 1.0],
    })

    result = sector_percentile(df, "metric", ascending=True)

    assert result.iloc[0] == 1 / 3
    assert result.iloc[1] == 2 / 3
    assert result.iloc[2] == 1.0
    assert np.isnan(result.iloc[3])


def test_sector_percentile_uses_midpoint_for_no_dispersion_group():
    df = pd.DataFrame({
        "sector": ["A", "A", "A"],
        "metric": [10.0, 10.0, 10.0],
    })

    result = sector_percentile(df, "metric", ascending=True)

    assert result.tolist() == [0.5, 0.5, 0.5]
