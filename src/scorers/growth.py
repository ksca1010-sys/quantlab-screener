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
    """매출 YoY 성장률 (최근 연도 대비 전년도) → 0~25점."""
    scores: dict[str, float] = {}
    for code, df in financials.items():
        try:
            rev = _extract_by_year(df, "매출액")
            if rev is None or len(rev) < 2:
                scores[code] = np.nan
                continue
            recent, year_ago = float(rev.iloc[-1]), float(rev.iloc[-2])
            if year_ago <= 0:
                scores[code] = np.nan
                continue
            scores[code] = (recent - year_ago) / abs(year_ago) * 100
        except Exception:
            scores[code] = np.nan
    raw = pd.Series(scores)
    return minmax_scale(raw.clip(-100, 300), lower=0, upper=25)


def _operating_profit_yoy(financials: dict[str, pd.DataFrame]) -> pd.Series:
    """영업이익 YoY 성장률 → 0~25점."""
    scores: dict[str, float] = {}
    for code, df in financials.items():
        try:
            op = _extract_by_year(df, "영업이익")
            if op is None or len(op) < 2:
                scores[code] = np.nan
                continue
            recent, year_ago = float(op.iloc[-1]), float(op.iloc[-2])
            if year_ago == 0:
                scores[code] = np.nan
                continue
            scores[code] = (recent - year_ago) / abs(year_ago) * 100
        except Exception:
            scores[code] = np.nan
    raw = pd.Series(scores)
    return minmax_scale(raw.clip(-100, 300), lower=0, upper=25)


def _eps_cagr(financials: dict[str, pd.DataFrame]) -> pd.Series:
    """EPS CAGR (가용 연도 기준) → 0~25점."""
    scores: dict[str, float] = {}
    for code, df in financials.items():
        try:
            eps = _extract_by_year(df, "주당순이익")
            if eps is None or len(eps) < 2:
                scores[code] = np.nan
                continue
            end_val, start_val = float(eps.iloc[-1]), float(eps.iloc[0])
            n_years = len(eps) - 1
            if start_val <= 0 or end_val <= 0 or n_years == 0:
                scores[code] = np.nan
                continue
            cagr = (end_val / start_val) ** (1 / n_years) - 1
            scores[code] = cagr * 100
        except Exception:
            scores[code] = np.nan
    raw = pd.Series(scores)
    return minmax_scale(raw.clip(-50, 100), lower=0, upper=25)


def _revenue_acceleration(financials: dict[str, pd.DataFrame]) -> pd.Series:
    """매출 성장 가속도 (연도별 추세 기울기) → 0~25점."""
    scores: dict[str, float] = {}
    for code, df in financials.items():
        try:
            rev = _extract_by_year(df, "매출액")
            if rev is None or len(rev) < 2:
                scores[code] = np.nan
                continue
            vals = rev.values.astype(float)
            x = np.arange(len(vals))
            slope = np.polyfit(x, vals, 1)[0]
            base = abs(vals.mean()) if vals.mean() != 0 else 1
            scores[code] = slope / base * 100
        except Exception:
            scores[code] = np.nan
    raw = pd.Series(scores)
    return minmax_scale(raw.clip(-50, 50), lower=0, upper=25)


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

    s1 = _revenue_yoy(fin)           # 0~25
    s2 = _operating_profit_yoy(fin)  # 0~25
    s3 = _eps_cagr(fin)              # 0~25
    s4 = _revenue_acceleration(fin)  # 0~25

    total = (
        s1.reindex(codes).fillna(0)
        + s2.reindex(codes).fillna(0)
        + s3.reindex(codes).fillna(0)
        + s4.reindex(codes).fillna(0)
    )  # 합산 범위 0~100, 별도 배율 없음

    result = clip_score(total)
    result.index = codes
    return result


# ── DART 계정 매핑 (IFRS account_id 우선, account_nm 한글명 보조) ────────────────
_ACCOUNT_MAP = {
    "매출액": {
        "id_patterns": ["Revenue", "Sales"],
        "nm_patterns": ["매출액", "영업수익", "수익(매출액)", "매출"],
        "sj_div": "IS",
        "exclude_nm": ["매출원가", "매출채권", "매출총이익"],
    },
    "영업이익": {
        "id_patterns": ["OperatingIncome", "OperatingProfit"],
        "nm_patterns": ["영업이익"],
        "sj_div": "IS",
        "exclude_nm": [],
    },
    "주당순이익": {
        "id_patterns": ["BasicEarnings"],
        "nm_patterns": ["기본주당이익", "주당순이익"],
        "sj_div": "IS",
        "exclude_nm": ["희석"],
    },
}


def _extract_by_year(df: pd.DataFrame, account: str) -> pd.Series | None:
    """
    DART finstate_all 결과에서 연도별 계정 금액 시계열 추출.
    account_id (IFRS 코드) 우선 매칭, account_nm 한글명 보조.
    """
    if df.empty or "bsns_year" not in df.columns:
        return None

    mapping = _ACCOUNT_MAP.get(account)
    if mapping is None:
        return None

    # IS 구분 필터
    is_df = df[df.get("sj_div", pd.Series(dtype=str)) == mapping["sj_div"]].copy() if "sj_div" in df.columns else df.copy()
    if is_df.empty:
        return None

    # account_id 패턴 매칭
    matched = pd.DataFrame()
    if "account_id" in is_df.columns:
        for pat in mapping["id_patterns"]:
            cands = is_df[is_df["account_id"].str.contains(pat, na=False, case=False)]
            if not cands.empty:
                matched = cands
                break

    # account_nm 폴백
    if matched.empty and "account_nm" in is_df.columns:
        for pat in mapping["nm_patterns"]:
            cands = is_df[is_df["account_nm"].str.contains(pat, na=False)]
            if not cands.empty:
                # 제외 패턴 적용
                for excl in mapping["exclude_nm"]:
                    cands = cands[~cands["account_nm"].str.contains(excl, na=False)]
                if not cands.empty:
                    matched = cands
                    break

    if matched.empty:
        return None

    val_col = "thstrm_amount"
    if val_col not in matched.columns:
        return None

    # 연도별 집계 (중복 시 첫 번째 값 사용)
    yearly = (
        matched.groupby("bsns_year")[val_col]
        .first()
        .apply(lambda x: pd.to_numeric(x, errors="coerce"))
        .sort_index()
    )
    return yearly if len(yearly) >= 1 else None


def _extract_quarterly(df: pd.DataFrame, account: str) -> pd.Series | None:
    """연도별 시계열 반환 (하위 호환용 별칭)."""
    return _extract_by_year(df, account)


def _extract_annual(df: pd.DataFrame, account: str) -> pd.Series | None:
    return _extract_by_year(df, account)
