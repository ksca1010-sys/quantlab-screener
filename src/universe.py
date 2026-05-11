"""
유니버스 관리: KOSPI + KOSDAQ 통합 시총 상위 100개 종목 선정
pykrx API 불안정 대비: FinanceDataReader를 1차 소스로 사용
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import FinanceDataReader as fdr
import pandas as pd
import yaml

logger = logging.getLogger(__name__)

UNIVERSE_PATH = Path("config/universe.yaml")


def _universe_snapshot_path(as_of_date: str, kospi_top: int, kosdaq_top: int) -> Path:
    """기준일 유니버스 스냅샷 경로."""
    date_tag = pd.Timestamp(as_of_date).strftime("%Y%m%d")
    return Path(os.getenv("DATA_DIR", "./data")) / "universe" / f"{date_tag}_K{kospi_top}_Q{kosdaq_top}.csv"


def _fetch_listing_with_marcap(as_of_date: str | None = None) -> pd.DataFrame:
    """
    기준일 종목 + 시총 일괄 조회.
    과거 기준일은 pykrx 날짜 고정 시총만 허용하고, 최신 기준일에만 현재 FDR 목록 fallback을 허용한다.
    """
    if as_of_date:
        date_str = pd.Timestamp(as_of_date).strftime("%Y%m%d")
        frames = []
        try:
            from pykrx import stock as krx
            for market in ("KOSPI", "KOSDAQ"):
                cap = krx.get_market_cap_by_ticker(date_str, market=market)
                if cap is None or cap.empty:
                    continue
                work = cap.reset_index().rename(columns={"티커": "code", "시가총액": "market_cap"})
                if "code" not in work.columns:
                    work = work.rename(columns={work.columns[0]: "code"})
                work["code"] = work["code"].astype(str).str.zfill(6)
                work["name"] = work["code"].map(lambda c: krx.get_market_ticker_name(c))
                work["market"] = market
                frames.append(work[["code", "name", "market", "market_cap"]])
            if frames:
                return pd.concat(frames, ignore_index=True)
        except Exception as e:
            logger.warning("pykrx 기준일 유니버스 조회 실패(%s): %s", date_str, e)

        from pandas.tseries.offsets import BDay
        today = pd.Timestamp.today().normalize()
        ref = pd.Timestamp(as_of_date).normalize()
        latest_allowed = today - BDay(1) if today.weekday() >= 5 else today
        if ref < latest_allowed - BDay(1):
            raise RuntimeError(
                f"과거 기준일 유니버스 조회 실패({as_of_date}). 현재 FDR 목록으로 fallback하면 point-in-time이 깨집니다."
            )
        logger.warning("최신 기준일로 간주하고 FDR 현재 목록 fallback 사용")

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


_ETF_NAME_PREFIXES = (
    "KODEX", "TIGER", "KBSTAR", "KOSEF", "ARIRANG", "HANARO", "SOL",
    "KINDEX", "ACE", "RISE", "PLUS", "TIMEFOLIO", "KTOP", "FOCUS",
)
_EXCLUDE_NAME_KEYWORDS = ("스팩", "리츠", "SPAC", "REIT", "인프라펀드")


def _is_investable(name: str, code: str) -> bool:
    """ETF·스팩·리츠·우선주를 제외한 보통주 여부 판별."""
    n = str(name).strip()
    # ETF: 대형 운용사 접두사
    if n.upper().startswith(_ETF_NAME_PREFIXES):
        return False
    # 스팩·리츠·인프라펀드
    if any(kw in n for kw in _EXCLUDE_NAME_KEYWORDS):
        return False
    # 우선주: 이름이 '우', '우B', '우C', '우D' 등으로 끝남
    if n.endswith(("우", "우B", "우C", "우D")):
        return False
    return True


def build_universe(
    as_of_date: str | None = None,
    kospi_top: int = 200,
    kosdaq_top: int = 100,
) -> pd.DataFrame:
    """
    KOSPI 상위 kospi_top + KOSDAQ 상위 kosdaq_top 종목 합산 유니버스 반환.
    Columns: code, name, market, sector, market_cap
    """
    from pandas.tseries.offsets import BDay

    # 주말/공휴일이면 가장 최근 영업일로 롤백 (KRX는 주말 데이터 없음)
    ref_ts = pd.Timestamp(as_of_date) if as_of_date else pd.Timestamp.today()
    if ref_ts.weekday() >= 5:  # 토=5, 일=6
        ref_ts = ref_ts - BDay(1)
    ref_date = ref_ts.strftime("%Y%m%d")
    snapshot_path = _universe_snapshot_path(ref_ts.strftime("%Y-%m-%d"), kospi_top, kosdaq_top)
    if snapshot_path.exists():
        try:
            logger.info("유니버스 스냅샷 사용: %s", snapshot_path)
            cached = pd.read_csv(snapshot_path, dtype={"code": str})
            cached["code"] = cached["code"].astype(str).str.zfill(6)
            cached.index = cached.index + 1
            cached.index.name = "rank"
            return cached[["code", "name", "market", "sector", "market_cap"]]
        except Exception as e:
            logger.warning("유니버스 스냅샷 읽기 실패(%s): %s", snapshot_path, e)

    logger.info("종목 목록 + 시총 조회 중 (기준일: %s)...", ref_date)
    listing = _fetch_listing_with_marcap(as_of_date=ref_ts.strftime("%Y-%m-%d"))

    listing["market_cap"] = pd.to_numeric(listing["market_cap"], errors="coerce").fillna(0.0)
    listing = listing[listing["market_cap"] > 0]

    # ETF·스팩·리츠·우선주 제외 — 재무 데이터 없어 스코어 왜곡 방지
    before = len(listing)
    listing = listing[listing.apply(lambda r: _is_investable(r["name"], r["code"]), axis=1)]
    logger.info("비투자 종목 제외: %d개 → %d개 (ETF·스팩·우선주 등 %d개 제거)",
                before, len(listing), before - len(listing))

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

    # 시장별 분리 선정: KOSPI 상위 N + KOSDAQ(+GLOBAL) 상위 M
    kospi_df = (
        listing[listing["market"] == "KOSPI"]
        .sort_values("market_cap", ascending=False)
        .head(kospi_top)
    )
    kosdaq_df = (
        listing[listing["market"].str.startswith("KOSDAQ")]
        .sort_values("market_cap", ascending=False)
        .head(kosdaq_top)
    )
    combined = (
        pd.concat([kospi_df, kosdaq_df])
        .sort_values("market_cap", ascending=False)
        .drop_duplicates(subset="code")
        .reset_index(drop=True)[["code", "name", "market", "sector", "market_cap"]]
    )
    combined.index = combined.index + 1
    combined.index.name = "rank"

    logger.info(
        "유니버스 확정: %d개 종목 (KOSPI %d + KOSDAQ %d)",
        len(combined), len(kospi_df), len(kosdaq_df),
    )
    try:
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        combined.to_csv(snapshot_path, index=False, encoding="utf-8-sig")
        logger.info("유니버스 스냅샷 저장: %s", snapshot_path)
    except Exception as e:
        logger.warning("유니버스 스냅샷 저장 실패(%s): %s", snapshot_path, e)
    return combined


def load_universe(
    refresh: bool = False,
    as_of_date: str | None = None,
    kospi_top: int = 200,
    kosdaq_top: int = 100,
) -> pd.DataFrame:
    """
    universe.yaml이 존재하면 로드, 없거나 refresh=True이면 재생성.
    """
    UNIVERSE_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not refresh and UNIVERSE_PATH.exists():
        logger.info("기존 유니버스 로드: %s", UNIVERSE_PATH)
        with open(UNIVERSE_PATH) as f:
            data = yaml.safe_load(f)
        cache_matches = (
            data.get("as_of_date") == as_of_date
            and data.get("kospi_top") == kospi_top
            and data.get("kosdaq_top") == kosdaq_top
        )
        if not cache_matches:
            logger.info(
                "유니버스 캐시 기준 불일치(as_of=%s, requested=%s) → 재생성",
                data.get("as_of_date"), as_of_date,
            )
        else:
            return pd.DataFrame(data["stocks"])

    logger.info("유니버스 재생성 중...")
    df = build_universe(as_of_date=as_of_date, kospi_top=kospi_top, kosdaq_top=kosdaq_top)

    with open(UNIVERSE_PATH, "w") as f:
        yaml.dump(
            {
                "generated_at": pd.Timestamp.now().isoformat(),
                "as_of_date": as_of_date,
                "kospi_top": kospi_top,
                "kosdaq_top": kosdaq_top,
                "count": len(df),
                "stocks": df.reset_index().to_dict(orient="records"),
            },
            f,
            allow_unicode=True,
            default_flow_style=False,
        )
    logger.info("유니버스 저장 완료: %s (%d개)", UNIVERSE_PATH, len(df))
    return df
