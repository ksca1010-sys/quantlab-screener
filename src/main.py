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
    """Naver Finance HTML에서 PER·PBR·배당수익률 수집. 허수 없음 — 미확보 시 NaN."""
    from src.data_loader import fetch_naver_fundamentals
    import time

    nan = float("nan")
    records = []
    for _, row in tqdm(universe.iterrows(), total=len(universe), desc="시장 데이터 수집"):
        code = str(row["code"]).zfill(6)
        rec: dict = {"code": code}
        try:
            fund = fetch_naver_fundamentals(code)
            rec["per"] = fund["per"]
            rec["pbr"] = fund["pbr"]
            rec["dividend_yield"] = fund["dividend_yield"]
        except Exception as e:
            logger.warning("[%s] 시장 데이터 조회 실패: %s", code, e)
            rec.update({"per": nan, "pbr": nan, "dividend_yield": nan})
        rec.update({"peg": nan, "roe": nan, "operating_margin": nan,
                    "debt_ratio": nan, "interest_coverage": nan})
        records.append(rec)
        time.sleep(0.3)  # Naver 레이트 제한

    if not records:
        return pd.DataFrame(columns=["code", "per", "pbr", "dividend_yield", "peg",
                                     "roe", "operating_margin", "debt_ratio", "interest_coverage"])
    return pd.DataFrame(records)


def _compute_peg(market_data: pd.DataFrame, financials: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """PEG = PER ÷ EPS CAGR(%). 두 값 모두 실데이터일 때만 계산 — 허수 없음."""
    from src.scorers.growth import _extract_by_year

    peg_map: dict[str, float] = {}
    for code, df in financials.items():
        if df.empty:
            continue
        try:
            eps = _extract_by_year(df, "주당순이익")
            if eps is None or len(eps) < 2:
                continue
            end_val = float(eps.iloc[-1])
            start_val = float(eps.iloc[0])
            n_years = len(eps) - 1
            if start_val <= 0 or end_val <= 0 or n_years == 0:
                continue
            eps_cagr_pct = ((end_val / start_val) ** (1 / n_years) - 1) * 100
            if eps_cagr_pct <= 0:
                continue
            code_str = str(code).zfill(6)
            per_row = market_data[market_data["code"] == code_str]
            if per_row.empty:
                continue
            per = float(per_row["per"].iloc[0])
            if pd.isna(per) or per <= 0:
                continue
            peg_map[code_str] = per / eps_cagr_pct
        except Exception:
            continue

    if not peg_map:
        return market_data
    peg_series = pd.Series(peg_map, name="peg_computed")
    result = market_data.copy()
    result = result.set_index("code")
    result["peg"] = result["peg"].where(result["peg"].notna(), peg_series)
    return result.reset_index()


def _enrich_from_dart(market_data: pd.DataFrame, financials: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """DART 재무제표(CIS/IS + BS)에서 ROE·영업이익률·부채비율·이자보상배율 계산하여 market_data 보강."""

    def _val(df: pd.DataFrame, id_pat: str, nm_pat: str, divs: tuple) -> float:
        sub = df[df["sj_div"].isin(divs)] if "sj_div" in df.columns else df
        if "account_id" in sub.columns:
            # _pat 단어경계 우선: EquityAndLiabilities·InvestmentAccountedForUsingEquityMethod 등 false-positive 방지
            rows = sub[sub["account_id"].str.endswith(f"_{id_pat}", na=False)]
            if rows.empty:
                rows = sub[sub["account_id"].str.contains(id_pat, na=False, case=False)]
            if not rows.empty:
                try:
                    return float(str(rows["thstrm_amount"].iloc[0]).replace(",", ""))
                except Exception:
                    pass
        if "account_nm" in sub.columns:
            # 완전 일치 우선: 자본총계 contains가 부채와자본총계까지 매칭하는 문제 방지
            rows = sub[sub["account_nm"] == nm_pat]
            if rows.empty:
                rows = sub[sub["account_nm"].str.contains(nm_pat, na=False)]
            if not rows.empty:
                try:
                    return float(str(rows["thstrm_amount"].iloc[0]).replace(",", ""))
                except Exception:
                    pass
        return float("nan")

    records = []
    for code, df in financials.items():
        if df.empty or "bsns_year" not in df.columns:
            continue
        df = df[df["bsns_year"] == df["bsns_year"].max()]
        IS = ("IS", "CIS")
        BS = ("BS",)
        revenue    = _val(df, "Revenue",        "매출액",   IS)
        op_income  = _val(df, "OperatingIncome", "영업이익", IS)
        net_income = _val(df, "ProfitLoss",      "당기순이익", IS)
        equity     = _val(df, "Equity",          "자본총계", BS)
        liabilities= _val(df, "Liabilities",     "부채총계", BS)
        fin_costs  = _val(df, "FinanceCosts",    "금융비용", IS)

        def safe_div(a, b):
            return (a / b * 100) if (not pd.isna(a) and not pd.isna(b) and b != 0) else float("nan")

        # 자본잠식(equity <= 0): ROE·부채비율 계산 불가 → NaN
        roe_val = safe_div(net_income, equity) if (not pd.isna(equity) and equity > 0) else float("nan")
        dr_val  = safe_div(liabilities, equity) if (not pd.isna(equity) and equity > 0) else float("nan")
        # 무차입(fin_costs == 0): 이자보상배율 무한대 → cap 100
        if not pd.isna(op_income) and not pd.isna(fin_costs):
            ic_val = (op_income / fin_costs) if fin_costs > 0 else (100.0 if fin_costs == 0 else float("nan"))
        else:
            ic_val = float("nan")

        records.append({
            "code": str(code).zfill(6),
            "roe":              roe_val,
            "operating_margin": safe_div(op_income, revenue),
            "debt_ratio":       dr_val,
            "interest_coverage": ic_val,
        })

    if not records:
        return market_data

    dart_df = pd.DataFrame(records)
    result = market_data.merge(dart_df, on="code", how="left", suffixes=("", "_dart"))
    for col in ["roe", "operating_margin", "debt_ratio", "interest_coverage"]:
        dart_col = f"{col}_dart"
        if dart_col in result.columns:
            mask = result[col].isna()
            result.loc[mask, col] = result.loc[mask, dart_col]
            result.drop(columns=[dart_col], inplace=True)
    return result


def _build_financial_data(universe: pd.DataFrame, as_of_date: str) -> dict[str, pd.DataFrame]:
    """DART에서 분기 재무 데이터 수집 (DART_API_KEY 필요)."""
    from src.data_loader import get_financial_data
    import time

    # 우선주 → 보통주 코드 매핑 (DART는 보통주 코드로만 공시)
    _PREFERRED_PARENT: dict[str, str] = {
        "005935": "005930",  # 삼성전자우 → 삼성전자
        "005387": "005380",  # 현대차2우B → 현대차
        "005385": "005380",  # 현대차우 → 현대차
        "000271": "000270",  # 기아우 → 기아
        "012451": "012450",  # 한화에어로스페이스우 → 한화에어로스페이스
        "003601": "003600",  # SK우 → SK
        "096771": "096770",  # SK이노베이션우 → SK이노베이션
    }

    result: dict[str, pd.DataFrame] = {}
    codes = universe["code"].tolist()

    for code in tqdm(codes, desc="재무 데이터 수집 (DART)"):
        dart_code = _PREFERRED_PARENT.get(str(code).zfill(6), code)
        df = get_financial_data(dart_code, as_of_date)
        result[code] = df  # 원본 코드로 저장 (스코어링 인덱스 일치)
        time.sleep(0.1)  # DART 레이트 제한

    return result


def _build_price_data(
    universe: pd.DataFrame, as_of_date: str
) -> dict[str, pd.DataFrame]:
    """FinanceDataReader로 가격 데이터 수집 (1년치). KOSPI 지수(KS11) 포함."""
    from src.data_loader import get_price_data

    start = (pd.Timestamp(as_of_date) - pd.DateOffset(days=380)).strftime("%Y-%m-%d")
    result: dict[str, pd.DataFrame] = {}

    # KOSPI 지수 — Risk 축 베타 계산용
    result["KS11"] = get_price_data("KS11", start, as_of_date)

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
    from src.scorers.risk import score_risk
    from src.aggregator import aggregate, add_data_grade, to_csv

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

    # 4-b. DART 재무제표로 ROE·영업이익률·부채비율 보강
    if dart_available:
        market_data = _enrich_from_dart(market_data, financials)
        market_data = _compute_peg(market_data, financials)

    # 5. 스코어링
    logger.info("[5/6] 5축 스코어링...")
    growth  = score_growth(universe, financials)
    value   = score_value(universe, financials, market_data)
    quality = score_quality(universe, financials, market_data)
    trend   = score_trend(universe, price_data)
    risk    = score_risk(universe, price_data)

    # 6. 집계 & 저장
    logger.info("[6/6] 집계 및 결과 저장...")
    result = aggregate(universe, growth, value, quality, trend, risk)

    # 섹터 고정값 적용 (config/sector_map.yaml 우선 — pykrx 실패로 덮어씌워지는 것 방지)
    sector_map_path = os.path.join(os.path.dirname(__file__), "..", "config", "sector_map.yaml")
    if os.path.exists(sector_map_path):
        import yaml
        with open(sector_map_path, encoding="utf-8") as f:
            sector_map = yaml.safe_load(f)
        result["code_str"] = result["code"].astype(str).str.zfill(6)
        fixed = result["code_str"].map(sector_map)
        result["sector"] = fixed.where(fixed.notna(), result["sector"])
        result.drop(columns=["code_str"], inplace=True)
        logger.info("섹터 고정값 적용 완료 (config/sector_map.yaml)")

    # 데이터 신뢰도 등급 부여 (A/B/C/D) — 원시 지표 컬럼을 임시 병합 후 등급 계산
    _grade_cols = ["code", "per", "pbr", "dividend_yield", "roe", "operating_margin"]
    _available = [c for c in _grade_cols if c in market_data.columns]
    result = result.merge(market_data[_available], on="code", how="left")
    result = add_data_grade(result)
    result = result.drop(columns=[c for c in _available if c != "code" and c in result.columns])

    output_dir = os.getenv("OUTPUT_DIR", "./output")
    # 전체 유니버스 (300개) 저장 — 상위권 밖 탐색용
    to_csv(result, f"{output_dir}/stocks_universe_full.csv")
    logger.info("전체 유니버스 저장 완료: %s/stocks_universe_full.csv (%d개)", output_dir, len(result))
    # 상위 100개만 저장 — 대시보드 + 하위호환
    to_csv(result, f"{output_dir}/stocks_top100.csv", top_n=100)
    logger.info("TOP 100 저장 완료: %s/stocks_top100.csv", output_dir)

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
        ["rank", "name", "code", "market", "sector", "Growth", "Value", "Quality", "Trend", "Risk", "Total"]
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
    parser.add_argument(
        "--yes",
        action="store_true",
        help="비대화형 모드 (cron/CI 자동화용) — DART 키 없으면 즉시 종료",
    )
    args = parser.parse_args()

    # STOP 조건 확인: DART API 키
    if not _check_dart_key():
        if args.yes:
            print("[STOP] DART_API_KEY 없음. .env 파일을 확인하세요.")
            sys.exit(1)
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
