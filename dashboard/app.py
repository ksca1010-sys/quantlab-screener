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
from src.analyst import fetch_consensus, fetch_current_price, fetch_report_titles

st.set_page_config(
    page_title="QuantLab Screener",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

CSV_PATH = Path(__file__).parent.parent / "output" / "stocks_top100.csv"

AXES = ["Growth", "Value", "Quality", "Trend", "Risk"]
AXIS_LABELS = {"Growth": "성장", "Value": "가치", "Quality": "펀더멘털", "Trend": "추세", "Risk": "리스크"}
AXIS_COLORS = {
    "Growth":  "#4CAF50",
    "Value":   "#2196F3",
    "Quality": "#FF9800",
    "Trend":   "#9C27B0",
    "Risk":    "#00BCD4",
    "Total":   "#F44336",
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
    "최우수": {"bg": "#00C853", "text": "#003300", "border": "#00E676", "label": "최우수"},
    "우수":   {"bg": "#1E88E5", "text": "#ffffff", "border": "#42A5F5", "label": "우수"},
    "보통":   {"bg": "#FB8C00", "text": "#ffffff", "border": "#FFA726", "label": "보통"},
    "관찰":   {"bg": "#E53935", "text": "#ffffff", "border": "#EF5350", "label": "관찰"},
}

# Design: shared Plotly layout token
PLOTLY_BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Noto Sans KR, sans-serif", size=12),
    margin=dict(l=40, r=20, t=50, b=40),
    height=350,
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


# ── 세션 상태 초기화 ──────────────────────────────────────────────────────────
def _init_session_state() -> None:
    defaults = {
        "search_query": "",
        "selected_compare": "없음",
        "watchlist": [],
        "tab2_search": "",
        "selected_code": None,  # Tab1 클릭 → Tab2 연동
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ── CSS 주입 (Design) ─────────────────────────────────────────────────────────
def _inject_css() -> None:
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap');

/* Streamlit 기본 UI 제거 */
#MainMenu { visibility: hidden; }
[data-testid="stToolbar"] { display: none !important; }
header[data-testid="stHeader"] { display: none !important; }
footer { visibility: hidden; }

:root {
  --bg-card: rgba(255,255,255,0.06);
  --bg-inset: rgba(0,0,0,0.08);
  --border-subtle: rgba(128,128,128,0.18);
  --text-muted: rgba(128,128,128,0.8);
  --track-bg: rgba(128,128,128,0.15);
  --accent: #2196F3;
}

/* 전체 폰트 */
.stApp, .stMarkdown, [data-testid="stMetricLabel"],
[data-testid="stMetricValue"], [data-testid="stMetricDelta"] {
  font-family: 'Noto Sans KR', sans-serif !important;
}
.stMarkdown p, .stMarkdown li {
  line-height: 1.5;
  word-break: keep-all;
}

/* 탭 바 */
.stTabs [data-baseweb="tab-list"] {
  gap: 2px;
  background: rgba(128,128,128,0.08);
  padding: 4px 6px;
  border-radius: 12px;
  border: 1px solid var(--border-subtle);
}
.stTabs [data-baseweb="tab"] {
  border-radius: 8px;
  padding: 5px 18px;
  font-size: 0.9rem;
  font-weight: 500;
  color: var(--text-muted);
  transition: background 0.15s;
}
.stTabs [aria-selected="true"] {
  background: rgba(33,150,243,0.18) !important;
  color: #64B5F6 !important;
  font-weight: 700;
}

/* 메트릭 카드 */
[data-testid="stMetric"] {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 10px 14px !important;
}

/* 사이드바 */
section[data-testid="stSidebar"] {
  background: rgba(10,10,20,0.3) !important;
  border-right: 1px solid var(--border-subtle);
}
section[data-testid="stSidebar"] .stSelectbox label,
section[data-testid="stSidebar"] .stRadio label {
  font-size: 0.82rem;
  color: var(--text-muted);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* 버튼 */
.stButton > button {
  border-radius: 8px !important;
  font-size: 0.85rem !important;
  font-weight: 500 !important;
  transition: opacity 0.15s !important;
}
.stButton > button:hover { opacity: 0.85; }

/* 데이터프레임 헤더 */
[data-testid="stDataFrame"] th {
  background: rgba(33,150,243,0.08) !important;
  font-weight: 700 !important;
  font-size: 0.82rem !important;
}

/* expander */
[data-testid="stExpander"] {
  border: 1px solid var(--border-subtle) !important;
  border-radius: 8px !important;
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
    # Korean stock codes have leading zeros (005930); keep as str
    df["code"] = df["code"].astype(str)

    df = df.reset_index(drop=True)
    df.index = df.index + 1
    df.index.name = "rank"
    return df


def _last_updated() -> str:
    if CSV_PATH.exists():
        mtime = CSV_PATH.stat().st_mtime
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
    return "알 수 없음"


# ── 투자등급 (분위 기반 동적 임계값 — 전문가 패널 #3) ──────────────────────────
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
        f'border:1px solid {cfg["border"]};padding:3px 12px;border-radius:12px;'
        f'font-size:0.82rem;font-weight:700;letter-spacing:0.04em;">{label}</span>'
    )


def compute_grade_thresholds(df: pd.DataFrame) -> tuple[float, float, float]:
    """유니버스 분위 기반 동적 등급 임계값 (상위20%/50%/80%)."""
    return (
        float(df["Total"].quantile(0.80)),
        float(df["Total"].quantile(0.50)),
        float(df["Total"].quantile(0.20)),
    )


def data_quality_label(row: pd.Series) -> str:
    """축별 실데이터 비율 표시 (0점 = 데이터 미확보). 5축 기준."""
    real = sum([
        row["Growth"] > 0,
        row["Value"] > 0,
        row["Quality"] > 0,
        True,  # Trend 항상 유효 (가격 데이터)
        True,  # Risk 항상 유효 (가격 데이터)
    ])
    return {5: "●●●●●", 4: "●●●●○", 3: "●●●○○", 2: "●●○○○", 1: "●○○○○"}.get(real, "?????")


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
        fillcolor="rgba(33,150,243,0.2)",
        line=dict(color="#2196F3", width=2),
        name=name,
    ))

    if row2 is not None and name2:
        vals2 = [float(row2[a]) for a in AXES] + [float(row2[AXES[0]])]
        fig.add_trace(go.Scatterpolar(
            r=vals2, theta=cats, fill="toself",
            fillcolor="rgba(244,67,54,0.15)",
            line=dict(color="#F44336", width=2, dash="dash"),
            name=name2,
        ))

    # Design: transparent backgrounds, Korean font, readable gridlines
    fig.update_layout(
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(
                visible=True, range=[0, 100],
                tickfont=dict(size=9, color="rgba(150,150,150,0.7)"),
                gridcolor="rgba(150,150,150,0.15)",
            ),
            angularaxis=dict(
                tickfont=dict(size=11),
                gridcolor="rgba(150,150,150,0.2)",
            ),
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Noto Sans KR, sans-serif"),
        showlegend=row2 is not None,
        margin=dict(l=30, r=30, t=40, b=30),
        height=340,
    )
    return fig


def score_bar(value: float, color: str, max_val: float = 100) -> str:
    """Design: animated glow bar. UX: ARIA attributes for accessibility."""
    pct = min(value / max_val * 100, 100)
    return (
        f'<div role="progressbar" aria-valuenow="{value:.0f}" '
        f'aria-valuemin="0" aria-valuemax="{max_val:.0f}" aria-label="점수 {value:.0f}점" '
        f'style="background:var(--track-bg,#e0e0e0);border-radius:6px;height:10px;width:100%;overflow:hidden;">'
        f'<div style="background:{color};height:10px;border-radius:6px;'
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
        f"| 리스크 | **{avg_risk:.1f}점** |",
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
    start = (pd.Timestamp.today() - pd.DateOffset(years=1)).strftime("%Y-%m-%d")
    return get_price_data(code, start, end)


def _price_chart(price_df: pd.DataFrame, name: str) -> "go.Figure | None":
    """1년 주가 라인차트 + MA20/60/120 + 52주 고저 + 거래량."""
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

    has_vol = "Volume" in df.columns and df["Volume"].sum() > 0
    rows    = 2 if has_vol else 1
    heights = [0.72, 0.28] if has_vol else [1.0]

    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True,
                        row_heights=heights, vertical_spacing=0.03)

    fig.add_trace(go.Scatter(
        x=df.index, y=df["Close"], name="종가",
        line=dict(color="#2196F3", width=2),
        hovertemplate="%{x|%Y-%m-%d}<br>종가: %{y:,.0f}원<extra></extra>",
    ), row=1, col=1)

    for ma, color in [("MA20","#FF9800"), ("MA60","#9C27B0"), ("MA120","#F44336")]:
        fig.add_trace(go.Scatter(
            x=df.index, y=df[ma], name=ma,
            line=dict(color=color, width=1, dash="dot"),
            hovertemplate=f"{ma}: %{{y:,.0f}}원<extra></extra>",
        ), row=1, col=1)

    fig.add_hline(y=w52_high, line_dash="dash", line_color="rgba(0,200,83,0.55)",
                  annotation_text=f"52주 고점 {w52_high:,.0f}",
                  annotation_position="top right", row=1, col=1)
    fig.add_hline(y=w52_low, line_dash="dash", line_color="rgba(229,57,53,0.55)",
                  annotation_text=f"52주 저점 {w52_low:,.0f}",
                  annotation_position="bottom right", row=1, col=1)

    if has_vol:
        closes = df["Close"].values
        vcol = ["#ef5350" if i > 0 and closes[i] < closes[i-1] else "#26a69a"
                for i in range(len(closes))]
        fig.add_trace(go.Bar(
            x=df.index, y=df["Volume"], name="거래량",
            marker_color=vcol, showlegend=False,
            hovertemplate="거래량: %{y:,.0f}<extra></extra>",
        ), row=2, col=1)

    fig.update_layout(
        title=dict(text=f"<b>{name}</b> — 1년 주가 (MA20·60·120)", font=dict(size=13)),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Noto Sans KR, sans-serif", size=11),
        margin=dict(l=55, r=20, t=50, b=20), height=420,
        showlegend=True,
        legend=dict(orientation="h", y=1.10, x=0, font=dict(size=10)),
        xaxis=dict(gridcolor="rgba(128,128,128,0.1)", rangeslider=dict(visible=False)),
        yaxis=dict(gridcolor="rgba(128,128,128,0.1)", tickformat=",.0f", title="주가 (원)"),
    )
    if has_vol:
        fig.update_xaxes(gridcolor="rgba(128,128,128,0.1)", row=2, col=1)
        fig.update_yaxes(gridcolor="rgba(128,128,128,0.1)", title_text="거래량", row=2, col=1)
    return fig


def _score_comparison_chart(row: pd.Series, df_univ: pd.DataFrame) -> go.Figure:
    """5축 점수 vs 유니버스 평균 그룹 바 차트."""
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
        **base, barmode="group", height=300,
        title="5축 점수 vs 유니버스 평균",
        yaxis=dict(range=[0, 115], gridcolor="rgba(128,128,128,0.1)"),
        legend=dict(orientation="h", y=1.12, font=dict(size=10)),
    )
    return fig


@st.dialog("종목 분석", width="large")
def _show_stock_dialog(row: pd.Series, df_univ: pd.DataFrame, fdf: pd.DataFrame,
                       grade_thresholds: tuple) -> None:
    """Tab1 행 클릭 시 모달 팝업으로 5축 종목 분석 표시."""
    code  = str(row["code"])
    name  = str(row["name"])
    total = float(row["Total"])
    rank_val = int(row.get("rank", 0))

    options = fdf.reset_index().apply(
        lambda r: f"{int(r['rank'])}위 {r['name']} ({r['code']})", axis=1
    ).tolist()

    # 헤더: 등급 배지 + 종합점수
    st.markdown(grade_badge_html(total, grade_thresholds), unsafe_allow_html=True)
    st.markdown(
        f"<div style='display:flex;align-items:baseline;gap:10px;margin:6px 0 10px;'>"
        f"<span style='font-size:1.5rem;font-weight:800;'>{name}</span>"
        f"<span style='color:#888;font-size:0.9rem;'>{code} · 유니버스 {rank_val}위</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # 관심목록 버튼
    wl = st.session_state.watchlist
    if code in wl:
        if st.button("⭐ 관심 목록에서 제거", key="dlg_wl"):
            wl.remove(code)
            st.rerun()
    else:
        if st.button("☆ 관심 목록에 추가", key="dlg_wl"):
            wl.append(code)
            st.rerun()

    # 주가 차트
    with st.spinner("주가 데이터 로딩 중..."):
        try:
            price_df = _get_price_history(code)
            fig_p = _price_chart(price_df, name)
            if fig_p:
                st.plotly_chart(fig_p, use_container_width=True)
        except Exception as _pe:
            st.warning(f"주가 차트 오류: {_pe}")

    # 레이더 + 5축 점수
    compare_options = ["없음"] + [o for o in options if f"({code})" not in o]
    sel_compare = st.selectbox("비교 종목 선택 (선택사항)", compare_options, key="dlg_compare")
    row2 = name2 = None
    if sel_compare != "없음":
        cmp_idx = options.index(sel_compare)
        row2 = fdf.reset_index().iloc[cmp_idx]
        name2 = row2["name"]

    col_radar, col_scores = st.columns([1, 1])
    with col_radar:
        st.plotly_chart(radar_chart(row, name, row2, name2), use_container_width=True)
    with col_scores:
        st.markdown(f"#### {name} 5축 점수")
        _kor_to_eng = {"성장": "Growth", "가치": "Value", "펀더멘털": "Quality", "추세": "Trend", "리스크": "Risk"}
        for axis in AXES:
            val = float(row[axis])
            st.markdown(
                f"**{AXIS_LABELS[axis]}** &nbsp;&nbsp; {color_score(val)} **{val:.1f}점**"
                f'  <span title="{AXIS_TOOLTIPS[axis]}" style="cursor:help;color:#999;font-size:0.85em">ℹ️</span>',
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

    # 진입 분석
    st.markdown("**📡 진입 분석**")
    ic1, ic2, ic3, ic4 = st.columns(4)
    row_dict = row.to_dict() if hasattr(row, "to_dict") else {}
    _rsi = row_dict.get("RSI")
    _pos = row_dict.get("week52_pos")
    _sig = row_dict.get("entry_signal")
    if _rsi is not None and pd.notna(_rsi):
        rsi_v = float(_rsi)
        rsi_desc = "과매수 주의" if rsi_v > 70 else "과매도 반등 구간" if rsi_v < 30 else "적정 구간"
        ic1.metric("RSI(14)", f"{rsi_v:.0f}", delta=rsi_desc, delta_color="off")
    if _pos is not None and pd.notna(_pos):
        ic2.metric("52주 위치", f"{float(_pos):.0f}%")
    if _sig:
        sig_map = {"매수유망": "🟢 매수유망", "관심": "🔵 관심", "과열주의": "🔴 과열주의",
                   "대기": "⚪ 대기", "확인필요": "❓ 확인필요"}
        ic3.metric("진입 신호", sig_map.get(_sig, _sig))
    try:
        _cur = _get_current_price(code)
        _cons, _ = _get_analyst_data(code)
        _tp = _cons.target_price if _cons and not _cons.error else None
        if _cur and _tp and _cur > 0:
            upside = (_tp - _cur) / _cur * 100
            ic4.metric("목표주가 상승여력", f"{upside:+.1f}%", delta=f"목표 {_tp:,}원",
                       delta_color="normal" if upside >= 0 else "inverse")
        else:
            ic4.metric("목표주가 상승여력", "—")
    except Exception:
        ic4.metric("목표주가 상승여력", "—")

    st.markdown("---")

    # 유니버스 포지셔닝 바 차트
    st.markdown("**유니버스 포지셔닝 — 5축 점수 비교**")
    try:
        st.plotly_chart(_score_comparison_chart(row, df_univ), use_container_width=True)
    except Exception:
        pass

    # 투자 포인트 / 주의 사항
    strengths  = [(AXIS_LABELS[a], float(row[a]), a) for a in AXES if float(row[a]) >= 60]
    weaknesses = [(AXIS_LABELS[a], float(row[a]), a) for a in AXES if float(row[a]) < 40]
    univ_ranks = {a: int((df_univ[a] > float(row[a])).sum()) + 1 for a in AXES}

    if strengths or weaknesses:
        _sw = st.columns(2)
        with _sw[0]:
            if strengths:
                st.markdown("**✅ 투자 포인트** (60점 이상)")
                for lbl, score, akey in strengths:
                    st.markdown(
                        f"<div style='border-left:3px solid {AXIS_COLORS[akey]};padding:7px 10px;"
                        f"margin:4px 0;background:rgba(0,200,83,0.07);border-radius:0 6px 6px 0;'>"
                        f"<b>{lbl}</b> <span style='color:{AXIS_COLORS[akey]};font-weight:700;'>"
                        f"{score:.1f}점</span> — 유니버스 <b>{univ_ranks[akey]}위</b>/{len(df_univ)}위</div>",
                        unsafe_allow_html=True,
                    )
        with _sw[1]:
            if weaknesses:
                st.markdown("**⚠️ 주의 사항** (40점 미만)")
                for lbl, score, akey in weaknesses:
                    st.markdown(
                        f"<div style='border-left:3px solid {AXIS_COLORS[akey]};padding:7px 10px;"
                        f"margin:4px 0;background:rgba(244,67,54,0.07);border-radius:0 6px 6px 0;'>"
                        f"<b>{lbl}</b> <span style='color:#F44336;font-weight:700;'>"
                        f"{score:.1f}점</span> — 유니버스 <b>{univ_ranks[akey]}위</b>/{len(df_univ)}위</div>",
                        unsafe_allow_html=True,
                    )

    # 5축 선별 근거 상세
    st.markdown("**📝 5축 선별 근거 상세**")
    _kor_to_eng2 = {"성장": "Growth", "가치": "Value", "펀더멘털": "Quality", "추세": "Trend", "리스크": "Risk"}
    try:
        reasons = explain_stock(code, fdf.reset_index())
    except Exception as _ex:
        reasons = {}
        st.warning(f"선별 근거 조회 오류: {_ex}")
    summary_text = f" — {reasons['summary']}" if reasons.get("summary") else ""
    if reasons.get("total"):
        st.markdown(
            f"<div style='padding:12px;background:rgba(33,150,243,0.12);border-radius:8px;"
            f"border-left:4px solid #2196F3;margin-bottom:8px;color:inherit;'>"
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
                f"<div style='padding:10px;background:rgba(244,67,54,0.10);border-radius:8px;"
                f"border-left:4px solid #F44336;margin-bottom:8px;color:inherit;'>"
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
    ].head(5).reset_index()[["rank","name","code","Growth","Value","Quality","Trend","Risk","Total"]]
    if not similar.empty:
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
    col_a, col_b, col_c = st.columns(3)
    if consensus.target_price:
        col_a.metric("컨센서스 목표주가", f"{consensus.target_price:,}원")
    if consensus.analyst_count:
        col_b.metric("추정 증권사 수", f"{consensus.analyst_count}개")
    if consensus.consensus_score:
        score_label = {5: "강력매수", 4: "매수", 3: "중립", 2: "매도", 1: "강력매도"}.get(
            round(consensus.consensus_score), f"{consensus.consensus_score:.1f}"
        )
        col_c.metric("컨센서스 의견", score_label)

    # 매수/중립/매도 분포
    total_ops = consensus.buy_count + consensus.neutral_count + consensus.sell_count
    if total_ops > 0:
        buy_pct = consensus.buy_count / total_ops * 100
        neu_pct = consensus.neutral_count / total_ops * 100
        sell_pct = consensus.sell_count / total_ops * 100
        st.markdown(
            f'<div style="display:flex;gap:4px;margin:8px 0;">'
            f'<div style="flex:{buy_pct:.0f};background:#00C853;height:20px;'
            f'border-radius:4px 0 0 4px;text-align:center;color:#003300;'
            f'font-size:0.75rem;line-height:20px;" title="매수 {consensus.buy_count}개">'
            f'매수 {buy_pct:.0f}%</div>'
            f'<div style="flex:{neu_pct:.0f};background:#FB8C00;height:20px;'
            f'text-align:center;color:#fff;font-size:0.75rem;line-height:20px;" '
            f'title="중립 {consensus.neutral_count}개">'
            f'중립 {neu_pct:.0f}%</div>'
            f'<div style="flex:{max(sell_pct,1):.0f};background:#E53935;height:20px;'
            f'border-radius:0 4px 4px 0;text-align:center;color:#fff;'
            f'font-size:0.75rem;line-height:20px;" title="매도 {consensus.sell_count}개">'
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
                    f" <span style='background:#1565C0;color:#fff;padding:1px 7px;"
                    f"border-radius:4px;font-size:0.82rem;margin-left:6px'>"
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


# ── 메인 ─────────────────────────────────────────────────────────────────────
def main() -> None:
    _init_session_state()
    _inject_css()
    df = load_data()
    grade_thresholds = compute_grade_thresholds(df) if not df.empty else (60.0, 50.0, 40.0)

    # UX: Full-page onboarding when no data
    if df.empty:
        st.title("QuantLab Screener")
        st.markdown("### 데이터가 아직 없습니다")
        st.info("터미널에서 아래 명령어를 실행해 스코어링 데이터를 생성하세요.")
        st.code("source .venv/bin/activate\npython -m src.main", language="bash")
        st.markdown("생성 완료 후 사이드바의 **데이터 새로고침** 버튼을 클릭하세요.")
        with st.sidebar:
            st.title("QuantLab Screener")
            if st.button("데이터 새로고침"):
                st.cache_data.clear()
                st.rerun()
        st.stop()

    # ── 사이드바 ──────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(
            "<div style='padding:16px 0 8px;'>"
            "<div style='font-size:1.6rem;font-weight:800;letter-spacing:-0.02em;'>QuantLab Screener</div>"
            "<div style='font-size:0.8rem;color:#888;margin-top:5px;'>KOSPI·KOSDAQ 5축 스코어링</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.divider()
        st.markdown(
            "<div style='font-size:0.72rem;color:#888;margin-bottom:10px;'>"
            f"📅 {_last_updated()}</div>",
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
            all_signals = ["전체", "매수유망", "관심", "과열주의", "대기", "확인필요"]
            signal_icons = {"매수유망": "🟢", "관심": "🔵", "과열주의": "🔴", "대기": "⚪", "확인필요": "❓"}
            signal_labels = ["전체"] + [f"{signal_icons.get(s,'')} {s}" for s in all_signals[1:]]
            sel_signal_label = st.selectbox("진입 신호", signal_labels)
            sel_signal = all_signals[signal_labels.index(sel_signal_label)]
        else:
            sel_signal = "전체"

        grade_options = ["전체", "최우수", "우수", "보통", "관찰"]
        sel_grade = st.selectbox("투자등급", grade_options)

        if st.button("필터 초기화", use_container_width=True):
            st.session_state.tab2_search = ""
            st.rerun()

        st.divider()
        st.markdown("**🔍 빠른 종목 분석**")
        quick_srch = st.text_input("종목명 또는 코드", key="sidebar_quick_search", placeholder="예: 삼성전자")
        if quick_srch:
            st.session_state.tab2_search = quick_srch
            st.caption("→ '종목 분석' 탭을 클릭하세요")

        st.divider()

        # CustMgmt: In-session watchlist
        if st.session_state.watchlist:
            st.subheader(f"⭐ 관심 종목 ({len(st.session_state.watchlist)}개)")
            st.caption("⚠️ 세션 종료(새로고침) 시 초기화됩니다")
            wl_df = df.reset_index()
            wl_df = wl_df[wl_df["code"].isin(st.session_state.watchlist)][
                ["name", "code", "Total"]
            ].sort_values("Total", ascending=False)
            for _, wrow in wl_df.iterrows():
                col_w1, col_w2 = st.columns([3, 1])
                col_w1.caption(f"{wrow['name']} ({wrow['code']}) — {wrow['Total']:.1f}점")
                if col_w2.button("✕", key=f"wl_rm_{wrow['code']}"):
                    st.session_state.watchlist.remove(wrow["code"])
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
        f"""<div style="display:flex;align-items:center;justify-content:space-between;
          padding:14px 0 10px;border-bottom:1px solid rgba(128,128,128,0.18);margin-bottom:14px;">
          <div style="display:flex;align-items:baseline;gap:12px;">
            <span style="font-size:2.2rem;font-weight:800;letter-spacing:-0.03em;">
              QuantLab Screener</span>
            <span style="font-size:0.88rem;color:#888;">
              KOSPI·KOSDAQ 시총 상위 100개 · 5축 스코어링</span>
          </div>
          <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;">
            <span style="background:rgba(33,150,243,0.14);border:1px solid rgba(33,150,243,0.28);
              padding:3px 11px;border-radius:20px;font-size:0.75rem;color:#64B5F6;font-weight:600;">
              {len(fdf)}개 종목</span>
            <span style="background:rgba(128,128,128,0.08);border:1px solid rgba(128,128,128,0.18);
              padding:3px 11px;border-radius:20px;font-size:0.75rem;color:#aaa;">
              KOSPI {kospi_cnt} · KOSDAQ {kosdaq_cnt}</span>
            <span style="font-size:0.75rem;color:#666;">📅 {_last_updated()}</span>
          </div>
        </div>""",
        unsafe_allow_html=True,
    )

    is_empty = fdf.empty
    tab1, tab3, tab4, tab5 = st.tabs(["📋 종목 랭킹", "📈 분포 분석", "💬 시장 코멘트", "🔬 IC 검증"])

    # ── Tab 1: 랭킹 ───────────────────────────────────────────────────────────
    with tab1:
        t1, t2, t3 = grade_thresholds
        st.markdown(
            f"<div style='display:flex;align-items:center;justify-content:space-between;"
            f"margin-bottom:8px;flex-wrap:wrap;gap:8px;'>"
            f"<span style='font-size:1.05rem;font-weight:700;'>종목 랭킹 "
            f"<span style='color:#64B5F6;'>{len(fdf)}개</span></span>"
            f"<div style='display:flex;gap:6px;align-items:center;flex-wrap:wrap;'>"
            f"<span style='font-size:0.72rem;color:#888;'>등급 기준</span>"
            f"<span style='background:#00C853;color:#003300;padding:2px 9px;border-radius:12px;"
            f"font-size:0.72rem;font-weight:700;'>최우수 ≥{t1:.0f}</span>"
            f"<span style='background:#1E88E5;color:#fff;padding:2px 9px;border-radius:12px;"
            f"font-size:0.72rem;font-weight:700;'>우수 ≥{t2:.0f}</span>"
            f"<span style='background:#FB8C00;color:#fff;padding:2px 9px;border-radius:12px;"
            f"font-size:0.72rem;font-weight:700;'>보통 ≥{t3:.0f}</span>"
            f"<span style='background:#E53935;color:#fff;padding:2px 9px;border-radius:12px;"
            f"font-size:0.72rem;font-weight:700;'>관찰</span>"
            f"<span style='font-size:0.7rem;color:#666;'>· 정량 스크리닝 결과, 투자 추천 아님</span>"
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

            base_cols = ["name", "code", "market", "sector",
                         "Growth", "Value", "Quality", "Trend", "Risk", "Total"]
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
            display["리스크"] = display["Risk"].apply(lambda x: f"{color_score(x)} {x:.1f}")
            display["등급"] = display["Total"].apply(
                lambda x: investment_grade(x, grade_thresholds)
            )
            display["데이터"] = display.apply(data_quality_label, axis=1)

            _signal_icon = {"매수유망": "🟢 매수유망", "관심": "🔵 관심",
                            "과열주의": "🔴 과열주의", "대기": "⚪ 대기", "확인필요": "❓ 확인필요"}
            if "entry_signal" in display.columns:
                display["진입신호"] = display["entry_signal"].map(lambda x: _signal_icon.get(x, x))
            if "RSI" in display.columns:
                display["RSI"] = display["RSI"].apply(lambda x: f"{x:.0f}" if pd.notna(x) else "—")
            if "week52_pos" in display.columns:
                display["52주위치"] = display["week52_pos"].apply(lambda x: f"{x:.0f}%" if pd.notna(x) else "—")

            show_cols = ["순위", "종목", "market", "sector", "성장", "가치", "펀더멘털", "추세", "리스크", "Total", "등급"]
            if "진입신호" in display.columns:
                show_cols += ["진입신호", "RSI", "52주위치"]
            show_cols += ["데이터"]

            st.caption("💡 종목명 클릭 → 분석 팝업 | 헤더 정렬은 '종목 정렬' 셀렉트박스 사용")

            # ── 커스텀 클릭 테이블 헤더 ──────────────────────────────────────
            _GCOLS = [0.35, 1.9, 0.65, 1.0, 0.7, 0.7, 0.75, 0.7, 0.7, 0.75, 0.65]
            _GHEADS = ["순위", "종목명 ↗클릭", "시장", "업종", "성장", "가치", "펀더멘털", "추세", "리스크", "종합", "등급"]
            st.markdown("""
<style>
/* 종목명 tertiary 버튼 — 텍스트 링크 스타일 */
div[data-testid="stHorizontalBlock"] button[kind="tertiary"] {
    color: #64B5F6 !important;
    padding: 2px 4px !important;
    font-size: 0.88rem !important;
    text-align: left !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
}
div[data-testid="stHorizontalBlock"] button[kind="tertiary"]:hover {
    color: #42A5F5 !important;
    text-decoration: underline !important;
}
</style>""", unsafe_allow_html=True)

            _hcols = st.columns(_GCOLS)
            for _hc, _hl in zip(_hcols, _GHEADS):
                _hc.markdown(f"<span style='font-size:0.78rem;font-weight:700;color:#888;'>{_hl}</span>",
                             unsafe_allow_html=True)
            st.markdown("<hr style='margin:3px 0;border-color:rgba(128,128,128,0.2);'>",
                        unsafe_allow_html=True)

            # ── 종목 행 렌더링 (종목명 = tertiary 버튼) ──────────────────────
            _grade_colors = {"최우수": "#00C853", "우수": "#1E88E5", "보통": "#FB8C00", "관찰": "#E53935"}
            for _, _drow in display.iterrows():
                _rc = st.columns(_GCOLS)
                _rc[0].markdown(f"<span style='font-size:0.85rem;color:#aaa;'>{_drow['순위']}</span>",
                                unsafe_allow_html=True)
                _stock_name = str(_drow["종목"]).split("(")[0].strip()
                _stock_code = str(_drow["code"])
                if _rc[1].button(_stock_name, key=f"stk_{_stock_code}", type="tertiary",
                                 use_container_width=True):
                    _clicked_row = fdf.reset_index()[fdf.reset_index()["code"] == _stock_code]
                    if not _clicked_row.empty:
                        _show_stock_dialog(_clicked_row.iloc[0], df, fdf, grade_thresholds)
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
                _gc = _grade_colors.get(_grade, "#888")
                _rc[10].markdown(
                    f"<span style='background:{_gc};color:#fff;padding:2px 7px;"
                    f"border-radius:10px;font-size:0.72rem;font-weight:700;'>{_grade}</span>",
                    unsafe_allow_html=True)

            st.divider()
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
                            f'border-radius:8px;padding:10px 12px;margin-bottom:10px;">'
                            f'<div style="font-size:0.72rem;color:rgba(180,180,180,0.8);margin-bottom:4px;">'
                            f'{icon} {srow["sector"]}</div>'
                            f'<div style="font-size:1rem;font-weight:700;margin-bottom:6px;">{srow["name"]}</div>'
                            f'<span style="background:{cfg["bg"]};color:{cfg["text"]};'
                            f'padding:2px 8px;border-radius:10px;font-size:0.75rem;font-weight:700;">'
                            f'{grade}</span>'
                            f'<span style="font-size:0.85rem;margin-left:6px;opacity:0.9;">{srow["Total"]:.1f}점</span>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

    # ── Tab 3: 분포 분석 ──────────────────────────────────────────────────────
    with tab3:
        st.subheader("점수 분포 분석")

        if is_empty:
            st.warning("필터 조건에 맞는 종목이 없습니다.")
        else:
            st.caption("💡 드래그로 확대 · 더블클릭으로 초기화 · 호버로 상세 확인")

            # 데이터 품질 요약
            missing_growth = (fdf["Growth"] == 0).sum()
            flat_value = (fdf["Value"] == 37.5).sum()
            if missing_growth > 0 or flat_value > 0:
                st.caption(
                    f"⚠️ 데이터 제한: 성장(DART 미확보 {missing_growth}개 Growth=0) · "
                    f"가치·펀더멘털(pykrx API 불능으로 중립값 고정 {flat_value}개) — 차트에 반영됨"
                )

            col_a, col_b = st.columns(2)

            with col_a:
                try:
                    box_df = fdf[AXES].rename(columns=AXIS_LABELS).melt(var_name="축", value_name="점수")
                    fig_box = px.box(
                        box_df, x="축", y="점수", color="축",
                        color_discrete_map={v: AXIS_COLORS[k] for k, v in AXIS_LABELS.items()},
                        title="5축 점수 분포",
                    )
                    fig_box.update_layout(
                        **PLOTLY_BASE, showlegend=False,
                        xaxis=dict(gridcolor="rgba(128,128,128,0.1)", title=""),
                        yaxis=dict(gridcolor="rgba(128,128,128,0.1)", range=[-5, 105], title="점수"),
                    )
                    st.plotly_chart(fig_box, use_container_width=True)
                except Exception as e:
                    st.warning(f"박스플롯 오류: {e}")

            with col_b:
                try:
                    fig_hist = px.histogram(
                        fdf, x="Total", nbins=15,
                        title="종합점수 분포",
                        color_discrete_sequence=["#2196F3"],
                        labels={"Total": "종합점수", "count": "종목 수"},
                    )
                    fig_hist.update_layout(
                        **PLOTLY_BASE,
                        xaxis=dict(gridcolor="rgba(128,128,128,0.1)", title="종합점수"),
                        yaxis=dict(gridcolor="rgba(128,128,128,0.1)", title="종목 수"),
                        bargap=0.05,
                    )
                    st.plotly_chart(fig_hist, use_container_width=True)
                except Exception as e:
                    st.warning(f"히스토그램 오류: {e}")

            col_c, col_d = st.columns(2)

            # 업종별 평균 종합점수 차트 (섹터 재분류 반영)
            col_sector_chart, col_sector_count = st.columns(2)
            with col_sector_chart:
                try:
                    sec_avg = (
                        fdf.groupby("sector")["Total"].mean()
                        .sort_values(ascending=True)
                        .reset_index()
                    )
                    fig_sec = px.bar(
                        sec_avg, x="Total", y="sector", orientation="h",
                        title="업종별 평균 종합점수",
                        color="Total",
                        color_continuous_scale="RdYlGn",
                        labels={"Total": "평균점수", "sector": "업종"},
                    )
                    _base_sec = {k: v for k, v in PLOTLY_BASE.items() if k != "height"}
                    fig_sec.update_layout(
                        **_base_sec,
                        xaxis=dict(gridcolor="rgba(128,128,128,0.1)", range=[0, 100]),
                        yaxis=dict(gridcolor="rgba(128,128,128,0.1)", title=""),
                        coloraxis_showscale=False,
                        height=400,
                    )
                    st.plotly_chart(fig_sec, use_container_width=True)
                except Exception as e:
                    st.warning(f"업종별 차트 오류: {e}")

            with col_sector_count:
                try:
                    sec_cnt = fdf["sector"].value_counts().reset_index()
                    sec_cnt.columns = ["업종", "종목 수"]
                    fig_cnt = px.pie(
                        sec_cnt, names="업종", values="종목 수",
                        title="업종별 종목 수 비중",
                        hole=0.45,
                    )
                    _base_cnt = {k: v for k, v in PLOTLY_BASE.items() if k != "height"}
                    fig_cnt.update_layout(
                        **_base_cnt,
                        showlegend=True,
                        legend=dict(font=dict(size=10), orientation="v"),
                        height=400,
                    )
                    fig_cnt.update_traces(textposition="inside", textinfo="percent+label")
                    st.plotly_chart(fig_cnt, use_container_width=True)
                except Exception as e:
                    st.warning(f"업종 비중 차트 오류: {e}")

            with col_c:
                try:
                    # DART 미확보 종목(Growth=0) 제외해 산점도를 깔끔하게
                    scatter_df = fdf.reset_index()
                    excluded = (scatter_df["Growth"] == 0).sum()
                    scatter_df = scatter_df[scatter_df["Growth"] > 0]
                    title_suffix = f" ({excluded}개 Growth=0 제외)" if excluded > 0 else ""
                    fig_scatter = px.scatter(
                        scatter_df, x="Growth", y="Trend",
                        hover_data=["name", "code", "Total"],
                        color="Total",
                        color_continuous_scale="RdYlGn",
                        size_max=10,
                        title=f"성장 vs 추세{title_suffix}",
                        labels={"Growth": "성장점수", "Trend": "추세점수"},
                    )
                    fig_scatter.add_hline(y=50, line_dash="dot", line_color="rgba(128,128,128,0.3)", line_width=1)
                    fig_scatter.add_vline(x=50, line_dash="dot", line_color="rgba(128,128,128,0.3)", line_width=1)
                    fig_scatter.update_layout(
                        **PLOTLY_BASE,
                        xaxis=dict(gridcolor="rgba(128,128,128,0.1)"),
                        yaxis=dict(gridcolor="rgba(128,128,128,0.1)"),
                        coloraxis_colorbar=dict(thickness=12, len=0.6),
                    )
                    st.plotly_chart(fig_scatter, use_container_width=True)
                except Exception as e:
                    st.warning(f"산점도 오류: {e}")

            with col_d:
                try:
                    # KOSPI/KOSDAQ만 표시 (KOSDAQ GLOBAL 등 소수 카테고리 정리)
                    mkt_fdf = fdf[fdf["market"].isin(["KOSPI", "KOSDAQ"])]
                    mkt_avg = mkt_fdf.groupby("market")[AXES + ["Total"]].mean().round(1)
                    mkt_avg.columns = [AXIS_LABELS.get(c, c) for c in mkt_avg.columns]
                    fig_bar = px.bar(
                        mkt_avg.reset_index().melt(id_vars="market"),
                        x="variable", y="value", color="market",
                        barmode="group",
                        color_discrete_map={"KOSPI": "#2196F3", "KOSDAQ": "#FF9800"},
                        title="KOSPI vs KOSDAQ 평균 점수",
                        labels={"variable": "", "value": "평균점수", "market": "시장"},
                    )
                    fig_bar.update_layout(
                        **PLOTLY_BASE,
                        xaxis=dict(gridcolor="rgba(128,128,128,0.1)"),
                        yaxis=dict(gridcolor="rgba(128,128,128,0.1)"),
                        legend=dict(orientation="h", y=1.1, x=0),
                    )
                    st.plotly_chart(fig_bar, use_container_width=True)
                except Exception as e:
                    st.warning(f"막대차트 오류: {e}")

            # P4: Risk 분포 차트
            col_risk1, col_risk2 = st.columns(2)
            with col_risk1:
                try:
                    fig_risk = px.histogram(
                        fdf, x="Risk", nbins=15,
                        title="리스크 점수 분포 (높을수록 저위험)",
                        color_discrete_sequence=["#00BCD4"],
                        labels={"Risk": "리스크 점수", "count": "종목 수"},
                    )
                    fig_risk.add_vline(x=fdf["Risk"].mean(), line_dash="dash",
                                       line_color="white", annotation_text=f"평균 {fdf['Risk'].mean():.1f}")
                    fig_risk.update_layout(
                        **PLOTLY_BASE,
                        xaxis=dict(gridcolor="rgba(128,128,128,0.1)", range=[-5, 105]),
                        yaxis=dict(gridcolor="rgba(128,128,128,0.1)"),
                        bargap=0.05,
                    )
                    st.plotly_chart(fig_risk, use_container_width=True)
                except Exception as e:
                    st.warning(f"리스크 분포 오류: {e}")

            with col_risk2:
                try:
                    fig_rv = px.scatter(
                        fdf.reset_index(), x="Risk", y="Trend",
                        hover_data=["name", "code", "Total"],
                        color="Total",
                        color_continuous_scale="RdYlGn",
                        title="리스크 vs 추세 (우상단 = 저위험·상승추세)",
                        labels={"Risk": "리스크 점수", "Trend": "추세 점수"},
                    )
                    fig_rv.add_hline(y=50, line_dash="dot", line_color="rgba(128,128,128,0.3)", line_width=1)
                    fig_rv.add_vline(x=50, line_dash="dot", line_color="rgba(128,128,128,0.3)", line_width=1)
                    fig_rv.update_layout(
                        **PLOTLY_BASE,
                        xaxis=dict(gridcolor="rgba(128,128,128,0.1)"),
                        yaxis=dict(gridcolor="rgba(128,128,128,0.1)"),
                        coloraxis_colorbar=dict(thickness=12, len=0.6),
                    )
                    st.plotly_chart(fig_rv, use_container_width=True)
                except Exception as e:
                    st.warning(f"리스크·추세 산점도 오류: {e}")

    # ── Tab 4: 시장 코멘트 ────────────────────────────────────────────────────
    with tab4:
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
    with tab5:
        st.subheader("IC/IR 백테스트 — 점수의 예측력 검증")
        st.markdown(
            "**이 탭은 스크리너 점수가 실제로 미래 수익률을 예측하는지 검증합니다.**\n\n"
            "- **IC (정보계수)**: 점수 순위와 실제 주가 수익률 순위의 일치도 (−1 ~ +1)\n"
            "  - `IC > 0.10`: 유의미한 예측력 ✅  |  `0.05~0.10`: 약한 신호 🟡  |  `< 0.05`: 무의미 🔴\n"
            "- **IR (정보비율)**: IC가 얼마나 안정적으로 나오는지 (IC 평균 ÷ IC 변동성)\n"
            "  - `IR > 0.5`: 안정적 ✅  |  `0.3~0.5`: 보통 🟡  |  `< 0.3`: 불안정 🔴\n"
            "- **포워드 수익률**: 점수 계산 이후 1·3·6개월 뒤 주가 변화율"
        )

        col_bt1, col_bt2 = st.columns([1, 1])

        with col_bt1:
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
                # IC 시계열 차트
                try:
                    import plotly.graph_objects as go
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
                    fig_ic.update_layout(title="분기별 IC 추이", **PLOTLY_BASE)
                    st.plotly_chart(fig_ic, use_container_width=True)
                except Exception:
                    pass
            else:
                st.info("위 버튼을 눌러 백테스트를 실행하세요.")

        with col_bt2:
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


if __name__ == "__main__":
    main()
