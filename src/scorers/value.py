"""
Value 스코어러: 가치 4개 항목 합산 (0~100점)
"""
from __future__ import annotations

import logging

import pandas as pd

from src.normalizer import clip_score, minmax_scale, sector_percentile

logger = logging.getLogger(__name__)


def score_value(
    universe: pd.DataFrame,
    financials: dict[str, pd.DataFrame],
    market_data: pd.DataFrame,
) -> pd.Series:
    """
    Value 최종 점수 (0~100).
    universe: code, sector 컬럼 포함
    market_data: code, per, pbr, peg, dividend_yield 컬럼 포함
    """
    df = universe[["code", "sector"]].copy()
    df = df.merge(market_data, on="code", how="left")

    s1 = _per_score(df)       # 0~30
    s2 = _pbr_score(df)       # 0~30
    s3 = _peg_score(df)       # 0~25
    s4 = _dividend_score(df)  # 0~15

    total = s1 + s2 + s3 + s4  # 0~100
    result = clip_score(total)
    result.index = df["code"].tolist()
    return result


def _per_score(df: pd.DataFrame) -> pd.Series:
    """PER 섹터 분위수 (낮을수록 좋음) → 0~30점."""
    if "per" not in df.columns:
        return pd.Series(15.0, index=df.index)  # 데이터 없으면 중간값
    valid = df[df["per"] > 0].copy()
    if valid.empty:
        return pd.Series(15.0, index=df.index)
    # ascending=False: 낮은 PER → 높은 분위수 → 높은 점수
    pct = sector_percentile(valid, "per", ascending=False)
    full = pct.reindex(df.index).fillna(0.5)
    return (full * 30).rename(None)


def _pbr_score(df: pd.DataFrame) -> pd.Series:
    """PBR 섹터 분위수 (낮을수록 좋음) → 0~30점."""
    if "pbr" not in df.columns:
        return pd.Series(15.0, index=df.index)
    valid = df[df["pbr"] > 0].copy()
    if valid.empty:
        return pd.Series(15.0, index=df.index)
    # ascending=False: 낮은 PBR → 높은 분위수 → 높은 점수
    pct = sector_percentile(valid, "pbr", ascending=False)
    full = pct.reindex(df.index).fillna(0.5)
    return (full * 30).rename(None)


def _peg_score(df: pd.DataFrame) -> pd.Series:
    """PEG 1 이하 만점, 이상 감점 → 0~25점."""
    if "peg" not in df.columns:
        return pd.Series(0.0, index=df.index)
    peg = pd.to_numeric(df["peg"], errors="coerce")
    score = pd.Series(0.0, index=df.index)
    score[peg <= 0] = 0.0
    mask_good = (peg > 0) & (peg <= 1)
    score[mask_good] = 25.0
    mask_mid = (peg > 1) & (peg <= 3)
    score[mask_mid] = 25.0 * (3 - peg[mask_mid]) / 2
    score[peg > 3] = 0.0
    return score.fillna(0.0)


def _dividend_score(df: pd.DataFrame) -> pd.Series:
    """배당수익률 → 0~15점 (min-max 정규화, upper=15)."""
    if "dividend_yield" not in df.columns:
        return pd.Series(0.0, index=df.index)
    dy = pd.to_numeric(df["dividend_yield"], errors="coerce").clip(0, 10)
    return minmax_scale(dy.fillna(0), lower=0, upper=15).rename(None)
