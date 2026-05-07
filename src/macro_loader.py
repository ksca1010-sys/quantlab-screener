"""
매크로 데이터 로더: 글로벌 지표·환율·원자재·금리 수집
---
기본 지표 (API 키 불필요):
  USD/KRW 환율, WTI 원유, Gold, KOSPI, KOSDAQ, BDI(발틱건화물지수)

추가 지표 (환경변수 설정 시 자동 활성화):
  ECOS_API_KEY  → 한국은행 기준금리 (https://ecos.bok.or.kr 무료 가입)
  KOSIS_API_KEY → 건설수주통계 (https://kosis.kr 무료 가입)
"""
from __future__ import annotations

import logging
import os
import time as _time
from datetime import date, timedelta
from typing import Optional

import pandas as pd
import requests

# FIX 4: module-level TTL cache for FDR calls (1시간)
_INDICATOR_CACHE: dict[int, tuple[float, dict[str, pd.DataFrame]]] = {}
_INDICATOR_CACHE_TTL = 3600

logger = logging.getLogger(__name__)

try:
    import FinanceDataReader as fdr
    _FDR_AVAILABLE = True
except ImportError:
    fdr = None
    _FDR_AVAILABLE = False

# ── 지표 메타데이터 ────────────────────────────────────────────────────────────
INDICATORS: dict[str, dict] = {
    # 국내 지수
    "KOSPI":   {"label": "KOSPI",          "unit": "pt",      "color": "#38B26B"},
    "KOSDAQ":  {"label": "KOSDAQ",         "unit": "pt",      "color": "#6FCFCF"},
    # 글로벌 지수
    "SP500":   {"label": "S&P 500",        "unit": "pt",      "color": "#38B26B"},
    "NASDAQ":  {"label": "NASDAQ",         "unit": "pt",      "color": "#6FCFCF"},
    "DOW":     {"label": "다우존스",        "unit": "pt",      "color": "#9A9278"},
    "DAX":     {"label": "DAX (독일)",     "unit": "pt",      "color": "#F0C040"},
    "Nikkei":  {"label": "니케이 225",     "unit": "pt",      "color": "#E07030"},
    "FTSE":    {"label": "FTSE 100",       "unit": "pt",      "color": "#B8922E"},
    "HSI":     {"label": "항셍 지수",      "unit": "pt",      "color": "#E03030"},
    # 원자재
    "WTI":     {"label": "WTI 원유",       "unit": "USD/bbl", "color": "#E03030"},
    "Gold":    {"label": "금",             "unit": "USD/oz",  "color": "#B8922E"},
    "Silver":  {"label": "은",             "unit": "USD/oz",  "color": "#9A9278"},
    "Copper":  {"label": "구리",           "unit": "USD/lb",  "color": "#E07030"},
    # 채권·금리
    "US10Y":   {"label": "미국 10Y 금리",  "unit": "%",       "color": "#F0C040"},
    "US2Y":    {"label": "미국 2Y 금리",   "unit": "%",       "color": "#9A9278"},
    # 환율
    "USD/KRW": {"label": "원달러 환율",    "unit": "원",      "color": "#F0C040"},
    "EUR/USD": {"label": "유로달러",       "unit": "USD",     "color": "#6FCFCF"},
    "DXY":     {"label": "달러 인덱스",    "unit": "pt",      "color": "#B8922E"},
    # 공포
    "VIX":     {"label": "VIX (공포지수)", "unit": "pt",      "color": "#E03030"},
    # 에너지
    "NatGas":  {"label": "천연가스",       "unit": "USD",     "color": "#6FCFCF"},
    "Brent":   {"label": "브렌트유",       "unit": "USD/bbl", "color": "#E07030"},
    # 암호화폐
    "BTC":     {"label": "비트코인",       "unit": "USD",     "color": "#F0C040"},
    "ETH":     {"label": "이더리움",       "unit": "USD",     "color": "#6FCFCF"},
    # 해운
    "BDI":     {"label": "BDRY 해운 ETF",  "unit": "USD",     "color": "#70D6FF"},
}

# 카테고리별 지표 그룹
INDICATOR_CATEGORIES: dict[str, list[str]] = {
    "글로벌 지수":  ["SP500", "NASDAQ", "DOW", "DAX", "Nikkei", "FTSE", "HSI"],
    "국내 지수":    ["KOSPI", "KOSDAQ"],
    "원자재":       ["WTI", "Gold", "Silver", "Copper", "NatGas", "Brent"],
    "채권·금리":    ["US10Y", "US2Y"],
    "환율":         ["USD/KRW", "EUR/USD", "DXY"],
    "공포·해운":    ["VIX", "BDI"],
    "암호화폐":     ["BTC", "ETH"],
}

# FDR에 넘길 실제 심볼 (Yahoo Finance / 자체 소스)
_FDR_SYMBOLS: dict[str, str] = {
    # 국내
    "KOSPI":   "KS11",
    "KOSDAQ":  "KQ11",
    # 글로벌 지수 (Yahoo Finance)
    "SP500":   "^GSPC",
    "NASDAQ":  "^IXIC",
    "DOW":     "^DJI",
    "DAX":     "^GDAXI",
    "Nikkei":  "^N225",
    "FTSE":    "^FTSE",
    "HSI":     "^HSI",
    # 원자재 (Yahoo Finance 선물)
    "WTI":     "CL=F",
    "Gold":    "GC=F",
    "Silver":  "SI=F",
    "Copper":  "HG=F",
    "NatGas":  "NG=F",
    "Brent":   "BZ=F",
    # 채권·금리
    "US10Y":   "^TNX",
    "US2Y":    "^IRX",
    # 환율
    "USD/KRW": "USD/KRW",
    "EUR/USD": "EURUSD=X",
    "DXY":     "DX-Y.NYB",
    # 공포
    "VIX":     "^VIX",
    # 암호화폐
    "BTC":     "BTC-USD",
    "ETH":     "ETH-USD",
    # 해운: BDI 원지수는 공개 CSV 소스가 불안정해 BDRY ETF를 해운 운임 proxy로 사용한다.
    "BDI":     "BDRY",
}

# ── 섹터별 매크로 연관성 ──────────────────────────────────────────────────────
# (지표키, 방향성, 설명)
# 방향성: "+" = 지표 상승 → 호재,  "-" = 지표 상승 → 역풍,  "0" = 무관
SECTOR_MACRO_MAP: dict[str, list[tuple[str, str, str]]] = {
    "전기·전자":  [("USD/KRW", "+", "달러 강세 → 수출 수익 증가"),
                  ("KOSPI",   "+", "경기 순행")],
    "반도체":     [("USD/KRW", "+", "달러 매출 환산 이익"),
                  ("BDI",     "+", "교역량 증가 → 수요 선행")],
    "화학":       [("WTI",    "-", "유가 상승 → 나프타 원가 압박"),
                  ("USD/KRW", "+", "수출 수익 환차익")],
    "철강·금속":  [("BDI",    "+", "교역량 증가 → 철강 수요"),
                  ("WTI",    "-", "에너지 원가 상승")],
    "운수·창고":  [("BDI",    "+", "운임 상승 = 업황 직결"),
                  ("WTI",    "-", "연료비 증가")],
    "조선":       [("BDI",    "+", "발주 수요 선행지표"),
                  ("USD/KRW", "+", "달러 수주 환차익")],
    "건설":       [("KOSPI",  "+", "경기 순행"),
                  ("WTI",    "-", "건설 원자재 원가")],
    "의약품":     [("KOSPI",  "0", "방어주 — 매크로 비연동"),
                  ("USD/KRW", "+", "원료 수입비용 인상 명분")],
    "금융":       [("KOSPI",  "+", "경기 순행"),
                  ("USD/KRW", "-", "외화 자산 환차손")],
    "방산":       [("USD/KRW", "+", "달러 수주"),
                  ("KOSPI",  "0", "정책 연동")],
    "기계":       [("USD/KRW", "+", "수출 수익"),
                  ("BDI",    "+", "교역량 증가 → 수주 선행")],
    "음식료품":   [("WTI",    "-", "원자재·물류비 증가"),
                  ("KOSPI",  "0", "내수 방어주")],
    "서비스업":   [("KOSPI",  "+", "내수 경기 순행"),
                  ("USD/KRW", "-", "수입 비용 상승")],
}


def get_market_indicators(period_days: int = 180) -> dict[str, pd.DataFrame]:
    """
    FDR로 주요 매크로 지표 시계열 수집 (Close 컬럼만 반환).
    실패한 지표는 빈 DataFrame으로 처리 — 허수 없음.
    결과는 TTL 1시간 메모리 캐시 적용 (6개 FDR 직렬 호출 비용 절감).
    """
    now = _time.time()
    cached = _INDICATOR_CACHE.get(period_days)
    if cached is not None and now - cached[0] < _INDICATOR_CACHE_TTL:
        return cached[1]

    if not _FDR_AVAILABLE:
        logger.warning("FinanceDataReader 미설치 — 매크로 지표 수집 불가")
        return {k: pd.DataFrame() for k in _FDR_SYMBOLS}

    end   = date.today().strftime("%Y-%m-%d")
    start = (date.today() - timedelta(days=period_days)).strftime("%Y-%m-%d")

    def _fetch_one(key: str, symbol: str) -> tuple[str, pd.DataFrame]:
        try:
            df = fdr.DataReader(symbol, start, end)
            if df is None or df.empty:
                return key, pd.DataFrame()
            close_col = "Close" if "Close" in df.columns else df.columns[0]
            return key, df[[close_col]].rename(columns={close_col: "Close"})
        except Exception as e:
            logger.debug("[%s] 조회 실패 (%s): %s", key, symbol, e)
            return key, pd.DataFrame()

    # 병렬 호출 — 직렬 대비 ~5배 빠름
    from concurrent.futures import ThreadPoolExecutor, as_completed
    result: dict[str, pd.DataFrame] = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_fetch_one, k, s): k for k, s in _FDR_SYMBOLS.items()}
        for future in as_completed(futures):
            key, df = future.result()
            result[key] = df

    _INDICATOR_CACHE[period_days] = (now, result)
    return result


def get_ecos_base_rate(months: int = 36) -> pd.DataFrame:
    """
    한국은행 ECOS API로 기준금리 시계열 조회.
    ECOS_API_KEY 환경변수 필요 (https://ecos.bok.or.kr 회원가입 무료).
    미설정 시 빈 DataFrame 반환.
    """
    api_key = os.getenv("ECOS_API_KEY", "")
    if not api_key:
        return pd.DataFrame()

    end_dt   = date.today()
    start_dt = date(max(end_dt.year - (months // 12 + 1), 2000), 1, 1)
    url = (
        f"https://ecos.bok.or.kr/api/StatisticSearch/{api_key}/json/kr"
        f"/1/1000/722Y001/M/{start_dt.strftime('%Y%m')}/{end_dt.strftime('%Y%m')}"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        rows = resp.json().get("StatisticSearch", {}).get("row", [])
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        # FIX 3: explicit column detection (df.get() on DataFrame returns a column, not a scalar)
        item_col = "ITEM_CODE1" if "ITEM_CODE1" in df.columns else "item_code1" if "item_code1" in df.columns else None
        if item_col:
            filtered = df[df[item_col] == "0101000"].copy()
            # FIX 2: filter 실패 시 혼합 금리 시리즈 사용 금지 → 빈 DataFrame 반환
            if filtered.empty:
                return pd.DataFrame()
            df = filtered
        time_col  = "TIME"       if "TIME"       in df.columns else "time"
        val_col   = "DATA_VALUE" if "DATA_VALUE" in df.columns else "data_value"
        df["date"]  = pd.to_datetime(df[time_col], format="%Y%m", errors="coerce")
        df["Close"] = pd.to_numeric(df[val_col],   errors="coerce")
        return df[["date", "Close"]].dropna().set_index("date").sort_index()
    except Exception as e:
        logger.warning("ECOS 기준금리 조회 실패: %s", e)
        return pd.DataFrame()


def get_kosis_construction_orders(months: int = 24) -> pd.DataFrame:
    """
    KOSIS API로 건설수주액(계절조정) 시계열 조회 — PublicDataReader 사용.
    KOSIS_API_KEY 환경변수 필요 (https://kosis.kr 무료 가입).

    통계표: 건설수주액(계절조정) ORG_ID=101 / TBL_ID=DT_1G1B045 (통계청)
    단위: 백만원
    """
    api_key = os.getenv("KOSIS_API_KEY", "")
    if not api_key:
        return pd.DataFrame()

    try:
        from PublicDataReader import Kosis
    except ImportError:
        logger.warning("PublicDataReader 미설치 — pip install PublicDataReader")
        return pd.DataFrame()

    end_dt   = date.today()
    start_dt = date(end_dt.year - (months // 12 + 1), 1, 1)

    try:
        api = Kosis(api_key)
        df = api.get_data(
            "통계자료",
            orgId="101",
            tblId="DT_1G1B045",
            objL1="ALL",
            itmId="ALL",
            prdSe="M",
            startPrdDe=start_dt.strftime("%Y%m"),
            endPrdDe=end_dt.strftime("%Y%m"),
        )
        if df is None or df.empty:
            return pd.DataFrame()

        # 공종별=계(총합) 행만 필터
        val_col = "수치값" if "수치값" in df.columns else "DT"
        prd_col = "수록시점" if "수록시점" in df.columns else "PRD_DE"
        cls_col = next((c for c in df.columns if "분류값명" in c), None)

        # FIX 6: contains("계|Total") 은 "하계", "동계" 등 과도 매칭 → 정확한 집계 행만 선택
        if cls_col:
            df = df[df[cls_col].str.match(r"^(계|총계|합계|Total)$", na=False)]

        df = df[[prd_col, val_col]].copy()
        df["date"]  = pd.to_datetime(df[prd_col], format="%Y%m", errors="coerce")
        df["Close"] = pd.to_numeric(df[val_col], errors="coerce")
        result = df[["date", "Close"]].dropna().set_index("date").sort_index()
        # 중복 인덱스 제거
        return result[~result.index.duplicated(keep="last")]

    except Exception as e:
        logger.warning("KOSIS 건설수주 조회 실패: %s", e)
        return pd.DataFrame()


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI (지수이동평균 방식). pandas만 사용."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def compute_rebound_signals(indicators: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    각 지표에 대해 반등 가능성 신호를 계산한다.
    반환 컬럼: key | 지표 | 현재값 | 단위 | RSI14 | MA50대비 | MA200대비 | 52주낙폭 | 신호 | 신호점수
    신호: 강한 반등 후보 / 반등 후보 / 관심 / 중립 / 과매수
    """
    rows = []
    for key, df in indicators.items():
        if df.empty or "Close" not in df.columns:
            continue
        s = df["Close"].dropna()
        if len(s) < 30:
            continue

        meta = INDICATORS.get(key, {})
        current = float(s.iloc[-1])

        # RSI(14)
        rsi_series = compute_rsi(s)
        rsi = float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else None

        # MA50 / MA200
        ma50_s  = s.rolling(50,  min_periods=20).mean()
        ma200_s = s.rolling(200, min_periods=60).mean()
        ma50  = float(ma50_s.iloc[-1])  if not pd.isna(ma50_s.iloc[-1])  else None
        ma200 = float(ma200_s.iloc[-1]) if not pd.isna(ma200_s.iloc[-1]) else None

        vs_ma50  = (current / ma50  - 1) * 100 if ma50  else None
        vs_ma200 = (current / ma200 - 1) * 100 if ma200 else None

        # 52주 최고가 대비 낙폭
        window = min(252, len(s))
        high_52w = float(s.iloc[-window:].max())
        drawdown = (current / high_52w - 1) * 100 if high_52w > 0 else None

        # 황금/데드 크로스 (최근 10일 내 MA20 > MA50 전환)
        ma20_s = s.rolling(20, min_periods=10).mean()
        golden_cross = False
        if len(ma20_s) >= 11 and ma50_s is not None:
            recent20  = ma20_s.iloc[-10:]
            recent50  = ma50_s.iloc[-10:]
            was_below = (recent20.iloc[0] <= recent50.iloc[0])
            is_above  = (recent20.iloc[-1] > recent50.iloc[-1])
            golden_cross = bool(was_below and is_above)

        # 신호 점수 계산
        score = 0
        if rsi is not None:
            if rsi < 30:   score += 3   # 과매도 — 강한 반등 후보
            elif rsi < 40: score += 2
            elif rsi < 50: score += 1
            elif rsi > 70: score -= 2   # 과매수
            elif rsi > 60: score -= 1
        if drawdown is not None:
            if drawdown < -30: score += 2   # 52주 고점 대비 -30% 이하
            elif drawdown < -20: score += 1
        if vs_ma200 is not None and vs_ma200 < -15:
            score += 1   # 장기 평균 대폭 하회
        if golden_cross:
            score += 1   # 단기 반등 크로스

        if score >= 4:
            signal = "강한 반등 후보"
        elif score >= 2:
            signal = "반등 후보"
        elif score == 1:
            signal = "관심"
        elif score <= -2:
            signal = "과매수"
        else:
            signal = "중립"

        rows.append({
            "key":      key,
            "지표":     meta.get("label", key),
            "현재값":   current,
            "단위":     meta.get("unit", ""),
            "RSI14":    round(rsi, 1) if rsi is not None else None,
            "MA50대비": round(vs_ma50,  1) if vs_ma50  is not None else None,
            "MA200대비":round(vs_ma200, 1) if vs_ma200 is not None else None,
            "52주낙폭": round(drawdown, 1) if drawdown is not None else None,
            "신호":     signal,
            "신호점수": score,
        })

    return (
        pd.DataFrame(rows)
        .sort_values("신호점수", ascending=False)
        .reset_index(drop=True)
    )


def compute_sector_signals(
    indicators: dict[str, pd.DataFrame],
    lookback_days: int = 30,
) -> pd.DataFrame:
    """
    현재 매크로 환경이 각 섹터에 미치는 영향 계산.
    반환 컬럼: sector | score | signal | reasons
    score: +2(강한 호재) ~ -2(강한 역풍)
    """
    _THRESHOLD_WEAK   = 2.0   # 변화율 ±2% 미만은 노이즈로 무시
    _THRESHOLD_STRONG = 5.0   # ±5% 이상은 delta=2 (강한 신호)

    changes: dict[str, float] = {}
    for key, df in indicators.items():
        if df.empty or "Close" not in df.columns:
            continue
        s = df["Close"].dropna()
        if len(s) < 5:
            continue
        # FIX 1: 데이터 span이 lookback_days보다 짧으면 변화율 계산 불가 → 허수 방지
        if (s.index[-1] - s.index[0]).days < lookback_days:
            continue
        cutoff = s.index[-1] - pd.Timedelta(days=lookback_days)
        past = s[s.index <= cutoff]
        if past.empty:
            continue
        base = float(past.iloc[-1])
        if base == 0:
            continue
        changes[key] = float((s.iloc[-1] - base) / abs(base) * 100)

    rows = []
    for sector, signals in SECTOR_MACRO_MAP.items():
        score = 0.0
        reasons: list[str] = []
        for ind_key, direction, desc in signals:
            chg = changes.get(ind_key)
            if chg is None or direction == "0":
                continue
            label = INDICATORS.get(ind_key, {}).get("label", ind_key)
            chg_str = f"{chg:+.1f}%"
            # FIX 5: 4개 중복 분기를 부호 기반 단일 흐름으로 통합
            sign      = 1 if direction == "+" else -1
            effective = sign * chg  # 양수=호재, 음수=역풍
            if abs(effective) <= _THRESHOLD_WEAK:
                continue
            delta = 2 if abs(effective) >= _THRESHOLD_STRONG else 1
            if effective > 0:
                score += delta
                reasons.append(f"✅ {label} {chg_str} ({desc})")
            else:
                score -= delta
                reasons.append(f"⚠️ {label} {chg_str} ({desc})")

        signal_label = (
            "강한 호재" if score >= 2 else
            "호재"      if score == 1 else
            "중립"      if score == 0 else
            "역풍"      if score == -1 else
            "강한 역풍"
        )
        rows.append({
            "sector":  sector,
            "score":   int(score),
            "signal":  signal_label,
            "reasons": " | ".join(reasons) if reasons else "변동 미미 또는 데이터 부족",
        })

    return (
        pd.DataFrame(rows)
        .sort_values("score", ascending=False)
        .reset_index(drop=True)
    )


def get_indicator_summary(indicators: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    각 지표의 현재값·전일 대비·1개월 대비·3개월 대비 변화율 요약 테이블 반환.
    """
    rows = []
    for key, df in indicators.items():
        if df.empty or "Close" not in df.columns:
            continue
        s = df["Close"].dropna()
        if len(s) < 2:
            continue
        meta = INDICATORS.get(key, {})
        current = float(s.iloc[-1])

        def _pct(days: int) -> Optional[float]:
            cutoff = s.index[-1] - pd.Timedelta(days=days)
            past = s[s.index <= cutoff]
            if past.empty:
                return None
            base = float(past.iloc[-1])
            return (current - base) / abs(base) * 100 if base != 0 else None

        rows.append({
            "지표":      meta.get("label", key),
            "현재값":    current,
            "단위":      meta.get("unit", ""),
            "1일 변화":  _pct(1),
            "1개월 변화": _pct(30),
            "3개월 변화": _pct(90),
        })
    return pd.DataFrame(rows)


def get_all_macro(period_days: int = 180) -> dict:
    """대시보드용 단일 진입점 — 모든 매크로 데이터를 dict로 반환."""
    indicators      = get_market_indicators(period_days)
    base_rate       = get_ecos_base_rate()
    construction    = get_kosis_construction_orders()
    sector_signals  = compute_sector_signals(indicators)
    rebound_signals = compute_rebound_signals(indicators)
    summary         = get_indicator_summary(indicators)
    return {
        "indicators":      indicators,
        "base_rate":       base_rate,
        "construction":    construction,
        "sector_signals":  sector_signals,
        "rebound_signals": rebound_signals,
        "summary":         summary,
    }
