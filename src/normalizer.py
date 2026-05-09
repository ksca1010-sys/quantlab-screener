"""
정규화 유틸리티: 섹터 분위수, min-max 스케일
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def sector_percentile(
    df: pd.DataFrame,
    column: str,
    sector_col: str = "sector",
    ascending: bool = True,
    min_peer_count: int = 3,
) -> pd.Series:
    """
    섹터 내 분위수 정규화 (0~1).

    - ascending=False: 값이 낮을수록 높은 분위수 (PER, PBR 등 낮을수록 유리)
    - ascending=True: 값이 높을수록 높은 분위수 (ROE, 성장률 등)

    절댓값 비교 금지 규칙에 따라 전체 유니버스 fallback 없이 섹터 내부에서만 비교한다.
    유효 peer 수가 너무 적으면 순위 근거가 부족하므로 NaN으로 남겨 후단에서 0점 처리한다.
    """
    result = pd.Series(index=df.index, dtype=float)

    for sector, group in df.groupby(sector_col):
        valid = group[column].dropna()
        if len(valid) < min_peer_count:
            continue
        if valid.nunique(dropna=True) == 1:
            result.loc[valid.index] = 0.5
            continue
        ranks = valid.rank(pct=True, ascending=ascending)
        result.loc[ranks.index] = ranks

    return result


def minmax_scale(series: pd.Series, lower: float = 0.0, upper: float = 100.0) -> pd.Series:
    """시리즈를 [lower, upper] 범위로 min-max 정규화. NaN은 보존."""
    s_min = series.min()  # NaN 무시
    s_max = series.max()  # NaN 무시
    if s_max == s_min:
        # 모든 유효값이 동일하면 중간값, NaN은 그대로 유지
        result = series.copy().astype(float)
        result[series.notna()] = (lower + upper) / 2
        return result
    return lower + (series - s_min) / (s_max - s_min) * (upper - lower)


def clip_score(series: pd.Series) -> pd.Series:
    """점수를 0~100 범위로 클리핑."""
    return series.clip(0, 100)
