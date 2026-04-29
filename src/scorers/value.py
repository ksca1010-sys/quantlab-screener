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

    # PEG 커버리지 < 50% 시: PEG 0점 처리하고 나머지에 비례 재배분 (PER 40 + PBR 40 + Div 20)
    # 이유: PEG 데이터 없는 종목에 0점을 부여하면 섹터 내 순위를 왜곡함 (헌법 위반)
    # 50%: 절반 미만 커버리지면 이미 통계적 신뢰성 없음 → 즉시 재배분
    if "peg" in df.columns:
        peg_valid = pd.to_numeric(df["peg"], errors="coerce")
        peg_coverage = (peg_valid > 0).sum() / max(len(df), 1)
    else:
        peg_coverage = 0.0

    if peg_coverage < 0.50:
        logger.debug("PEG 커버리지 %.0f%% < 50%% → 재배분 (PER 40 + PBR 40 + Div 20)", peg_coverage * 100)
        s1 = s1 * (40 / 30)
        s2 = s2 * (40 / 30)
        s4 = s4 * (20 / 15)
        s3 = pd.Series(0.0, index=s3.index)

    total = s1 + s2 + s3 + s4  # 0~100
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
    # ascending=False: 낮은 PER → 높은 분위수 → 높은 점수
    pct = sector_percentile(valid, "per", ascending=False)
    full = pct.reindex(df.index).fillna(0)  # 데이터 없으면 0점 (허수 없음)
    return (full * 30).rename(None)


def _pbr_score(df: pd.DataFrame) -> pd.Series:
    """PBR 섹터 분위수 (낮을수록 좋음) → 0~30점."""
    if "pbr" not in df.columns:
        return pd.Series(0.0, index=df.index)
    valid = df[df["pbr"] > 0].copy()
    if valid.empty:
        return pd.Series(0.0, index=df.index)
    # ascending=False: 낮은 PBR → 높은 분위수 → 높은 점수
    pct = sector_percentile(valid, "pbr", ascending=False)
    full = pct.reindex(df.index).fillna(0)  # 데이터 없으면 0점 (허수 없음)
    return (full * 30).rename(None)


def _peg_score(df: pd.DataFrame) -> pd.Series:
    """PEG 섹터 분위수 → 0~25점 (낮을수록 유리). 섹터 없으면 절대값 폴백.
    섹터 분위수 전환 이유: 성장 섹터(IT·바이오)는 구조적으로 PEG가 높아
    절대 임계값(PEG<1=만점) 방식은 가치 섹터에 일방적으로 유리함.
    """
    if "peg" not in df.columns:
        return pd.Series(0.0, index=df.index)
    work = df.copy()
    work["peg"] = pd.to_numeric(work["peg"], errors="coerce")
    valid = work[work["peg"] > 0]
    if valid.empty:
        return pd.Series(0.0, index=df.index)
    if "sector" in work.columns:
        pct = sector_percentile(valid, "peg", ascending=False)  # 낮은 PEG → 높은 분위수
        return (pct.reindex(df.index).fillna(0) * 25).rename(None)
    # 섹터 정보 없을 때 기존 절대값 방식 폴백
    peg = work["peg"]
    score = pd.Series(0.0, index=df.index)
    score[(peg > 0) & (peg <= 1)] = 25.0
    mask_mid = (peg > 1) & (peg <= 3)
    score[mask_mid] = 25.0 * (3 - peg[mask_mid]) / 2
    return score.fillna(0.0)


def _dividend_score(df: pd.DataFrame) -> pd.Series:
    """배당수익률 → 0~15점 (min-max 정규화, upper=15)."""
    if "dividend_yield" not in df.columns:
        return pd.Series(0.0, index=df.index)
    dy = pd.to_numeric(df["dividend_yield"], errors="coerce").clip(0, 10)
    return minmax_scale(dy, lower=0, upper=15).fillna(0).rename(None)
