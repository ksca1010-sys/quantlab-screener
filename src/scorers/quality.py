"""
Quality 스코어러: 펀더멘털 건전성 4개 항목 합산 (0~100점)
"""
from __future__ import annotations

import logging

import pandas as pd

from src.normalizer import clip_score, sector_percentile

logger = logging.getLogger(__name__)


def score_quality(
    universe: pd.DataFrame,
    financials: dict[str, pd.DataFrame],
    market_data: pd.DataFrame,
) -> pd.Series:
    """
    Quality 최종 점수 (0~100).
    universe: code, sector 컬럼 포함
    market_data: code, roe, operating_margin, debt_ratio, interest_coverage 컬럼
    ROE·영업이익률은 섹터 분위수 정규화 (절댓값 비교 금지 — CLAUDE.md 헌법)
    """
    df = universe[["code", "sector"]].copy() if "sector" in universe.columns else universe[["code"]].copy()
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
    """ROE (%) 섹터 분위수 → 0~30점. NaN → 0점."""
    if "roe" not in df.columns:
        return pd.Series(0.0, index=df.index)
    work = df.copy()
    work["roe"] = pd.to_numeric(work["roe"], errors="coerce").clip(-50, 100)
    if "sector" not in work.columns:
        work["sector"] = "기타"
    return (sector_percentile(work, "roe", ascending=True).fillna(0) * 30).rename(None)


def _op_margin_score(df: pd.DataFrame) -> pd.Series:
    """영업이익률 (%) 섹터 분위수 → 0~25점. NaN → 0점."""
    if "operating_margin" not in df.columns:
        return pd.Series(0.0, index=df.index)
    work = df.copy()
    work["operating_margin"] = pd.to_numeric(work["operating_margin"], errors="coerce").clip(-50, 80)
    if "sector" not in work.columns:
        work["sector"] = "기타"
    return (sector_percentile(work, "operating_margin", ascending=True).fillna(0) * 25).rename(None)


def _debt_ratio_score(df: pd.DataFrame) -> pd.Series:
    """부채비율 섹터 분위수: 낮을수록 좋음 → 0~25점. NaN은 0점."""
    if "debt_ratio" not in df.columns:
        return pd.Series(0.0, index=df.index)
    work = df.copy()
    work["debt_ratio"] = pd.to_numeric(work["debt_ratio"], errors="coerce").clip(0, 1000)
    if "sector" not in work.columns:
        work["sector"] = "기타"
    return (sector_percentile(work, "debt_ratio", ascending=False).fillna(0) * 25).rename(None)


def _interest_coverage_score(df: pd.DataFrame) -> pd.Series:
    """이자보상배율 섹터 분위수: 높을수록 좋음 → 0~20점. NaN은 0점."""
    if "interest_coverage" not in df.columns:
        return pd.Series(0.0, index=df.index)
    work = df.copy()
    work["interest_coverage"] = pd.to_numeric(work["interest_coverage"], errors="coerce").clip(-10, 100)
    if "sector" not in work.columns:
        work["sector"] = "기타"
    return (sector_percentile(work, "interest_coverage", ascending=True).fillna(0) * 20).rename(None)
