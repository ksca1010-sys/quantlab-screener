"""
유니버스 관리: KOSPI + KOSDAQ 통합 시총 상위 100개 종목 선정
"""
from __future__ import annotations

import logging
from pathlib import Path

import FinanceDataReader as fdr
import pandas as pd
import yaml
from pykrx import stock as krx

logger = logging.getLogger(__name__)

UNIVERSE_PATH = Path("config/universe.yaml")


def _fetch_market_cap_bulk(date_str: str) -> dict[str, float]:
    """pykrx로 KOSPI+KOSDAQ 전 종목 시총 일괄 조회."""
    caps: dict[str, float] = {}
    for market in ("KOSPI", "KOSDAQ"):
        try:
            df = krx.get_market_cap_by_ticker(date_str, market=market)
            for code, row in df.iterrows():
                caps[str(code)] = float(row.get("시가총액", 0) or 0)
        except Exception as e:
            logger.warning("시총 조회 실패 (%s): %s", market, e)
    return caps


def _fetch_listing() -> pd.DataFrame:
    """FinanceDataReader로 KRX 전체 종목 목록 조회."""
    df = fdr.StockListing("KRX")
    df = df.rename(columns={"Code": "code", "Name": "name", "Market": "market"})
    df["code"] = df["code"].astype(str).str.zfill(6)
    return df[["code", "name", "market"]].copy()


def _get_sector_map() -> dict[str, str]:
    """pykrx로 KRX 업종분류 코드 매핑 조회."""
    sector_map: dict[str, str] = {}
    for market in ("KOSPI", "KOSDAQ"):
        try:
            tickers = krx.get_market_ticker_list(market=market)
            for ticker in tickers:
                try:
                    sector = krx.get_market_ticker_sector(ticker)
                    sector_map[str(ticker).zfill(6)] = sector
                except Exception:
                    pass
        except Exception as e:
            logger.warning("섹터 조회 실패 (%s): %s", market, e)
    return sector_map


def build_universe(as_of_date: str | None = None) -> pd.DataFrame:
    """
    KOSPI + KOSDAQ 통합 시총 상위 100개 종목 DataFrame 반환.

    Columns: code, name, market, sector, market_cap
    """
    from datetime import date, timedelta

    if as_of_date is None:
        # 최근 영업일 기준 (오늘 - 1일)
        ref_date = (date.today() - timedelta(days=1)).strftime("%Y%m%d")
    else:
        ref_date = as_of_date.replace("-", "")

    logger.info("종목 목록 조회 중...")
    listing = _fetch_listing()

    logger.info("시총 조회 중 (기준일: %s)...", ref_date)
    caps = _fetch_market_cap_bulk(ref_date)

    listing["market_cap"] = listing["code"].map(caps).fillna(0.0)
    listing = listing[listing["market_cap"] > 0]

    logger.info("섹터 분류 조회 중...")
    sector_map = _get_sector_map()
    listing["sector"] = listing["code"].map(sector_map).fillna("기타")

    top100 = (
        listing.sort_values("market_cap", ascending=False)
        .head(100)
        .reset_index(drop=True)
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
