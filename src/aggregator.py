"""
집계기: 4축 점수 합산, 랭킹, 최종 결과 DataFrame 생성
"""
from __future__ import annotations

import pandas as pd


def aggregate(
    universe: pd.DataFrame,
    growth: pd.Series,
    value: pd.Series,
    quality: pd.Series,
    trend: pd.Series,
    risk: pd.Series,
) -> pd.DataFrame:
    """
    4축 점수를 동일 가중 평균으로 합산. Risk는 보조지표로만 보존한다.
    TotalScore = 0.25 × (Growth + Value + Quality + Trend)
    """
    df = universe[["code", "name", "market", "sector", "market_cap"]].copy()
    df = df.set_index("code")

    df["Growth"]  = pd.to_numeric(growth.reindex(df.index),  errors="coerce").fillna(0).round(2)
    df["Value"]   = pd.to_numeric(value.reindex(df.index),   errors="coerce").fillna(0).round(2)
    df["Quality"] = pd.to_numeric(quality.reindex(df.index), errors="coerce").fillna(0).round(2)
    df["Trend"]   = pd.to_numeric(trend.reindex(df.index),   errors="coerce").fillna(0).round(2)
    df["Risk"]    = pd.to_numeric(risk.reindex(df.index),    errors="coerce").fillna(0).round(2)

    df["Total"] = (
        0.25 * df["Growth"]
        + 0.25 * df["Value"]
        + 0.25 * df["Quality"]
        + 0.25 * df["Trend"]
    ).round(2)

    df = df.sort_values("Total", ascending=False).reset_index()
    df.index = df.index + 1
    df.index.name = "rank"

    return df


def add_data_grade(df: pd.DataFrame) -> pd.DataFrame:
    """
    각 종목의 데이터 커버리지를 A/B/C/D 등급으로 표시.
    A: 5개 재무 지표 모두 확보, B: 3~4개, C: 1~2개, D: 0개 (가격만)
    """
    key_cols = ["per", "pbr", "dividend_yield", "roe", "operating_margin"]
    available = [c for c in key_cols if c in df.columns]
    if not available:
        df = df.copy()
        df["data_grade"] = "D"
        return df

    count = df[available].notna().sum(axis=1)
    n = len(available)
    grade = pd.cut(
        count,
        bins=[-1, 0, n * 0.4, n * 0.8, n],
        labels=["D", "C", "B", "A"],
    )
    df = df.copy()
    df["data_grade"] = grade.astype(str)
    return df


def to_csv(df: pd.DataFrame, path: str, top_n: int | None = None) -> None:
    """결과 DataFrame을 CSV로 저장. top_n 지정 시 상위 N개만 저장."""
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = (df.head(top_n) if top_n is not None else df).copy()
    data.insert(0, "rank", range(1, len(data) + 1))
    data.to_csv(path, index=False, encoding="utf-8-sig")


def save_snapshot(df: pd.DataFrame, as_of_date: str) -> str:
    """
    백테스트용 스냅샷 저장: output/snapshots/YYYYMMDD.csv
    파이프라인 실행마다 자동 호출 — 분기 IC 검증의 기반 데이터.
    """
    import os
    snap_dir = os.path.join("output", "snapshots")
    os.makedirs(snap_dir, exist_ok=True)
    date_tag = as_of_date.replace("-", "")
    path = os.path.join(snap_dir, f"{date_tag}.csv")
    cols = ["code", "name", "sector", "Growth", "Value", "Quality", "Trend", "Risk", "Total"]
    available = [c for c in cols if c in df.columns]
    df[available].to_csv(path, index=False, encoding="utf-8-sig")
    return path
