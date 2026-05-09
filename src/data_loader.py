"""
데이터 로더: 주가, 재무, 시총 데이터 조회 + 인메모리 캐시
"""
from __future__ import annotations

import logging
import os
import re
import time
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

try:
    import FinanceDataReader as fdr
except ImportError:
    fdr = None  # Streamlit Cloud: 주가 차트 비활성화

try:
    from pykrx import stock as krx
except ImportError:
    krx = None  # Streamlit Cloud: 시총 조회 비활성화

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


@lru_cache(maxsize=64)
def fetch_krx_fundamentals_by_date(as_of_date: str, market: str = "ALL") -> pd.DataFrame:
    """
    pykrx로 특정 기준일의 PER·PBR·배당수익률을 조회한다.
    과거 --as-of-date 실행에서 현재 Naver 지표가 섞이는 look-ahead bias를 막기 위한 날짜 고정 소스다.
    """
    columns = ["code", "per", "pbr", "dividend_yield"]
    date_str = pd.Timestamp(as_of_date).strftime("%Y%m%d")
    cached = _load_krx_fundamentals_cache(date_str, market)
    if not cached.empty:
        cached["market_data_source"] = "krx_fundamental_cache"
        return cached

    if krx is None:
        return pd.DataFrame(columns=columns)

    frames = []
    markets = ["KOSPI", "KOSDAQ"] if market == "ALL" else [market]
    for mkt in markets:
        try:
            df = krx.get_market_fundamental_by_ticker(date_str, market=mkt)
            if df is None or df.empty:
                continue
            work = df.reset_index().rename(columns={
                "티커": "code",
                "PER": "per",
                "PBR": "pbr",
                "DIV": "dividend_yield",
            })
            if "code" not in work.columns:
                work = work.rename(columns={work.columns[0]: "code"})
            work["code"] = work["code"].astype(str).str.zfill(6)
            for col in ["per", "pbr", "dividend_yield"]:
                if col not in work.columns:
                    work[col] = float("nan")
                work[col] = pd.to_numeric(work[col], errors="coerce")
            frames.append(work[columns])
        except Exception as e:
            logger.warning("[%s] KRX 기준일 밸류에이션 조회 실패(%s): %s", mkt, as_of_date, e)

    if not frames:
        return pd.DataFrame(columns=columns)
    result = pd.concat(frames, ignore_index=True).drop_duplicates(subset="code")
    _save_krx_fundamentals_cache(result, date_str, market)
    result["market_data_source"] = "krx_fundamental_by_date"
    return result


def _krx_fundamentals_cache_path(date_str: str, market: str = "ALL") -> Path:
    """기준일 KRX valuation 스냅샷 경로."""
    data_dir = Path(os.getenv("DATA_DIR", "./data"))
    return data_dir / "krx_fundamentals" / f"{date_str}_{market}.csv"


def _load_krx_fundamentals_cache(date_str: str, market: str = "ALL") -> pd.DataFrame:
    """저장된 기준일 KRX valuation 스냅샷을 읽는다."""
    columns = ["code", "per", "pbr", "dividend_yield"]
    path = _krx_fundamentals_cache_path(date_str, market)
    if not path.exists():
        return pd.DataFrame(columns=columns)
    try:
        df = pd.read_csv(path, dtype={"code": str})
        missing = [c for c in columns if c not in df.columns]
        if missing:
            logger.warning("KRX valuation 캐시 컬럼 누락(%s): %s", path, ",".join(missing))
            return pd.DataFrame(columns=columns)
        df = df[columns].copy()
        df["code"] = df["code"].astype(str).str.zfill(6)
        for col in ["per", "pbr", "dividend_yield"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        logger.info("KRX valuation 캐시 사용: %s", path)
        return df.drop_duplicates(subset="code")
    except Exception as e:
        logger.warning("KRX valuation 캐시 읽기 실패(%s): %s", path, e)
        return pd.DataFrame(columns=columns)


def _save_krx_fundamentals_cache(df: pd.DataFrame, date_str: str, market: str = "ALL") -> None:
    """성공한 기준일 KRX valuation을 PIT 재실행용 스냅샷으로 저장한다."""
    columns = ["code", "per", "pbr", "dividend_yield"]
    if df.empty:
        return
    path = _krx_fundamentals_cache_path(date_str, market)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        work = df[columns].copy()
        work["code"] = work["code"].astype(str).str.zfill(6)
        work.to_csv(path, index=False, encoding="utf-8-sig")
        logger.info("KRX valuation 캐시 저장: %s (%d개)", path, len(work))
    except Exception as e:
        logger.warning("KRX valuation 캐시 저장 실패(%s): %s", path, e)


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
    cached = _load_price_cache(code, start, end)
    if not cached.empty:
        return cached
    if fdr is None:
        return pd.DataFrame()
    try:
        df = fdr.DataReader(code, start, end)
        if df is None or df.empty:
            logger.warning("[%s] 가격 데이터 없음 (start=%s, end=%s)", code, start, end)
            return pd.DataFrame()
        _save_price_cache(df, code, start, end)
        return df
    except Exception as e:
        logger.warning("[%s] 가격 데이터 조회 실패: %s", code, e)
        return pd.DataFrame()


def _price_cache_path(code: str, start: str, end: str) -> Path:
    """가격 데이터 디스크 캐시 경로."""
    data_dir = Path(os.getenv("DATA_DIR", "./data"))
    safe = f"{str(code).zfill(6)}_{start.replace('-', '')}_{end.replace('-', '')}.csv"
    return data_dir / "prices" / safe


def _load_price_cache(code: str, start: str, end: str) -> pd.DataFrame:
    """저장된 가격 데이터를 읽는다."""
    path = _price_cache_path(code, start, end)
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        return df
    except Exception as e:
        logger.warning("[%s] 가격 캐시 읽기 실패(%s): %s", code, path, e)
        return pd.DataFrame()


def _save_price_cache(df: pd.DataFrame, code: str, start: str, end: str) -> None:
    """성공한 가격 조회 결과를 저장한다."""
    if df.empty:
        return
    path = _price_cache_path(code, start, end)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, encoding="utf-8-sig")
    except Exception as e:
        logger.warning("[%s] 가격 캐시 저장 실패(%s): %s", code, path, e)


@lru_cache(maxsize=256)
def get_financial_data(code: str, as_of_date: str) -> pd.DataFrame:
    """
    OpenDartReader로 연간 재무제표 조회 (최근 3개년).

    # 공시 시차 45일 룰:
    # 기업은 사업연도 종료 후 최대 90일(상장사 45일) 이내에 연간 실적을 공시한다.
    # 분석 시점 t에서 (t - 45일) 이전 공시분만 사용하여 look-ahead bias를 방지한다.
    # 예: 2026-04-25 기준 → cutoff = 2026-03-11 → 2025년 연간보고서까지 사용 가능.
    """
    cached = _load_financial_cache(code, as_of_date)
    if not cached.empty:
        return cached
    try:
        # cutoff 접수일 계산 (공시 시차 45일 적용)
        cutoff_ts = pd.Timestamp(as_of_date) - timedelta(days=45)
        cutoff = cutoff_ts.strftime("%Y%m%d")

        dart = _dart_client()
        report_meta = _annual_report_metadata_before_cutoff(dart, code, cutoff)
        if not report_meta:
            logger.warning("[%s] 45일 공시 시차 기준 내 연간보고서 없음 (as_of=%s)", code, as_of_date)
            return pd.DataFrame()
        frames = []

        # 최근 3개년 연간 재무제표 수집. 실제 접수일이 cutoff 이하인 사업보고서 접수번호만 사용한다.
        # OpenDART 전체 재무제표 API는 입력에 rcept_no가 없으므로 응답의 rcept_no가 선택한 접수번호와 일치할 때만 채택한다.
        for year in sorted(report_meta)[-3:]:
            try:
                meta = report_meta.get(year, {})
                df = _fetch_finstate_all_for_receipt(dart, code, str(year), str(meta.get("rcept_no", "")))
                if df is not None and not df.empty:
                    df = df.copy()
                    df["bsns_year"] = year
                    df["source_rcept_no"] = meta.get("rcept_no")
                    df["source_rcept_dt"] = meta.get("rcept_dt")
                    frames.append(df)
                else:
                    logger.warning(
                        "[%s] %d년 재무제표 접수번호 고정 실패(rcept_no=%s) → 해당 연도 제외",
                        code, year, meta.get("rcept_no"),
                    )
            except Exception as e:
                logger.debug("[%s] %d년 재무 조회 실패: %s", code, year, e)

        if not frames:
            logger.warning("[%s] 재무 데이터 없음 (as_of=%s)", code, as_of_date)
            return pd.DataFrame()

        combined = pd.concat(frames, ignore_index=True)

        # 연결재무제표(CFS) 우선, 연도별로 CFS가 존재하면 단독(OFS) 제거.
        # 지주회사·금융지주 등은 연결과 단독이 크게 다르므로 명시적 우선순위 필수.
        if "fs_div" in combined.columns:
            years_with_cfs = set(
                combined.loc[combined["fs_div"] == "CFS", "bsns_year"].unique()
            )
            if years_with_cfs:
                drop_mask = (
                    combined["bsns_year"].isin(years_with_cfs)
                    & (combined["fs_div"] == "OFS")
                )
                combined = combined[~drop_mask]

        _save_financial_cache(combined, code, as_of_date)
        return combined

    except EnvironmentError:
        raise
    except Exception as e:
        logger.warning("[%s] 재무 데이터 조회 실패: %s", code, e)
        return pd.DataFrame()


def _financial_cache_path(code: str, as_of_date: str) -> Path:
    """DART 재무제표 디스크 캐시 경로."""
    data_dir = Path(os.getenv("DATA_DIR", "./data"))
    date_tag = pd.Timestamp(as_of_date).strftime("%Y%m%d")
    return data_dir / "dart_financials" / f"{str(code).zfill(6)}_{date_tag}.csv"


def _load_financial_cache(code: str, as_of_date: str) -> pd.DataFrame:
    """저장된 DART 재무제표를 읽는다."""
    path = _financial_cache_path(code, as_of_date)
    if not path.exists():
        return pd.DataFrame()
    try:
        logger.info("[%s] DART 재무 캐시 사용: %s", code, path)
        return pd.read_csv(path, dtype={"source_rcept_no": str, "source_rcept_dt": str})
    except Exception as e:
        logger.warning("[%s] DART 재무 캐시 읽기 실패(%s): %s", code, path, e)
        return pd.DataFrame()


def _save_financial_cache(df: pd.DataFrame, code: str, as_of_date: str) -> None:
    """DART 재무제표를 기준일별로 저장한다."""
    if df.empty:
        return
    path = _financial_cache_path(code, as_of_date)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False, encoding="utf-8-sig")
    except Exception as e:
        logger.warning("[%s] DART 재무 캐시 저장 실패(%s): %s", code, path, e)


def _annual_report_years_before_cutoff(dart, code: str, cutoff: str) -> list[int]:
    """
    DART 접수일 기준으로 사용 가능한 사업보고서 사업연도를 찾는다.
    # 공시 시차 45일 룰: 분석 시점 t에서 t-45일 이전에 실제 접수된 사업보고서만 재무제표 조회 대상으로 삼는다.
    """
    return sorted(_annual_report_metadata_before_cutoff(dart, code, cutoff).keys())


def _annual_report_metadata_before_cutoff(dart, code: str, cutoff: str) -> dict[int, dict]:
    """
    DART 접수일 기준 사용 가능한 사업보고서 메타데이터를 반환한다.
    # 공시 시차 45일 룰: 실제 접수일이 cutoff 이하인 사업보고서만 허용하고 rcept_no/rcept_dt를 감사용으로 보존한다.
    """
    start = (pd.Timestamp(cutoff) - pd.DateOffset(years=5)).strftime("%Y%m%d")
    reports = dart.list(corp=code, start=start, end=cutoff, kind="A", final=True)
    if reports is None or reports.empty or "report_nm" not in reports.columns:
        return {}

    reports = reports[reports["report_nm"].str.contains("사업보고서", na=False)].copy()
    if "rcept_dt" in reports.columns:
        reports = reports[reports["rcept_dt"].astype(str) <= cutoff]
    if reports.empty:
        return {}

    years: dict[int, dict] = {}
    for _, row in reports.iterrows():
        match = re.search(r"\((\d{4})\.", str(row.get("report_nm", "")))
        if match:
            year = int(match.group(1))
            current = years.get(year)
            rcept_dt = str(row.get("rcept_dt", ""))
            if current is None or rcept_dt > str(current.get("rcept_dt", "")):
                years[year] = {
                    "rcept_no": row.get("rcept_no"),
                    "rcept_dt": rcept_dt,
                    "report_nm": row.get("report_nm"),
                }
    return years


def _fetch_finstate_all_for_receipt(dart, code: str, year: str, rcept_no: str) -> pd.DataFrame:
    """OpenDART 전체 재무제표 응답을 선택된 접수번호와 대조해 반환한다."""
    if not rcept_no:
        return pd.DataFrame()

    corp_code = dart.find_corp_code(code)
    if not corp_code:
        raise ValueError(f'could not find "{code}"')

    frames = []
    for fs_div in ("CFS", "OFS"):
        time.sleep(_DART_SLEEP)
        df = _request_finstate_all(
            api_key=dart.api_key,
            corp_code=corp_code,
            bsns_year=year,
            reprt_code="11011",
            fs_div=fs_div,
        )
        if df.empty or "rcept_no" not in df.columns:
            continue
        matched = df[df["rcept_no"].astype(str) == str(rcept_no)].copy()
        if not matched.empty:
            matched["fs_div"] = fs_div
            frames.append(matched)
        else:
            actual = sorted(df["rcept_no"].dropna().astype(str).unique().tolist())
            logger.info(
                "[%s] %s년 %s 재무제표 rcept_no 불일치(target=%s, actual=%s)",
                code, year, fs_div, rcept_no, "|".join(actual[:5]),
            )

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _request_finstate_all(
    api_key: str,
    corp_code: str,
    bsns_year: str,
    reprt_code: str = "11011",
    fs_div: str = "CFS",
) -> pd.DataFrame:
    """OpenDART 단일회사 전체 재무제표 API를 DataFrame으로 반환한다."""
    url = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
    params = {
        "crtfc_key": api_key,
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "reprt_code": reprt_code,
        "fs_div": fs_div,
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    payload = resp.json()
    rows = payload.get("list")
    if not rows:
        status = payload.get("status")
        message = payload.get("message")
        if status not in (None, "013"):
            logger.warning(
                "[%s] OpenDART 전체 재무제표 조회 실패(year=%s, fs_div=%s, status=%s, message=%s)",
                corp_code, bsns_year, fs_div, status, message,
            )
        return pd.DataFrame()
    return pd.DataFrame(rows)


@lru_cache(maxsize=512)
def get_market_cap(code: str, date_str: str) -> float:
    """pykrx로 특정 날짜 시총 조회 (원 단위)."""
    if krx is None:
        return float("nan")
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


@lru_cache(maxsize=256)
def get_contract_liabilities_ratio(code: str, as_of_date: str) -> float:
    """
    DART 재무제표에서 계약부채(선수금) / 매출액 비율 반환.
    백로그 강도 지표 — 높을수록 향후 매출이 이미 확보된 상태.
    조선·방산·건설·IT서비스 등 수주 기반 업종에서 유의미.
    데이터 미확보 시 NaN 반환 (허수 없음).
    """
    nan = float("nan")
    try:
        df = get_financial_data(code, as_of_date)
        if df.empty or "bsns_year" not in df.columns:
            return nan

        latest = df[df["bsns_year"] == df["bsns_year"].max()].copy()

        def _extract(sj_divs: tuple, nm_patterns: list, id_patterns: list) -> float:
            sub = (
                latest[latest["sj_div"].isin(sj_divs)]
                if "sj_div" in latest.columns
                else latest
            )
            if "account_id" in sub.columns:
                for pat in id_patterns:
                    rows = sub[sub["account_id"].str.contains(pat, na=False, case=False)]
                    if not rows.empty:
                        try:
                            return float(str(rows["thstrm_amount"].iloc[0]).replace(",", ""))
                        except Exception:
                            pass
            if "account_nm" in sub.columns:
                for pat in nm_patterns:
                    exact = sub[sub["account_nm"] == pat]
                    rows = exact if not exact.empty else sub[sub["account_nm"].str.contains(pat, na=False)]
                    if not rows.empty:
                        try:
                            return float(str(rows["thstrm_amount"].iloc[0]).replace(",", ""))
                        except Exception:
                            pass
            return nan

        contract_liabilities = _extract(
            sj_divs=("BS",),
            nm_patterns=["계약부채", "선수금"],
            id_patterns=["ContractLiabilities", "AdvancesFromCustomers"],
        )
        revenue = _extract(
            sj_divs=("IS", "CIS"),
            nm_patterns=["매출액", "영업수익"],
            id_patterns=["Revenue", "Sales"],
        )

        if pd.isna(contract_liabilities) or pd.isna(revenue) or revenue <= 0:
            return nan
        return contract_liabilities / revenue  # 0.5 = 매출의 50%가 이미 수주 확보

    except Exception as e:
        logger.debug("[%s] 계약부채 조회 실패: %s", code, e)
        return float("nan")
