"""
QuantLab 포트폴리오 백테스트 — Track A
pykrx 과거 PER/PBR + FDR 가격으로 분기별 IC 산출

실행: python -m src.backtest_portfolio
결과: output/backtest_portfolio.csv, output/backtest_ic_by_axis.csv
"""
from __future__ import annotations
import logging, sys
from pathlib import Path
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
logger = logging.getLogger("backtest")

OUTPUT_DIR   = Path("output")
SNAPSHOT_DIR = OUTPUT_DIR / "snapshots"
QUARTERS = [
    "20231001", "20240101", "20240401",
    "20240701", "20241001", "20250101",
    "20250401", "20250701", "20251001",
]
FORWARD_DAYS = {"1M": 21, "3M": 63, "6M": 126}


def _spearman_ic(s: pd.Series, r: pd.Series) -> float:
    aligned = pd.concat([s, r], axis=1).dropna()
    if len(aligned) < 10:
        return float("nan")
    return float(aligned.iloc[:, 0].rank().corr(aligned.iloc[:, 1].rank()))


def _load_universe() -> list[str]:
    df = pd.read_csv(OUTPUT_DIR / "stocks_universe_full.csv", index_col=0)
    return df["code"].astype(str).str.zfill(6).tolist()


def _fetch_price_slice(codes: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
    import FinanceDataReader as fdr
    import time
    price: dict[str, pd.DataFrame] = {}
    for code in codes:
        try:
            df = fdr.DataReader(code, start, end)
            if not df.empty:
                price[code] = df
        except Exception:
            pass
        time.sleep(0.05)
    try:
        price["KS11"] = fdr.DataReader("KS11", start, end)
    except Exception:
        pass
    return price


def _fetch_pykrx_fundamental(codes: list[str], date: str) -> pd.DataFrame:
    """pykrx get_market_fundamental 로 PER·PBR·배당수익률 수집."""
    try:
        from pykrx import stock as krx
        rows = []
        for market in ("KOSPI", "KOSDAQ"):
            try:
                df = krx.get_market_fundamental(date, market=market)
                if df.empty:
                    continue
                df.index = df.index.astype(str).str.zfill(6)
                for code in codes:
                    if code in df.index:
                        r = df.loc[code]
                        rows.append({
                            "code": code,
                            "per": float(r.get("PER", float("nan"))),
                            "pbr": float(r.get("PBR", float("nan"))),
                            "dividend_yield": float(r.get("DY", float("nan"))),
                        })
            except Exception as e:
                logger.warning("pykrx fundamental %s %s: %s", market, date, e)
        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["code","per","pbr","dividend_yield"])
    except ImportError:
        logger.warning("pykrx 없음 — Value 축 건너뜀")
        return pd.DataFrame(columns=["code","per","pbr","dividend_yield"])


def _score_trend_risk(codes: list[str], price: dict[str, pd.DataFrame]) -> tuple[pd.Series, pd.Series]:
    from src.scorers.trend import score_trend
    from src.scorers.risk  import score_risk
    universe = pd.DataFrame({"code": codes})
    try:
        t = score_trend(universe, price)
    except Exception:
        t = pd.Series(float("nan"), index=codes)
    try:
        r = score_risk(universe, price)
    except Exception:
        r = pd.Series(float("nan"), index=codes)
    return t, r


def _score_value(codes: list[str], fund_df: pd.DataFrame) -> pd.Series:
    """PBR 역수 기반 단순 Value 점수 (섹터 분위수 없이 — 과거 섹터 정보 미확보)."""
    if fund_df.empty:
        return pd.Series(float("nan"), index=codes)
    fund = fund_df.set_index("code").reindex(codes)
    pbr = pd.to_numeric(fund["pbr"], errors="coerce")
    per = pd.to_numeric(fund["per"],  errors="coerce")
    dy  = pd.to_numeric(fund["dividend_yield"], errors="coerce")
    # 낮은 PBR·PER → 높은 점수 (역수 min-max)
    from src.normalizer import minmax_scale
    inv_pbr = (1 / pbr.clip(0.01, 20)).fillna(0)
    inv_per = (1 / per.clip(0.01, 100)).fillna(0)
    s_pbr = minmax_scale(inv_pbr, 0, 40).fillna(0)
    s_per = minmax_scale(inv_per, 0, 40).fillna(0)
    s_dy  = minmax_scale(dy.clip(0, 10), 0, 20).fillna(0)
    return (s_pbr + s_per + s_dy).rename(None)


def _forward_returns(price: dict[str, pd.DataFrame], codes: list[str],
                     base: str, fwd: int) -> pd.Series:
    base_ts = pd.Timestamp(base)
    ret: dict[str, float] = {}
    for code in codes:
        df = price.get(code, pd.DataFrame())
        if df.empty or "Close" not in df.columns:
            continue
        past   = df[df.index <= base_ts]
        future = df[df.index >  base_ts]
        if past.empty or len(future) < fwd:
            continue
        p0 = float(past["Close"].iloc[-1])
        pe = float(future["Close"].iloc[fwd - 1])
        if p0 > 0:
            ret[code] = (pe / p0 - 1) * 100
    return pd.Series(ret)


def run_backtest(quarters: list[str] | None = None) -> pd.DataFrame:
    if quarters is None:
        quarters = QUARTERS

    codes = _load_universe()
    logger.info("유니버스: %d종목", len(codes))

    # 최장 기간 가격 데이터 한 번에 수집 (재사용)
    price_start = (pd.Timestamp(min(quarters)) - pd.DateOffset(days=420)).strftime("%Y-%m-%d")
    price_end   = (pd.Timestamp(max(quarters)) + pd.DateOffset(days=180)).strftime("%Y-%m-%d")
    logger.info("가격 데이터 수집: %s ~ %s (약 5~10분 소요)", price_start, price_end)
    price_full = _fetch_price_slice(codes, price_start, price_end)
    logger.info("가격 수집 완료: %d종목", len(price_full) - 1)  # KS11 제외

    records = []
    for q_date in quarters:
        logger.info("분기 %s 처리 중...", q_date)
        q_ts  = pd.Timestamp(q_date)
        q_str = q_ts.strftime("%Y-%m-%d")

        # 해당 분기 가격 슬라이스 (1년치)
        q_start = (q_ts - pd.DateOffset(days=420)).strftime("%Y-%m-%d")
        sliced  = {c: df[(df.index >= q_start) & (df.index <= q_str)]
                   for c, df in price_full.items()}

        # 스코어링
        trend_s, risk_s = _score_trend_risk(codes, sliced)
        fund_df = _fetch_pykrx_fundamental(codes, q_date)
        value_s = _score_value(codes, fund_df)

        # 포워드 수익률
        for period, fwd in FORWARD_DAYS.items():
            ret = _forward_returns(price_full, codes, q_str, fwd)
            if ret.empty:
                continue
            row = {"date": q_date, "period": period, "n": len(ret)}
            row["IC_Trend"] = _spearman_ic(trend_s, ret)
            row["IC_Risk"]  = _spearman_ic(risk_s,  ret)
            row["IC_Value"] = _spearman_ic(value_s, ret)
            # Equal-weight composite (Trend+Risk+Value)
            composite = (trend_s.reindex(ret.index).fillna(0) +
                         risk_s.reindex(ret.index).fillna(0) +
                         value_s.reindex(ret.index).fillna(0)) / 3
            row["IC_Composite"] = _spearman_ic(composite, ret)
            records.append(row)
            logger.info("  %s %s: IC_Trend=%.3f  IC_Value=%.3f  IC_Risk=%.3f  IC_Comp=%.3f",
                        q_date, period,
                        row["IC_Trend"], row["IC_Value"], row["IC_Risk"], row["IC_Composite"])

    if not records:
        logger.error("백테스트 결과 없음")
        return pd.DataFrame()

    result = pd.DataFrame(records)
    OUTPUT_DIR.mkdir(exist_ok=True)
    result.to_csv(OUTPUT_DIR / "backtest_portfolio.csv", index=False, encoding="utf-8-sig")
    logger.info("저장: output/backtest_portfolio.csv")

    # 축별 IC 요약
    summary_rows = []
    for axis in ["IC_Trend", "IC_Risk", "IC_Value", "IC_Composite"]:
        for period in ["1M", "3M", "6M"]:
            sub = result[result["period"] == period][axis].dropna()
            if len(sub) == 0:
                continue
            ir = float(sub.mean() / sub.std() * np.sqrt(4)) if sub.std() > 0 else float("nan")
            summary_rows.append({
                "axis": axis.replace("IC_", ""),
                "period": period,
                "IC_mean": round(sub.mean(), 4),
                "IC_std":  round(sub.std(), 4),
                "IR":      round(ir, 3),
                "n_quarters": len(sub),
                "positive_rate": round((sub > 0).mean(), 3),
            })
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(OUTPUT_DIR / "backtest_ic_by_axis.csv", index=False, encoding="utf-8-sig")
    logger.info("저장: output/backtest_ic_by_axis.csv")
    print("\n=== IC 요약 ===")
    print(summary.to_string(index=False))
    return result


if __name__ == "__main__":
    run_backtest()
