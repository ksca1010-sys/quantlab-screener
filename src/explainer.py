"""
종목별 선별 근거 텍스트 생성
"""
from __future__ import annotations

import pandas as pd


def _pct_rank(value: float, series: pd.Series) -> int:
    """유니버스 내 백분위 순위 (1=최상위)."""
    if pd.isna(value):
        return 50
    return int((series > value).sum()) + 1


def _sector_pct_rank(code: str, df: pd.DataFrame, axis: str) -> tuple[int, int]:
    """섹터 내 백분위 순위 반환 (rank, sector_size)."""
    row = df[df["code"] == code]
    if row.empty:
        return 0, 0
    sector = row["sector"].iloc[0]
    sector_df = df[df["sector"] == sector]
    value = float(row[axis].iloc[0])
    rank = int((sector_df[axis] > value).sum()) + 1
    return rank, len(sector_df)


def growth_reason(code: str, df: pd.DataFrame) -> str:
    row = df[df["code"] == code]
    if row.empty:
        return "성장 데이터 없음"
    score = float(row["Growth"].iloc[0])
    rank = _pct_rank(score, df["Growth"])
    s_rank, s_size = _sector_pct_rank(code, df, "Growth")
    total = len(df)
    sector_note = f" | 섹터 내 {s_rank}위/{s_size}위" if s_size > 0 else ""

    if score == 0:
        return "⚠️ DART 재무 데이터 미확보 (연결재무제표 없음 또는 공시 미게재)"
    elif score >= 70:
        return (
            f"✅ 매출·영업이익 YoY 성장률 유니버스 내 **{rank}위/{total}위** "
            f"(상위 {rank/total*100:.0f}%){sector_note}"
            f" — Growth 점수 **{score:.1f}점**. 강한 성장 모멘텀, 2년 연속 매출 확대 추세."
        )
    elif score >= 45:
        return (
            f"🔵 매출·영업이익 성장률 **{rank}위/{total}위**{sector_note}"
            f" — Growth 점수 **{score:.1f}점**."
            f" 안정적 성장 구간, 역성장 리스크 낮음."
        )
    else:
        return (
            f"🟡 매출·영업이익 성장률 **{rank}위/{total}위**{sector_note}"
            f" — Growth 점수 **{score:.1f}점**."
            f" 성장 둔화 또는 역성장 구간, 이익 회복 여부 모니터링 필요."
        )


def value_reason(code: str, df: pd.DataFrame) -> str:
    row = df[df["code"] == code]
    if row.empty:
        return "밸류에이션 데이터 없음"
    score = float(row["Value"].iloc[0])
    rank = _pct_rank(score, df["Value"])
    s_rank, s_size = _sector_pct_rank(code, df, "Value")
    total = len(df)
    sector_note = f" | 섹터 내 {s_rank}위/{s_size}위" if s_size > 0 else ""

    if abs(score - 37.5) < 0.1:
        return "⚠️ PER/PBR 시장 데이터 미확보 (pykrx API 일시 불능) — 배당수익률 중립값 적용"
    elif score >= 60:
        return (
            f"✅ 섹터 내 PER·PBR 하위권 (저평가 구간) — Value 점수 **{score:.1f}점**, "
            f"**{rank}위/{total}위**{sector_note}."
            f" 현재 주가 대비 이익·자산가치 매력도 높음."
        )
    elif score >= 40:
        return (
            f"🔵 섹터 내 밸류에이션 **{rank}위/{total}위**{sector_note}"
            f" — Value 점수 **{score:.1f}점**."
            f" 적정 가격 구간, 고평가·저평가 중립."
        )
    else:
        return (
            f"🔴 섹터 내 PER·PBR 상위권 (고평가 구간) — Value 점수 **{score:.1f}점**, "
            f"**{rank}위/{total}위**{sector_note}."
            f" 현재 주가가 이익·자산 대비 프리미엄. 성장성으로 정당화 여부 확인 필요."
        )


def quality_reason(code: str, df: pd.DataFrame) -> str:
    row = df[df["code"] == code]
    if row.empty:
        return "펀더멘털 데이터 없음"
    score = float(row["Quality"].iloc[0])
    rank = _pct_rank(score, df["Quality"])
    s_rank, s_size = _sector_pct_rank(code, df, "Quality")
    total = len(df)
    sector_note = f" | 섹터 내 {s_rank}위/{s_size}위" if s_size > 0 else ""

    if abs(score - 50.0) < 0.1:
        return "⚠️ ROE·부채비율 데이터 미확보 (pykrx API 일시 불능) — 중립값 적용"
    elif score >= 70:
        return (
            f"✅ ROE·영업이익률 우수, 부채비율 낮음 — Quality 점수 **{score:.1f}점**, "
            f"**{rank}위/{total}위**{sector_note}."
            f" 자본 효율성과 재무 건전성 동시 충족."
        )
    elif score >= 40:
        return (
            f"🔵 수익성·안정성 **{rank}위/{total}위**{sector_note}"
            f" — Quality 점수 **{score:.1f}점**."
            f" 평균 수준의 재무 품질, 특이 리스크 없음."
        )
    else:
        return (
            f"🔴 수익성 또는 재무 건전성 주의 — Quality 점수 **{score:.1f}점**, "
            f"**{rank}위/{total}위**{sector_note}."
            f" ROE 저하 또는 부채비율 높음. 세부 재무제표 확인 권장."
        )


def trend_reason(code: str, df: pd.DataFrame) -> str:
    row = df[df["code"] == code]
    if row.empty:
        return "추세 데이터 없음"
    score = float(row["Trend"].iloc[0])
    rank = _pct_rank(score, df["Trend"])
    s_rank, s_size = _sector_pct_rank(code, df, "Trend")
    total = len(df)
    sector_note = f" | 섹터 내 {s_rank}위/{s_size}위" if s_size > 0 else ""

    if score >= 90:
        return (
            f"✅ 이동평균 정배열(20>60>120일) + 52주 고점 근접 + 거래량 증가"
            f" — Trend 점수 **{score:.1f}점**, **{rank}위/{total}위**{sector_note}."
            f" 강한 상승 모멘텀 진행 중."
        )
    elif score >= 65:
        return (
            f"🔵 이동평균 부분 정배열, 상승 추세 진행 중"
            f" — Trend 점수 **{score:.1f}점**, **{rank}위/{total}위**{sector_note}."
            f" 추세 강화 여부 지속 모니터링."
        )
    elif score >= 40:
        return (
            f"🟡 추세 중립 구간, 방향성 불명확"
            f" — Trend 점수 **{score:.1f}점**, **{rank}위/{total}위**{sector_note}."
            f" 거래량 확인 후 진입 판단 권장."
        )
    else:
        return (
            f"🔴 이동평균 역배열 또는 52주 저점 근접"
            f" — Trend 점수 **{score:.1f}점**, **{rank}위/{total}위**{sector_note}."
            f" 단기 추세 비우호적, 반등 신호 대기."
        )


def total_verdict(code: str, df: pd.DataFrame) -> str:
    row = df[df["code"] == code]
    if row.empty:
        return "데이터 없음"
    score = float(row["Total"].iloc[0])
    rank = int(row.index[0])

    if score >= 55:
        verdict = "**최우수** — 성장·추세·가치 전반 상위권"
    elif score >= 45:
        verdict = "**우수** — 주요 축에서 고른 강점"
    elif score >= 35:
        verdict = "**보통** — 일부 축 강점, 일부 약점 혼재"
    else:
        verdict = "**관찰** — 복수 축에서 낮은 점수"

    return f"종합점수 **{score:.1f}점** (유니버스 {rank}위) → {verdict}"


def _make_summary(code: str, df: pd.DataFrame) -> str:
    row = df[df["code"] == code]
    if row.empty:
        return ""
    g = float(row["Growth"].iloc[0])
    v = float(row["Value"].iloc[0])
    q = float(row["Quality"].iloc[0])
    t = float(row["Trend"].iloc[0])
    total = float(row["Total"].iloc[0])
    name = row["name"].iloc[0]

    strengths = [lbl for lbl, val in [("성장", g), ("가치", v), ("펀더멘털", q), ("추세", t)] if val >= 60]
    weaknesses = [lbl for lbl, val in [("성장", g), ("가치", v), ("펀더멘털", q), ("추세", t)] if val < 35]

    summary = f"{name}는 종합 {total:.1f}점"
    if strengths:
        summary += f"으로 **{'·'.join(strengths)}** 축이 강점"
    if weaknesses:
        summary += f", **{'·'.join(weaknesses)}** 축은 보완 필요"
    summary += "."
    return summary


def explain_stock(code: str, df: pd.DataFrame) -> dict[str, str]:
    """종목 한 개의 4축 선별 근거 딕셔너리 반환."""
    return {
        "total": total_verdict(code, df),
        "growth": growth_reason(code, df),
        "value": value_reason(code, df),
        "quality": quality_reason(code, df),
        "trend": trend_reason(code, df),
        "summary": _make_summary(code, df),
    }
