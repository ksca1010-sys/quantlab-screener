"""
IC/IR 백테스트 모듈

두 가지 분석:
1) 가격 축 히스토리컬 IC/IR — Trend·Risk를 과거 n분기에 걸쳐 검증 (FDR만 사용, DART 불필요)
2) 단일 기간 IC 확인 — CSV 생성일로부터 forward period 경과 후 전 축 IC 계산

IC 해석:
  IC > 0.10 : 유의미한 예측력
  IC 0.05~0.10 : 약한 신호
  IC < 0.05 : 무의미
IR = IC_mean / IC_std × sqrt(분기 수) 연환산
  IR > 0.5 : 안정적 신호
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

CSV_PATH  = Path(__file__).parent.parent / "output" / "stocks_top100.csv"
BT_OUTPUT = Path(__file__).parent.parent / "output" / "backtest_ic.csv"
PRICE_AXES = ["Trend", "Risk"]
ALL_AXES   = ["Growth", "Value", "Quality", "Trend", "Risk", "Total"]
FORWARD_PERIODS = {"1개월": 21, "3개월": 63, "6개월": 126}


# ── 핵심 유틸리티 ──────────────────────────────────────────────────────────────

def _spearman_ic(scores: pd.Series, returns: pd.Series) -> float:
    """Spearman 순위 상관 (IC). scipy 불필요 — 순위 변환 후 Pearson."""
    aligned = pd.concat([scores, returns], axis=1).dropna()
    if len(aligned) < 10:
        return float("nan")
    r1 = aligned.iloc[:, 0].rank()
    r2 = aligned.iloc[:, 1].rank()
    return float(r1.corr(r2))


def compute_ir(ic_series: pd.Series) -> float:
    """IR = IC_mean / IC_std. 분기 기준 연환산 (×√4)."""
    clean = ic_series.dropna()
    if len(clean) < 3:
        return float("nan")
    std = clean.std()
    if std == 0:
        return float("nan")
    return float(clean.mean() / std * np.sqrt(4))


def _forward_returns(price_full: dict[str, pd.DataFrame], codes: list[str],
                     base_date: str, fwd_days: int) -> pd.Series:
    """base_date 이후 fwd_days 영업일 수익률."""
    ret: dict[str, float] = {}
    for code in codes:
        df = price_full.get(code, pd.DataFrame())
        if df.empty or "Close" not in df.columns:
            continue
        if not isinstance(df.index, pd.DatetimeIndex):
            continue
        past = df[df.index <= base_date]
        future = df[df.index > base_date]
        if past.empty or len(future) < fwd_days:
            continue
        p0 = float(past["Close"].iloc[-1])
        pe = float(future["Close"].iloc[fwd_days - 1])
        if p0 > 0:
            ret[code] = (pe / p0 - 1) * 100
    return pd.Series(ret)


# ── 가격 축 히스토리컬 백테스트 ────────────────────────────────────────────────

def run_price_ic_backtest(
    codes: list[str],
    as_of_date: str,
    n_quarters: int = 8,
) -> pd.DataFrame:
    """
    Trend·Risk 히스토리컬 IC/IR 분석 (FDR 가격 데이터만 사용).

    과거 n_quarters 분기 기준점마다 Trend·Risk 점수를 계산하고
    1개월·3개월 포워드 수익률과의 Spearman IC를 산출한다.

    Returns:
        DataFrame(index=분기기준일, columns=[Trend_1M, Trend_3M, Risk_1M, Risk_3M])
    """
    from src.data_loader import get_price_data
    from src.scorers.trend import score_trend
    from src.scorers.risk import score_risk

    # 3년치 가격 데이터 일괄 수집 (캐싱 활용)
    start_3y = (pd.Timestamp(as_of_date) - pd.DateOffset(years=3)).strftime("%Y-%m-%d")
    logger.info("가격 백테스트 시작: %d종목, %d분기", len(codes), n_quarters)

    price_full: dict[str, pd.DataFrame] = {}
    for code in codes:
        price_full[code] = get_price_data(code, start_3y, as_of_date)
    price_full["KS11"] = get_price_data("KS11", start_3y, as_of_date)

    universe = pd.DataFrame({"code": codes})

    # 분기 기준점 생성 (현재 기준 n_quarters 분기 전부터 1분기 전까지)
    quarter_dates = [
        (pd.Timestamp(as_of_date) - pd.DateOffset(months=3 * i)).strftime("%Y-%m-%d")
        for i in range(n_quarters, 0, -1)
    ]

    records = []
    for q_date in quarter_dates:
        q_start_1y = (pd.Timestamp(q_date) - pd.DateOffset(years=1)).strftime("%Y-%m-%d")

        # 해당 기준일 이전 1년치 데이터로 슬라이싱
        def _slice(code: str) -> pd.DataFrame:
            df = price_full.get(code, pd.DataFrame())
            if df.empty or not isinstance(df.index, pd.DatetimeIndex):
                return df
            return df[(df.index >= q_start_1y) & (df.index <= q_date)]

        sliced = {c: _slice(c) for c in codes}
        sliced["KS11"] = _slice("KS11")

        try:
            trend_s = score_trend(universe, sliced)
            risk_s  = score_risk(universe, sliced)
        except Exception as e:
            logger.warning("분기 %s 스코어링 실패: %s", q_date, e)
            continue

        ret_1m = _forward_returns(price_full, codes, q_date, 21)
        ret_3m = _forward_returns(price_full, codes, q_date, 63)

        records.append({
            "date":      q_date,
            "Trend_1M":  _spearman_ic(trend_s, ret_1m),
            "Trend_3M":  _spearman_ic(trend_s, ret_3m),
            "Risk_1M":   _spearman_ic(risk_s,  ret_1m),
            "Risk_3M":   _spearman_ic(risk_s,  ret_3m),
        })

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records).set_index("date")
    logger.info("가격 백테스트 완료: %d분기 IC 산출", len(df))
    return df


def price_ic_summary(bt_df: pd.DataFrame) -> pd.DataFrame:
    """히스토리컬 IC에서 IC 평균·표준편차·IR 집계."""
    if bt_df.empty:
        return pd.DataFrame()
    rows = []
    for col in bt_df.columns:
        series = bt_df[col].dropna()
        axis, period = col.split("_", 1)
        rows.append({
            "축":     axis,
            "기간":   period,
            "IC 평균": round(series.mean(), 4) if len(series) else float("nan"),
            "IC 표준편차": round(series.std(), 4) if len(series) >= 2 else float("nan"),
            "IR":     round(compute_ir(series), 3),
            "유효 분기": len(series),
        })
    return pd.DataFrame(rows)


# ── 단일 기간 IC 확인 (CSV 생성 후 forward period 경과 시) ────────────────────

def run_single_ic_check(csv_path: Path = CSV_PATH) -> pd.DataFrame:
    """
    CSV 생성일 기준으로 forward period 경과 여부를 확인하고
    경과된 기간에 대해 전 축 IC를 계산한다.

    아직 경과되지 않은 기간은 '대기 중'으로 표시.
    """
    if not csv_path.exists():
        return pd.DataFrame()

    from src.data_loader import get_price_data

    df = pd.read_csv(csv_path, index_col=0)
    if "code" not in df.columns:
        return pd.DataFrame()

    gen_date = pd.Timestamp.fromtimestamp(csv_path.stat().st_mtime).strftime("%Y-%m-%d")
    elapsed  = (pd.Timestamp.today() - pd.Timestamp(gen_date)).days
    scores   = df.set_index("code")

    rows = []
    for period, fwd in FORWARD_PERIODS.items():
        row: dict = {"기간": period, "경과일": elapsed}
        if elapsed < int(fwd * 1.4):
            row["상태"] = f"대기 중 ({fwd}일 필요)"
            for axis in ALL_AXES:
                row[axis] = float("nan")
            rows.append(row)
            continue

        # 포워드 수익률 계산
        end_dt = (pd.Timestamp(gen_date) + pd.DateOffset(days=fwd + 40)).strftime("%Y-%m-%d")
        ret: dict[str, float] = {}
        for code in scores.index.astype(str).tolist():
            pdata = get_price_data(code, gen_date, end_dt)
            if pdata.empty or "Close" not in pdata.columns or len(pdata) < fwd:
                continue
            p0 = float(pdata["Close"].iloc[0])
            pe = float(pdata["Close"].iloc[min(fwd - 1, len(pdata) - 1)])
            if p0 > 0:
                ret[code] = (pe / p0 - 1) * 100

        ret_series = pd.Series(ret)
        row["상태"] = "완료"
        for axis in ALL_AXES:
            if axis in scores.columns:
                row[axis] = round(_spearman_ic(scores[axis], ret_series), 4)
            else:
                row[axis] = float("nan")
        rows.append(row)

    return pd.DataFrame(rows).set_index("기간") if rows else pd.DataFrame()


# ── 캐시 관리 ─────────────────────────────────────────────────────────────────

def save_backtest(bt_df: pd.DataFrame, path: Path = BT_OUTPUT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    bt_df.to_csv(path, encoding="utf-8-sig")


def load_backtest(path: Path = BT_OUTPUT) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        return pd.read_csv(path, index_col=0)
    except Exception:
        return None
