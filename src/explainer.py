"""
종목별 선별 근거 텍스트 생성
"""
from __future__ import annotations

import pandas as pd


def _pct_rank(value: float, series: pd.Series) -> int:
    """유니버스 내 백분위 순위 (1=최상위)."""
    if pd.isna(value):
        return 50
    rank = int((series > value).sum()) + 1
    return rank


def growth_reason(code: str, df: pd.DataFrame) -> str:
    row = df[df["code"] == code]
    if row.empty:
        return "성장 데이터 없음"
    score = float(row["Growth"].iloc[0])
    rank = _pct_rank(score, df["Growth"])
    total = len(df)

    if score == 0:
        return "⚠️ DART 재무 데이터 미확보 (연결재무제표 없음 또는 공시 미게재)"
    elif score >= 70:
        return f"✅ 매출·영업이익 YoY 성장률 유니버스 내 **{rank}위/{total}위** (상위 {rank/total*100:.0f}%) — 강한 성장 모멘텀"
    elif score >= 45:
        return f"🔵 매출·영업이익 성장률 **{rank}위/{total}위** — 안정적 성장 구간"
    else:
        return f"🟡 매출·영업이익 성장률 **{rank}위/{total}위** — 성장 둔화 또는 역성장 구간"


def value_reason(code: str, df: pd.DataFrame) -> str:
    row = df[df["code"] == code]
    if row.empty:
        return "밸류에이션 데이터 없음"
    score = float(row["Value"].iloc[0])
    rank = _pct_rank(score, df["Value"])
    total = len(df)

    if abs(score - 37.5) < 0.1:
        return "⚠️ PER/PBR 시장 데이터 미확보 (pykrx API 일시 불능) — 배당수익률 중립값 적용"
    elif score >= 60:
        return f"✅ 섹터 내 PER·PBR 하위권 (저평가 구간) — **{rank}위/{total}위**"
    elif score >= 40:
        return f"🔵 섹터 내 밸류에이션 **{rank}위/{total}위** — 적정 가격 구간"
    else:
        return f"🔴 섹터 내 PER·PBR 상위권 (고평가 구간) — **{rank}위/{total}위**"


def quality_reason(code: str, df: pd.DataFrame) -> str:
    row = df[df["code"] == code]
    if row.empty:
        return "펀더멘털 데이터 없음"
    score = float(row["Quality"].iloc[0])
    rank = _pct_rank(score, df["Quality"])
    total = len(df)

    if abs(score - 50.0) < 0.1:
        return "⚠️ ROE·부채비율 데이터 미확보 (pykrx API 일시 불능) — 중립값 적용"
    elif score >= 70:
        return f"✅ ROE·영업이익률 우수, 부채비율 낮음 — **{rank}위/{total}위**"
    elif score >= 40:
        return f"🔵 수익성·안정성 **{rank}위/{total}위** — 평균 수준"
    else:
        return f"🔴 수익성 또는 재무 건전성 주의 — **{rank}위/{total}위**"


def trend_reason(code: str, df: pd.DataFrame) -> str:
    row = df[df["code"] == code]
    if row.empty:
        return "추세 데이터 없음"
    score = float(row["Trend"].iloc[0])
    rank = _pct_rank(score, df["Trend"])
    total = len(df)

    if score >= 90:
        return f"✅ 이동평균 정배열(20>60>120일) + 52주 고점 근접 + 거래량 증가 — **{rank}위/{total}위**"
    elif score >= 65:
        return f"🔵 이동평균 부분 정배열, 상승 추세 진행 중 — **{rank}위/{total}위**"
    elif score >= 40:
        return f"🟡 추세 중립 구간, 방향성 불명확 — **{rank}위/{total}위**"
    else:
        return f"🔴 이동평균 역배열 또는 52주 저점 근접 — **{rank}위/{total}위**"


def total_verdict(code: str, df: pd.DataFrame) -> str:
    row = df[df["code"] == code]
    if row.empty:
        return ""
    score = float(row["Total"].iloc[0])
    name = row["name"].iloc[0]
    rank = int(row.index[0])

    if score >= 55:
        verdict = "**종합 최우수** — 성장·추세·가치 전반 상위권"
    elif score >= 45:
        verdict = "**종합 우수** — 주요 축에서 고른 강점"
    elif score >= 35:
        verdict = "**종합 보통** — 일부 축 강점, 일부 약점 혼재"
    else:
        verdict = "**종합 주의** — 복수 축에서 낮은 점수"

    return f"종합점수 **{score:.1f}점** (유니버스 {rank}위) → {verdict}"


def explain_stock(code: str, df: pd.DataFrame) -> dict[str, str]:
    """종목 한 개의 4축 선별 근거 딕셔너리 반환."""
    return {
        "total": total_verdict(code, df),
        "growth": growth_reason(code, df),
        "value": value_reason(code, df),
        "quality": quality_reason(code, df),
        "trend": trend_reason(code, df),
    }
