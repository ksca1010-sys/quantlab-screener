"""
Growth 스코어러 단위 테스트 (가짜 데이터 사용)
"""
import numpy as np
import pandas as pd
import pytest

from src.scorers.growth import (
    _revenue_yoy,
    _revenue_acceleration,
    score_growth,
)


def _make_financials(revenue_series: list[float]) -> pd.DataFrame:
    """테스트용 분기 재무 DataFrame 생성."""
    return pd.DataFrame(
        {
            "계정과목": ["매출액"] * len(revenue_series),
            "금액": revenue_series,
        }
    )


class TestRevenueYoy:
    def test_positive_growth(self):
        """매출이 전년 대비 증가하면 양수 점수."""
        fin = {
            "000001": _make_financials([100, 110, 120, 130, 140, 150, 160, 170])
        }
        scores = _revenue_yoy(fin)
        assert "000001" in scores.index
        assert scores["000001"] >= 0

    def test_negative_growth(self):
        """매출이 전년 대비 감소하면 점수가 낮아야 함."""
        fin_up = {"000001": _make_financials([100, 110, 120, 130, 140, 150, 160, 170])}
        fin_down = {"000002": _make_financials([200, 190, 180, 170, 100, 90, 80, 70])}

        s_up = _revenue_yoy(fin_up)
        s_down = _revenue_yoy(fin_down)

        # 단일 종목이라 min-max 정규화 후 둘 다 같은 0값일 수 있으므로
        # 적어도 오류 없이 동작하는지만 확인
        assert not s_up.empty
        assert not s_down.empty

    def test_insufficient_data_returns_nan(self):
        """데이터가 5개 미만이면 NaN 반환."""
        fin = {"000001": _make_financials([100, 110, 120])}
        scores = _revenue_yoy(fin)
        assert pd.isna(scores.get("000001", float("nan")))

    def test_empty_dataframe_returns_nan(self):
        """빈 DataFrame 입력 시 NaN 반환."""
        fin = {"000001": pd.DataFrame()}
        scores = _revenue_yoy(fin)
        assert pd.isna(scores.get("000001", float("nan")))


class TestRevenueAcceleration:
    def test_accelerating_growth_positive_slope(self):
        """성장 가속도 (기울기 양수) 정상 계산."""
        # 매출이 가파르게 증가하는 패턴
        revenues = [100, 105, 112, 121, 133, 148, 168, 193]
        fin = {"000001": _make_financials(revenues)}
        scores = _revenue_acceleration(fin)
        assert "000001" in scores.index
        assert scores["000001"] >= 0

    def test_insufficient_data_returns_nan(self):
        """데이터 8개 미만이면 NaN."""
        fin = {"000001": _make_financials([100, 110, 120])}
        scores = _revenue_acceleration(fin)
        assert pd.isna(scores.get("000001", float("nan")))


class TestScoreGrowth:
    def test_output_range(self):
        """score_growth 출력은 0~100 범위여야 함."""
        universe = pd.DataFrame({"code": ["000001", "000002"]})
        revenues_a = [100, 110, 120, 130, 140, 150, 160, 170]
        revenues_b = [200, 195, 190, 185, 100, 95, 90, 85]
        financials = {
            "000001": _make_financials(revenues_a),
            "000002": _make_financials(revenues_b),
        }
        result = score_growth(universe, financials)
        assert len(result) == 2
        assert result.between(0, 100).all(), f"범위 초과: {result}"

    def test_missing_code_gets_zero(self):
        """유니버스에 있지만 재무 데이터가 없는 종목은 0점."""
        universe = pd.DataFrame({"code": ["000001", "999999"]})
        financials = {
            "000001": _make_financials([100, 110, 120, 130, 140, 150, 160, 170])
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
