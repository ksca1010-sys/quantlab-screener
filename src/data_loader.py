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
import requests
from bs4 import BeautifulSoup
from pykrx import stock as krx

logger = logging.getLogger(__name__)

# DART API 레이트 제한 (호출 간 0.1초 sleep)
_DART_SLEEP = 0.1

_NAVER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.naver.com/",
    "Accept-Language": "ko-KR,ko;q=0.9",
}


@lru_cache(maxsize=512)
def fetch_naver_fundamentals(code: str) -> dict:
    """Naver Finance HTML에서 PER·PBR·배당수익률 스크래핑.

    per_table 구조 (em[0] = 수치, "N/A" = 해당없음):
      Row 0: 후행PER  Row 2: PBR  Row 3: 배당수익률
    데이터가 없거나 N/A이면 해당 항목 NaN 반환 (허수 없음).
    """
    nan = float("nan")
    result: dict = {"per": nan, "pbr": nan, "dividend_yield": nan}

    def _to_float(text: str) -> float:
        t = text.replace(",", "").replace("%", "").replace("배", "").strip()
        if t in ("N/A", "-", "", "—"):
            return nan
        try:
            return float(t)
        except ValueError:
            return nan

    try:
        resp = requests.get(
            f"https://finance.naver.com/item/main.naver?code={code}",
            headers=_NAVER_HEADERS,
            timeout=8,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table", class_="per_table")
        if table is None:
            return result
        rows = table.find_all("tr")

        def _em(row_idx: int) -> str:
            if row_idx >= len(rows):
                return "N/A"
            ems = rows[row_idx].find_all("em")
            return ems[0].get_text(strip=True) if ems else "N/A"

        result["per"] = _to_float(_em(0))            # 후행 PER
        result["pbr"] = _to_float(_em(2))            # PBR
        result["dividend_yield"] = _to_float(_em(3)) # 배당수익률
    except Exception as e:
        logger.warning("[%s] Naver fundamentals 조회 실패: %s", code, e)

    return result


def _get_dart_api_key() -> str:
    """DART API 키 조회 — .env → Streamlit secrets 순서로 탐색."""
    import os
    key = os.getenv("DART_API_KEY", "")
    if not key:
        try:
            import streamlit as st
            key = st.secrets.get("DART_API_KEY", "")
        except Exception:
            pass
    return key


def _dart_client():
    """OpenDartReader 클라이언트 초기화."""
    import OpenDartReader
    key = _get_dart_api_key()
    if not key:
        raise EnvironmentError("DART_API_KEY가 .env 또는 Streamlit Secrets에 설정되지 않았습니다.")
    return OpenDartReader(key)


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
    OpenDartReader로 연간 재무제표 조회 (최근 3개년).

    # 공시 시차 45일 룰:
    # 기업은 사업연도 종료 후 최대 90일(상장사 45일) 이내에 연간 실적을 공시한다.
    # 분석 시점 t에서 (t - 45일) 이전 공시분만 사용하여 look-ahead bias를 방지한다.
    # 예: 2026-04-25 기준 → cutoff = 2026-03-11 → 2025년 연간보고서까지 사용 가능.
    """
    try:
        # cutoff 연도 계산 (공시 시차 45일 적용)
        cutoff_ts = pd.Timestamp(as_of_date) - timedelta(days=45)
        cutoff_year = cutoff_ts.year

        dart = _dart_client()
        frames = []

        # 최근 3개년 연간 재무제표 수집
        for year in range(cutoff_year - 2, cutoff_year + 1):
            try:
                time.sleep(_DART_SLEEP)
                df = dart.finstate_all(code, str(year), reprt_code="11011")
                if df is not None and not df.empty:
                    df = df.copy()
                    df["bsns_year"] = year
                    frames.append(df)
            except Exception as e:
                logger.debug("[%s] %d년 재무 조회 실패: %s", code, year, e)

        if not frames:
            logger.warning("[%s] 재무 데이터 없음 (as_of=%s)", code, as_of_date)
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

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
