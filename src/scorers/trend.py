"""
Trend 스코어러: 가격 추세 4개 항목 합산 (0~100점)

변경 이력:
- MA 정배열: 0/15/30 이진 → MA 갭 비율 연속 강도 (신호 정보 손실 해소)
- RSI 평균회귀 시그널 제거 → 12-1개월 수익률 모멘텀으로 대체
  (RSI와 정배열은 서로 상쇄되는 시그널이었음: 강한 추세 = RSI 과매수 = 감점)
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from src.normalizer import clip_score, sector_percentile

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

    sector_map = universe.set_index("code")["sector"] if "sector" in universe.columns else pd.Series("기타", index=codes)

    def _sector_score(raw: pd.Series, upper: float) -> pd.Series:
        work = pd.DataFrame({
            "code": codes,
            "sector": sector_map.reindex(codes).fillna("기타").values,
            "value": raw.reindex(codes),
        }).set_index("code")
        return sector_percentile(work, "value", ascending=True).reindex(codes).fillna(0) * upper

    s1 = _sector_score(_ma_strength_raw(codes, price_data), 30)   # MA 갭 연속 강도
    s2 = _sector_score(_high52w_raw(codes, price_data), 25)        # 52주 신고가 위치
    s3 = _sector_score(_volume_trend_raw(codes, price_data), 25)   # 거래량 추세
    s4 = _sector_score(_momentum_raw(codes, price_data), 20)       # 12-1개월 수익률 모멘텀

    total = s1 + s2 + s3 + s4  # 0~100
    result = clip_score(total)
    result.index = codes
    return result


def _ma_strength_raw(codes: list[str], price_data: dict[str, pd.DataFrame]) -> pd.Series:
    """MA 갭 비율 연속 강도 raw 값.

    MA20/MA60 갭 + MA60/MA120 갭을 합산한 연속값으로 추세 강도를 측정.
    양수 = 정배열(강세), 음수 = 역배열(약세). 이진/삼진 점수의 정보 손실 해소.
    """
    scores: dict[str, float] = {}
    for code in codes:
        df = price_data.get(code, pd.DataFrame())
        if df.empty or "Close" not in df.columns or len(df) < 120:
            scores[code] = np.nan
            continue
        close = df["Close"].dropna()
        ma20  = close.rolling(20).mean().iloc[-1]
        ma60  = close.rolling(60).mean().iloc[-1]
        ma120 = close.rolling(120).mean().iloc[-1]
        if pd.isna(ma20) or pd.isna(ma60) or pd.isna(ma120) or ma60 <= 0 or ma120 <= 0:
            scores[code] = np.nan
            continue
        gap_short = (ma20 / ma60 - 1) * 100    # MA20 vs MA60 갭 (%)
        gap_long  = (ma60 / ma120 - 1) * 100   # MA60 vs MA120 갭 (%)
        scores[code] = gap_short + gap_long
    return pd.Series(scores).clip(-20, 20).rename(None)


def _high52w_raw(codes: list[str], price_data: dict[str, pd.DataFrame]) -> pd.Series:
    """52주 신고가 대비 현재가 위치 raw 값."""
    scores: dict[str, float] = {}
    for code in codes:
        df = price_data.get(code, pd.DataFrame())
        if df.empty or "Close" not in df.columns or len(df) < 20:
            scores[code] = np.nan
            continue
        close = df["Close"].dropna()
        last   = close.iloc[-1]
        high52 = close.iloc[-min(252, len(close)):].max()
        if high52 <= 0:
            scores[code] = np.nan
            continue
        scores[code] = (last / high52) * 100
    return pd.Series(scores).clip(0, 100).rename(None)


def _volume_trend_raw(codes: list[str], price_data: dict[str, pd.DataFrame]) -> pd.Series:
    """거래량 추세 raw 값 (최근 20일 평균 / 과거 60일 평균)."""
    scores: dict[str, float] = {}
    for code in codes:
        df = price_data.get(code, pd.DataFrame())
        if df.empty or "Volume" not in df.columns or len(df) < 80:
            scores[code] = np.nan
            continue
        vol   = df["Volume"].dropna()
        avg20 = vol.iloc[-20:].mean()
        avg60 = vol.iloc[-80:-20].mean()
        if avg60 <= 0:
            scores[code] = np.nan
            continue
        scores[code] = avg20 / avg60
    return pd.Series(scores).clip(0, 3).rename(None)


def _momentum_raw(codes: list[str], price_data: dict[str, pd.DataFrame]) -> pd.Series:
    """12-1개월 수익률 모멘텀 raw 값 (직전 1개월 제외).

    학술 표준 Carhart(1997) 모멘텀: t-12 ~ t-1 구간 수익률.
    직전 1개월을 제외하는 이유: 단기 반전(short-term reversal) 효과 배제.
    데이터 부족(< 252일) 시 0점 (보수적 처리).
    """
    scores: dict[str, float] = {}
    for code in codes:
        df = price_data.get(code, pd.DataFrame())
        if df.empty or "Close" not in df.columns:
            scores[code] = np.nan
            continue
        close = df["Close"].dropna()
        if len(close) < 252:
            scores[code] = np.nan
            continue
        p_start = float(close.iloc[-252])  # 약 12개월 전
        p_end   = float(close.iloc[-21])   # 약 1개월 전
        if p_start <= 0:
            scores[code] = np.nan
            continue
        scores[code] = (p_end - p_start) / p_start * 100
    return pd.Series(scores).clip(-50, 100).rename(None)
