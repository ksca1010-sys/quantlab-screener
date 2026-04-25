"""
Growth 스코어러: 성장성 4개 항목 합산 (0~100점)
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from src.normalizer import clip_score, minmax_scale

logger = logging.getLogger(__name__)


def _revenue_yoy(financials: dict[str, pd.DataFrame]) -> pd.Series:
    """매출 YoY 성장률 (최근 분기 기준) → 0~25점."""
    scores: dict[str, float] = {}
    for code, df in financials.items():
        try:
            rev = _extract_quarterly(df, "매출액")
            if rev is None or len(rev) < 5:
                scores[code] = np.nan
                continue
            recent = rev.iloc[-1]
            year_ago = rev.iloc[-5]
            if year_ago <= 0:
                scores[code] = np.nan
                continue
            scores[code] = (recent - year_ago) / abs(year_ago) * 100
        except Exception:
            scores[code] = np.nan
    raw = pd.Series(scores)
    return minmax_scale(raw.clip(-100, 300)) * 0.25  # 25점 만점


def _operating_profit_yoy(financials: dict[str, pd.DataFrame]) -> pd.Series:
    """영업이익 YoY 성장률 → 0~25점."""
    scores: dict[str, float] = {}
    for code, df in financials.items():
        try:
            op = _extract_quarterly(df, "영업이익")
            if op is None or len(op) < 5:
                scores[code] = np.nan
                continue
            recent = op.iloc[-1]
            year_ago = op.iloc[-5]
            if year_ago == 0:
                scores[code] = np.nan
                continue
            scores[code] = (recent - year_ago) / abs(year_ago) * 100
        except Exception:
            scores[code] = np.nan
    raw = pd.Series(scores)
    return minmax_scale(raw.clip(-100, 300)) * 0.25


def _eps_cagr(financials: dict[str, pd.DataFrame]) -> pd.Series:
    """EPS 3개년 CAGR → 0~25점."""
    scores: dict[str, float] = {}
    for code, df in financials.items():
        try:
            eps = _extract_annual(df, "주당순이익")
            if eps is None or len(eps) < 4:
                scores[code] = np.nan
                continue
            end_val = eps.iloc[-1]
            start_val = eps.iloc[-4]
            if start_val <= 0 or end_val <= 0:
                scores[code] = np.nan
                continue
            cagr = (end_val / start_val) ** (1 / 3) - 1
            scores[code] = cagr * 100
        except Exception:
            scores[code] = np.nan
    raw = pd.Series(scores)
    return minmax_scale(raw.clip(-50, 100)) * 0.25


def _revenue_acceleration(financials: dict[str, pd.DataFrame]) -> pd.Series:
    """매출 성장 가속도 (최근 4분기 추세 기울기) → 0~25점."""
    scores: dict[str, float] = {}
    for code, df in financials.items():
        try:
            rev = _extract_quarterly(df, "매출액")
            if rev is None or len(rev) < 8:
                scores[code] = np.nan
                continue
            recent4 = rev.iloc[-4:].values.astype(float)
            x = np.arange(4)
            # 선형 회귀 기울기 (numpy polyfit)
            slope = np.polyfit(x, recent4, 1)[0]
            base = abs(recent4.mean()) if recent4.mean() != 0 else 1
            scores[code] = slope / base * 100
        except Exception:
            scores[code] = np.nan
    raw = pd.Series(scores)
    return minmax_scale(raw.clip(-50, 50)) * 0.25


def score_growth(
    universe: pd.DataFrame,
    financials: dict[str, pd.DataFrame],
) -> pd.Series:
    """
    Growth 최종 점수 (0~100).
    universe: code 컬럼 포함 DataFrame
    financials: {code: 재무 DataFrame}
    """
    codes = universe["code"].tolist()
    fin = {c: financials.get(c, pd.DataFrame()) for c in codes}

    s1 = _revenue_yoy(fin)
    s2 = _operating_profit_yoy(fin)
    s3 = _eps_cagr(fin)
    s4 = _revenue_acceleration(fin)

    total = (
        s1.reindex(codes).fillna(0)
        + s2.reindex(codes).fillna(0)
        + s3.reindex(codes).fillna(0)
        + s4.reindex(codes).fillna(0)
    ) * 100  # 각 항목이 0~0.25이므로 합산 후 100배 → 0~100

    result = clip_score(total)
    result.index = codes
    return result


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _extract_quarterly(df: pd.DataFrame, account: str) -> pd.Series | None:
    """재무 DataFrame에서 특정 계정과목의 분기별 시계열 추출."""
    if df.empty:
        return None
    col_candidates = [c for c in df.columns if "계정" in c or "account" in c.lower()]
    val_candidates = [c for c in df.columns if "금액" in c or "amount" in c.lower() or "thstrm" in c.lower()]
    if not col_candidates or not val_candidates:
        return None
    acct_col = col_candidates[0]
    val_col = val_candidates[0]
    sub = df[df[acct_col].str.contains(account, na=False)].copy()
    if sub.empty:
        return None
    sub[val_col] = pd.to_numeric(sub[val_col], errors="coerce")
    return sub[val_col].reset_index(drop=True)


def _extract_annual(df: pd.DataFrame, account: str) -> pd.Series | None:
    """연간 집계 시계열 추출 (분기 합산 또는 연간 보고서)."""
    return _extract_quarterly(df, account)
