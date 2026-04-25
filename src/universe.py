"""
유니버스 관리: KOSPI + KOSDAQ 통합 시총 상위 100개 종목 선정
pykrx API 불안정 대비: FinanceDataReader를 1차 소스로 사용
"""
from __future__ import annotations

import logging
from pathlib import Path

import FinanceDataReader as fdr
import pandas as pd
import yaml

logger = logging.getLogger(__name__)

UNIVERSE_PATH = Path("config/universe.yaml")


def _fetch_listing_with_marcap() -> pd.DataFrame:
    """
    fdr.StockListing('KRX')로 전 종목 + 시총 일괄 조회.
    Marcap 컬럼을 바로 활용하므로 pykrx 의존 없음.
    """
    df = fdr.StockListing("KRX")
    rename_map = {
        "Code": "code",
        "Name": "name",
        "Market": "market",
        "Marcap": "market_cap",
        "Dept": "sector_raw",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    df["code"] = df["code"].astype(str).str.zfill(6)
    needed = ["code", "name", "market", "market_cap"]
    if "sector_raw" in df.columns:
        needed.append("sector_raw")
    return df[needed].copy()


def _get_sector_map_pykrx(ref_date: str) -> dict[str, str]:
    """
    pykrx로 KRX 업종분류 코드 조회 (실패 시 빈 dict 반환).
    date 파라미터를 명시해 내부 영업일 자동조회 로직을 우회.
    """
    sector_map: dict[str, str] = {}
    try:
        from pykrx import stock as krx
        for market in ("KOSPI", "KOSDAQ"):
            try:
                tickers = krx.get_market_ticker_list(date=ref_date, market=market)
                if not tickers:
                    continue
                for ticker in tickers:
                    try:
                        sector = krx.get_market_ticker_sector(ticker)
                        sector_map[str(ticker).zfill(6)] = sector
                    except Exception:
                        pass
            except Exception as e:
                logger.debug("pykrx 섹터 조회 실패 (%s): %s", market, e)
    except Exception as e:
        logger.debug("pykrx import 실패: %s", e)
    return sector_map


def build_universe(as_of_date: str | None = None) -> pd.DataFrame:
    """
    KOSPI + KOSDAQ 통합 시총 상위 100개 종목 DataFrame 반환.
    Columns: code, name, market, sector, market_cap
    """
    from pandas.tseries.offsets import BDay

    # 주말/공휴일이면 가장 최근 영업일로 롤백 (KRX는 주말 데이터 없음)
    ref_ts = pd.Timestamp(as_of_date) if as_of_date else pd.Timestamp.today()
    if ref_ts.weekday() >= 5:  # 토=5, 일=6
        ref_ts = ref_ts - BDay(1)
    ref_date = ref_ts.strftime("%Y%m%d")

    logger.info("종목 목록 + 시총 조회 중 (기준일: %s)...", ref_date)
    listing = _fetch_listing_with_marcap()

    listing["market_cap"] = pd.to_numeric(listing["market_cap"], errors="coerce").fillna(0.0)
    listing = listing[listing["market_cap"] > 0]

    # 섹터: fdr Dept 컬럼 우선, 없으면 pykrx 시도, 최종 fallback '기타'
    if "sector_raw" in listing.columns and listing["sector_raw"].notna().any():
        listing["sector"] = listing["sector_raw"].fillna("기타")
        logger.info("섹터 정보: fdr Dept 컬럼 사용")
    else:
        logger.info("섹터 분류 조회 중 (pykrx)...")
        sector_map = _get_sector_map_pykrx(ref_date)
        if sector_map:
            listing["sector"] = listing["code"].map(sector_map).fillna("기타")
            logger.info("섹터 정보: pykrx 사용 (%d개 매핑)", len(sector_map))
        else:
            listing["sector"] = "기타"
            logger.warning("섹터 정보 조회 실패 → 전체 '기타'로 처리")

    top100 = (
        listing.sort_values("market_cap", ascending=False)
        .head(100)
        .reset_index(drop=True)[["code", "name", "market", "sector", "market_cap"]]
    )
    top100.index = top100.index + 1
    top100.index.name = "rank"

    logger.info("유니버스 확정: %d개 종목", len(top100))
    return top100


def load_universe(refresh: bool = False, as_of_date: str | None = None) -> pd.DataFrame:
    """
    universe.yaml이 존재하면 로드, 없거나 refresh=True이면 재생성.
    """
    UNIVERSE_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not refresh and UNIVERSE_PATH.exists():
        logger.info("기존 유니버스 로드: %s", UNIVERSE_PATH)
        with open(UNIVERSE_PATH) as f:
            data = yaml.safe_load(f)
        return pd.DataFrame(data["stocks"])

    logger.info("유니버스 재생성 중...")
    df = build_universe(as_of_date=as_of_date)

    with open(UNIVERSE_PATH, "w") as f:
        yaml.dump(
            {
                "generated_at": pd.Timestamp.now().isoformat(),
                "as_of_date": as_of_date,
                "count": len(df),
                "stocks": df.reset_index().to_dict(orient="records"),
            },
            f,
            allow_unicode=True,
            default_flow_style=False,
        )
    logger.info("유니버스 저장 완료: %s", UNIVERSE_PATH)
    return df
