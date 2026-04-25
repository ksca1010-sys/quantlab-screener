"""
Trend 스코어러: 가격 추세 4개 항목 합산 (0~100점)
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from src.normalizer import clip_score, minmax_scale

logger = logging.getLogger(__name__)


def score_trend(
    universe: pd.DataFrame,
    price_data: dict[str, pd.DataFrame],
) -> pd.Series:
    """
    Trend 최종 점수 (0~100).

    price_data: {code: OHLCV DataFrame (Close, Volume 컬럼 필수)}
    """
    codes = universe["code"].tolist()

    s1 = _ma_alignment_score(codes, price_data)    # 30점
    s2 = _high52w_score(codes, price_data)         # 25점
    s3 = _volume_trend_score(codes, price_data)    # 25점
    s4 = _rsi_score(codes, price_data)             # 20점

    total = s1 + s2 + s3 + s4
    result = clip_score(total)
    result.index = codes
    return result


def _ma_alignment_score(codes: list[str], price_data: dict[str, pd.DataFrame]) -> pd.Series:
    """이동평균 정배열 (20 > 60 > 120일) → 0~30점."""
    scores: dict[str, float] = {}
    for code in codes:
        df = price_data.get(code, pd.DataFrame())
        if df.empty or "Close" not in df.columns or len(df) < 120:
            scores[code] = 0.0
            continue
        close = df["Close"].dropna()
        ma20 = close.rolling(20).mean().iloc[-1]
        ma60 = close.rolling(60).mean().iloc[-1]
        ma120 = close.rolling(120).mean().iloc[-1]
        if pd.isna(ma20) or pd.isna(ma60) or pd.isna(ma120):
            scores[code] = 0.0
        elif ma20 > ma60 > ma120:
            scores[code] = 30.0  # 완전 정배열
        elif ma20 > ma60 or ma60 > ma120:
            scores[code] = 15.0  # 부분 정배열
        else:
            scores[code] = 0.0
    return pd.Series(scores)


def _high52w_score(codes: list[str], price_data: dict[str, pd.DataFrame]) -> pd.Series:
    """52주 신고가 대비 현재가 위치 (%) → 0~25점."""
    scores: dict[str, float] = {}
    for code in codes:
        df = price_data.get(code, pd.DataFrame())
        if df.empty or "Close" not in df.columns or len(df) < 20:
            scores[code] = 0.0
            continue
        close = df["Close"].dropna()
        last = close.iloc[-1]
        high52 = close.iloc[-min(252, len(close)):].max()
        if high52 <= 0:
            scores[code] = 0.0
            continue
        ratio = last / high52  # 0~1
        scores[code] = ratio * 25
    return pd.Series(scores)


def _volume_trend_score(codes: list[str], price_data: dict[str, pd.DataFrame]) -> pd.Series:
    """거래량 추세 (최근 20일 평균 / 지난 60일 평균) → 0~25점."""
    scores: dict[str, float] = {}
    for code in codes:
        df = price_data.get(code, pd.DataFrame())
        if df.empty or "Volume" not in df.columns or len(df) < 80:
            scores[code] = np.nan
            continue
        vol = df["Volume"].dropna()
        avg20 = vol.iloc[-20:].mean()
        avg60 = vol.iloc[-80:-20].mean()
        if avg60 <= 0:
            scores[code] = np.nan
            continue
        scores[code] = avg20 / avg60  # 1.0 = 보통, >1 = 증가
    raw = pd.Series(scores)
    # 비율 0~3 범위로 min-max → 0~25점
    return (minmax_scale(raw.clip(0, 3).fillna(1)) * 25).rename(None)


def _rsi_score(codes: list[str], price_data: dict[str, pd.DataFrame]) -> pd.Series:
    """RSI(14) 30~70 정상 범위 → 0~20점."""
    scores: dict[str, float] = {}
    for code in codes:
        df = price_data.get(code, pd.DataFrame())
        if df.empty or "Close" not in df.columns or len(df) < 20:
            scores[code] = 10.0  # 데이터 없으면 중간값
            continue
        rsi = _compute_rsi(df["Close"].dropna(), period=14)
        if pd.isna(rsi):
            scores[code] = 10.0
            continue
        if 30 <= rsi <= 70:
            scores[code] = 20.0
        elif rsi < 30:
            # 과매도: rsi 30에 가까울수록 가점
            scores[code] = rsi / 30 * 10
        else:
            # 과매수: rsi 70에 가까울수록 가점, 100으로 갈수록 감점
            scores[code] = max(0, (100 - rsi) / 30 * 10)
    return pd.Series(scores)


def _compute_rsi(close: pd.Series, period: int = 14) -> float:
    """Wilder 방식 RSI 계산."""
    delta = close.diff().dropna()
    if len(delta) < period:
        return float("nan")
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(period).mean().iloc[-1]
    avg_loss = loss.rolling(period).mean().iloc[-1]
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))
