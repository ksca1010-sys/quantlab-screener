"""
Growth 스코어러 단위 테스트 (DART 포맷 가짜 데이터 사용)
"""
import numpy as np
import pandas as pd
import pytest

from src.scorers.growth import (
    _revenue_yoy,
    _revenue_acceleration,
    _operating_profit_yoy,
    score_growth,
)


def _make_dart_fin(account_nm: str, account_id: str, by_year: dict[int, float]) -> pd.DataFrame:
    """DART finstate_all 포맷 테스트용 DataFrame 생성."""
    rows = []
    for year, amount in by_year.items():
        rows.append({
            "bsns_year": year,
            "sj_div": "IS",
            "account_nm": account_nm,
            "account_id": account_id,
            "thstrm_amount": str(int(amount)),
        })
    return pd.DataFrame(rows)


def _make_financials(revenue_by_year: dict[int, float]) -> pd.DataFrame:
    """매출액 데이터만 포함한 테스트용 DART DataFrame."""
    return _make_dart_fin("영업수익", "ifrs-full_Revenue", revenue_by_year)


class TestRevenueYoy:
    def test_positive_growth(self):
        """매출이 전년 대비 증가하면 점수가 유효해야 함."""
        fin = {
            "000001": _make_financials({2022: 100, 2023: 140, 2024: 170})
        }
        scores = _revenue_yoy(fin)
        assert "000001" in scores.index
        assert not pd.isna(scores["000001"])
        assert scores["000001"] >= 0

    def test_negative_growth_lower_than_positive(self):
        """성장 종목이 역성장 종목보다 높은 점수를 받아야 함."""
        fin = {
            "000001": _make_financials({2023: 100, 2024: 130}),  # +30%
            "000002": _make_financials({2023: 200, 2024: 160}),  # -20%
        }
        scores = _revenue_yoy(fin)
        assert scores["000001"] > scores["000002"]

    def test_insufficient_data_returns_nan(self):
        """데이터가 1년치만 있으면 NaN 반환 (YoY 계산 불가)."""
        fin = {"000001": _make_financials({2024: 100})}
        scores = _revenue_yoy(fin)
        assert pd.isna(scores.get("000001", float("nan")))

    def test_empty_dataframe_returns_nan(self):
        """빈 DataFrame 입력 시 NaN 반환."""
        fin = {"000001": pd.DataFrame()}
        scores = _revenue_yoy(fin)
        assert pd.isna(scores.get("000001", float("nan")))


class TestRevenueAcceleration:
    def test_accelerating_growth_positive_slope(self):
        """매출 증가 추세면 점수가 유효해야 함."""
        fin = {
            "000001": _make_financials({2022: 100, 2023: 130, 2024: 170})
        }
        scores = _revenue_acceleration(fin)
        assert "000001" in scores.index
        assert scores["000001"] >= 0

    def test_insufficient_data_returns_nan(self):
        """데이터 1년치면 추세 계산 불가 → NaN."""
        fin = {"000001": _make_financials({2024: 100})}
        scores = _revenue_acceleration(fin)
        assert pd.isna(scores.get("000001", float("nan")))


class TestScoreGrowth:
    def test_output_range(self):
        """score_growth 출력은 0~100 범위여야 함."""
        universe = pd.DataFrame({"code": ["000001", "000002"]})
        financials = {
            "000001": _make_financials({2022: 100, 2023: 130, 2024: 170}),
            "000002": _make_financials({2022: 200, 2023: 190, 2024: 170}),
        }
        result = score_growth(universe, financials)
        assert len(result) == 2
        assert result.between(0, 100).all(), f"범위 초과: {result}"

    def test_missing_code_gets_zero(self):
        """유니버스에 있지만 재무 데이터가 없는 종목은 0점."""
        universe = pd.DataFrame({"code": ["000001", "999999"]})
        financials = {
            "000001": _make_financials({2022: 100, 2023: 130, 2024: 170})
        }
        result = score_growth(universe, financials)
        assert result["999999"] == 0.0

    def test_index_matches_codes(self):
        """결과 인덱스가 유니버스 코드와 일치해야 함."""
        codes = ["000001", "000002", "000003"]
        universe = pd.DataFrame({"code": codes})
        financials = {c: pd.DataFrame() for c in codes}
        result = score_growth(universe, financials)
        assert list(result.index) == codes

    def test_growing_scores_higher_than_declining(self):
        """성장 종목이 역성장 종목보다 높은 종합 점수를 받아야 함."""
        universe = pd.DataFrame({"code": ["grow", "flat", "decline"]})
        financials = {
            "grow": _make_financials({2022: 100, 2023: 130, 2024: 170}),
            "flat": _make_financials({2022: 100, 2023: 105, 2024: 110}),
            "decline": _make_financials({2022: 200, 2023: 160, 2024: 130}),
        }
        result = score_growth(universe, financials)
        assert result["grow"] > result["decline"]

    def test_missing_submetrics_do_not_reweight_available_growth_components(self):
        """매출만 있으면 매출 YoY와 가속도 배점까지만 받을 수 있어야 함."""
        universe = pd.DataFrame({"code": ["best", "mid", "low"], "sector": ["Tech", "Tech", "Tech"]})
        financials = {
            "best": _make_financials({2022: 100, 2023: 140, 2024: 220}),
            "mid": _make_financials({2022: 100, 2023: 120, 2024: 150}),
            "low": _make_financials({2022: 100, 2023: 90, 2024: 80}),
        }

        result = score_growth(universe, financials)

        assert result["best"] <= 40.0
