"""
데이터 로더: 주가, 재무, 시총 데이터 조회 + 인메모리 캐시
"""
from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from functools import lru_cache

import FinanceDataReader as fdr
import pandas as pd
from pykrx import stock as krx

logger = logging.getLogger(__name__)

# DART API 레이트 제한 (호출 간 0.1초 sleep)
_DART_SLEEP = 0.1


def _dart_client():
    """OpenDartReader 클라이언트 초기화."""
    import os
    import OpenDartReader as odr
    key = os.getenv("DART_API_KEY", "")
    if not key:
        raise EnvironmentError("DART_API_KEY가 .env에 설정되지 않았습니다.")
    return odr.OpenDartReader(key)


@lru_cache(maxsize=512)
def get_price_data(code: str, start: str, end: str) -> pd.DataFrame:
    """
    FinanceDataReader로 일봉 OHLCV 조회.
    Returns: DataFrame with columns [Open, High, Low, Close, Volume]
    """
    try:
        df = fdr.DataReader(code, start, end)
        if df is None or df.empty:
            logger.warning("[%s] 가격 데이터 없음 (start=%s, end=%s)", code, start, end)
            return pd.DataFrame()
        return df
    except Exception as e:
        logger.warning("[%s] 가격 데이터 조회 실패: %s", code, e)
        return pd.DataFrame()


@lru_cache(maxsize=256)
def get_financial_data(code: str, as_of_date: str) -> pd.DataFrame:
    """
    OpenDartReader로 분기 재무제표 조회.

    # 공시 시차 45일 룰:
    # 기업은 분기 종료 후 최대 45일 이내에 실적을 공시한다.
    # 분석 시점 t의 재무 데이터는 (t - 45일) 이전 공시분만 사용해야
    # 미래 정보(look-ahead bias)를 방지할 수 있다.
    cutoff = as_of_date - 45days
    """
    try:
        cutoff = (
            pd.Timestamp(as_of_date) - timedelta(days=45)
        ).strftime("%Y%m%d")

        dart = _dart_client()
        time.sleep(_DART_SLEEP)

        # 최근 5년치 분기 재무제표 조회
        df = dart.finstate_all(code, bgn_de=_years_ago(5), end_de=cutoff)
        if df is None or df.empty:
            logger.warning("[%s] 재무 데이터 없음 (cutoff=%s)", code, cutoff)
            return pd.DataFrame()
        return df
    except EnvironmentError:
        raise
    except Exception as e:
        logger.warning("[%s] 재무 데이터 조회 실패: %s", code, e)
        return pd.DataFrame()


@lru_cache(maxsize=512)
def get_market_cap(code: str, date_str: str) -> float:
    """pykrx로 특정 날짜 시총 조회 (원 단위)."""
    try:
        df = krx.get_market_cap_by_ticker(date_str.replace("-", ""))
        if code in df.index:
            return float(df.loc[code, "시가총액"])
        return float("nan")
    except Exception as e:
        logger.warning("[%s] 시총 조회 실패: %s", code, e)
        return float("nan")


def _years_ago(n: int) -> str:
    return (date.today() - timedelta(days=365 * n)).strftime("%Y%m%d")
