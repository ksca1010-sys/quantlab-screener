import pandas as pd

from src.aggregator import aggregate, to_csv
from src.main import print_summary


def test_total_uses_four_axis_equal_weight_and_ignores_risk():
    universe = pd.DataFrame({
        "code": ["000001", "000002"],
        "name": ["A", "B"],
        "market": ["KOSPI", "KOSPI"],
        "sector": ["Tech", "Tech"],
        "market_cap": [1000, 900],
    })
    growth = pd.Series({"000001": 100, "000002": 100})
    value = pd.Series({"000001": 80, "000002": 80})
    quality = pd.Series({"000001": 60, "000002": 60})
    trend = pd.Series({"000001": 40, "000002": 40})
    risk = pd.Series({"000001": 0, "000002": 100})

    result = aggregate(universe, growth, value, quality, trend, risk)

    assert set(result["Risk"]) == {0, 100}
    assert result.loc[result["code"] == "000001", "Total"].iloc[0] == 70.0
    assert result.loc[result["code"] == "000002", "Total"].iloc[0] == 70.0


def test_print_summary_handles_result_without_rank_index(capsys):
    result = pd.DataFrame({
        "code": ["000001"],
        "name": ["A"],
        "market": ["KOSPI"],
        "sector": ["Tech"],
        "Growth": [70.0],
        "Value": [60.0],
        "Quality": [50.0],
        "Trend": [40.0],
        "Risk": [30.0],
        "Total": [55.0],
    })

    print_summary(result)

    out = capsys.readouterr().out
    assert "처리 결과 요약" in out
    assert "A" in out


def test_to_csv_is_idempotent_when_rank_column_already_exists(tmp_path):
    result = pd.DataFrame({
        "rank": [99],
        "code": ["000001"],
        "name": ["A"],
        "market": ["KOSPI"],
        "sector": ["Tech"],
        "Growth": [70.0],
        "Value": [60.0],
        "Quality": [50.0],
        "Trend": [40.0],
        "Risk": [30.0],
        "Total": [55.0],
    })
    out = tmp_path / "stocks_top100.csv"

    to_csv(result, str(out))

    saved = pd.read_csv(out)
    assert saved.columns.tolist().count("rank") == 1
    assert saved["rank"].tolist() == [1]
