"""
QuantLab Screener Dashboard
실행: streamlit run dashboard/app.py
"""
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.explainer import explain_stock
from src.analyst import fetch_consensus, fetch_current_price, fetch_report_titles, fetch_company_info

st.set_page_config(
    page_title="QuantLab Screener",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",  # CSS로 항상 강제 표시
)

CSV_PATH = Path(__file__).parent.parent / "output" / "stocks_top100.csv"

AXES = ["Growth", "Value", "Quality", "Trend"]
AXIS_LABELS = {"Growth": "성장", "Value": "가치", "Quality": "펀더멘털", "Trend": "추세", "Risk": "리스크"}
AXIS_COLORS = {
    "Growth":  "#38B26B",   # terminal green
    "Value":   "#6FCFCF",   # terminal cyan
    "Quality": "#F0C040",   # terminal amber
    "Trend":   "#9A9278",   # terminal text-base
    "Risk":    "#E03030",   # terminal red
    "Total":   "#B8922E",   # amber-dim
}
AXIS_TOOLTIPS = {
    "Growth":  "YoY 매출성장률·영업이익성장률·EPS CAGR (DART 공시 기반). 데이터 없으면 0점.",
    "Value":   "PER·PBR 업종 내 백분위 + PEG + 배당수익률 (Naver Finance). 데이터 없으면 0점.",
    "Quality": "ROE·영업이익률·부채비율·이자보상배율 (DART). 자본잠식 종목 NaN → 0점.",
    "Trend":   "MA 갭 연속 강도·52주 신고가 위치·거래량 추세·12-1개월 모멘텀 (가격 데이터).",
    "Risk":    "낮은 위험 = 높은 점수. 시장 베타·연환산 변동성·52주 최대낙폭(MDD) 역전 스케일링.",
}
REQUIRED_COLS = ["name", "code", "market", "sector"] + AXES + ["Total"]

# Design: Grade colors — accessible contrast, no emoji
GRADE_CONFIG = {
    "최우수": {"bg": "#1A3A20", "text": "#38B26B", "border": "#1E6B40", "label": "최우수"},
    "우수":   {"bg": "#162030", "text": "#6FCFCF", "border": "#2A5060", "label": "우수"},
    "보통":   {"bg": "#2A1A00", "text": "#F0C040", "border": "#B8922E", "label": "보통"},
    "관찰":   {"bg": "#2A0A0A", "text": "#E03030", "border": "#9B2020", "label": "관찰"},
}

# Design: shared Plotly layout token
PLOTLY_BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="-apple-system, 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif", size=11),
    margin=dict(l=36, r=12, t=36, b=28),
    height=300,
)

BENCHMARK_PLATFORMS = [
    {"name": "FnGuide", "url": "fnguide.com", "feature": "기관 전용 재무/추정 데이터, 컨센서스"},
    {"name": "KRX 정보데이터시스템", "url": "data.krx.co.kr", "feature": "거래소 공식 시장/재무 데이터"},
    {"name": "증권플러스 (두나무)", "url": "stockplus.com", "feature": "개인 투자자용 퀀트 스크리너, 스크리닝 조건 저장"},
    {"name": "에프앤가이드 QuizScore", "url": "fnguide.com/fisis", "feature": "종목 평가 스코어카드, 재무 품질 레이팅"},
    {"name": "씽크풀", "url": "thinkpool.com", "feature": "퀀트 분석 + 커뮤니티 통합, 기술적 분석"},
    {"name": "토스증권 스탁스크리너", "url": "tossinvest.com", "feature": "간편 필터 UI, 모바일 최적화"},
    {"name": "Wisefn", "url": "wisefn.com", "feature": "FnGuide 계열 개인용, 재무비율 멀티팩터"},
    {"name": "Simplywall.st", "url": "simplywall.st", "feature": "글로벌 스노우플레이크 레이더 차트, 직관적 시각화"},
    {"name": "Finviz (글로벌)", "url": "finviz.com", "feature": "멀티팩터 스크리너, 히트맵 시각화의 글로벌 표준"},
    {"name": "Stock Analysis (글로벌)", "url": "stockanalysis.com", "feature": "깔끔한 재무 테이블, AI 요약 코멘트"},
]


_WATCHLIST_PATH = Path(__file__).parent.parent / "output" / "watchlist.json"


def _load_watchlist() -> list[str]:
    """관심 종목을 파일에서 불러온다 (없으면 빈 리스트)."""
    import json
    try:
        if _WATCHLIST_PATH.exists():
            with _WATCHLIST_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
                return [str(c) for c in data] if isinstance(data, list) else []
    except Exception:
        pass
    return []


def _save_watchlist(codes: list[str]) -> None:
    """관심 종목을 파일에 저장."""
    import json
    try:
        _WATCHLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _WATCHLIST_PATH.open("w", encoding="utf-8") as f:
            json.dump(codes, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.warning(f"관심 종목 저장 실패: {e}")


# ── 세션 상태 초기화 ──────────────────────────────────────────────────────────
def _init_session_state() -> None:
    defaults = {
        "search_query": "",
        "selected_compare": "없음",
        "watchlist": _load_watchlist(),
        "tab2_search": "",
        "selected_code": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ── CSS 주입 (Design) ─────────────────────────────────────────────────────────
def _inject_css() -> None:
    st.markdown("""
<style>
/* 시스템 폰트 사용 — CDN 제거로 렌더 속도 개선 */

/* ── Streamlit 기본 UI 제거 ── */
#MainMenu { visibility: hidden; }
[data-testid="stToolbar"] { display: none !important; }
[data-testid="stHeader"] { background: transparent !important; height: 0 !important; min-height: 0 !important; overflow: hidden !important; }
footer { visibility: hidden; }

/* ── 사이드바 항상 표시 (분할화면·좁은 뷰포트 대응) ── */
section[data-testid="stSidebar"] {
  transform: translateX(0) !important;
  display: flex !important;
  visibility: visible !important;
  min-width: 200px !important;
  max-width: 260px !important;
}
/* 접기 버튼 숨김 (좁은 화면에서 헷갈림 방지) */
[data-testid="stSidebarCollapseButton"],
[data-testid="collapsedControl"] {
  display: none !important;
}

/* ── CSS Variables ── */
:root {
  --bg-root:    #0A0A0A;
  --bg-panel:   #111111;
  --bg-header:  #161616;
  --border:     #2A2A2A;
  --border-hi:  #3A3A3A;
  --amber:      #F0C040;
  --amber-dim:  #B8922E;
  --amber-glow: rgba(240,192,64,0.10);
  --red:        #E03030;
  --green:      #38B26B;
  --green-dim:  #1E6B40;
  --cyan:       #6FCFCF;
  --text-hi:    #E8E0CC;
  --text-base:  #9A9278;
  --text-dim:   #4A4438;
  --text-label: #6A6050;
  --mono:       'Menlo', 'Consolas', 'Monaco', monospace;
  --sans:       'Noto Sans KR', sans-serif;
  /* legacy compat */
  --bg-card:      rgba(255,255,255,0.03);
  --bg-inset:     rgba(0,0,0,0.15);
  --border-subtle: #2A2A2A;
  --text-muted:   #6A6050;
  --track-bg:     #1A1A1A;
  --accent:       #F0C040;
}

/* ── Global ── */
.stApp {
  background: var(--bg-root) !important;
  font-family: var(--mono) !important;
}
.stMarkdown, [data-testid="stMetricLabel"],
[data-testid="stMetricValue"], [data-testid="stMetricDelta"] {
  font-family: var(--mono) !important;
}
.stMarkdown p, .stMarkdown li {
  font-family: var(--sans) !important;
  line-height: 1.5;
  word-break: keep-all;
  overflow-wrap: break-word;
  color: var(--text-base);
}
h1, h2, h3 {
  font-family: var(--mono) !important;
  color: var(--text-hi) !important;
  letter-spacing: 0.05em;
}

/* ── 상단 여백 ── */
.block-container,
[data-testid="stMainBlockContainer"] {
  padding-top: 1rem !important;
  max-width: 100% !important;
  background: var(--bg-root) !important;
}

/* ── 탭 바 완전 숨김 ── */
.stTabs [data-baseweb="tab-list"],
.stTabs [data-baseweb="tab-list"]::-webkit-scrollbar,
[data-testid="stTabs"] > div:first-child,
div[role="tablist"] {
  display: none !important;
}

/* ── 메트릭 카드 ── */
[data-testid="stMetric"] {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 2px;
  padding: 10px 14px !important;
}
[data-testid="stMetricLabel"] {
  font-size: 0.68rem !important;
  font-weight: 700 !important;
  letter-spacing: 0.1em !important;
  text-transform: uppercase !important;
  color: var(--text-label) !important;
}
[data-testid="stMetricValue"] {
  font-size: 1.4rem !important;
  font-weight: 600 !important;
  color: var(--amber) !important;
  font-family: var(--mono) !important;
}
[data-testid="stMetricDelta"] svg { display: none; }

/* ── 사이드바 ── */
section[data-testid="stSidebar"] {
  background: #050505 !important;
  border-right: 1px solid var(--border) !important;
}
section[data-testid="stSidebar"] .stSelectbox label,
section[data-testid="stSidebar"] .stSlider label {
  font-size: 0.68rem !important;
  color: var(--text-label) !important;
  font-weight: 700 !important;
  text-transform: uppercase !important;
  letter-spacing: 0.1em !important;
  font-family: var(--mono) !important;
}

/* ── 사이드바 라디오 메뉴 ── */
section[data-testid="stSidebar"] div[data-testid="stRadio"] > label {
  display: none !important;
}
section[data-testid="stSidebar"] div[data-testid="stRadio"] [role="radiogroup"] {
  gap: 4px !important;
}
section[data-testid="stSidebar"] div[data-testid="stRadio"] label {
  padding: 6px 10px !important;
  border-radius: 3px !important;
  border: 1px solid transparent !important;
  transition: background 0.12s, border-color 0.12s !important;
  cursor: pointer !important;
}
section[data-testid="stSidebar"] div[data-testid="stRadio"] label:hover {
  background: rgba(240,192,64,0.05) !important;
  border-color: #2A2A2A !important;
}
section[data-testid="stSidebar"] div[data-testid="stRadio"] label p {
  font-size: 0.95rem !important;
  font-weight: 500 !important;
  color: #9A9278 !important;
  font-family: var(--mono) !important;
  text-transform: none !important;
  letter-spacing: 0 !important;
  margin: 0 !important;
}
section[data-testid="stSidebar"] div[data-testid="stRadio"] label:hover p {
  color: #E8E0CC !important;
}
section[data-testid="stSidebar"] div[data-testid="stRadio"] label:has(input:checked) {
  background: rgba(240,192,64,0.10) !important;
  border-color: #B8922E !important;
}
section[data-testid="stSidebar"] div[data-testid="stRadio"] label:has(input:checked) p {
  color: #F0C040 !important;
  font-weight: 700 !important;
}
/* 라디오 원형 아이콘 숨기기 (골드박스로만 선택 표시) */
section[data-testid="stSidebar"] div[data-testid="stRadio"] label [data-baseweb="radio"],
section[data-testid="stSidebar"] div[data-testid="stRadio"] label > div:first-child {
  display: none !important;
}
section[data-testid="stSidebar"] [data-baseweb="select"] > div {
  background: #0A0A0A !important;
  border: 1px solid var(--border-hi) !important;
  border-radius: 2px !important;
  color: var(--text-base) !important;
  font-family: var(--mono) !important;
  font-size: 0.8rem !important;
}
section[data-testid="stSidebar"] [data-baseweb="select"] > div:focus-within {
  border-color: var(--amber-dim) !important;
}

/* ── 버튼 ── */
.stButton > button {
  border-radius: 2px !important;
  font-size: 0.75rem !important;
  font-weight: 700 !important;
  letter-spacing: 0.08em !important;
  text-transform: uppercase !important;
  font-family: var(--mono) !important;
  min-height: 36px !important;
  border: 1px solid var(--border-hi) !important;
  background: var(--bg-panel) !important;
  color: var(--text-base) !important;
  transition: border-color 0.1s, color 0.1s !important;
}
.stButton > button:hover {
  border-color: var(--amber-dim) !important;
  color: var(--amber) !important;
}
.stButton > button[kind="primary"] {
  background: var(--amber) !important;
  color: #000 !important;
  border-color: var(--amber) !important;
  font-weight: 700 !important;
}

/* ── 데이터프레임 ── */
[data-testid="stDataFrame"] {
  border: 1px solid var(--border) !important;
  border-radius: 0 !important;
}
[data-testid="stDataFrame"] th {
  background: var(--bg-header) !important;
  font-weight: 700 !important;
  font-size: 0.7rem !important;
  letter-spacing: 0.08em !important;
  text-transform: uppercase !important;
  color: var(--text-label) !important;
  font-family: var(--mono) !important;
  border-bottom: 2px solid var(--amber-dim) !important;
}

/* ── Expander ── */
[data-testid="stExpander"] {
  border: 1px solid var(--border) !important;
  border-radius: 2px !important;
  background: var(--bg-panel) !important;
}
[data-testid="stExpander"] summary {
  font-family: var(--mono) !important;
  font-size: 0.75rem !important;
  font-weight: 700 !important;
  letter-spacing: 0.08em !important;
  text-transform: uppercase !important;
  color: var(--text-base) !important;
}

/* ── 입력 필드 ── */
[data-testid="stTextInput"] input {
  background: #0A0A0A !important;
  border: 1px solid var(--border-hi) !important;
  border-radius: 2px !important;
  color: var(--text-hi) !important;
  font-family: var(--mono) !important;
  font-size: 0.8rem !important;
}
[data-testid="stTextInput"] input:focus {
  border-color: var(--amber-dim) !important;
  box-shadow: 0 0 0 1px var(--amber-dim) !important;
}

/* ── 다운로드 버튼 ── */
[data-testid="stDownloadButton"] button {
  border-radius: 2px !important;
  font-family: var(--mono) !important;
  font-size: 0.7rem !important;
  font-weight: 700 !important;
  letter-spacing: 0.08em !important;
  text-transform: uppercase !important;
  border: 1px solid var(--border-hi) !important;
  background: var(--bg-panel) !important;
  color: var(--text-base) !important;
}

/* ── 섹터 강도 툴팁 ── */
.ql-sector-row { position: relative; cursor: default; }
.ql-sector-tooltip {
  display: none;
  position: absolute;
  left: 0; top: 100%;
  z-index: 9999;
  background: var(--bg-header);
  border: 1px solid var(--border-hi);
  border-radius: 2px;
  padding: 8px 12px;
  min-width: 200px;
  font-size: 0.75rem;
  font-family: var(--mono);
  white-space: nowrap;
  box-shadow: 0 4px 20px rgba(0,0,0,0.7);
  pointer-events: none;
}
.ql-sector-row:hover .ql-sector-tooltip { display: block; }
.ql-tt-row { display: flex; justify-content: space-between; gap: 16px; padding: 2px 0; }
.ql-tt-name { color: var(--text-base); }
.ql-tt-ret { font-weight: 700; }

/* ── 모바일 카드 ── */
.ql-card-list { display: none; }
@media (max-width: 768px) {
  .ql-card-list { display: block; }
  .block-container, [data-testid="stMainBlockContainer"] {
    padding-top: 0.5rem !important;
    padding-left: 0.75rem !important;
    padding-right: 0.75rem !important;
  }
  section[data-testid="stSidebar"] { width: 85vw !important; min-width: 0 !important; }
  .stTabs [data-baseweb="tab"] { padding: 0 8px; font-size: 0.65rem; }
  [data-testid="stMetric"] { padding: 6px 8px !important; }
  .sidebar-sector-strength { display: none !important; }
  .sidebar-brand { display: none !important; }
}
@media (max-width: 480px) {
  div[data-testid="stDialog"] > div {
    width: 100vw !important; max-width: 100vw !important;
    margin: 0 !important; border-radius: 0 !important;
    padding: 0.75rem !important;
  }
  [data-testid="stHorizontalBlock"] { flex-direction: column !important; }
  [data-testid="stHorizontalBlock"] > [data-testid="stVerticalBlockBorderWrapper"],
  [data-testid="stHorizontalBlock"] > div[class*="stColumn"] {
    width: 100% !important; flex: none !important; min-width: 100% !important;
  }
  .stTabs [data-baseweb="tab"] { padding: 0 5px; font-size: 0.6rem; }
  div[data-testid="stHorizontalBlock"] button[kind="tertiary"] {
    min-height: 44px !important; padding: 10px 4px !important;
    font-size: 0.875rem !important; white-space: normal !important;
  }
}

.ql-card {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 2px;
  padding: 10px 12px;
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.ql-card-rank { font-size: 0.7rem; color: var(--text-dim); min-width: 22px; text-align: center; }
.ql-card-body { flex: 1; min-width: 0; }
.ql-card-name {
  font-size: 0.9rem; font-weight: 600; color: var(--amber);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  font-family: var(--sans) !important;
}
.ql-card-sub { font-size: 0.72rem; color: var(--text-label); margin-top: 2px; display: flex; align-items: center; gap: 6px; }
.ql-card-right { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; }
.ql-card-score { font-size: 1.05rem; font-weight: 700; color: var(--text-hi); }
.ql-grade-badge {
  font-size: 0.65rem; font-weight: 700; color: #000;
  padding: 1px 6px; border-radius: 1px; white-space: nowrap;
  font-family: var(--mono) !important; letter-spacing: 0.06em;
}
.ql-bull-badge {
  font-size: 0.65rem; font-weight: 700; color: var(--green);
  background: rgba(56,178,107,0.15); border: 1px solid var(--green-dim);
  padding: 1px 6px; border-radius: 1px; white-space: nowrap;
}
</style>
""", unsafe_allow_html=True)


# ── 데이터 로드 ───────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_data() -> pd.DataFrame:
    if not CSV_PATH.exists():
        return pd.DataFrame()
    df = pd.read_csv(CSV_PATH, index_col=0)

    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        st.error(f"CSV 필수 컬럼 누락: {missing} — python -m src.main 재실행 필요")
        return pd.DataFrame()

    for col in AXES + ["Total"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    # Korean stock codes have leading zeros (005930); zfill(6) restores them after int64 parsing
    df["code"] = df["code"].astype(str).str.zfill(6)
    if "entry_signal" in df.columns:
        df["entry_signal"] = df["entry_signal"].replace({"매수유망": "강세후보"})

    df = df.reset_index(drop=True)
    df.index = df.index + 1
    df.index.name = "rank"
    return df


@st.cache_data(ttl=3600)
def _get_company_info(code: str, name: str) -> dict:
    try:
        return fetch_company_info(code, name)
    except Exception:
        return {}


def _last_updated() -> str:
    if CSV_PATH.exists():
        mtime = CSV_PATH.stat().st_mtime
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
    return "알 수 없음"


def _last_updated_relative() -> str:
    """파일 수정시각 대비 경과시간을 한국어로 반환 (예: '3시간 전')."""
    if not CSV_PATH.exists():
        return "데이터 없음"
    mtime = CSV_PATH.stat().st_mtime
    delta = datetime.now().timestamp() - mtime
    if delta < 60:
        return "방금 전"
    if delta < 3600:
        return f"{int(delta // 60)}분 전"
    if delta < 86400:
        return f"{int(delta // 3600)}시간 전"
    days = int(delta // 86400)
    if days < 30:
        return f"{days}일 전"
    return f"{days // 30}개월 전"


# ── 분석등급 (분위 기반 동적 임계값 — 전문가 패널 #3) ──────────────────────────
def investment_grade(score: float, thresholds: tuple[float, float, float] = (60, 50, 40)) -> str:
    t1, t2, t3 = thresholds
    if score >= t1:
        return "최우수"
    elif score >= t2:
        return "우수"
    elif score >= t3:
        return "보통"
    return "관찰"


def grade_badge_html(score: float, thresholds: tuple[float, float, float] = (60, 50, 40)) -> str:
    label = investment_grade(score, thresholds)
    cfg = GRADE_CONFIG[label]
    return (
        f'<span style="background:{cfg["bg"]};color:{cfg["text"]};'
        f'border:1px solid {cfg["border"]};padding:4px 12px;border-radius:2px;'
        f'font-size:0.75rem;font-weight:700;letter-spacing:0.08em;'
        f'font-family:monospace;text-transform:uppercase;">{label}</span>'
    )


def compute_grade_thresholds(df: pd.DataFrame) -> tuple[float, float, float]:
    """유니버스 분위 기반 동적 등급 임계값 (상위20%/50%/80%)."""
    return (
        float(df["Total"].quantile(0.80)),
        float(df["Total"].quantile(0.50)),
        float(df["Total"].quantile(0.20)),
    )


def data_quality_label(row: pd.Series) -> str:
    """축별 실데이터 비율 표시 (0점 = 데이터 미확보). 4축 기준."""
    real = sum([
        row["Growth"] > 0,
        row["Value"] > 0,
        row["Quality"] > 0,
        True,  # Trend 항상 유효 (가격 데이터)
    ])
    return {4: "●●●●", 3: "●●●○", 2: "●●○○", 1: "●○○○"}.get(real, "????")


# ── 차트 헬퍼 ─────────────────────────────────────────────────────────────────
def radar_chart(
    row: pd.Series,
    name: str,
    row2: pd.Series | None = None,
    name2: str | None = None,
) -> go.Figure:
    cats = [AXIS_LABELS[a] for a in AXES] + [AXIS_LABELS[AXES[0]]]
    vals = [float(row[a]) for a in AXES] + [float(row[AXES[0]])]

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=vals, theta=cats, fill="toself",
        fillcolor="rgba(240,192,64,0.12)",
        line=dict(color="#F0C040", width=1.5),
        name=name,
    ))

    if row2 is not None and name2:
        vals2 = [float(row2[a]) for a in AXES] + [float(row2[AXES[0]])]
        fig.add_trace(go.Scatterpolar(
            r=vals2, theta=cats, fill="toself",
            fillcolor="rgba(224,48,48,0.15)",
            line=dict(color="#E03030", width=1.5, dash="dash"),
            name=name2,
        ))

    # Design: transparent backgrounds, Korean font, readable gridlines
    fig.update_layout(
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(
                visible=True, range=[0, 100],
                tickfont=dict(size=8, color="rgba(150,150,150,0.7)"),
                gridcolor="rgba(150,150,150,0.15)",
            ),
            angularaxis=dict(
                tickfont=dict(size=9),
                gridcolor="rgba(150,150,150,0.2)",
            ),
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="-apple-system, 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif"),
        showlegend=row2 is not None,
        margin=dict(l=10, r=10, t=30, b=10),
        height=280,
    )
    return fig


def score_bar(value: float, color: str, max_val: float = 100) -> str:
    """Design: animated glow bar. UX: ARIA attributes for accessibility."""
    pct = min(value / max_val * 100, 100)
    return (
        f'<div role="progressbar" aria-valuenow="{value:.0f}" '
        f'aria-valuemin="0" aria-valuemax="{max_val:.0f}" aria-label="점수 {value:.0f}점" '
        f'style="background:#1A1A1A;border-radius:0;height:14px;width:100%;overflow:hidden;">'
        f'<div style="background:{color};height:14px;border-radius:0;'
        f'width:{pct:.0f}%;transition:width 0.4s ease;'
        f'box-shadow:0 0 8px {color}55;"></div>'
        f'</div>'
    )


def color_score(val: float) -> str:
    if val >= 60:
        return "🟢"
    elif val >= 40:
        return "🔵"
    elif val >= 20:
        return "🟡"
    return "🔴"


# ── 시장 코멘트 (dynamic, data-driven) ───────────────────────────────────────
def market_commentary(df: pd.DataFrame) -> str:
    if df.empty:
        return ""
    ref_date = _last_updated()
    top5 = df.nlargest(5, "Total")
    top_names = ", ".join(top5["name"].tolist())
    avg_total   = df["Total"].mean()
    avg_growth  = df["Growth"].mean()
    avg_value   = df["Value"].mean()
    avg_quality = df["Quality"].mean()
    avg_trend   = df["Trend"].mean()
    avg_risk    = df["Risk"].mean() if "Risk" in df.columns else 0.0
    strong_count = (df["Total"] >= 60).sum()
    good_count   = ((df["Total"] >= 50) & (df["Total"] < 60)).sum()
    # 실데이터 있는 종목 비율 (0점 = 미확보)
    value_ok_pct   = (df["Value"] > 0).mean() * 100
    quality_ok_pct = (df["Quality"] > 0).mean() * 100

    lines = [
        f"**기준일: {ref_date}** | 유니버스 {len(df)}개 종목 분석",
        "",
        f"| 축 | 평균점수 |",
        f"|---|---|",
        f"| 종합 | **{avg_total:.1f}점** |",
        f"| 성장 | **{avg_growth:.1f}점** |",
        f"| 가치 | **{avg_value:.1f}점** |",
        f"| 펀더멘털 | **{avg_quality:.1f}점** |",
        f"| 추세 | **{avg_trend:.1f}점** |",
        *([f"| 리스크(보조) | **{avg_risk:.1f}점** |"] if "Risk" in df.columns else []),
        "",
        f"- 최우수 등급 **{strong_count}개**, 우수 등급 **{good_count}개**",
        f"- Value 데이터 확보율: **{value_ok_pct:.0f}%** | Quality 확보율: **{quality_ok_pct:.0f}%** (pykrx·DART 제공 기준)",
        f"- **종합 TOP 5**: {top_names}",
        "",
        "⚠️ 본 통계는 자동 생성 데이터이며 시황 판단을 포함하지 않습니다. "
        "공시 기준: 분석 시점 t-45일 이전 게재 공시만 반영됩니다.",
    ]
    return "\n".join(lines)


# ── 애널리스트 데이터 (캐시) ──────────────────────────────────────────────────
@st.cache_data(ttl=1800, show_spinner=False)
def _get_analyst_data(code: str) -> tuple:
    consensus = fetch_consensus(code)
    reports = fetch_report_titles(code)
    return consensus, reports


@st.cache_data(ttl=600, show_spinner=False)
def _get_current_price(code: str):
    return fetch_current_price(code)


@st.cache_data(ttl=3600, show_spinner=False)
def _get_price_history(code: str) -> pd.DataFrame:
    from src.data_loader import get_price_data
    end   = pd.Timestamp.today().strftime("%Y-%m-%d")
    start = (pd.Timestamp.today() - pd.DateOffset(days=380)).strftime("%Y-%m-%d")
    return get_price_data(code, start, end)


@st.cache_data(ttl=86400, show_spinner=False)
def _get_financial_statement_review(code: str) -> dict:
    from src.financial_analysis import get_financial_statement_review
    as_of_date = pd.Timestamp.today().strftime("%Y-%m-%d")
    return get_financial_statement_review(code, as_of_date)


_SECTOR_CACHE_PATH = Path(__file__).parent.parent / "output" / ".sector_strength_cache.json"
_SECTOR_CACHE_TTL  = 1800  # 30분


def _load_sector_cache() -> dict | None:
    """디스크 캐시에서 섹터 강도 데이터 로드 (TTL 30분)."""
    import json, time
    try:
        if not _SECTOR_CACHE_PATH.exists():
            return None
        if time.time() - _SECTOR_CACHE_PATH.stat().st_mtime > _SECTOR_CACHE_TTL:
            return None
        with _SECTOR_CACHE_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_sector_cache(data: dict) -> None:
    """섹터 강도 데이터를 디스크에 저장."""
    import json
    try:
        _SECTOR_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _SECTOR_CACHE_PATH.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass


@st.cache_data(ttl=1800, show_spinner=False)
def _compute_sector_strength(sector_nc_frozen: tuple) -> dict:
    """섹터별 최근 5일(1주) 수익률 계산 → 중앙값 기준 bull/bear 자동 분류.
    TTL=1800초(30분) + 디스크 캐시 (서버 재기동에도 유지).
    sector_nc_frozen: ((섹터명, ((name1,code1), ...)), ...) 해시 가능 튜플.
    """
    # 1) 디스크 캐시 먼저 확인 (서버 재기동 후 첫 진입 가속)
    disk_cached = _load_sector_cache()
    if disk_cached is not None:
        return disk_cached

    from concurrent.futures import ThreadPoolExecutor, as_completed
    from src.data_loader import get_price_data
    end   = pd.Timestamp.today().strftime("%Y-%m-%d")
    start = (pd.Timestamp.today() - pd.DateOffset(days=20)).strftime("%Y-%m-%d")

    # 1) 전체 (sector, name, code) 평탄화
    flat: list[tuple[str, str, str]] = [
        (sector, name, code)
        for sector, ncs in sector_nc_frozen
        for name, code in ncs
    ]

    def _one(item: tuple[str, str, str]) -> tuple[str, str, float] | None:
        sector, name, code = item
        try:
            pdata = get_price_data(code, start, end)
            if pdata.empty or "Close" not in pdata.columns or len(pdata) < 5:
                return None
            ret = (pdata["Close"].iloc[-1] / pdata["Close"].iloc[-5] - 1) * 100
            return sector, name, round(float(ret), 2)
        except Exception:
            return None

    # 2) 병렬 호출 (12 workers 권장)
    sector_buckets: dict[str, list[tuple[str, float]]] = {}
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = [executor.submit(_one, it) for it in flat]
        for fut in as_completed(futures):
            res = fut.result()
            if res is None:
                continue
            sector, name, ret = res
            sector_buckets.setdefault(sector, []).append((name, ret))

    sector_returns: dict[str, float] = {}
    sector_top:     dict[str, list]  = {}
    for sector, stock_rets in sector_buckets.items():
        if not stock_rets:
            continue
        vals = [r for _, r in stock_rets]
        sector_returns[sector] = round(float(pd.Series(vals).median()), 2)
        sector_top[sector] = sorted(stock_rets, key=lambda x: x[1], reverse=True)[:5]

    if not sector_returns:
        empty = {"sector_returns": {}, "bull_sectors": [], "median_return": 0.0, "sector_top": {}}
        return empty

    median_ret = float(pd.Series(list(sector_returns.values())).median())
    bull_sectors = [s for s, r in sector_returns.items() if r > median_ret]

    result = {
        "sector_returns": sector_returns,
        "bull_sectors":   bull_sectors,
        "median_return":  round(median_ret, 2),
        "sector_top":     sector_top,
    }
    _save_sector_cache(result)
    return result


def _price_chart(price_df: pd.DataFrame, name: str) -> "go.Figure | None":
    """1년 주가 라인차트 + MA20/60/120 + 52주 고저 + 거래량 + 추세 특이사항 마커."""
    if price_df.empty or "Close" not in price_df.columns:
        return None
    if not isinstance(price_df.index, pd.DatetimeIndex):
        return None
    from plotly.subplots import make_subplots
    df = price_df.copy()
    df["MA20"]  = df["Close"].rolling(20).mean()
    df["MA60"]  = df["Close"].rolling(60).mean()
    df["MA120"] = df["Close"].rolling(120).mean()
    w52_high = float(df["Close"].max())
    w52_low  = float(df["Close"].min())

    # ── Trend 지표 계산 ──────────────────────────────────────────────
    last_ma20  = float(df["MA20"].dropna().iloc[-1])  if df["MA20"].notna().any() else None
    last_ma60  = float(df["MA60"].dropna().iloc[-1])  if df["MA60"].notna().any() else None
    last_ma120 = float(df["MA120"].dropna().iloc[-1]) if df["MA120"].notna().any() else None
    is_aligned = (
        last_ma20 is not None and last_ma60 is not None and last_ma120 is not None
        and last_ma20 > last_ma60 > last_ma120
    )
    gap_short = (last_ma20 / last_ma60 - 1) * 100 if (last_ma20 is not None and last_ma60 is not None and last_ma60 != 0) else 0.0
    gap_long  = (last_ma60 / last_ma120 - 1) * 100 if (last_ma60 is not None and last_ma120 is not None and last_ma120 != 0) else 0.0

    # 52주 위치
    w52_pos = (float(df["Close"].iloc[-1]) / w52_high * 100) if w52_high > 0 else 0.0

    # 황금교차 / 데드교차
    gc_mask = (df["MA20"] > df["MA60"]) & (df["MA20"].shift(1) <= df["MA60"].shift(1))
    dc_mask = (df["MA20"] < df["MA60"]) & (df["MA20"].shift(1) >= df["MA60"].shift(1))
    gc_df = df[gc_mask.fillna(False)]
    dc_df = df[dc_mask.fillna(False)]

    has_vol = "Volume" in df.columns and df["Volume"].sum() > 0

    # 거래량 추세
    vol_ratio: float | None = None
    if has_vol and len(df) >= 80:
        avg20 = float(df["Volume"].iloc[-20:].mean())
        avg60 = float(df["Volume"].iloc[-80:-20].mean())
        vol_ratio = avg20 / avg60 if avg60 > 0 else None

    # 12-1개월 모멘텀
    momentum: float | None = None
    if len(df) >= 252:
        p_start = float(df["Close"].iloc[-252])
        p_end   = float(df["Close"].iloc[-21])
        if p_start > 0:
            momentum = (p_end - p_start) / p_start * 100

    rows    = 2 if has_vol else 1
    heights = [0.72, 0.28] if has_vol else [1.0]

    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True,
                        row_heights=heights, vertical_spacing=0.03)

    # ── 종가 + MA ─────────────────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=df.index, y=df["Close"], name="종가",
        line=dict(color="#F0C040", width=2),
        hovertemplate="%{x|%Y-%m-%d}<br>종가: %{y:,.0f}원<extra></extra>",
    ), row=1, col=1)

    for ma, color in [("MA20", "#FF8C00"), ("MA60", "#6FCFCF"), ("MA120", "#E03030")]:
        fig.add_trace(go.Scatter(
            x=df.index, y=df[ma], name=ma,
            line=dict(color=color, width=1, dash="dot"),
            hovertemplate=f"{ma}: %{{y:,.0f}}원<extra></extra>",
        ), row=1, col=1)

    # ── 52주 고저 ────────────────────────────────────────────────────
    fig.add_hline(y=w52_high, line_dash="dash", line_color="rgba(0,200,83,0.55)",
                  annotation_text=f"52H {w52_high:,.0f}",
                  annotation_position="top left", row=1, col=1)
    fig.add_hline(y=w52_low, line_dash="dash", line_color="rgba(229,57,53,0.55)",
                  annotation_text=f"52L {w52_low:,.0f}",
                  annotation_position="bottom left", row=1, col=1)

    # ── 황금교차 / 데드교차 마커 ─────────────────────────────────────────
    if not gc_df.empty:
        fig.add_trace(go.Scatter(
            x=gc_df.index, y=gc_df["MA20"],
            mode="markers", name="황금교차",
            marker=dict(symbol="triangle-up", size=12, color="#38B26B",
                        line=dict(color="#E8E0CC", width=1)),
            hovertemplate="🟢 황금교차<br>%{x|%Y-%m-%d}<extra></extra>",
        ), row=1, col=1)
    if not dc_df.empty:
        fig.add_trace(go.Scatter(
            x=dc_df.index, y=dc_df["MA20"],
            mode="markers", name="데드교차",
            marker=dict(symbol="triangle-down", size=12, color="#E03030",
                        line=dict(color="#E8E0CC", width=1)),
            hovertemplate="🔴 데드교차<br>%{x|%Y-%m-%d}<extra></extra>",
        ), row=1, col=1)

    # ── 거래량 + 거래량 MA20 + 급증 마커 ─────────────────────────────────
    if has_vol:
        closes = df["Close"].values
        vcol = ["#ef5350" if i > 0 and closes[i] < closes[i - 1] else "#26a69a"
                for i in range(len(closes))]
        fig.add_trace(go.Bar(
            x=df.index, y=df["Volume"], name="거래량",
            marker_color=vcol, showlegend=False,
            hovertemplate="거래량: %{y:,.0f}<extra></extra>",
        ), row=2, col=1)

        df["VolMA20"] = df["Volume"].rolling(20).mean()
        fig.add_trace(go.Scatter(
            x=df.index, y=df["VolMA20"], name="거래량MA20",
            line=dict(color="#F0C040", width=1, dash="dot"),
            showlegend=False,
            hovertemplate="거래량MA20: %{y:,.0f}<extra></extra>",
        ), row=2, col=1)

        # 거래량 급증 마커 (MA20 대비 2배 초과)
        surge_mask = df["Volume"] > df["VolMA20"] * 2
        surge_df   = df[surge_mask.fillna(False)]
        if not surge_df.empty:
            fig.add_trace(go.Scatter(
                x=surge_df.index, y=surge_df["Volume"],
                mode="markers", name="거래량급증",
                marker=dict(symbol="circle", size=7, color="#F0C040",
                            line=dict(color="#0A0A0A", width=1)),
                showlegend=False,
                hovertemplate="⚡ 거래량급증<br>%{x|%Y-%m-%d}<br>%{y:,.0f}<extra></extra>",
            ), row=2, col=1)

    # ── 모멘텀 측정 구간 음영 ─────────────────────────────────────────────
    if len(df) >= 252:
        fig.add_shape(
            type="rect",
            x0=df.index[-252], x1=df.index[-21],
            y0=0, y1=1, yref="y domain",
            fillcolor="rgba(240,192,64,0.10)", line_width=0,
            row=1, col=1,
        )

    # ── 하단 상태 요약 ────────────────────────────────────────────────
    align_label = f"{'▲ 정배열' if is_aligned else '▽ 역배열'} (단{gap_short:+.1f}%/장{gap_long:+.1f}%)"
    parts = [
        align_label,
        f"52주위치 {w52_pos:.0f}%",
        *([] if vol_ratio is None else [f"거래량추세 {vol_ratio:.2f}배"]),
        *([] if momentum is None else [f"12-1개월 모멘텀 {momentum:+.1f}%"]),
    ]
    status_text = "  |  ".join(parts)

    fig.update_layout(
        title=dict(text=f"<b>{name}</b> — 1년 주가 / 추세 지표", font=dict(size=12)),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="-apple-system, 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif", size=10, color="#E8E0CC"),
        margin=dict(l=52, r=8, t=38, b=64), height=520,
        showlegend=True,
        legend=dict(orientation="h", y=1.12, x=0, font=dict(size=9)),
        xaxis=dict(gridcolor="rgba(128,128,128,0.1)", rangeslider=dict(visible=False)),
        yaxis=dict(gridcolor="rgba(128,128,128,0.1)", tickformat=",.0f", title="원"),
    )
    fig.add_annotation(
        text=status_text,
        xref="paper", yref="paper",
        x=0, y=-0.10, showarrow=False,
        font=dict(size=9, color="#9A9278"),
        align="left",
    )
    if has_vol:
        fig.update_xaxes(gridcolor="rgba(128,128,128,0.1)", row=2, col=1)
        fig.update_yaxes(gridcolor="rgba(128,128,128,0.1)", title_text="거래량", row=2, col=1)
    return fig


def _score_comparison_chart(row: pd.Series, df_univ: pd.DataFrame) -> go.Figure:
    """4축 점수 vs 유니버스 평균 그룹 바 차트."""
    labels = [AXIS_LABELS[a] for a in AXES]
    scores = [float(row[a]) for a in AXES]
    avgs   = [float(df_univ[a].mean()) for a in AXES]
    colors = [AXIS_COLORS[a] for a in AXES]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name=str(row.get("name", "선택 종목")),
        x=labels, y=scores, marker_color=colors, opacity=0.9,
        text=[f"{v:.1f}" for v in scores], textposition="outside",
    ))
    fig.add_trace(go.Bar(
        name="유니버스 평균",
        x=labels, y=avgs, marker_color="rgba(150,150,150,0.35)",
        text=[f"{v:.1f}" for v in avgs], textposition="outside",
    ))
    base = {k: v for k, v in PLOTLY_BASE.items() if k != "height"}
    fig.update_layout(
        **base, barmode="group", height=260,
        title="4축 점수 vs 유니버스 평균",
        yaxis=dict(range=[0, 120], gridcolor="rgba(128,128,128,0.1)"),
        legend=dict(orientation="h", y=1.08, font=dict(size=9)),
    )
    return fig


def _render_financial_statement_section(code: str, name: str) -> None:
    """DART 기반 재무제표와 사업보고서 검토 섹션."""
    st.markdown("#### 재무제표·사업보고서 분석")
    st.caption("출처: DART 사업보고서/재무제표. 45일 공시 시차 룰을 적용해 분석 시점보다 45일 이전 접수 자료만 사용합니다.")

    try:
        with st.spinner("DART 재무제표와 사업보고서 조회 중..."):
            review = _get_financial_statement_review(code)
    except Exception as e:
        st.info(f"DART 데이터를 불러오지 못했습니다: {e}")
        return

    fin = review.get("financials", {})
    biz = review.get("business", {})

    if not fin.get("available"):
        st.info(fin.get("reason", "재무제표 데이터가 없습니다."))
    else:
        summary = fin.get("summary", {})
        metric_cols = st.columns(4)
        metric_cols[0].metric("매출 YoY", _fmt_metric_pct(summary.get("revenue_yoy")))
        metric_cols[1].metric("매출 CAGR", _fmt_metric_pct(summary.get("revenue_cagr")))
        metric_cols[2].metric("영업이익 YoY", _fmt_metric_pct(summary.get("operating_income_yoy")))
        metric_cols[3].metric("순이익 YoY", _fmt_metric_pct(summary.get("net_income_yoy")))

        overall_comment = fin.get("overall_comment")
        if overall_comment:
            st.markdown("**재무제표 전체 총론**")
            st.markdown(
                f"<div style='border-left:3px solid #3BA2FF;padding:9px 11px;"
                f"margin:6px 0 10px;background:rgba(59,162,255,0.07);border-radius:0 2px 2px 0;'>"
                f"{overall_comment}</div>",
                unsafe_allow_html=True,
            )

        annual_df = pd.DataFrame(fin.get("annual", []))
        ratio_df = pd.DataFrame(fin.get("ratios", []))
        if not annual_df.empty:
            st.markdown("**3개년 주요 재무제표**")
            st.dataframe(annual_df, use_container_width=True, hide_index=True)
        if not ratio_df.empty:
            st.markdown("**수익성·안정성 비율**")
            st.dataframe(ratio_df, use_container_width=True, hide_index=True)

        comments = fin.get("comments", [])
        if comments:
            st.markdown("**재무제표 해석**")
            for comment in comments:
                st.markdown(
                    f"<div style='border-left:3px solid #F0C040;padding:7px 10px;"
                    f"margin:4px 0;background:rgba(240,192,64,0.06);border-radius:0 2px 2px 0;'>"
                    f"{comment}</div>",
                    unsafe_allow_html=True,
                )

    st.markdown("**사업계획·사업보고서 검토 포인트**")
    if not biz.get("available"):
        st.caption(biz.get("reason", "사업보고서 섹션을 찾지 못했습니다."))
    else:
        st.caption(
            f"{biz.get('report_name', '사업보고서')} · 접수일 {biz.get('rcept_dt', '—')} · "
            f"공시 cutoff {biz.get('cutoff', '—')}"
        )
        report_brief = biz.get("report_brief", [])
        if report_brief:
            st.markdown("**사업보고서 종합 보고자료**")
            for line in report_brief:
                st.markdown(f"- {line}")

        section_summaries = biz.get("section_summaries", [])
        if section_summaries:
            with st.expander("원문 섹션별 자동 요약", expanded=False):
                for item in section_summaries:
                    st.markdown(f"**{item.get('title', 'DART 섹션')}**")
                    st.markdown(item.get("summary", "요약 텍스트가 없습니다."))

        sections = biz.get("sections", [])
        if sections:
            st.markdown("**원문 링크**")
            for section in sections:
                title = section.get("title", "DART 섹션")
                url = section.get("url", "")
                if url:
                    st.markdown(f"- [{title}]({url})")
                else:
                    st.markdown(f"- {title}")
        else:
            st.caption("사업보고서 원문 섹션 링크를 찾지 못했습니다.")

    st.markdown(
        "- 사업계획은 원문 기반으로 매출처 집중도, 수주잔고, CAPEX/생산능력, 연구개발비, 신규 제품 일정을 확인해야 합니다.\n"
        "- 위 재무 코멘트는 공시 숫자 기반의 정량 해석이며, 사업계획 원문을 대체하지 않습니다."
    )


def _fmt_metric_pct(value) -> str:
    try:
        if pd.isna(value):
            return "—"
        return f"{float(value):+.1f}%"
    except Exception:
        return "—"


def _show_company_overview(row: pd.Series, grade_thresholds: tuple) -> None:
    """종목 기본 개요 카드 — tab2 상단에 표시."""
    name = str(row.get("name", ""))
    code = str(row.get("code", ""))
    market = str(row.get("market", ""))
    sector = str(row.get("sector", ""))
    total = float(row.get("Total", 0))
    data_grade = str(row.get("data_grade", ""))

    mc_str = "—"
    mc_raw = row.get("market_cap", None)
    if mc_raw is not None and pd.notna(mc_raw):
        mc = float(mc_raw)
        if mc >= 1e12:
            mc_str = f"{mc / 1e12:.1f}조원"
        elif mc >= 1e8:
            mc_str = f"{mc / 1e8:.0f}억원"

    grade = investment_grade(total, grade_thresholds)
    cfg = GRADE_CONFIG[grade]
    market_color = "#4A90D9" if market == "KOSPI" else "#4ABF6A"

    st.markdown(
        f"<div style='background:rgba(255,255,255,0.03);border-radius:2px;"
        f"padding:16px 20px;margin-bottom:16px;border:1px solid #2A2A2A;'>"
        f"<div style='display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:10px;'>"
        f"<span style='font-size:1.5rem;font-weight:800;color:#E8E0CC;'>{name}</span>"
        f"<span style='color:#6A6050;font-size:0.9rem;'>{code}</span>"
        f"<span style='background:{cfg['bg']};color:{cfg['text']};padding:3px 12px;"
        f"border:1px solid {cfg['border']};border-radius:2px;font-size:0.75rem;font-weight:700;"
        f"font-family:monospace;text-transform:uppercase;letter-spacing:0.08em;'>{grade}</span>"
        f"</div>"
        f"<div style='display:flex;gap:12px;flex-wrap:wrap;align-items:center;'>"
        f"<span style='background:{market_color}33;color:{market_color};padding:3px 10px;"
        f"border-radius:2px;font-weight:700;font-size:0.88rem;'>{market}</span>"
        f"<span style='color:#9A9278;font-size:0.9rem;'>📂 {sector}</span>"
        f"<span style='color:#9A9278;font-size:0.9rem;'>💰 {mc_str}</span>"
        f"<span style='color:#6A6050;font-size:0.82rem;'>데이터등급 {data_grade}</span>"
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


@st.dialog("종목 분석", width="large")
def _show_stock_dialog(row: pd.Series, df_univ: pd.DataFrame, fdf: pd.DataFrame,
                       grade_thresholds: tuple, sector_info: dict | None = None) -> None:
    """Tab1 행 클릭 시 모달 팝업."""
    _render_stock_detail(row, df_univ, fdf, grade_thresholds, sector_info)


def _render_stock_detail(row: pd.Series, df_univ: pd.DataFrame, fdf: pd.DataFrame,
                         grade_thresholds: tuple, sector_info: dict | None = None) -> None:
    """4축 종목 분석 인라인 렌더링 (Tab2 직접 호출 / dialog 래퍼 공유)."""
    code  = str(row["code"])
    name  = str(row["name"])
    total = float(row["Total"])
    rank_val = int(row.get("rank", 0))
    sector = str(row.get("sector", ""))

    _bull_sectors = set(sector_info.get("bull_sectors", [])) if sector_info else set()
    _sec_rets = sector_info.get("sector_returns", {}) if sector_info else {}
    _is_bull = sector in _bull_sectors
    _trend_val = float(row.get("Trend", 0))
    _is_bull_pick = _is_bull and _trend_val >= 65

    fdf_display = fdf.reset_index()
    if "rank" not in fdf_display.columns:
        fdf_display["rank"] = range(1, len(fdf_display) + 1)
    options = fdf_display.apply(
        lambda r: f"{int(r['rank'])}위 {r['name']} ({r['code']})", axis=1
    ).tolist()

    # 헤더: 등급 배지 + 종합점수
    st.markdown(grade_badge_html(total, grade_thresholds), unsafe_allow_html=True)

    _sec_ret = _sec_rets.get(sector)
    if _is_bull_pick and _sec_ret is not None:
        _sec_badge = (
            f"<span style='background:rgba(56,178,107,0.15);color:#38B26B;padding:2px 9px;"
            f"border:1px solid #1E6B40;border-radius:2px;font-size:0.75rem;margin-left:8px;"
            f"font-weight:700;font-family:monospace;text-transform:uppercase;letter-spacing:0.06em;'>"
            f"강세섹터 픽 {_sec_ret:+.1f}%</span>"
        )
    elif _is_bull_pick:
        _sec_badge = (
            "<span style='background:rgba(56,178,107,0.15);color:#38B26B;padding:2px 9px;"
            "border:1px solid #1E6B40;border-radius:2px;font-size:0.75rem;margin-left:8px;"
            "font-weight:700;font-family:monospace;text-transform:uppercase;letter-spacing:0.06em;'>"
            "강세섹터 픽</span>"
        )
    elif _is_bull and _sec_ret is not None:
        _sec_badge = (
            f"<span style='background:rgba(56,178,107,0.15);color:#38B26B;padding:2px 9px;"
            f"border:1px solid #1E6B40;border-radius:2px;font-size:0.75rem;margin-left:8px;'>"
            f"▲ 강세섹터 {_sec_ret:+.1f}%</span>"
        )
    elif _sec_ret is not None:
        _sec_badge = (
            f"<span style='background:#161616;color:#E03030;padding:2px 9px;"
            f"border:1px solid #9B2020;border-radius:2px;font-size:0.75rem;margin-left:8px;'>"
            f"▽ 약세섹터 {_sec_ret:+.1f}%</span>"
        )
    else:
        _sec_badge = ""

    st.markdown(
        f"<div style='display:flex;flex-direction:column;gap:4px;margin:6px 0 10px;'>"
        f"<div style='display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;'>"
        f"<span style='font-size:1.4rem;font-weight:800;'>{name}</span>"
        f"<span style='color:#6A6050;font-size:0.88rem;'>{code} · 유니버스 {rank_val}위</span>"
        f"</div>"
        f"<div>{_sec_badge}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # 기업 개요 카드 (Toss 스타일)
    _market_val = str(row.get("market", ""))
    _mc_raw = row.get("market_cap", None)
    _mc_str = ""
    if _mc_raw is not None and pd.notna(_mc_raw):
        _mc = float(_mc_raw)
        _mc_str = f"{_mc / 1e12:.1f}조원" if _mc >= 1e12 else f"{_mc / 1e8:.0f}억원"
    _market_color = "#4A90D9" if _market_val == "KOSPI" else "#4ABF6A"

    _ci = _get_company_info(code, name)
    _industry  = _ci.get("industry", "") or sector
    _main_prod = _ci.get("main_product", "")
    _ceo       = _ci.get("ceo", "") or "—"
    _listed    = _ci.get("listed_date", "") or "—"
    _eng_name  = _ci.get("eng_name", "") or "—"
    _shares    = _ci.get("shares", None)
    _shares_str = f"{_shares:,}주" if _shares else "—"

    # 헤더: 시장·업종·시총 배지
    _mc_badge = (
        f"<span style='color:#9A9278;font-size:0.85rem;'>💰 {_mc_str}</span>"
        if _mc_str else ""
    )
    st.markdown(
        f"<div style='display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px;'>"
        f"<span style='background:{_market_color}33;color:{_market_color};padding:2px 9px;"
        f"border-radius:2px;font-size:0.82rem;font-weight:700;'>{_market_val}</span>"
        f"<span style='color:#9A9278;font-size:0.88rem;'>📂 {sector}</span>"
        f"{_mc_badge}"
        f"</div>",
        unsafe_allow_html=True,
    )

    # 사업 개요 텍스트 박스
    _desc = (
        f"{_industry} 업종 영위 기업. 주요 사업: {_main_prod}"
        if _main_prod else f"{_industry} 업종 영위 기업."
    )
    st.markdown(
        f"<div style='background:rgba(0,0,0,0.15);border-radius:2px;"
        f"padding:12px 14px;margin-bottom:10px;color:#9A9278;font-size:0.88rem;line-height:1.6;'>"
        f"{_desc}</div>",
        unsafe_allow_html=True,
    )

    # 정보 그리드
    _grid_items = [
        ("시가총액",   _mc_str or "—"),
        ("대표이사",   _ceo),
        ("기업명(영문)", _eng_name),
        ("상장일",     _listed),
        ("발행주식수", _shares_str),
        ("업종",       _industry),
    ]
    _grid_html = (
        "<div style='display:grid;grid-template-columns:1fr 1fr;gap:1px;"
        "background:#2A2A2A;border-radius:0;overflow:hidden;margin-bottom:14px;'>"
    )
    for _lbl, _val in _grid_items:
        _grid_html += (
            f"<div style='background:#111111;padding:10px 12px;'>"
            f"<div style='color:#6A6050;font-size:0.75rem;margin-bottom:3px;'>{_lbl}</div>"
            f"<div style='color:#E8E0CC;font-size:0.88rem;font-weight:500;'>{_val}</div>"
            f"</div>"
        )
    _grid_html += "</div>"
    st.markdown(_grid_html, unsafe_allow_html=True)

    # 관심목록 버튼
    wl = st.session_state.watchlist
    if code in wl:
        if st.button("⭐ 관심 목록에서 제거", key=f"dlg_wl_rm_{code}"):
            wl.remove(code)
            _save_watchlist(wl)
            st.rerun()
    else:
        if st.button("☆ 관심 목록에 추가", key=f"dlg_wl_add_{code}"):
            wl.append(code)
            _save_watchlist(wl)
            st.rerun()

    # 주가 차트
    try:
        price_df = _get_price_history(code)
        fig_p = _price_chart(price_df, name)
        if fig_p is not None:
            st.plotly_chart(fig_p, use_container_width=True, theme=None,
                            key=f"price_chart_{code}")
        else:
            st.caption("주가 데이터를 불러올 수 없습니다.")
    except Exception as _pe:
        st.warning(f"주가 차트 오류: {_pe}")

    # 레이더 + 4축 점수
    compare_options = ["없음"] + [o for o in options if f"({code})" not in o]
    st.caption("비교 종목 (선택사항)")
    sel_compare = st.selectbox("비교 종목 선택", compare_options, key="dlg_compare",
                               label_visibility="collapsed")
    row2 = name2 = None
    if sel_compare != "없음":
        cmp_idx = options.index(sel_compare)
        row2 = fdf.reset_index().iloc[cmp_idx]
        name2 = row2["name"]

    # 레이더 차트 — 풀 너비 (모바일 @media 컬럼 스택 적용)
    st.plotly_chart(radar_chart(row, name, row2, name2), use_container_width=True)

    # 4축 점수 — 레이더 아래 전체 너비
    st.markdown(f"#### {name} 4축 점수")
    for axis in AXES:
        val = float(row[axis])
        st.markdown(
            f"**{AXIS_LABELS[axis]}** &nbsp;&nbsp; {color_score(val)} **{val:.1f}점**"
            f'  <span title="{AXIS_TOOLTIPS[axis]}" style="cursor:help;color:#999;'
            f'font-size:0.85em;white-space:nowrap;">ℹ️</span>',
            unsafe_allow_html=True,
        )
        st.markdown(score_bar(val, AXIS_COLORS[axis]), unsafe_allow_html=True)
    st.markdown(
        f"<div style='margin-top:10px;padding:10px;background:rgba(128,128,128,0.12);"
        f"border-radius:8px;text-align:center'>"
        f"<span style='font-size:1.3em;font-weight:700;color:#1f77b4'>"
        f"종합 {total:.1f}점 / 100점</span></div>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ── 밸류에이션 매트릭 (PER·PBR·배당) ─────────────────────────────────────
    st.markdown("#### 💰 밸류에이션")
    try:
        from src.valuation import get_stock_valuation, get_sector_valuation_avg
        with st.spinner("PER·PBR 조회 중..."):
            stock_val = get_stock_valuation(code)
            sector_val = get_sector_valuation_avg(sector, df_univ)

        def _val_card(label: str, key: str, fmt: str, lower_is_better: bool = True) -> str:
            stock_v  = stock_val.get(key)
            sector_v = sector_val.get(key)
            if stock_v is None or pd.isna(stock_v):
                stock_str = "—"
                color     = "#6A6050"
                badge     = ""
            else:
                stock_str = fmt.format(stock_v)
                # 섹터 평균과 비교
                if sector_v is not None:
                    diff_pct = (stock_v - sector_v) / abs(sector_v) * 100 if sector_v != 0 else 0
                    if lower_is_better:
                        color = "#38B26B" if stock_v < sector_v else "#E03030"
                        arrow = "▼" if stock_v < sector_v else "▲"
                        good_label = "저평가" if stock_v < sector_v else "고평가"
                    else:
                        color = "#38B26B" if stock_v > sector_v else "#E03030"
                        arrow = "▲" if stock_v > sector_v else "▼"
                        good_label = "유리" if stock_v > sector_v else "불리"
                    badge = (
                        f"<div style='font-size:0.65rem;color:{color};font-family:monospace;margin-top:2px;'>"
                        f"{arrow} 섹터 대비 {good_label} ({diff_pct:+.0f}%)</div>"
                    )
                else:
                    color = "#F0C040"
                    badge = ""
            sector_str = fmt.format(sector_v) if sector_v is not None else "—"
            return (
                f"<div style='background:#111;border:1px solid #2A2A2A;border-radius:4px;"
                f"padding:10px 12px;'>"
                f"<div style='font-size:0.62rem;color:#6A6050;font-family:monospace;letter-spacing:0.08em;'>{label}</div>"
                f"<div style='font-size:1.3rem;font-weight:800;font-family:monospace;color:{color};'>{stock_str}</div>"
                f"<div style='font-size:0.65rem;color:#9A9278;font-family:monospace;'>섹터 중앙값 {sector_str}</div>"
                f"{badge}"
                f"</div>"
            )

        v_col1, v_col2, v_col3 = st.columns(3)
        v_col1.markdown(_val_card("PER (배)",      "per", "{:.1f}", lower_is_better=True),  unsafe_allow_html=True)
        v_col2.markdown(_val_card("PBR (배)",      "pbr", "{:.2f}", lower_is_better=True),  unsafe_allow_html=True)
        v_col3.markdown(_val_card("배당수익률 (%)", "dividend_yield", "{:.2f}", lower_is_better=False), unsafe_allow_html=True)
        st.caption(f"섹터: {sector} · 비교 표본 {sector_val.get('n', 0)}개 종목 · 출처: Naver Finance · 30분 캐시")
    except Exception as e:
        st.warning(f"밸류에이션 조회 실패: {e}")

    st.markdown("---")

    _render_financial_statement_section(code, name)

    st.markdown("---")

    # ── 상대 강도(RS) — 시장 대비 ────────────────────────────────────────────
    st.markdown("#### 📈 상대 강도 (vs KOSPI)")
    st.caption("RS Line = 종목 가격 / KOSPI × 100 (기간 시작일 = 100). 우상향이면 시장 대비 강함.")
    try:
        from src.valuation import compute_relative_strength
        with st.spinner("RS 계산 중..."):
            rs_df = compute_relative_strength(code, benchmark="KS11", period_days=180)
        if rs_df is not None and not rs_df.empty:
            current_rs = float(rs_df["rs_norm"].iloc[-1])
            rs_change  = current_rs - 100
            rs_color   = "#38B26B" if rs_change >= 0 else "#E03030"
            rs_arrow   = "▲" if rs_change >= 0 else "▼"
            rs_label   = "시장보다 강함" if rs_change >= 0 else "시장보다 약함"

            fig_rs = go.Figure()
            fig_rs.add_trace(go.Scatter(
                x=rs_df.index, y=rs_df["rs_norm"].values,
                mode="lines", line=dict(color=rs_color, width=2),
                name="RS Line",
                hovertemplate="%{x|%Y-%m-%d}<br>RS: %{y:.1f}<extra></extra>",
                fill="tonexty",
            ))
            fig_rs.add_hline(y=100, line_dash="dash", line_color="#6A6050", line_width=1,
                             annotation_text="기준선 (시장과 동일)")
            fig_rs.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#0D0D0D",
                font=dict(family="monospace", size=10, color="#9A9278"),
                margin=dict(l=50, r=20, t=20, b=30), height=240,
                xaxis=dict(showgrid=False, tickfont=dict(size=9)),
                yaxis=dict(gridcolor="rgba(255,255,255,0.05)", tickfont=dict(size=9)),
                title=dict(
                    text=f"<span style='color:{rs_color};font-weight:700;'>{rs_arrow} RS {current_rs:.1f}</span>"
                         f"  <span style='color:#9A9278;'>· {rs_label} ({rs_change:+.1f}p)</span>",
                    x=0, y=0.97, font=dict(size=11),
                ),
                showlegend=False,
            )
            st.plotly_chart(fig_rs, use_container_width=True, theme=None,
                            key=f"rs_chart_{code}")
        else:
            st.info("상대 강도 계산을 위한 가격 데이터가 부족합니다.")
    except Exception as e:
        st.warning(f"RS 계산 실패: {e}")

    st.markdown("---")

    # 기술 신호
    st.markdown("**📡 기술 신호**")
    row_dict = row.to_dict() if hasattr(row, "to_dict") else {}
    _rsi = row_dict.get("RSI")
    _pos = row_dict.get("week52_pos")
    _sig = row_dict.get("entry_signal")
    _ic_metrics: list[tuple] = []
    if _rsi is not None and pd.notna(_rsi):
        rsi_v = float(_rsi)
        rsi_desc = "과매수 주의" if rsi_v > 70 else "과매도 반등 구간" if rsi_v < 30 else "적정 구간"
        _ic_metrics.append(("RSI(14)", f"{rsi_v:.0f}", rsi_desc, "off"))
    if _pos is not None and pd.notna(_pos):
        _ic_metrics.append(("52주 위치", f"{float(_pos):.0f}%", None, "off"))
    if _sig:
        sig_map = {"강세후보": "🟢 강세 후보", "관심": "🔵 관심", "과열주의": "🔴 과열주의",
                   "대기": "⚪ 대기", "확인필요": "❓ 확인필요"}
        _ic_metrics.append(("기술 신호", sig_map.get(_sig, _sig), None, "off"))
    try:
        _cur = _get_current_price(code)
        _cons, _ = _get_analyst_data(code)
        _tp = _cons.target_price if _cons and not _cons.error else None
        if _cur and _tp and _cur > 0:
            upside = (_tp - _cur) / _cur * 100
            _ic_metrics.append(("목표주가 상승여력", f"{upside:+.1f}%", f"목표 {_tp:,}원",
                                 "normal" if upside >= 0 else "inverse"))
        else:
            _ic_metrics.append(("목표주가 상승여력", "—", None, "off"))
    except Exception:
        _ic_metrics.append(("목표주가 상승여력", "—", None, "off"))
    if _ic_metrics:
        _ic_cols = st.columns(len(_ic_metrics))
        for _col, (_lbl, _val, _delta, _dcol) in zip(_ic_cols, _ic_metrics):
            if _delta:
                _col.metric(_lbl, _val, delta=_delta, delta_color=_dcol)
            else:
                _col.metric(_lbl, _val)

    st.markdown("---")

    # 유니버스 포지셔닝 바 차트
    st.markdown("**유니버스 포지셔닝 — 4축 점수 비교**")
    try:
        st.plotly_chart(_score_comparison_chart(row, df_univ), use_container_width=True)
    except Exception:
        pass

    # 분석 포인트 / 주의 사항
    strengths  = [(AXIS_LABELS[a], float(row[a]), a) for a in AXES if float(row[a]) >= 60]
    weaknesses = [(AXIS_LABELS[a], float(row[a]), a) for a in AXES if float(row[a]) < 40]
    univ_ranks = {a: int((df_univ[a] > float(row[a])).sum()) + 1 for a in AXES}

    if strengths or weaknesses:
        if strengths:
            st.markdown("**✅ 분석 포인트** (60점 이상)")
            for lbl, score, akey in strengths:
                st.markdown(
                    f"<div style='border-left:3px solid {AXIS_COLORS[akey]};padding:7px 10px;"
                    f"margin:4px 0;background:rgba(0,200,83,0.07);border-radius:0 6px 6px 0;'>"
                    f"<b>{lbl}</b> <span style='color:{AXIS_COLORS[akey]};font-weight:700;'>"
                    f"{score:.1f}점</span> — 유니버스 <b>{univ_ranks[akey]}위</b>/{len(df_univ)}위</div>",
                    unsafe_allow_html=True,
                )
        if weaknesses:
            st.markdown("**⚠️ 주의 사항** (40점 미만)")
            for lbl, score, akey in weaknesses:
                st.markdown(
                    f"<div style='border-left:3px solid {AXIS_COLORS[akey]};padding:7px 10px;"
                    f"margin:4px 0;background:rgba(224,48,48,0.07);border-radius:0 2px 2px 0;'>"
                    f"<b>{lbl}</b> <span style='color:#E03030;font-weight:700;'>"
                    f"{score:.1f}점</span> — 유니버스 <b>{univ_ranks[akey]}위</b>/{len(df_univ)}위</div>",
                    unsafe_allow_html=True,
                )

    # 4축 선별 근거 상세
    st.markdown("**📝 4축 선별 근거 상세**")
    _kor_to_eng2 = {"성장": "Growth", "가치": "Value", "펀더멘털": "Quality", "추세": "Trend"}
    try:
        reasons = explain_stock(code, fdf.reset_index())
    except Exception as _ex:
        reasons = {}
        st.warning(f"선별 근거 조회 오류: {_ex}")
    summary_text = f" — {reasons['summary']}" if reasons.get("summary") else ""
    if reasons.get("total"):
        st.markdown(
            f"<div style='padding:12px;background:rgba(240,192,64,0.08);border-radius:2px;"
            f"border-left:4px solid #B8922E;margin-bottom:8px;color:inherit;'>"
            f"📌 {reasons['total']}{summary_text}</div>",
            unsafe_allow_html=True,
        )
    for axis, key in [("성장","growth"),("가치","value"),("펀더멘털","quality"),("추세","trend"),("리스크","risk")]:
        color = AXIS_COLORS.get(_kor_to_eng2.get(axis, axis), "#888")
        reason_text = reasons.get(key, "데이터 없음")
        st.markdown(
            f"<div style='border-left:3px solid {color};padding:7px 12px;margin:4px 0;"
            f"background:rgba(128,128,128,0.05);border-radius:0 4px 4px 0;font-size:0.88rem;color:inherit;'>"
            f"<strong>{axis}</strong> — {reason_text}</div>",
            unsafe_allow_html=True,
        )

    # 비교 종목 근거
    if row2 is not None and name2:
        st.markdown("---")
        st.markdown(f"**{name2} — 비교 종목 선별 근거**")
        try:
            reasons2 = explain_stock(row2["code"], fdf.reset_index())
        except Exception:
            reasons2 = {}
        summary2 = f" — {reasons2['summary']}" if reasons2.get("summary") else ""
        if reasons2.get("total"):
            st.markdown(
                f"<div style='padding:10px;background:rgba(224,48,48,0.10);border-radius:2px;"
                f"border-left:4px solid #E03030;margin-bottom:8px;color:inherit;'>"
                f"📌 {reasons2['total']}{summary2}</div>",
                unsafe_allow_html=True,
            )
        for axis2, key2 in [("성장","growth"),("가치","value"),("펀더멘털","quality"),("추세","trend"),("리스크","risk")]:
            color2 = AXIS_COLORS.get(_kor_to_eng2.get(axis2, axis2), "#888")
            reason2_text = reasons2.get(key2, "데이터 없음")
            st.markdown(
                f"<div style='border-left:3px solid {color2};padding:6px 12px;margin:3px 0;"
                f"background:rgba(128,128,128,0.04);border-radius:0 4px 4px 0;font-size:0.86rem;color:inherit;'>"
                f"<strong>{axis2}</strong> — {reason2_text}</div>",
                unsafe_allow_html=True,
            )

    # 유사 점수 종목
    st.markdown("**유사 점수 종목** (±10점 이내)")
    similar = fdf[
        (fdf["Total"].between(total - 10, total + 10)) & (fdf["code"] != code)
    ].head(5).reset_index()[["rank", "name", "Total"]]
    if not similar.empty:
        st.caption("← 좌우 스크롤 가능")
        st.dataframe(similar, use_container_width=True, hide_index=True)
    else:
        st.caption("유사 점수 종목 없음")

    st.markdown("---")
    _render_analyst_section(code, name)


def _render_analyst_section(code: str, name: str) -> None:
    """Tab2: 애널리스트 컨센서스 및 리포트 섹션."""
    st.markdown("#### 애널리스트 컨센서스")
    st.caption("출처: Naver Finance / WiseReport (FnGuide 제공) — 정량 스크리닝 보조 참고용")

    with st.spinner("애널리스트 데이터 조회 중..."):
        consensus, reports = _get_analyst_data(code)

    if consensus.error:
        st.warning(f"데이터 조회 실패: {consensus.error}")
        return

    if consensus.target_price is None and consensus.analyst_count is None:
        st.info("이 종목의 애널리스트 커버리지 데이터를 찾을 수 없습니다.")
        return

    # 목표주가 + 애널리스트 수
    col_a, col_b = st.columns(2)
    if consensus.target_price:
        col_a.metric("컨센서스 목표주가", f"{consensus.target_price:,}원")
    if consensus.analyst_count:
        col_b.metric("추정 증권사 수", f"{consensus.analyst_count}개")
    if consensus.consensus_score:
        score_label = {5: "강력매수", 4: "매수", 3: "중립", 2: "매도", 1: "강력매도"}.get(
            round(consensus.consensus_score), f"{consensus.consensus_score:.1f}"
        )
        st.metric("컨센서스 의견", score_label)

    # 매수/중립/매도 분포
    total_ops = consensus.buy_count + consensus.neutral_count + consensus.sell_count
    if total_ops > 0:
        buy_pct = consensus.buy_count / total_ops * 100
        neu_pct = consensus.neutral_count / total_ops * 100
        sell_pct = consensus.sell_count / total_ops * 100
        st.markdown(
            f'<div style="display:flex;gap:2px;margin:8px 0;flex-wrap:wrap;">'
            f'<div style="flex:{buy_pct:.0f};min-width:40px;background:#38B26B;height:28px;'
            f'border-radius:0;text-align:center;color:#000;'
            f'font-size:0.75rem;line-height:28px;font-family:monospace;font-weight:700;" title="매수 {consensus.buy_count}개">'
            f'매수 {buy_pct:.0f}%</div>'
            f'<div style="flex:{neu_pct:.0f};min-width:40px;background:#F0C040;height:28px;'
            f'text-align:center;color:#000;font-size:0.75rem;line-height:28px;font-family:monospace;font-weight:700;" '
            f'title="중립 {consensus.neutral_count}개">'
            f'중립 {neu_pct:.0f}%</div>'
            f'<div style="flex:{max(sell_pct,1):.0f};min-width:40px;background:#E03030;height:28px;'
            f'border-radius:0;text-align:center;color:#fff;'
            f'font-size:0.75rem;line-height:28px;font-family:monospace;font-weight:700;" title="매도 {consensus.sell_count}개">'
            f'매도 {sell_pct:.0f}%</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # 증권사별 최근 리포트
    if consensus.recent_reports:
        with st.expander(f"증권사별 목표주가 ({len(consensus.recent_reports)}건)"):
            rpt_df = pd.DataFrame(consensus.recent_reports)
            st.dataframe(rpt_df, use_container_width=True, hide_index=True)

    # 리포트 제목 목록
    if reports:
        with st.expander(f"최근 리포트 제목 ({len(reports)}건)"):
            for r in reports:
                tp = r.get("target_price")
                tp_badge = (
                    f" <span style='background:#162030;color:#6FCFCF;padding:1px 7px;"
                    f"border:1px solid #2A5060;border-radius:2px;font-size:0.75rem;"
                    f"margin-left:6px;font-family:monospace;'>"
                    f"목표 {tp:,}원</span>"
                    if tp else ""
                )
                st.markdown(
                    f"**{r['broker']}** `{r['date']}`{tp_badge}  \n"
                    f"{r['title']}  \n"
                    f"<small style='color:var(--text-muted,#888)'>{r['preview']}</small>",
                    unsafe_allow_html=True,
                )
                st.divider()


def _mobile_card_html(rank: int, name: str, sector: str,
                      total: float, grade: str, is_bull: bool) -> str:
    """모바일 카드 뷰 — CSS .ql-card-list 내부에서만 표시됨."""
    _gc = GRADE_CONFIG.get(grade, {"bg": "#2A2A2A", "text": "#9A9278", "border": "#3A3A3A"})
    _gc_bg, _gc_text, _gc_border = _gc["bg"], _gc["text"], _gc["border"]
    bull_badge = '<span class="ql-bull-badge">강세섹터</span>' if is_bull else ""
    return (
        f'<div class="ql-card">'
        f'<div class="ql-card-rank">{rank}</div>'
        f'<div class="ql-card-body">'
        f'<div class="ql-card-name">{name}</div>'
        f'<div class="ql-card-sub">{sector}{" " + bull_badge if bull_badge else ""}</div>'
        f'</div>'
        f'<div class="ql-card-right">'
        f'<span class="ql-card-score">{total:.1f}</span>'
        f'<span class="ql-grade-badge" style="background:{_gc_bg};color:{_gc_text};border:1px solid {_gc_border};">{grade}</span>'
        f'</div>'
        f'</div>'
    )


# ── 메인 ─────────────────────────────────────────────────────────────────────
def main() -> None:
    _init_session_state()
    _inject_css()
    df = load_data()
    grade_thresholds = compute_grade_thresholds(df) if not df.empty else (60.0, 50.0, 40.0)

    # 섹터 강도 계산 (5일 수익률, 10분 캐시)
    sector_info: dict = {}
    if not df.empty:
        _sec_map = tuple(sorted(
            (sec, tuple(zip(grp["name"].tolist(), grp["code"].tolist())))
            for sec, grp in df.groupby("sector")
        ))
        try:
            sector_info = _compute_sector_strength(_sec_map)
        except Exception:
            sector_info = {}
    _bull_sectors_main = set(sector_info.get("bull_sectors", []))

    # UX: Full-page onboarding when no data
    if df.empty:
        st.title("QuantLab Screener")
        st.markdown("### 데이터가 아직 없습니다")
        st.info("터미널에서 아래 명령어를 실행해 스코어링 데이터를 생성하세요.")
        st.code("source .venv/bin/activate\npython -m src.main", language="bash")
        st.markdown("생성 완료 후 아래 버튼을 클릭하세요.")
        if st.button("데이터 새로고침", type="primary", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        with st.sidebar:
            st.title("QuantLab Screener")
            if st.button("데이터 새로고침", key="sidebar_refresh"):
                st.cache_data.clear()
                st.rerun()
        st.stop()

    # ── 사이드바 ──────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(
            "<div class='sidebar-brand' style='padding:16px 0 8px;'>"
            "<div style='font-size:1.6rem;font-weight:800;letter-spacing:-0.02em;'>QuantLab Screener</div>"
            "<div style='font-size:0.875rem;color:#888;margin-top:5px;'>KOSPI·KOSDAQ 4축 스코어링</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.divider()

        _NAV_PAGES = [
            "종목 분석",
            "글로벌 지표",
            "섹터 현황",
            "IC검증",
        ]
        sel_page = st.radio(
            "페이지",
            _NAV_PAGES,
            label_visibility="collapsed",
            key="nav_page",
        )

        st.divider()

        st.markdown(
            "<div style='font-size:0.72rem;color:#888;margin-bottom:10px;'>"
            f"📅 {_last_updated()}<br>"
            f"<span style='color:#B8922E;'>· {_last_updated_relative()}</span></div>",
            unsafe_allow_html=True,
        )

        st.markdown("**필터**")

        market_order = ["KOSPI", "KOSDAQ", "KOSDAQ GLOBAL"]
        avail_markets = [m for m in market_order if m in df["market"].values]
        sel_market = st.selectbox("시장", ["전체"] + avail_markets)

        SECTOR_ICONS = {
            "전기·전자": "💡", "의약품": "💊", "기계": "⚙️",
            "서비스업": "🌐", "운수장비": "🚗", "은행": "🏦",
            "화학": "🧪", "증권": "📈", "건설업": "🏗️",
            "운수·창고업": "✈️", "철강·금속": "🔩", "보험업": "🛡️",
            "통신업": "📡", "음식료품": "🍜", "화장품·의류": "💄",
            "전기·가스업": "⚡", "담배": "🌿",
        }
        raw_sectors = sorted(df["sector"].unique().tolist())
        sector_labels = ["전체"] + [f"{SECTOR_ICONS.get(s, '📌')} {s}" for s in raw_sectors]
        sector_values = ["전체"] + raw_sectors
        sel_sector_label = st.selectbox("업종", sector_labels)
        sel_sector = sector_values[sector_labels.index(sel_sector_label)]

        search = ""

        has_signal = "entry_signal" in df.columns
        if has_signal:
            all_signals = ["전체", "강세후보", "관심", "과열주의", "대기", "확인필요"]
            signal_labels_by_value = {
                "강세후보": "🟢 강세 후보",
                "관심": "🔵 관심",
                "과열주의": "🔴 과열주의",
                "대기": "⚪ 대기",
                "확인필요": "❓ 확인필요",
            }
            signal_labels = ["전체"] + [signal_labels_by_value.get(s, s) for s in all_signals[1:]]
            sel_signal_label = st.selectbox("기술 신호", signal_labels)
            sel_signal = all_signals[signal_labels.index(sel_signal_label)]
        else:
            sel_signal = "전체"

        grade_options = ["전체", "최우수", "우수", "보통", "관찰"]
        sel_grade = st.selectbox("분석등급", grade_options)

        if st.button("필터 초기화", use_container_width=True):
            st.session_state.tab2_search = ""
            st.rerun()

        st.divider()
        st.markdown("**🔍 빠른 종목 검색**")
        quick_srch = st.text_input("종목명 또는 코드", key="sidebar_quick_search", placeholder="예: 삼성전자")
        if quick_srch:
            st.session_state.tab2_search = quick_srch
            if sel_page == "종목 분석":
                st.caption(f"✓ 랭킹에서 '{quick_srch}' 필터링 중")
            else:
                st.caption(f"→ '종목 분석' 메뉴 클릭 시 '{quick_srch}' 결과 표시")

        st.divider()

        # 섹터 강도 현황 (5일 수익률 기준 자동 갱신)
        st.markdown("<div class='sidebar-sector-strength'>", unsafe_allow_html=True)
        st.markdown("**📡 섹터 강도** <small style='color:#888;font-size:0.8125rem;'>5일 수익률 기준</small>",
                    unsafe_allow_html=True)
        if sector_info and sector_info.get("sector_returns"):
            _sr = sector_info["sector_returns"]
            _bull_set = set(sector_info.get("bull_sectors", []))
            _med = sector_info.get("median_return", 0)
            _top = sector_info.get("sector_top", {})
            _rows_html = []
            for _sname, _sret in sorted(_sr.items(), key=lambda x: x[1], reverse=True):
                _icon = "🔥" if _sname in _bull_set else "▽"
                _col = "#FF6F00" if _sname in _bull_set else "#78909C"
                _stocks = _top.get(_sname, [])
                if _stocks:
                    _tt_parts = []
                    for _i, (_n, _r) in enumerate(_stocks):
                        _rc = "#4CAF50" if _r >= 0 else "#EF5350"
                        _tt_parts.append(
                            f"<div class='ql-tt-row'>"
                            f"<span class='ql-tt-name'>{_i+1}. {_n}</span>"
                            f"<span class='ql-tt-ret' style='color:{_rc}'>{_r:+.1f}%</span>"
                            f"</div>"
                        )
                    _tt_rows = "".join(_tt_parts)
                else:
                    _tt_rows = "<div style='color:#888;'>데이터 없음</div>"
                _rows_html.append(
                    f"<div class='ql-sector-row'>"
                    f"<div style='display:flex;justify-content:space-between;padding:2px 0;font-size:0.875rem;'>"
                    f"<span style='color:#ccc;'>{_icon} {_sname}</span>"
                    f"<span style='color:{_col};font-weight:700;'>{_sret:+.1f}%</span>"
                    f"</div>"
                    f"<div class='ql-sector-tooltip'>"
                    f"<div style='color:#aaa;font-size:0.75rem;margin-bottom:4px;'>5일 수익률 상위 종목</div>"
                    f"{_tt_rows}"
                    f"</div>"
                    f"</div>"
                )
            st.markdown("\n".join(_rows_html), unsafe_allow_html=True)
            st.caption(f"섹터 중앙값 {_med:+.1f}% | 10분마다 자동 갱신")
        else:
            st.caption("섹터 강도 데이터 로딩 중...")
        st.markdown("</div>", unsafe_allow_html=True)

        st.divider()

        # CustMgmt: 영구 저장된 관심 종목
        if st.session_state.watchlist:
            st.subheader(f"⭐ 관심 종목 ({len(st.session_state.watchlist)}개)")
            st.caption("💾 파일 영구 저장됨")
            wl_df = df.reset_index()
            wl_df = wl_df[wl_df["code"].isin(st.session_state.watchlist)][
                ["name", "code", "Total"]
            ].sort_values("Total", ascending=False)
            for _, wrow in wl_df.iterrows():
                col_w1, col_w2 = st.columns([3, 1])
                col_w1.caption(f"{wrow['name']} ({wrow['code']}) — {wrow['Total']:.1f}점")
                if col_w2.button("✕", key=f"wl_rm_{wrow['code']}"):
                    st.session_state.watchlist.remove(wrow["code"])
                    _save_watchlist(st.session_state.watchlist)
                    st.rerun()
            st.divider()

        if st.button("데이터 새로고침"):
            st.cache_data.clear()
            st.rerun()

    # 필터 적용
    fdf = df.copy()
    if search:
        mask = (
            fdf["name"].str.contains(search, case=False, na=False)
            | fdf["code"].str.contains(search, case=False, na=False)
        )
        fdf = fdf[mask]
    if sel_market != "전체":
        fdf = fdf[fdf["market"] == sel_market]
    if sel_sector != "전체":
        fdf = fdf[fdf["sector"] == sel_sector]
    if sel_signal != "전체" and "entry_signal" in fdf.columns:
        fdf = fdf[fdf["entry_signal"] == sel_signal]
    if sel_grade != "전체":
        fdf = fdf[fdf["Total"].apply(lambda x: investment_grade(x, grade_thresholds)) == sel_grade]

    # ── 헤더 ────────────────────────────────────────────────────────────────────
    kospi_cnt = int((df["market"] == "KOSPI").sum())
    kosdaq_cnt = int((df["market"] == "KOSDAQ").sum())
    st.markdown(
        f"""<div style="display:flex;flex-direction:column;gap:8px;
          padding:14px 0 10px;border-bottom:1px solid rgba(128,128,128,0.18);margin-bottom:14px;">
          <div style="display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;">
            <span style="font-size:clamp(1.4rem,4vw,2.2rem);font-weight:800;letter-spacing:-0.03em;">
              QuantLab Screener</span>
            <span style="font-size:0.875rem;color:#6A6050;word-break:keep-all;">
              KOSPI·KOSDAQ 시총 상위 100개 · 4축 스코어링</span>
          </div>
          <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;">
            <span style="background:rgba(240,192,64,0.10);border:1px solid #B8922E;
              padding:3px 11px;border-radius:2px;font-size:0.75rem;color:#F0C040;font-weight:600;font-family:monospace;">
              {len(fdf)}개 종목</span>
            <span style="background:#111111;border:1px solid #2A2A2A;
              padding:3px 11px;border-radius:2px;font-size:0.75rem;color:#9A9278;font-family:monospace;">
              KOSPI {kospi_cnt} · KOSDAQ {kosdaq_cnt}</span>
            <span style="font-size:0.75rem;color:#6A6050;font-family:monospace;">📅 {_last_updated()}</span>
          </div>
        </div>""",
        unsafe_allow_html=True,
    )

    is_empty = fdf.empty

    # ── Tab 1: 종목 분석 ─────────────────────────────────────────────────────
    if sel_page == "종목 분석":
        t1, t2, t3 = grade_thresholds
        st.markdown(
            f"<div style='display:flex;align-items:center;justify-content:space-between;"
            f"margin-bottom:8px;flex-wrap:wrap;gap:8px;'>"
            f"<span style='font-size:1.05rem;font-weight:700;'>종목 랭킹 "
            f"<span style='color:#F0C040;'>{len(fdf)}개</span></span>"
            f"<div style='display:flex;gap:6px;align-items:center;flex-wrap:wrap;'>"
            f"<span style='font-size:0.75rem;color:#6A6050;font-family:monospace;'>등급 기준</span>"
            f"<span style='background:#1A3A20;color:#38B26B;border:1px solid #1E6B40;padding:3px 9px;border-radius:2px;"
            f"font-size:0.75rem;font-weight:700;font-family:monospace;text-transform:uppercase;'>최우수 ≥{t1:.0f}</span>"
            f"<span style='background:#162030;color:#6FCFCF;border:1px solid #2A5060;padding:3px 9px;border-radius:2px;"
            f"font-size:0.75rem;font-weight:700;font-family:monospace;text-transform:uppercase;'>우수 ≥{t2:.0f}</span>"
            f"<span style='background:#2A1A00;color:#F0C040;border:1px solid #B8922E;padding:3px 9px;border-radius:2px;"
            f"font-size:0.75rem;font-weight:700;font-family:monospace;text-transform:uppercase;'>보통 ≥{t3:.0f}</span>"
            f"<span style='background:#2A0A0A;color:#E03030;border:1px solid #9B2020;padding:3px 9px;border-radius:2px;"
            f"font-size:0.75rem;font-weight:700;font-family:monospace;text-transform:uppercase;'>관찰</span>"
            f"<span style='font-size:0.72rem;color:#4A4438;'>· 정량 스크리닝 결과, 투자 추천 아님</span>"
            f"</div></div>",
            unsafe_allow_html=True,
        )

        if is_empty:
            st.warning("필터 조건에 맞는 종목이 없습니다. 조건을 완화하거나 **필터 초기화**를 클릭하세요.")
        else:
            today_str = datetime.now().strftime("%Y%m%d")
            csv_bytes = fdf.reset_index().to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                label="⬇️ CSV 다운로드",
                data=csv_bytes,
                file_name=f"quantlab_screener_{today_str}.csv",
                mime="text/csv",
            )

            # ── 상대 강도(RS) TOP — 시장 대비 강한 종목 ─────────────────────
            with st.expander("📈 시장보다 강한 종목 TOP 20 (vs KOSPI)", expanded=False):
                rs_col1, rs_col2 = st.columns([3, 1])
                with rs_col1:
                    rs_period = st.radio(
                        "기간",
                        ["20일", "60일", "120일"],
                        index=1,
                        horizontal=True,
                        key="rs_top_period",
                        label_visibility="collapsed",
                    )
                rs_days = {"20일": 20, "60일": 60, "120일": 120}[rs_period]
                with rs_col2:
                    rs_run = st.button("계산 실행", key="rs_run_btn",
                                       use_container_width=True, type="primary")

                cache_key = f"rs_top_result_{rs_days}"
                if rs_run:
                    @st.cache_data(ttl=1800, show_spinner="RS 계산 중 (100종목 병렬)...")
                    def _cached_rs_top(period_days: int) -> pd.DataFrame:
                        from src.valuation import get_top_relative_strength
                        return get_top_relative_strength(
                            df.reset_index(),
                            benchmark="KS11",
                            lookback_days=period_days,
                            top_n=20,
                        )
                    st.session_state[cache_key] = _cached_rs_top(rs_days)

                rs_top_df = st.session_state.get(cache_key)
                if rs_top_df is None:
                    st.info("👆 '계산 실행' 버튼을 눌러주세요. (~5~10초 소요)")
                elif rs_top_df.empty:
                    st.warning("RS 계산을 위한 가격 데이터가 부족합니다.")
                else:
                    rs_disp = rs_top_df[["name", "code", "sector", "stock_ret", "bench_ret", "excess_ret"]].copy()
                    rs_disp.columns = ["종목명", "코드", "섹터", "종목수익률(%)", "KOSPI수익률(%)", "초과수익률(%)"]
                    st.dataframe(
                        rs_disp.style.format({
                            "종목수익률(%)":   "{:+.2f}",
                            "KOSPI수익률(%)":  "{:+.2f}",
                            "초과수익률(%)":   "{:+.2f}",
                        }).background_gradient(subset=["초과수익률(%)"], cmap="RdYlGn"),
                        use_container_width=True,
                        hide_index=True,
                        height=420,
                    )
                    st.caption(f"기간: 최근 {rs_days}일 · 벤치마크: KOSPI (KS11) · 30분 캐시")


            with st.expander("🏆 업종별 TOP 종목"):
                SECTOR_ICONS = {
                    "전기·전자": "💡", "의약품": "💊", "기계": "⚙️",
                    "서비스업": "🌐", "운수장비": "🚗", "은행": "🏦",
                    "화학": "🧪", "증권": "📈", "건설업": "🏗️",
                    "운수·창고업": "✈️", "철강·금속": "🔩", "보험업": "🛡️",
                    "화장품·의류": "💄", "통신업": "📡", "전기·가스업": "⚡",
                    "담배": "🌿", "음식료품": "🍱", "기타": "",
                }
                sector_top = (
                    fdf.reset_index()
                    .sort_values("Total", ascending=False)
                    .groupby("sector", as_index=False)
                    .first()
                    .sort_values("Total", ascending=False)
                )
                cols = st.columns(4)
                for i, (_, srow) in enumerate(sector_top.iterrows()):
                    grade = investment_grade(srow["Total"], grade_thresholds)
                    cfg = GRADE_CONFIG[grade]
                    icon = SECTOR_ICONS.get(srow["sector"], "")
                    with cols[i % 4]:
                        st.markdown(
                            f'<div style="border:1px solid {cfg["border"]};border-left:4px solid {cfg["bg"]};'
                            f'border-radius:2px;padding:10px 12px;margin-bottom:8px;">'
                            f'<div style="font-size:0.68rem;color:#6A6050;margin-bottom:4px;font-family:monospace;text-transform:uppercase;letter-spacing:0.08em;">'
                            f'{icon} {srow["sector"]}</div>'
                            f'<div style="font-size:0.95rem;font-weight:700;color:#E8E0CC;margin-bottom:6px;font-family:Noto Sans KR,sans-serif;">{srow["name"]}</div>'
                            f'<span style="background:{cfg["bg"]};color:{cfg["text"]};border:1px solid {cfg["border"]};'
                            f'padding:2px 7px;border-radius:2px;font-size:0.68rem;font-weight:700;font-family:monospace;text-transform:uppercase;letter-spacing:0.06em;">'
                            f'{grade}</span>'
                            f'<span style="font-size:0.82rem;margin-left:8px;color:#9A9278;font-family:monospace;">{srow["Total"]:.1f}</span>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

            base_cols = ["name", "code", "market", "sector",
                         "Growth", "Value", "Quality", "Trend", "Total"]
            if "Risk" in fdf.columns:
                base_cols.insert(-1, "Risk")
            extra_cols = [c for c in ["RSI", "week52_pos", "entry_signal"] if c in fdf.columns]
            display = (
                fdf.reset_index()[base_cols + extra_cols]
                .sort_values("Total", ascending=False, kind="stable")
                .reset_index(drop=True)
            )
            display.insert(0, "순위", range(1, len(display) + 1))

            display["종목"] = display["name"] + " (" + display["code"] + ")"
            display["성장"] = display["Growth"].apply(
                lambda x: "—" if x == 0 else f"{color_score(x)} {x:.1f}"
            )
            display["가치"] = display["Value"].apply(
                lambda x: f"⚪ {x:.1f}" if abs(x - 37.5) < 0.1 else f"{color_score(x)} {x:.1f}"
            )
            display["펀더멘털"] = display["Quality"].apply(
                lambda x: f"⚪ {x:.1f}" if abs(x - 50.0) < 0.1 else f"{color_score(x)} {x:.1f}"
            )
            display["추세"] = display["Trend"].apply(lambda x: f"{color_score(x)} {x:.1f}")
            if "Risk" in display.columns:
                display["리스크"] = display["Risk"].apply(lambda x: f"{color_score(x)} {x:.1f}")
            display["등급"] = display["Total"].apply(
                lambda x: investment_grade(x, grade_thresholds)
            )
            display["데이터"] = display.apply(data_quality_label, axis=1)

            _signal_icon = {"강세후보": "🟢 강세 후보", "관심": "🔵 관심",
                            "과열주의": "🔴 과열주의", "대기": "⚪ 대기", "확인필요": "❓ 확인필요"}
            if "entry_signal" in display.columns:
                display["기술신호"] = display["entry_signal"].map(lambda x: _signal_icon.get(x, x))
            if "RSI" in display.columns:
                display["RSI"] = display["RSI"].apply(lambda x: f"{x:.0f}" if pd.notna(x) else "—")
            if "week52_pos" in display.columns:
                display["52주위치"] = display["week52_pos"].apply(lambda x: f"{x:.0f}%" if pd.notna(x) else "—")

            show_cols = ["순위", "종목", "market", "sector", "성장", "가치", "펀더멘털", "추세"]
            if "리스크" in display.columns:
                show_cols += ["리스크"]
            show_cols += ["Total", "등급"]
            if "기술신호" in display.columns:
                show_cols += ["기술신호", "RSI", "52주위치"]
            show_cols += ["데이터"]

            st.caption("💡 종목명 클릭 → 분석 팝업 | 헤더 정렬은 '종목 정렬' 셀렉트박스 사용")

            # ── 모바일 카드 목록 (CSS로 모바일에서만 표시) ───────────────────
            _grade_thresh_card = grade_thresholds
            _cards_html = ['<div class="ql-card-list">']
            for _, _crow in display.iterrows():
                _cname   = str(_crow["종목"]).split("(")[0].strip()
                _csector = str(_crow.get("sector", ""))
                _ctrend  = float(_crow.get("Trend", 0)) if "Trend" in _crow else 0.0
                _cbull   = (_csector in _bull_sectors_main) and (_ctrend >= 65)
                _cards_html.append(_mobile_card_html(
                    rank=int(_crow["순위"]),
                    name=_cname,
                    sector=_csector,
                    total=float(_crow["Total"]),
                    grade=str(_crow["등급"]),
                    is_bull=_cbull,
                ))
            _cards_html.append('</div>')
            st.markdown("\n".join(_cards_html), unsafe_allow_html=True)

            # ── 커스텀 클릭 테이블 헤더 (데스크톱) ──────────────────────────
            _GCOLS = [0.35, 1.9, 0.65, 1.0, 0.7, 0.7, 0.75, 0.7, 0.7, 0.75, 0.65]
            _GHEADS = ["순위", "종목명 ↗클릭", "시장", "업종", "성장", "가치", "펀더멘털", "추세", "리스크", "종합", "등급"]
            st.markdown("""
<style>
/* 종목명 tertiary 버튼 — 텍스트 링크 스타일 */
div[data-testid="stHorizontalBlock"] button[kind="tertiary"] {
    color: #F0C040 !important;
    padding: 2px 4px !important;
    font-size: 0.88rem !important;
    text-align: left !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    min-height: 44px !important;
    font-family: 'Noto Sans KR', sans-serif !important;
}
div[data-testid="stHorizontalBlock"] button[kind="tertiary"]:hover {
    color: #B8922E !important;
    text-decoration: underline !important;
}
</style>""", unsafe_allow_html=True)

            _hcols = st.columns(_GCOLS)
            for _hc, _hl in zip(_hcols, _GHEADS):
                _hc.markdown(f"<span style='font-size:0.68rem;font-weight:700;color:#6A6050;font-family:monospace;letter-spacing:0.08em;text-transform:uppercase;'>{_hl}</span>",
                             unsafe_allow_html=True)
            st.markdown("<hr style='margin:3px 0;border-color:#2A2A2A;'>",
                        unsafe_allow_html=True)

            # ── 종목 행 렌더링 (종목명 = tertiary 버튼) ──────────────────────
            _grade_colors = {"최우수": "#38B26B", "우수": "#6FCFCF", "보통": "#F0C040", "관찰": "#E03030"}
            for _, _drow in display.iterrows():
                _rc = st.columns(_GCOLS)
                _rc[0].markdown(f"<span style='font-size:0.85rem;color:#4A4438;font-family:monospace;'>{_drow['순위']}</span>",
                                unsafe_allow_html=True)
                _stock_name = str(_drow["종목"]).split("(")[0].strip()
                _stock_code = str(_drow["code"])
                _row_sector = str(_drow.get("sector", ""))
                _row_trend = float(_drow.get("Trend", 0)) if "Trend" in _drow else 0.0
                _is_bull_row = (_row_sector in _bull_sectors_main) and (_row_trend >= 65)
                _btn_label = f"🔥 {_stock_name}" if _is_bull_row else _stock_name
                if _rc[1].button(_btn_label, key=f"stk_{_stock_code}", type="tertiary",
                                 use_container_width=True):
                    _clicked_row = fdf.reset_index()[fdf.reset_index()["code"] == _stock_code]
                    if not _clicked_row.empty:
                        _show_stock_dialog(_clicked_row.iloc[0], df, fdf, grade_thresholds,
                                           sector_info=sector_info)
                _rc[2].markdown(f"<span style='font-size:0.82rem;'>{_drow['market']}</span>",
                                unsafe_allow_html=True)
                _rc[3].markdown(f"<span style='font-size:0.82rem;'>{_drow['sector']}</span>",
                                unsafe_allow_html=True)
                _rc[4].markdown(f"<span style='font-size:0.82rem;'>{_drow['성장']}</span>",
                                unsafe_allow_html=True)
                _rc[5].markdown(f"<span style='font-size:0.82rem;'>{_drow['가치']}</span>",
                                unsafe_allow_html=True)
                _rc[6].markdown(f"<span style='font-size:0.82rem;'>{_drow['펀더멘털']}</span>",
                                unsafe_allow_html=True)
                _rc[7].markdown(f"<span style='font-size:0.82rem;'>{_drow['추세']}</span>",
                                unsafe_allow_html=True)
                _rc[8].markdown(f"<span style='font-size:0.82rem;'>{_drow['리스크']}</span>",
                                unsafe_allow_html=True)
                _total_v = float(_drow["Total"])
                _rc[9].markdown(
                    f"<span style='font-size:0.85rem;font-weight:700;'>{_total_v:.1f}</span>",
                    unsafe_allow_html=True)
                _grade = str(_drow["등급"])
                _gcfg = GRADE_CONFIG.get(_grade, {"bg": "#2A2A2A", "text": "#9A9278", "border": "#3A3A3A"})
                _gcfg_bg, _gcfg_text, _gcfg_border = _gcfg["bg"], _gcfg["text"], _gcfg["border"]
                _rc[10].markdown(
                    f"<span style='background:{_gcfg_bg};color:{_gcfg_text};border:1px solid {_gcfg_border};padding:3px 7px;"
                    f"border-radius:2px;font-size:0.72rem;font-weight:700;font-family:monospace;text-transform:uppercase;letter-spacing:0.06em;'>{_grade}</span>",
                    unsafe_allow_html=True)


    # ── Tab 2: 섹터 현황 ──────────────────────────────────────────────────────
    if sel_page == "섹터 현황":
        st.markdown(
            "<div style='font-size:1.05rem;font-weight:700;margin-bottom:2px;'>섹터 현황</div>"
            "<div style='font-size:0.8rem;color:#6A6050;margin-bottom:16px;'>"
            "업종별 최근 5일 수익률 · 평균 점수 · 대표 종목</div>",
            unsafe_allow_html=True,
        )

        if is_empty:
            st.warning("필터 조건에 맞는 종목이 없습니다.")
        else:
            # ── 섹터 카드 그리드 ──────────────────────────────────────────────
            sec_returns  = sector_info.get("sector_returns", {})
            bull_set     = set(sector_info.get("bull_sectors", []))
            sec_top      = sector_info.get("sector_top", {})
            sec_avg_score = (
                fdf.groupby("sector")["Total"].mean()
                .round(1).to_dict()
            )

            # 정렬 옵션
            _sort_opts = {
                "수익률 ↓":  ("return",  True),
                "수익률 ↑":  ("return",  False),
                "점수 ↓":    ("score",   True),
                "점수 ↑":    ("score",   False),
                "가나다 순": ("name",    False),
            }
            sort_label = st.radio(
                "정렬 기준",
                list(_sort_opts.keys()),
                index=0,
                horizontal=True,
                key="sector_sort",
                label_visibility="collapsed",
            )
            sort_key, sort_desc = _sort_opts[sort_label]

            _sector_set = set(list(sec_returns.keys()) + list(sec_avg_score.keys()))
            if sort_key == "return":
                all_sectors = sorted(_sector_set, key=lambda s: sec_returns.get(s) or -999, reverse=sort_desc)
            elif sort_key == "score":
                all_sectors = sorted(_sector_set, key=lambda s: sec_avg_score.get(s) or 0, reverse=sort_desc)
            else:
                all_sectors = sorted(_sector_set)

            n_sec_cols = 3
            for row_s in range(0, len(all_sectors), n_sec_cols):
                row_secs = all_sectors[row_s:row_s + n_sec_cols]
                scols = st.columns(n_sec_cols)
                for sc, sec in zip(scols, row_secs):
                    ret     = sec_returns.get(sec)
                    score   = sec_avg_score.get(sec)
                    tops    = sec_top.get(sec, [])
                    is_bull = sec in bull_set

                    ret_val   = ret or 0
                    ret_arrow = "▲" if ret_val > 0.3 else "▼" if ret_val < -0.3 else "◆"
                    ret_str   = f"{ret_arrow} {ret_val:+.1f}%" if ret is not None else "—"
                    ret_color = "#38B26B" if ret_val > 0.3 else "#E03030" if ret_val < -0.3 else "#9A9278"
                    score_str = f"{score:.0f}" if score is not None else "—"

                    # 수익률 미니 바 (폭 = abs(ret)/5 * 100%, 최대 100%)
                    bar_pct   = min(abs(ret_val) / 5 * 100, 100)
                    bar_color = ret_color

                    # 대표 종목 최대 3개
                    top_html = ""
                    for i, (nm, tr) in enumerate(tops[:3]):
                        tc = "#38B26B" if tr >= 0 else "#E03030"
                        top_html += (
                            f"<div style='display:flex;justify-content:space-between;"
                            f"padding:2px 0;'>"
                            f"<span style='font-size:0.75rem;color:#9A9278;'>{nm}</span>"
                            f"<span style='font-size:0.75rem;font-family:monospace;"
                            f"color:{tc};font-weight:600;'>{tr:+.1f}%</span></div>"
                        )

                    sc.markdown(
                        f"<div style='background:#111;border:1px solid #2A2A2A;"
                        f"border-top:3px solid {ret_color};"
                        f"border-radius:4px;padding:14px 16px;margin-bottom:8px;'>"
                        # 섹터명
                        f"<div style='font-size:0.88rem;font-weight:700;color:#E8E0CC;"
                        f"margin-bottom:10px;letter-spacing:0.02em;'>{sec}</div>"
                        # 수익률 + 점수
                        f"<div style='display:flex;justify-content:space-between;"
                        f"align-items:flex-end;margin-bottom:8px;'>"
                        f"<div>"
                        f"<div style='font-size:0.62rem;color:#6A6050;font-family:monospace;"
                        f"letter-spacing:0.08em;margin-bottom:2px;'>5일 수익률</div>"
                        f"<div style='font-size:1.4rem;font-weight:800;font-family:monospace;"
                        f"color:{ret_color};line-height:1;'>{ret_str}</div>"
                        f"</div>"
                        f"<div style='text-align:right;'>"
                        f"<div style='font-size:0.62rem;color:#6A6050;font-family:monospace;"
                        f"letter-spacing:0.08em;margin-bottom:2px;'>종합 점수</div>"
                        f"<div style='font-size:1.4rem;font-weight:800;font-family:monospace;"
                        f"color:#F0C040;line-height:1;'>{score_str}</div>"
                        f"</div></div>"
                        # 미니 바
                        f"<div style='background:#1A1A1A;border-radius:2px;height:3px;"
                        f"margin-bottom:10px;'>"
                        f"<div style='background:{bar_color};width:{bar_pct:.0f}%;height:3px;"
                        f"border-radius:2px;'></div></div>"
                        # 대표 종목
                        f"<div style='border-top:1px solid #1E1E1E;padding-top:8px;'>"
                        f"{top_html}</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

            st.markdown("---")

            # ── 업종별 평균 점수 가로 막대 차트 ──────────────────────────────
            st.markdown(
                "<div style='font-size:0.85rem;font-weight:700;color:#E8E0CC;"
                "margin-bottom:8px;'>업종별 평균 종합 점수</div>"
                "<div style='font-size:0.75rem;color:#6A6050;margin-bottom:12px;'>"
                "점수가 높을수록 성장·가치·펀더멘털·추세·리스크 종합 평가가 좋은 업종</div>",
                unsafe_allow_html=True,
            )
            try:
                sec_avg_df = (
                    fdf.groupby("sector")["Total"].mean()
                    .sort_values(ascending=True)
                    .reset_index()
                )
                sec_avg_df.columns = ["업종", "평균점수"]
                fig_sec = px.bar(
                    sec_avg_df, x="평균점수", y="업종", orientation="h",
                    color="평균점수",
                    color_continuous_scale=["#E03030", "#F0C040", "#38B26B"],
                    range_color=[30, 70],
                )
                fig_sec.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="#0D0D0D",
                    font=dict(family="monospace", size=10, color="#9A9278"),
                    xaxis=dict(gridcolor="rgba(255,255,255,0.05)", range=[0, 80],
                               title="평균 점수 (0~100)", tickfont=dict(size=9)),
                    yaxis=dict(gridcolor="rgba(255,255,255,0.05)", title="",
                               tickfont=dict(size=10)),
                    coloraxis_showscale=False,
                    height=max(320, len(sec_avg_df) * 28),
                    margin=dict(l=110, r=16, t=16, b=36),
                    hoverlabel=dict(bgcolor="#1A1A1A", bordercolor="#3A3A3A",
                                    font=dict(size=11, family="monospace")),
                )
                st.plotly_chart(fig_sec, use_container_width=True)
            except Exception as e:
                st.warning(f"업종별 차트 오류: {e}")

    # ── Tab 4: 시장 코멘트 ────────────────────────────────────────────────────
    if sel_page == "💬 코멘트":
        st.subheader("💬 시장 코멘트 및 추천 근거")

        if is_empty:
            st.warning("필터 조건에 맞는 종목이 없습니다.")
        else:
            st.markdown(market_commentary(fdf))

        st.subheader("🔖 참고 벤치마크 플랫폼")
        st.caption("QuantLab 개발 시 참고한 국내외 주식 스크리너 플랫폼 10곳")

        bm_cols = st.columns(2)
        for i, p in enumerate(BENCHMARK_PLATFORMS):
            with bm_cols[i % 2]:
                st.markdown(
                    f'<div style="border:1px solid var(--border-subtle,rgba(128,128,128,0.2));'
                    f'border-radius:8px;padding:12px 14px;margin-bottom:10px;">'
                    f'<strong>{i+1}. {p["name"]}</strong><br>'
                    f'<code style="font-size:0.75rem;opacity:0.7">{p["url"]}</code><br>'
                    f'<small style="color:var(--text-muted,#888)">{p["feature"]}</small>'
                    f'</div>',
                    unsafe_allow_html=True,
                )


    # ── Tab 5: IC 검증 ────────────────────────────────────────────────────────
    if sel_page == "IC검증":
        st.markdown(
            "<div style='font-size:1.05rem;font-weight:700;margin-bottom:2px;'>IC검증</div>"
            "<div style='font-size:0.8rem;color:#6A6050;margin-bottom:12px;'>"
            "스코어링 모델이 실제로 수익률을 예측하는지 확인하는 화면</div>",
            unsafe_allow_html=True,
        )

        # ── 초보자 해설 카드 ─────────────────────────────────────────────────
        with st.expander("🔰 이 화면이 뭔지 모르겠다면 여기를 펼치세요", expanded=True):
            st.markdown("""
**핵심 질문: "이 앱의 점수가 진짜 맞나요?"**

이 화면은 그 질문에 답합니다. 점수가 높은 종목이 실제로 이후 주가가 올랐는지를 과거 데이터로 검증합니다.

---

**보는 방법 (숫자 의미)**

| 지표 | 쉬운 설명 | 좋은 기준 |
|---|---|---|
| **IC 평균** | 예측 정확도. 1에 가까울수록 완벽 | **0.10 이상**이면 믿을 만함 |
| **IR** | 예측이 얼마나 일관적인지 | **0.5 이상**이면 안정적 |

**IC가 양수(+)** → 점수 높은 종목이 실제로 올랐다는 뜻 ✅
**IC가 음수(−)** → 점수가 오히려 반대로 작동했다는 뜻 ⚠️
**IC가 0에 가까움** → 해당 팩터는 수익률 예측에 도움이 안 됨

---

**결론을 어떻게 쓰나요?**
- Trend 3M IC ≈ 0.10, IR > 1.5 → **"추세 점수는 3개월 수익률 예측에 유효"** → 가중치 유지
- Risk IC < 0.05 → **"리스크 팩터 신뢰도 낮음"** → 가중치 조정 검토
""")

        st.markdown("---")
        st.subheader("IC/IR 백테스트 — 점수의 예측력 검증")
        st.markdown(
            "- **IC (정보계수)**: 점수 순위와 실제 주가 수익률 순위의 일치도 (−1 ~ +1)\n"
            "  - `IC > 0.10`: 유의미한 예측력 ✅  |  `0.05~0.10`: 약한 신호 🟡  |  `< 0.05`: 무의미 🔴\n"
            "- **IR (정보비율)**: IC가 얼마나 안정적으로 나오는지 (IC 평균 ÷ IC 변동성)\n"
            "  - `IR > 0.5`: 안정적 ✅  |  `0.3~0.5`: 보통 🟡  |  `< 0.3`: 불안정 🔴"
        )

        st.markdown("#### 🔄 가격 축 히스토리컬 IC/IR (Trend·Risk)")
        st.caption("FDR 가격 데이터만 사용 — 과거 N분기 × Spearman IC 산출")
        n_qtrs = st.slider("분석 분기 수", min_value=4, max_value=16, value=8, step=1,
                           help="몇 분기 전까지 소급해 IC를 계산할지 설정합니다. 분기 수가 많을수록 계산 시간이 길어집니다.")
        if st.button("가격 IC 백테스트 실행", key="btn_price_bt"):
            with st.spinner(f"{n_qtrs}분기 Trend·Risk IC 계산 중... (약 {n_qtrs * 4}초)"):
                try:
                    from src.backtest import run_price_ic_backtest, price_ic_summary, save_backtest
                    codes = df["code"].astype(str).tolist()
                    as_of = _last_updated().split(" ")[0] or pd.Timestamp.today().strftime("%Y-%m-%d")
                    bt = run_price_ic_backtest(codes, as_of, n_quarters=n_qtrs)
                    if bt.empty:
                        st.warning("충분한 가격 데이터가 없습니다.")
                    else:
                        save_backtest(bt)
                        st.session_state["price_bt"] = bt
                except Exception as e:
                    st.error(f"백테스트 실패: {e}")

        # 캐시 로드
        from src.backtest import load_backtest, price_ic_summary, BT_OUTPUT
        _bt_ss = st.session_state.get("price_bt")
        bt_cached = _bt_ss if (_bt_ss is not None) else load_backtest(BT_OUTPUT)
        if bt_cached is not None and not bt_cached.empty:
            summary = price_ic_summary(bt_cached)
            st.dataframe(
                summary.style.format({"IC 평균": "{:.4f}", "IC 표준편차": "{:.4f}", "IR": "{:.3f}"}),
                use_container_width=True,
            )
            try:
                fig_ic = go.Figure()
                for col in bt_cached.columns:
                    fig_ic.add_trace(go.Scatter(
                        x=bt_cached.index, y=bt_cached[col],
                        name=col, mode="lines+markers",
                    ))
                fig_ic.add_hline(y=0.10, line_dash="dash", line_color="green",
                                 annotation_text="IC=0.10 (유의미)")
                fig_ic.add_hline(y=0.05, line_dash="dot", line_color="orange",
                                 annotation_text="IC=0.05 (약한 신호)")
                fig_ic.add_hline(y=0, line_color="gray", line_width=1)
                fig_ic.update_layout(
                    title="분기별 IC 추이", **PLOTLY_BASE,
                    xaxis=dict(tickangle=-45, tickfont=dict(size=9),
                               gridcolor="rgba(128,128,128,0.1)"),
                    legend=dict(orientation="h", y=-0.25, font=dict(size=9)),
                )
                st.plotly_chart(fig_ic, use_container_width=True)
            except Exception:
                pass
        else:
            st.info("위 버튼을 눌러 백테스트를 실행하세요.")

        st.markdown("#### ⏳ 전 축 단일 기간 IC (CSV 생성 후 경과 시)")
        st.caption("1개월·3개월·6개월 수익률과 현재 점수의 IC — 기간 경과 후 자동 계산")
        if st.button("단일 기간 IC 확인", key="btn_single_ic"):
            with st.spinner("포워드 수익률 계산 중..."):
                try:
                    from src.backtest import run_single_ic_check
                    ic_df = run_single_ic_check()
                    st.session_state["single_ic"] = ic_df
                except Exception as e:
                    st.error(f"IC 계산 실패: {e}")

        ic_cached = st.session_state.get("single_ic")
        if ic_cached is not None and not ic_cached.empty:
            st.dataframe(ic_cached.style.format(
                {c: "{:.4f}" for c in ic_cached.columns if c not in ["상태", "경과일"]}
            ), use_container_width=True)
        else:
            st.info("위 버튼을 눌러 IC를 확인하세요.\n\n"
                    "CSV 생성 후 충분한 기간(1개월 이상)이 지나야 의미 있는 IC가 산출됩니다.")

        st.markdown("---")
        st.markdown("#### 📖 IC/IR 해석 가이드")
        guide_cols = st.columns(3)
        with guide_cols[0]:
            st.markdown("**IC 수준**")
            st.markdown("- `> 0.10` : 유의미한 예측력 ✅\n- `0.05~0.10` : 약한 신호 🟡\n- `< 0.05` : 무의미 🔴")
        with guide_cols[1]:
            st.markdown("**IR 수준**")
            st.markdown("- `> 0.5` : 안정적 신호 ✅\n- `0.3~0.5` : 사용 가능 🟡\n- `< 0.3` : 불안정 🔴")
        with guide_cols[2]:
            st.markdown("**주의사항**")
            st.markdown("- 과거 IC가 미래를 보장하지 않음\n- 8분기 = 통계적으로 낮은 신뢰도\n- 단독 의사결정 도구로 사용 금지")


    # ── Tab 6: 글로벌 지표 ────────────────────────────────────────────────────
    if sel_page == "글로벌 지표":
        _render_macro_tab()


def _render_macro_tab() -> None:
    """매크로 레이더 탭 — 글로벌 지수·원자재·채권·환율·반등 신호"""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent.parent / ".env")
    except ImportError:
        pass

    @st.cache_data(ttl=3600, show_spinner=False)
    def _load_macro(period: int) -> dict:
        from src.macro_loader import get_all_macro
        return get_all_macro(period_days=period)

    st.markdown(
        "<div style='font-size:1.05rem;font-weight:700;margin-bottom:4px;'>매크로 레이더"
        " <span style='font-size:0.75rem;font-weight:400;color:#6A6050;font-family:monospace;'>"
        "1시간 캐시 · Yahoo Finance / FDR</span></div>",
        unsafe_allow_html=True,
    )

    _period_options = {"3개월": 90, "6개월": 180, "1년": 365, "2년": 730}
    period_label = st.radio(
        "조회 기간",
        list(_period_options.keys()),
        index=2,
        horizontal=True,
        key="macro_period_label",
        label_visibility="collapsed",
    )
    period = _period_options[period_label]

    with st.spinner("글로벌 지표 수집 중..."):
        macro = _load_macro(period)

    indicators      = macro.get("indicators", {})
    summary_df      = macro.get("summary", None)
    sector_signals  = macro.get("sector_signals", None)
    rebound_signals = macro.get("rebound_signals", None)
    base_rate       = macro.get("base_rate", None)
    construction    = macro.get("construction", None)

    from src.macro_loader import INDICATORS as IND_META, INDICATOR_CATEGORIES
    valid_inds = {k: v for k, v in indicators.items() if not v.empty and "Close" in v.columns}

    # ── 비교 차트 (정규화) ──────────────────────────────────────────────────
    with st.expander("📊 지표 비교 (정규화 차트)", expanded=False):
        st.caption("선택한 지표들을 기간 시작일 = 100 으로 정규화하여 한 차트에 겹쳐 표시")
        comp_options = [(k, IND_META.get(k, {}).get("label", k)) for k in valid_inds.keys()]
        comp_keys = st.multiselect(
            "비교할 지표 (2~5개 권장)",
            options=[k for k, _ in comp_options],
            default=[k for k in ["SP500", "KOSPI", "Gold"] if k in valid_inds],
            format_func=lambda k: dict(comp_options).get(k, k),
            key="macro_compare_select",
            label_visibility="collapsed",
        )
        if len(comp_keys) >= 2:
            fig_cmp = go.Figure()
            for k in comp_keys:
                s = valid_inds[k]["Close"].dropna()
                if s.empty:
                    continue
                base = float(s.iloc[0])
                if base == 0:
                    continue
                norm = s / base * 100
                meta = IND_META.get(k, {})
                fig_cmp.add_trace(go.Scatter(
                    x=norm.index, y=norm.values,
                    mode="lines",
                    line=dict(color=meta.get("color", "#F0C040"), width=2),
                    name=meta.get("label", k),
                    hovertemplate="%{x|%Y-%m-%d}<br>" + meta.get("label", k) + ": %{y:.1f}<extra></extra>",
                ))
            fig_cmp.add_hline(y=100, line_dash="dot", line_color="#6A6050", line_width=1)
            fig_cmp.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#0D0D0D",
                font=dict(family="monospace", size=10, color="#9A9278"),
                margin=dict(l=50, r=20, t=24, b=40),
                height=380,
                xaxis=dict(showgrid=False, tickfont=dict(size=9)),
                yaxis=dict(gridcolor="rgba(255,255,255,0.05)",
                           title="정규화 지수 (시작일=100)",
                           tickfont=dict(size=9)),
                legend=dict(orientation="h", y=1.06, x=0,
                            font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
                hovermode="x unified",
            )
            st.plotly_chart(fig_cmp, use_container_width=True, theme=None,
                            key="macro_compare_chart")
        elif comp_keys:
            st.info("비교를 위해 2개 이상의 지표를 선택하세요.")

    st.markdown("---")

    # ── 반등 신호 스캐너 ─────────────────────────────────────────────────────
    st.markdown("#### 반등 신호 스캐너")
    st.caption("RSI(14) · 52주 낙폭 · MA200 대비 위치 기준 — 참고용 기술적 지표")

    _SIGNAL_STYLE = {
        "강한 반등 후보": ("#38B26B", "#1A3A20"),
        "반등 후보":      ("#6FCFCF", "#0D2530"),
        "관심":           ("#F0C040", "#2A1A00"),
        "중립":           ("#6A6050", "#111111"),
        "과매수":         ("#E03030", "#2A0A0A"),
    }

    if rebound_signals is not None and not rebound_signals.empty:
        # 필터 옵션
        f_col1, f_col2 = st.columns([3, 1])
        with f_col1:
            _filter_opts = {
                "강한 반등 후보만":  ["강한 반등 후보"],
                "반등 후보 이상":    ["강한 반등 후보", "반등 후보"],
                "관심 이상":         ["강한 반등 후보", "반등 후보", "관심"],
                "중립 제외 전체":    ["강한 반등 후보", "반등 후보", "관심", "과매수"],
            }
            filter_label = st.radio(
                "신호 필터",
                list(_filter_opts.keys()),
                index=2,
                horizontal=True,
                key="rebound_filter",
                label_visibility="collapsed",
            )
        with f_col2:
            sort_by_rsi = st.checkbox("RSI 낮은 순", value=False, key="rebound_sort_rsi")

        allowed_signals = _filter_opts[filter_label]
        filtered = rebound_signals[rebound_signals["신호"].isin(allowed_signals)].copy()
        if sort_by_rsi:
            filtered = filtered.sort_values("RSI14", na_position="last")

        highlight = filtered.head(8)
        if not highlight.empty:
            h_cols = st.columns(min(len(highlight), 4))
            for hc, (_, hr) in zip(h_cols * 2, highlight.iterrows()):
                sig = hr["신호"]
                txt_color, bg_color = _SIGNAL_STYLE.get(sig, ("#9A9278", "#111"))
                rsi_val = hr["RSI14"]
                dd_val  = hr["52주낙폭"]
                rsi_str = f"RSI {rsi_val:.0f}" if rsi_val is not None else "RSI —"
                dd_str  = f"52w {dd_val:+.0f}%" if dd_val is not None else ""
                val = hr["현재값"]
                val_str = f"{val:,.0f}" if val >= 100 else f"{val:.2f}"
                hc.markdown(
                    f"<div style='background:{bg_color};border:1px solid #2A2A2A;"
                    f"border-left:3px solid {txt_color};border-radius:4px;"
                    f"padding:10px 12px;margin-bottom:6px;'>"
                    f"<div style='font-size:0.65rem;color:#6A6050;font-family:monospace;'>{hr['지표']}</div>"
                    f"<div style='font-size:1.0rem;font-weight:700;font-family:monospace;color:{txt_color};'>"
                    f"{val_str} <span style='font-size:0.7rem;'>{hr['단위']}</span></div>"
                    f"<div style='font-size:0.7rem;color:{txt_color};font-family:monospace;margin-top:2px;'>{sig}</div>"
                    f"<div style='font-size:0.65rem;color:#6A6050;font-family:monospace;'>{rsi_str} · {dd_str}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        # 전체 신호 테이블
        with st.expander("전체 반등 신호 테이블"):
            display_cols = ["지표", "현재값", "단위", "RSI14", "MA50대비", "MA200대비", "52주낙폭", "신호"]
            tbl = rebound_signals[display_cols].copy()
            st.dataframe(
                tbl.style.format({
                    "현재값":   "{:,.2f}",
                    "RSI14":    lambda x: f"{x:.1f}" if x is not None and not pd.isna(x) else "—",
                    "MA50대비": lambda x: f"{x:+.1f}%" if x is not None and not pd.isna(x) else "—",
                    "MA200대비":lambda x: f"{x:+.1f}%" if x is not None and not pd.isna(x) else "—",
                    "52주낙폭": lambda x: f"{x:+.1f}%" if x is not None and not pd.isna(x) else "—",
                }),
                use_container_width=True,
                hide_index=True,
            )
    else:
        st.info("반등 신호 계산에 필요한 데이터가 부족합니다. 기간을 365일로 늘려보세요.")

    st.markdown("---")

    # ── 카테고리별 차트 렌더링 헬퍼 ─────────────────────────────────────────
    try:
        from src.macro_loader import compute_rsi as _compute_rsi
    except Exception:
        _compute_rsi = None

    def _make_chart(key: str, height: int = 280) -> "go.Figure | None":
        if key not in valid_inds:
            return None
        df_ind = valid_inds[key]
        meta   = IND_META.get(key, {})
        s = df_ind["Close"].dropna()
        if s.empty:
            return None

        color = meta.get("color", "#F0C040")
        try:
            r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
            fill_color = f"rgba({r},{g},{b},0.12)"
        except Exception:
            fill_color = "rgba(240,192,64,0.12)"

        current_val = float(s.iloc[-1])
        unit = meta.get("unit", "")

        # % 변화율 계산
        def _pct(n: int) -> float | None:
            if len(s) <= n:
                return None
            base = float(s.iloc[-n])
            return (current_val / base - 1) * 100 if base != 0 else None

        chg_1m  = _pct(22)
        chg_3m  = _pct(66)
        chg_1y  = _pct(252)

        # RSI
        rsi_val = None
        if _compute_rsi is not None and len(s) >= 20:
            try:
                rsi_series = _compute_rsi(s)
                v = rsi_series.iloc[-1]
                if not pd.isna(v):
                    rsi_val = float(v)
            except Exception:
                pass

        fig = go.Figure()

        # 가격 영역
        fig.add_trace(go.Scatter(
            x=s.index, y=s.values,
            mode="lines",
            line=dict(color=color, width=2),
            fill="tozeroy",
            fillcolor=fill_color,
            hovertemplate=f"%{{x|%Y-%m-%d}}<br>%{{y:,.2f}} {unit}<extra></extra>",
            name="가격",
        ))

        # MA50
        ma50 = s.rolling(50, min_periods=15).mean()
        if not ma50.dropna().empty:
            fig.add_trace(go.Scatter(
                x=ma50.index, y=ma50.values,
                mode="lines",
                line=dict(color="#F0C040", width=1.2, dash="dot"),
                name="MA50",
                hovertemplate="MA50: %{y:,.2f}<extra></extra>",
            ))

        # MA200
        ma200 = s.rolling(200, min_periods=60).mean()
        if not ma200.dropna().empty:
            fig.add_trace(go.Scatter(
                x=ma200.index, y=ma200.values,
                mode="lines",
                line=dict(color="#6A6050", width=1.2, dash="dash"),
                name="MA200",
                hovertemplate="MA200: %{y:,.2f}<extra></extra>",
            ))

        # RSI 과매도 구간 (< 30) 하이라이트
        if _compute_rsi is not None and len(s) >= 20:
            try:
                rsi_vals = _compute_rsi(s)
                # 과매도 구간을 연속 범위로 묶어 hrect 표시
                in_zone = rsi_vals < 30
                start = None
                for dt, val in in_zone.items():
                    if val and start is None:
                        start = dt
                    elif not val and start is not None:
                        fig.add_vrect(
                            x0=start, x1=dt,
                            fillcolor="rgba(56,178,107,0.10)",
                            layer="below", line_width=0,
                        )
                        start = None
                if start is not None:
                    fig.add_vrect(
                        x0=start, x1=s.index[-1],
                        fillcolor="rgba(56,178,107,0.10)",
                        layer="below", line_width=0,
                    )
            except Exception:
                pass

        # 우측 상단 annotation: 현재값 + 변화율 + RSI
        chg_color = (
            "#38B26B" if chg_1m and chg_1m >= 0
            else "#E03030" if chg_1m and chg_1m < 0
            else "#6A6050"
        )
        chg_str   = f"{chg_1m:+.1f}%" if chg_1m is not None else "—"
        chg3_str  = f"3M {chg_3m:+.1f}%" if chg_3m is not None else ""
        rsi_str   = f"RSI {rsi_val:.0f}" if rsi_val is not None else ""
        rsi_color = (
            "#38B26B" if rsi_val and rsi_val < 35
            else "#E03030" if rsi_val and rsi_val > 65
            else "#9A9278"
        )

        # 타이틀: 지표명 + 현재값
        val_str = f"{current_val:,.2f}" if current_val < 10000 else f"{current_val:,.0f}"
        title_text = (
            f"<b>{meta.get('label', key)}</b>  "
            f"<span style='font-size:1.1em;'>{val_str}</span> "
            f"<span style='color:{chg_color};'>{chg_str}</span>"
        )

        annotations = []
        if chg3_str or rsi_str:
            sub_parts = []
            if chg3_str:
                sub_parts.append(f"<span style='color:#9A9278;'>{chg3_str}</span>")
            if rsi_str:
                sub_parts.append(f"<span style='color:{rsi_color};'>{rsi_str}</span>")
            annotations.append(dict(
                text=" · ".join(sub_parts),
                xref="paper", yref="paper",
                x=0.0, y=1.0,
                xanchor="left", yanchor="bottom",
                showarrow=False,
                font=dict(size=9, family="monospace"),
                bgcolor="rgba(0,0,0,0)",
            ))

        fig.update_layout(
            title=dict(text=title_text, font=dict(size=11, family="monospace"), x=0, y=0.97),
            showlegend=True,
            legend=dict(
                orientation="h",
                x=1, y=1, xanchor="right", yanchor="top",
                font=dict(size=8, color="#6A6050"),
                bgcolor="rgba(0,0,0,0)",
                itemsizing="constant",
            ),
            annotations=annotations,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="#0D0D0D",
            font=dict(family="monospace", size=9, color="#9A9278"),
            margin=dict(l=48, r=12, t=52, b=28),
            height=height,
            xaxis=dict(
                showgrid=False,
                tickfont=dict(size=8),
                linecolor="#2A2A2A",
                tickcolor="#2A2A2A",
            ),
            yaxis=dict(
                gridcolor="rgba(255,255,255,0.05)",
                tickfont=dict(size=8),
                tickformat=",.2f",
                linecolor="#2A2A2A",
                zeroline=False,
            ),
            hovermode="x unified",
            hoverlabel=dict(
                bgcolor="#1A1A1A",
                bordercolor="#3A3A3A",
                font=dict(size=10, family="monospace"),
            ),
        )
        return fig

    def _render_category_charts(
        cat_name: str, keys: list[str],
        n_cols: int = 3, height: int = 280,
        expanded: bool = True,
    ) -> None:
        cat_keys = [k for k in keys if k in valid_inds]
        missing  = [k for k in keys if k not in valid_inds]

        if not cat_keys and not missing:
            return

        title_cnt = f"{len(cat_keys)}/{len(keys)}"
        with st.expander(f"**{cat_name}** · {title_cnt}", expanded=expanded):
            if not cat_keys:
                st.caption("이 카테고리는 데이터를 불러오지 못했습니다.")
            else:
                for row_start in range(0, len(cat_keys), n_cols):
                    row_keys = cat_keys[row_start:row_start + n_cols]
                    ccols = st.columns(n_cols)
                    for idx, cc in enumerate(ccols):
                        if idx < len(row_keys):
                            fig = _make_chart(row_keys[idx], height=height)
                            if fig:
                                cc.plotly_chart(fig, use_container_width=True, theme=None,
                                                key=f"macro_{row_keys[idx]}")
                        else:
                            cc.empty()
            if missing:
                missing_labels = ", ".join(IND_META.get(k, {}).get("label", k) for k in missing)
                st.caption(f"⚠️ 데이터 없음: {missing_labels}")

    # 글로벌 지수만 기본 펼침, 나머지는 접기 (초기 렌더 부담 감소)
    _render_category_charts("글로벌 주요 지수", INDICATOR_CATEGORIES["글로벌 지수"], n_cols=3, height=300, expanded=True)
    _render_category_charts("국내 지수",       INDICATOR_CATEGORIES["국내 지수"],   n_cols=2, height=300, expanded=True)
    _render_category_charts("원자재",          INDICATOR_CATEGORIES["원자재"],     n_cols=3, height=260, expanded=False)
    _render_category_charts("채권·금리",       INDICATOR_CATEGORIES["채권·금리"],   n_cols=2, height=280, expanded=False)
    _render_category_charts("환율",            INDICATOR_CATEGORIES["환율"],       n_cols=3, height=260, expanded=False)
    _render_category_charts("공포·해운",       INDICATOR_CATEGORIES["공포·해운"],   n_cols=2, height=260, expanded=False)
    _render_category_charts("암호화폐",        INDICATOR_CATEGORIES["암호화폐"],   n_cols=2, height=280, expanded=False)
    st.markdown("---")

    # ── 섹터별 매크로 신호 ────────────────────────────────────────────────────
    st.markdown("#### 섹터별 현재 매크로 신호")
    st.caption(f"최근 30일 지표 변화 기준 — 수집 지표: {', '.join(valid_inds.keys()) or '없음'}")

    if sector_signals is not None and not sector_signals.empty:
        _SIG_CLR = {
            "강한 호재": "#38B26B",
            "호재":      "#6FCFCF",
            "중립":      "#6A6050",
            "역풍":      "#E07030",
            "강한 역풍": "#E03030",
        }
        n_sig_cols = 3
        sig_rows = [sector_signals.iloc[i:i+n_sig_cols] for i in range(0, len(sector_signals), n_sig_cols)]
        for sig_row in sig_rows:
            sig_cols = st.columns(n_sig_cols)
            for sc, (_, sr) in zip(sig_cols, sig_row.iterrows()):
                clr = _SIG_CLR.get(sr["signal"], "#6A6050")
                sc.markdown(
                    f"<div style='background:#111;border:1px solid #2A2A2A;border-left:3px solid {clr};"
                    f"border-radius:4px;padding:8px 10px;margin-bottom:6px;'>"
                    f"<div style='font-size:0.8rem;font-weight:700;margin-bottom:2px;'>{sr['sector']}</div>"
                    f"<div style='font-size:0.75rem;color:{clr};font-family:monospace;margin-bottom:4px;'>"
                    f"{sr['signal']}</div>"
                    f"<div style='font-size:0.65rem;color:#6A6050;line-height:1.4;'>{sr['reasons']}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
    else:
        st.info("섹터 신호 계산에 필요한 지표 데이터가 부족합니다.")

    st.markdown("---")

    # ── ECOS 기준금리 ────────────────────────────────────────────────────────
    if base_rate is not None and not base_rate.empty:
        st.markdown("#### 한국은행 기준금리")
        fig_rate = go.Figure()
        fig_rate.add_trace(go.Scatter(
            x=base_rate.index, y=base_rate["Close"].values,
            mode="lines+markers",
            line=dict(color="#F0C040", width=2),
            marker=dict(size=4),
            hovertemplate="%{x|%Y-%m}<br>%{y:.2f}%<extra></extra>",
        ))
        fig_rate.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="-apple-system, 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif", size=10),
            margin=dict(l=30, r=10, t=20, b=20), height=220,
            xaxis=dict(showgrid=False),
            yaxis=dict(gridcolor="rgba(128,128,128,0.1)", ticksuffix="%"),
        )
        st.plotly_chart(fig_rate, use_container_width=True)
    else:
        st.markdown(
            "<div style='background:#111;border:1px solid #2A2A2A;border-radius:4px;"
            "padding:12px 16px;'>"
            "<span style='font-size:0.8rem;'>한국은행 기준금리 활성화: "
            "<code style='color:#F0C040;'>ECOS_API_KEY</code> 환경변수 설정 필요 "
            "(<a href='https://ecos.bok.or.kr' style='color:#6FCFCF;'>ecos.bok.or.kr</a> 무료 가입)</span>"
            "</div>",
            unsafe_allow_html=True,
        )

    # ── KOSIS 건설수주 ────────────────────────────────────────────────────────
    if construction is not None and not construction.empty:
        st.markdown("#### 건설수주 월별 추이 (KOSIS)")
        fig_con = go.Figure()
        fig_con.add_trace(go.Bar(
            x=construction.index, y=construction["Close"].values,
            marker_color="#6FCFCF",
            hovertemplate="%{x|%Y-%m}<br>%{y:,.0f}억원<extra></extra>",
        ))
        fig_con.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="-apple-system, 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif", size=10),
            margin=dict(l=30, r=10, t=20, b=20), height=220,
            xaxis=dict(showgrid=False),
            yaxis=dict(gridcolor="rgba(128,128,128,0.1)"),
        )
        st.plotly_chart(fig_con, use_container_width=True)
    else:
        st.markdown(
            "<div style='background:#111;border:1px solid #2A2A2A;border-radius:4px;"
            "padding:12px 16px;margin-top:8px;'>"
            "<span style='font-size:0.8rem;'>건설수주 통계 활성화: "
            "<code style='color:#F0C040;'>KOSIS_API_KEY</code> 환경변수 설정 필요 "
            "(<a href='https://kosis.kr' style='color:#6FCFCF;'>kosis.kr</a> 무료 가입)</span>"
            "</div>",
            unsafe_allow_html=True,
        )

    # ── 데이터 소스 안내 ─────────────────────────────────────────────────────
    with st.expander("데이터 소스 및 해석 주의사항"):
        st.markdown("""
**지표 목록** (FinanceDataReader / Yahoo Finance, API 키 불필요)
| 카테고리 | 지표 | 심볼 | 용도 |
|---|---|---|---|
| 글로벌 지수 | S&P 500 / NASDAQ / 다우 | ^GSPC / ^IXIC / ^DJI | 미국 증시 전반 |
| 글로벌 지수 | DAX / 니케이 / FTSE / 항셍 | ^GDAXI / ^N225 / ^FTSE / ^HSI | 유럽·아시아 |
| 국내 지수 | KOSPI / KOSDAQ | KS11 / KQ11 | 국내 시장 심리 |
| 원자재 | WTI / 금 / 은 / 구리 | CL=F / GC=F / SI=F / HG=F | 인플레·수요 선행 |
| 채권·금리 | 미국 10Y / 2Y | ^TNX / ^IRX | 할인율·경기침체 시그널 |
| 환율·공포 | 원달러 / VIX | USD/KRW / ^VIX | 안전자산 선호도 |
| 해운 | BDI (발틱건화물지수) | BDI | 글로벌 교역량 선행 |

**반등 신호 기준**
- RSI(14) < 30: 과매도 → 반등 후보 (점수 +3)
- RSI(14) < 40: 약한 과매도 → 관심 (점수 +2)
- 52주 고점 대비 -30% 이하: 깊은 조정 (점수 +2)
- MA200 대비 -15% 이하: 장기 평균 대폭 하회 (점수 +1)
- MA20이 최근 10일 내 MA50 돌파: 단기 황금 크로스 (점수 +1)

**추가 지표** (API 키 필요)
- **ECOS** (한국은행): 기준금리 시계열
- **KOSIS** (통계청): 건설수주 월별 추이

**주의사항**
- 매크로 신호는 참고용이며 종목 스코어링에 반영되지 않습니다.
- 기술적 지표 하나만으로 투자 판단 금지 — 복수 신호 교차 확인 필수.
- BDI는 stooq 소스 — 일부 날짜 공백 발생 가능.
        """)


if __name__ == "__main__":
    main()
