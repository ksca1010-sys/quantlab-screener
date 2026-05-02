"""
밸류에이션 매트릭 + 상대 강도(RS) 모듈
─────────────────────────────────────
- get_stock_valuation: PER·PBR·배당수익률 (Naver Finance)
- get_sector_valuation_avg: 섹터 평균 (TOP100 유니버스 내)
- compute_relative_strength: 시장 대비 상대 강도 시계열
- get_top_relative_strength: 시장보다 강한 종목 자동 추출
"""
from __future__ import annotations

import logging
import time as _time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

try:
    import FinanceDataReader as fdr
    _FDR_AVAILABLE = True
except ImportError:
    fdr = None
    _FDR_AVAILABLE = False

# 메모리 캐시
_VAL_CACHE: dict[str, tuple[float, dict]] = {}
_VAL_TTL = 1800  # 30분

_RS_CACHE: dict[tuple, tuple[float, pd.DataFrame]] = {}
_RS_TTL = 1800


def get_stock_valuation(code: str) -> dict:
    """
    개별 종목의 PER·PBR·배당수익률 조회 (Naver Finance).
    실패한 항목은 NaN — 허수 없음.
    """
    code_str = str(code).zfill(6)
    now = _time.time()
    cached = _VAL_CACHE.get(code_str)
    if cached is not None and now - cached[0] < _VAL_TTL:
        return cached[1]

    try:
        from src.data_loader import fetch_naver_fundamentals
        result = fetch_naver_fundamentals(code_str)
    except Exception as e:
        logger.debug("[%s] 밸류에이션 조회 실패: %s", code_str, e)
        nan = float("nan")
        result = {"per": nan, "pbr": nan, "dividend_yield": nan}

    _VAL_CACHE[code_str] = (now, result)
    return result


def get_sector_valuation_avg(
    sector: str, df_universe: pd.DataFrame,
) -> dict:
    """
    같은 섹터 종목들의 PER·PBR·배당수익률 평균(중앙값) 반환.
    df_universe: stocks_top100.csv 전체 (code, sector 컬럼 필요).
    병렬 호출로 빠른 수집.
    """
    sector_codes = df_universe[df_universe["sector"] == sector]["code"].astype(str).tolist()
    if not sector_codes:
        return {"per": None, "pbr": None, "dividend_yield": None, "n": 0}

    results = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(get_stock_valuation, c) for c in sector_codes]
        for fut in as_completed(futures):
            try:
                results.append(fut.result())
            except Exception:
                continue

    if not results:
        return {"per": None, "pbr": None, "dividend_yield": None, "n": 0}

    df = pd.DataFrame(results)
    return {
        "per":            float(df["per"].median())            if df["per"].notna().any()            else None,
        "pbr":            float(df["pbr"].median())            if df["pbr"].notna().any()            else None,
        "dividend_yield": float(df["dividend_yield"].median()) if df["dividend_yield"].notna().any() else None,
        "n": int(df.notna().any(axis=1).sum()),
    }


def compute_relative_strength(
    code: str,
    benchmark: str = "KS11",
    period_days: int = 180,
) -> Optional[pd.DataFrame]:
    """
    시장(벤치마크) 대비 상대 강도 시계열.
    RS Line = (종목가격 / 벤치마크가격) × 100 (기간 시작일 = 100 정규화)
    반환 DataFrame: index=date, columns=['stock', 'bench', 'rs', 'rs_norm']
    """
    if not _FDR_AVAILABLE:
        return None

    cache_key = (str(code), benchmark, period_days)
    now = _time.time()
    cached = _RS_CACHE.get(cache_key)
    if cached is not None and now - cached[0] < _RS_TTL:
        return cached[1]

    end   = date.today().strftime("%Y-%m-%d")
    start = (date.today() - timedelta(days=period_days)).strftime("%Y-%m-%d")
    try:
        stock = fdr.DataReader(str(code).zfill(6), start, end)
        bench = fdr.DataReader(benchmark, start, end)
        if stock.empty or bench.empty:
            return None
        s_close = stock["Close"].dropna()
        b_close = bench["Close"].dropna()
        # 같은 날짜만 교집합
        common = s_close.index.intersection(b_close.index)
        if len(common) < 5:
            return None
        s_close = s_close.loc[common]
        b_close = b_close.loc[common]
        rs = (s_close / b_close)
        rs_norm = rs / float(rs.iloc[0]) * 100
        result = pd.DataFrame({
            "stock":  s_close.values,
            "bench":  b_close.values,
            "rs":     rs.values,
            "rs_norm": rs_norm.values,
        }, index=common)
        _RS_CACHE[cache_key] = (now, result)
        return result
    except Exception as e:
        logger.debug("[%s] RS 계산 실패: %s", code, e)
        return None


def get_top_relative_strength(
    df_universe: pd.DataFrame,
    benchmark: str = "KS11",
    lookback_days: int = 60,
    top_n: int = 20,
) -> pd.DataFrame:
    """
    유니버스 전체 중 시장 대비 상대 강도 상위 N개 종목.
    반환: code | name | sector | rs_change_pct (시장 대비 초과 수익률)
    """
    if not _FDR_AVAILABLE:
        return pd.DataFrame()

    end   = date.today().strftime("%Y-%m-%d")
    start = (date.today() - timedelta(days=lookback_days + 30)).strftime("%Y-%m-%d")

    try:
        bench = fdr.DataReader(benchmark, start, end)
        if bench.empty:
            return pd.DataFrame()
        bench_close = bench["Close"].dropna()
        cutoff_date = bench_close.index[-1] - pd.Timedelta(days=lookback_days)
        past_bench = bench_close[bench_close.index <= cutoff_date]
        if past_bench.empty:
            return pd.DataFrame()
        bench_ret = (bench_close.iloc[-1] / past_bench.iloc[-1] - 1) * 100
    except Exception:
        return pd.DataFrame()

    def _stock_return(code_str: str) -> Optional[float]:
        try:
            df = fdr.DataReader(code_str, start, end)
            if df.empty:
                return None
            s = df["Close"].dropna()
            if len(s) < 5:
                return None
            past = s[s.index <= cutoff_date]
            if past.empty:
                return None
            return float((s.iloc[-1] / past.iloc[-1] - 1) * 100)
        except Exception:
            return None

    codes = df_universe["code"].astype(str).str.zfill(6).tolist()
    rows = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_code = {
            executor.submit(_stock_return, c): c for c in codes
        }
        for fut in as_completed(future_to_code):
            c = future_to_code[fut]
            try:
                ret = fut.result()
            except Exception:
                ret = None
            if ret is None:
                continue
            rows.append({
                "code":         c,
                "stock_ret":    ret,
                "bench_ret":    bench_ret,
                "excess_ret":   ret - bench_ret,
            })

    if not rows:
        return pd.DataFrame()

    rs_df = pd.DataFrame(rows)
    # 종목명·섹터 머지
    name_map   = dict(zip(df_universe["code"].astype(str).str.zfill(6), df_universe["name"]))
    sector_map = dict(zip(df_universe["code"].astype(str).str.zfill(6), df_universe["sector"]))
    rs_df["name"]   = rs_df["code"].map(name_map)
    rs_df["sector"] = rs_df["code"].map(sector_map)

    return (
        rs_df.sort_values("excess_ret", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )
