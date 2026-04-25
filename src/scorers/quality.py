"""
Quality 스코어러: 펀더멘털 건전성 4개 항목 합산 (0~100점)
"""
from __future__ import annotations

import logging

import pandas as pd

from src.normalizer import clip_score, minmax_scale

logger = logging.getLogger(__name__)


def score_quality(
    universe: pd.DataFrame,
    financials: dict[str, pd.DataFrame],
    market_data: pd.DataFrame,
) -> pd.Series:
    """
    Quality 최종 점수 (0~100).
    market_data: code, roe, operating_margin, debt_ratio, interest_coverage 컬럼
    """
    df = universe[["code"]].copy()
    df = df.merge(market_data, on="code", how="left")

    s1 = _roe_score(df)               # 0~30
    s2 = _op_margin_score(df)         # 0~25
    s3 = _debt_ratio_score(df)        # 0~25
    s4 = _interest_coverage_score(df) # 0~20

    total = s1 + s2 + s3 + s4  # 0~100
    result = clip_score(total)
    result.index = df["code"].tolist()
    return result


def _roe_score(df: pd.DataFrame) -> pd.Series:
    """ROE (%) 높을수록 좋음 → 0~30점."""
    if "roe" not in df.columns:
        return pd.Series(0.0, index=df.index)
    roe = pd.to_numeric(df["roe"], errors="coerce").clip(-50, 100)
    return minmax_scale(roe.fillna(0), lower=0, upper=30).rename(None)


def _op_margin_score(df: pd.DataFrame) -> pd.Series:
    """영업이익률 (%) 높을수록 좋음 → 0~25점."""
    if "operating_margin" not in df.columns:
        return pd.Series(0.0, index=df.index)
    margin = pd.to_numeric(df["operating_margin"], errors="coerce").clip(-50, 80)
    return minmax_scale(margin.fillna(0), lower=0, upper=25).rename(None)


def _debt_ratio_score(df: pd.DataFrame) -> pd.Series:
    """부채비율 역수: 낮을수록 좋음 → 0~25점."""
    if "debt_ratio" not in df.columns:
        return pd.Series(0.0, index=df.index)
    ratio = pd.to_numeric(df["debt_ratio"], errors="coerce").clip(0, 1000)
    inv = 1 / (1 + ratio.fillna(500))
    return minmax_scale(inv, lower=0, upper=25).rename(None)


def _interest_coverage_score(df: pd.DataFrame) -> pd.Series:
    """이자보상배율 높을수록 좋음 → 0~20점."""
    if "interest_coverage" not in df.columns:
        return pd.Series(0.0, index=df.index)
    ic = pd.to_numeric(df["interest_coverage"], errors="coerce").clip(-10, 100)
    return minmax_scale(ic.fillna(0), lower=0, upper=20).rename(None)
