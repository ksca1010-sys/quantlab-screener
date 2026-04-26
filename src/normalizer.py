"""
정규화 유틸리티: 섹터 분위수, min-max 스케일
"""
from __future__ import annotations

import numpy as np
import pandas as pd


_MIN_SECTOR_SIZE = 5  # 섹터 최소 종목 수 — 미만 시 전체 분위수로 fallback


def sector_percentile(
    df: pd.DataFrame,
    column: str,
    sector_col: str = "sector",
    ascending: bool = True,
) -> pd.Series:
    """
    섹터 내 분위수 정규화 (0~1).

    - ascending=False: 값이 낮을수록 높은 분위수 (PER, PBR 등 낮을수록 유리)
    - ascending=True: 값이 높을수록 높은 분위수 (ROE, 성장률 등)

    섹터 내 유효 종목 수 < _MIN_SECTOR_SIZE(5)이면 전체 유니버스 분위수로 fallback.
    절댓값 비교 금지 규칙에 따라 반드시 상대 비교를 유지한다.
    """
    result = pd.Series(index=df.index, dtype=float)

    # 전체 분위수 (소규모 섹터 fallback용)
    valid_all = df[column].dropna()
    global_ranks = valid_all.rank(pct=True, ascending=ascending) if not valid_all.empty else pd.Series(dtype=float)

    small_idx: list = []
    for sector, group in df.groupby(sector_col):
        valid = group[column].dropna()
        if valid.empty:
            continue
        if len(valid) < _MIN_SECTOR_SIZE:
            small_idx.extend(valid.index.tolist())
        else:
            ranks = valid.rank(pct=True, ascending=ascending)
            result.loc[ranks.index] = ranks

    if small_idx and not global_ranks.empty:
        result.loc[small_idx] = global_ranks.reindex(small_idx)

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
