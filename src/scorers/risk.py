"""
Risk 스코어러: 위험조정 3개 항목 합산 (0~100점)

모든 지표는 낮을수록 좋음 → 역전 스케일링 (upper - minmax_scale).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from src.normalizer import clip_score, minmax_scale

logger = logging.getLogger(__name__)

_MARKET_CODE = "KS11"  # KOSPI 지수 코드 (price_data 딕셔너리 키)


def score_risk(
    universe: pd.DataFrame,
    price_data: dict[str, pd.DataFrame],
) -> pd.Series:
    """
    Risk 최종 점수 (0~100). 낮은 위험 = 높은 점수.
    price_data에 'KS11' 키로 KOSPI 지수 데이터가 포함되어야 함.
    """
    codes = universe["code"].tolist()
    kospi = price_data.get(_MARKET_CODE, pd.DataFrame())

    s1 = _beta_score(codes, price_data, kospi)     # 0~30: 시장 베타 (낮을수록 좋음)
    s2 = _volatility_score(codes, price_data)       # 0~30: 연환산 변동성 (낮을수록 좋음)
    s3 = _mdd_score(codes, price_data)              # 0~40: 최대낙폭 MDD (낮을수록 좋음)

    total = s1 + s2 + s3
    result = clip_score(total)
    result.index = codes
    return result


def _beta_score(
    codes: list[str],
    price_data: dict[str, pd.DataFrame],
    kospi: pd.DataFrame,
) -> pd.Series:
    """시장 베타 (52주, vs KOSPI) → 0~30점. 베타 낮을수록 높은 점수."""
    if kospi.empty or "Close" not in kospi.columns:
        return pd.Series(0.0, index=range(len(codes)))

    mkt_ret = kospi["Close"].pct_change().dropna()

    scores: dict[str, float] = {}
    for code in codes:
        df = price_data.get(code, pd.DataFrame())
        if df.empty or "Close" not in df.columns:
            scores[code] = np.nan
            continue
        stk_ret = df["Close"].pct_change().dropna()
        aligned = pd.concat([stk_ret, mkt_ret], axis=1).dropna()
        aligned.columns = ["stk", "mkt"]
        if len(aligned) < 60:
            scores[code] = np.nan
            continue
        var_mkt = aligned["mkt"].var()
        if var_mkt == 0:
            scores[code] = np.nan
            continue
        beta = aligned["stk"].cov(aligned["mkt"]) / var_mkt
        scores[code] = beta

    raw = pd.Series(scores).clip(0, 3)
    # 역전: 베타 낮을수록 높은 점수
    scaled = minmax_scale(raw, lower=0, upper=30)
    return (30 - scaled).fillna(0).rename(None)


def _volatility_score(
    codes: list[str],
    price_data: dict[str, pd.DataFrame],
) -> pd.Series:
    """연환산 변동성 (52주, %) → 0~30점. 변동성 낮을수록 높은 점수."""
    scores: dict[str, float] = {}
    for code in codes:
        df = price_data.get(code, pd.DataFrame())
        if df.empty or "Close" not in df.columns or len(df) < 30:
            scores[code] = np.nan
            continue
        daily_ret = df["Close"].pct_change().dropna()
        vol = daily_ret.std() * np.sqrt(252) * 100  # 연환산 %
        scores[code] = vol

    raw = pd.Series(scores).clip(5, 80)
    # 역전: 변동성 낮을수록 높은 점수
    scaled = minmax_scale(raw, lower=0, upper=30)
    return (30 - scaled).fillna(0).rename(None)


def _mdd_score(
    codes: list[str],
    price_data: dict[str, pd.DataFrame],
) -> pd.Series:
    """52주 최대낙폭 MDD (%) → 0~40점. MDD 낮을수록 높은 점수."""
    scores: dict[str, float] = {}
    for code in codes:
        df = price_data.get(code, pd.DataFrame())
        if df.empty or "Close" not in df.columns or len(df) < 20:
            scores[code] = np.nan
            continue
        close = df["Close"].dropna()
        rolling_max = close.cummax()
        drawdown = (close - rolling_max) / rolling_max
        mdd = (-drawdown.min()) * 100  # 양수 %, 예: 25.0 = 25% 낙폭
        scores[code] = mdd

    raw = pd.Series(scores).clip(0, 60)
    # 역전: MDD 낮을수록 높은 점수
    scaled = minmax_scale(raw, lower=0, upper=40)
    return (40 - scaled).fillna(0).rename(None)
