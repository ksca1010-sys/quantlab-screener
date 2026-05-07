import pandas as pd

from src.scorers.value import score_value


def test_missing_peg_does_not_reweight_other_value_components():
    universe = pd.DataFrame({
        "code": ["best", "low"],
        "sector": ["Tech", "Tech"],
    })
    market_data = pd.DataFrame({
        "code": ["best", "low"],
        "per": [5.0, 20.0],
        "pbr": [0.5, 3.0],
        "peg": [float("nan"), float("nan")],
        "dividend_yield": [5.0, 0.0],
    })

    result = score_value(universe, {}, market_data)

    assert result["best"] == 75.0
