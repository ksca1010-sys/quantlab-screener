"""
메인 파이프라인 오케스트레이터
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from tabulate import tabulate
from tqdm import tqdm

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("quantlab")


def _check_dart_key() -> bool:
    return bool(os.getenv("DART_API_KEY", "").strip())


def _build_market_data(universe: pd.DataFrame, as_of_date: str) -> pd.DataFrame:
    """
    pykrx + OpenDartReader로 PER/PBR/ROE 등 지표 수집.
    개별 종목 실패 시 NaN으로 처리하고 계속 진행.
    """
    from pykrx import stock as krx
    import time

    records = []
    ref = as_of_date.replace("-", "")

    for _, row in tqdm(universe.iterrows(), total=len(universe), desc="시장 데이터 수집"):
        code = row["code"]
        rec: dict = {"code": code}
        try:
            fundamental = krx.get_market_fundamental_by_ticker(ref)
            if code in fundamental.index:
                f = fundamental.loc[code]
                rec["per"] = float(f.get("PER", float("nan")))
                rec["pbr"] = float(f.get("PBR", float("nan")))
                rec["dividend_yield"] = float(f.get("DIV", float("nan")))
            else:
                rec.update({"per": float("nan"), "pbr": float("nan"), "dividend_yield": float("nan")})
        except Exception as e:
            logger.warning("[%s] 펀더멘털 조회 실패: %s", code, e)
            rec.update({"per": float("nan"), "pbr": float("nan"), "dividend_yield": float("nan")})

        # 기본값 (DART 없이 추정 불가한 항목)
        rec.setdefault("peg", float("nan"))
        rec.setdefault("roe", float("nan"))
        rec.setdefault("operating_margin", float("nan"))
        rec.setdefault("debt_ratio", float("nan"))
        rec.setdefault("interest_coverage", float("nan"))
        records.append(rec)
        time.sleep(0.05)

    if not records:
        return pd.DataFrame(columns=["code", "per", "pbr", "dividend_yield", "peg", "roe", "operating_margin", "debt_ratio", "interest_coverage"])
    return pd.DataFrame(records)


def _build_financial_data(universe: pd.DataFrame, as_of_date: str) -> dict[str, pd.DataFrame]:
    """DART에서 분기 재무 데이터 수집 (DART_API_KEY 필요)."""
    from src.data_loader import get_financial_data
    import time

    result: dict[str, pd.DataFrame] = {}
    codes = universe["code"].tolist()

    for code in tqdm(codes, desc="재무 데이터 수집 (DART)"):
        df = get_financial_data(code, as_of_date)
        result[code] = df
        time.sleep(0.1)  # DART 레이트 제한

    return result


def _build_price_data(
    universe: pd.DataFrame, as_of_date: str
) -> dict[str, pd.DataFrame]:
    """FinanceDataReader로 가격 데이터 수집 (1년치)."""
    from src.data_loader import get_price_data

    start = (pd.Timestamp(as_of_date) - pd.DateOffset(years=1)).strftime("%Y-%m-%d")
    result: dict[str, pd.DataFrame] = {}

    for _, row in tqdm(
        universe.iterrows(), total=len(universe), desc="가격 데이터 수집"
    ):
        code = row["code"]
        df = get_price_data(code, start, as_of_date)
        result[code] = df

    return result


def run_pipeline(as_of_date: str, refresh_universe: bool) -> pd.DataFrame:
    from src.universe import load_universe
    from src.scorers.growth import score_growth
    from src.scorers.value import score_value
    from src.scorers.quality import score_quality
    from src.scorers.trend import score_trend
    from src.aggregator import aggregate, to_csv

    logger.info("=== QuantLab Screener 시작 (기준일: %s) ===", as_of_date)

    # 1. 유니버스 로드
    logger.info("[1/6] 유니버스 로드...")
    universe = load_universe(refresh=refresh_universe, as_of_date=as_of_date)
    logger.info("유니버스: %d개 종목", len(universe))

    # 2. 가격 데이터
    logger.info("[2/6] 가격 데이터 수집...")
    price_data = _build_price_data(universe, as_of_date)

    # 3. 시장 데이터 (PER/PBR 등)
    logger.info("[3/6] 시장 데이터 수집...")
    market_data = _build_market_data(universe, as_of_date)

    # 4. 재무 데이터 (DART)
    dart_available = _check_dart_key()
    financials: dict[str, pd.DataFrame] = {}
    if dart_available:
        logger.info("[4/6] 재무 데이터 수집 (DART)...")
        financials = _build_financial_data(universe, as_of_date)
    else:
        logger.warning("[4/6] DART_API_KEY 없음 → 재무 데이터 스킵 (Growth/Quality 0점)")
        financials = {row["code"]: pd.DataFrame() for _, row in universe.iterrows()}

    # 5. 스코어링
    logger.info("[5/6] 4축 스코어링...")
    growth = score_growth(universe, financials)
    value = score_value(universe, financials, market_data)
    quality = score_quality(universe, financials, market_data)
    trend = score_trend(universe, price_data)

    # 6. 집계 & 저장
    logger.info("[6/6] 집계 및 결과 저장...")
    result = aggregate(universe, growth, value, quality, trend)

    output_dir = os.getenv("OUTPUT_DIR", "./output")
    out_path = f"{output_dir}/stocks_top100.csv"
    to_csv(result, out_path)
    logger.info("결과 저장 완료: %s", out_path)

    return result


def print_summary(result: pd.DataFrame) -> None:
    total = len(result)
    nan_mask = result[["Growth", "Value", "Quality", "Trend"]].isna().any(axis=1)
    success = total - nan_mask.sum()
    fail = nan_mask.sum()

    print("\n" + "=" * 70)
    print("처리 결과 요약")
    print("=" * 70)
    print(f"  총 대상: {total}개")
    print(f"  성공:   {success}개")
    print(f"  실패:   {fail}개")

    print("\n상위 10개 종목")
    print("-" * 70)
    top10 = result.head(10).reset_index()[
        ["rank", "name", "code", "market", "sector", "Growth", "Value", "Quality", "Trend", "Total"]
    ]
    print(tabulate(top10, headers="keys", tablefmt="rounded_outline", showindex=False))

    print("\n섹터 분포 (상위 30개 기준)")
    print("-" * 70)
    sector_dist = result.head(30)["sector"].value_counts()
    for sector, cnt in sector_dist.items():
        print(f"  {sector:<20} {cnt}개")

    print("\n다음 단계 제안")
    print("-" * 70)
    print("  1. pykrx PER/PBR 복구 시 Value/Quality 점수가 더 정확해집니다.")
    print("  2. --as-of-date 옵션으로 과거 특정 시점 백테스트가 가능합니다.")
    print("  3. output/stocks_top100.csv 를 스프레드시트로 열어 추가 분석을 권장합니다.")
    print("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(description="QuantLab 종목 스크리너")
    parser.add_argument(
        "--refresh-universe",
        action="store_true",
        help="universe.yaml 재생성",
    )
    # 기본값: 최근 영업일 (주말이면 금요일로 롤백)
    from pandas.tseries.offsets import BDay
    _today = pd.Timestamp.today()
    _ref = _today - BDay(1) if _today.weekday() >= 5 else _today
    parser.add_argument(
        "--as-of-date",
        default=_ref.strftime("%Y-%m-%d"),
        help="분석 기준일 (YYYY-MM-DD, 기본: 최근 영업일)",
    )
    args = parser.parse_args()

    # STOP 조건 확인: DART API 키
    if not _check_dart_key():
        print("\n[STOP] DART API 키 입력 필요.")
        print(
            "opendart.fss.or.kr 에서 인증키 신청 후 "
            ".env 파일의 DART_API_KEY 뒤에 40자리 키 붙여넣기."
        )
        print("완료되면 continue 라고 답해주세요.")
        answer = input("> ").strip().lower()
        if answer != "continue":
            print("취소되었습니다.")
            sys.exit(0)
        load_dotenv(override=True)
        if not _check_dart_key():
            print("여전히 DART_API_KEY가 비어있습니다. .env 파일을 확인하세요.")
            sys.exit(1)

    result = run_pipeline(
        as_of_date=args.as_of_date,
        refresh_universe=args.refresh_universe,
    )

    # 누락 종목 수 출력
    missing = result[["Growth", "Value", "Quality", "Trend"]].isna().any(axis=1).sum()
    logger.info("누락 종목 수: %d개", missing)

    print_summary(result)


if __name__ == "__main__":
    main()
