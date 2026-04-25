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
) -> pd.DataFrame:
    """
    4축 점수를 동일 가중 평균으로 합산.
    TotalScore = 0.25 * Growth + 0.25 * Value + 0.25 * Quality + 0.25 * Trend
    """
    df = universe[["code", "name", "market", "sector", "market_cap"]].copy()
    df = df.set_index("code")

    df["Growth"] = growth.reindex(df.index).fillna(0).round(2)
    df["Value"] = value.reindex(df.index).fillna(0).round(2)
    df["Quality"] = quality.reindex(df.index).fillna(0).round(2)
    df["Trend"] = trend.reindex(df.index).fillna(0).round(2)

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


def to_csv(df: pd.DataFrame, path: str) -> None:
    """결과 DataFrame을 CSV로 저장."""
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_csv(path, encoding="utf-8-sig")
