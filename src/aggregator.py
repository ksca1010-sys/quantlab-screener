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
    5축 점수를 동일 가중 평균으로 합산.
    TotalScore = 0.20 × (Growth + Value + Quality + Trend + Risk)
    """
    df = universe[["code", "name", "market", "sector", "market_cap"]].copy()
    df = df.set_index("code")

    df["Growth"]  = pd.to_numeric(growth.reindex(df.index),  errors="coerce").fillna(0).round(2)
    df["Value"]   = pd.to_numeric(value.reindex(df.index),   errors="coerce").fillna(0).round(2)
    df["Quality"] = pd.to_numeric(quality.reindex(df.index), errors="coerce").fillna(0).round(2)
    df["Trend"]   = pd.to_numeric(trend.reindex(df.index),   errors="coerce").fillna(0).round(2)
    df["Risk"]    = pd.to_numeric(risk.reindex(df.index),    errors="coerce").fillna(0).round(2)

    df["Total"] = (
        0.20 * df["Growth"]
        + 0.20 * df["Value"]
        + 0.20 * df["Quality"]
        + 0.20 * df["Trend"]
        + 0.20 * df["Risk"]
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
    data = df.head(top_n) if top_n is not None else df
    data.to_csv(path, encoding="utf-8-sig")
