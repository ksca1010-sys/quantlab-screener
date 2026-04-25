"""
Value 스코어러: 가치 4개 항목 합산 (0~100점)
"""
from __future__ import annotations

import logging

import numpy as np
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

    s1 = _per_score(df)       # 30점
    s2 = _pbr_score(df)       # 30점
    s3 = _peg_score(df)       # 25점
    s4 = _dividend_score(df)  # 15점

    total = s1 + s2 + s3 + s4
    result = clip_score(total)
    result.index = df["code"].tolist()
    return result


def _per_score(df: pd.DataFrame) -> pd.Series:
    """PER 섹터 분위수 (낮을수록 좋음) → 0~30점."""
    if "per" not in df.columns:
        return pd.Series(0.0, index=df.index)
    valid = df[df["per"] > 0].copy()
    if valid.empty:
        return pd.Series(0.0, index=df.index)
    pct = sector_percentile(valid, "per", ascending=True)
    full = pct.reindex(df.index).fillna(0.5)
    return (full * 30).rename(None)


def _pbr_score(df: pd.DataFrame) -> pd.Series:
    """PBR 섹터 분위수 (낮을수록 좋음) → 0~30점."""
    if "pbr" not in df.columns:
        return pd.Series(0.0, index=df.index)
    valid = df[df["pbr"] > 0].copy()
    if valid.empty:
        return pd.Series(0.0, index=df.index)
    pct = sector_percentile(valid, "pbr", ascending=True)
    full = pct.reindex(df.index).fillna(0.5)
    return (full * 30).rename(None)


def _peg_score(df: pd.DataFrame) -> pd.Series:
    """PEG 1 이하 만점, 이상 감점 → 0~25점."""
    if "peg" not in df.columns:
        return pd.Series(0.0, index=df.index)
    peg = pd.to_numeric(df["peg"], errors="coerce")
    score = pd.Series(index=df.index, dtype=float)
    # PEG <= 0: 데이터 불신뢰
    score[peg <= 0] = 0.0
    # PEG 0~1: 선형으로 25점 ~ 25점 (만점)
    mask_good = (peg > 0) & (peg <= 1)
    score[mask_good] = 25.0
    # PEG 1~3: 선형으로 25 ~ 0점
    mask_mid = (peg > 1) & (peg <= 3)
    score[mask_mid] = 25.0 * (3 - peg[mask_mid]) / 2
    # PEG > 3: 0점
    score[peg > 3] = 0.0
    return score.fillna(0.0)


def _dividend_score(df: pd.DataFrame) -> pd.Series:
    """배당수익률 → 0~15점 (min-max 정규화)."""
    if "dividend_yield" not in df.columns:
        return pd.Series(0.0, index=df.index)
    dy = pd.to_numeric(df["dividend_yield"], errors="coerce").clip(0, 10)
    scaled = minmax_scale(dy.fillna(0)) * 0.15
    return (scaled * 100).rename(None)
