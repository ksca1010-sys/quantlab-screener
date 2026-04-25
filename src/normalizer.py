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
) -> pd.Series:
    """
    섹터 내 분위수 정규화 (0~1).

    - ascending=True: 값이 낮을수록 높은 분위수 (PER, PBR 등 낮을수록 유리)
    - ascending=False: 값이 높을수록 높은 분위수 (ROE, 성장률 등)

    절댓값 비교 금지 규칙에 따라 반드시 섹터 내에서만 비교한다.
    """
    result = pd.Series(index=df.index, dtype=float)

    for sector, group in df.groupby(sector_col):
        valid = group[column].dropna()
        if valid.empty:
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
