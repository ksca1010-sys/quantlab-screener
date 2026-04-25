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
from src.analyst import fetch_consensus, fetch_report_titles

st.set_page_config(
    page_title="QuantLab Screener",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

CSV_PATH = Path(__file__).parent.parent / "output" / "stocks_top100.csv"

AXES = ["Growth", "Value", "Quality", "Trend"]
AXIS_LABELS = {"Growth": "성장", "Value": "가치", "Quality": "펀더멘털", "Trend": "추세"}
AXIS_COLORS = {
    "Growth": "#4CAF50",
    "Value": "#2196F3",
    "Quality": "#FF9800",
    "Trend": "#9C27B0",
    "Total": "#F44336",
}
AXIS_TOOLTIPS = {
    "Growth": "YoY 매출성장률·영업이익성장률 (DART 공시 기반)",
    "Value": "PER·PBR 섹터 내 백분위 + 배당수익률",
    "Quality": "ROE·영업이익률·부채비율·이익잉여금",
    "Trend": "이동평균 배열(20/60/120일) + 52주 위치 + 거래량",
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
        "watchlist": [],       # in-session watchlist (CustMgmt)
        "tab2_search": "",     # Tab2 stock search-as-you-type (UX)
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ── CSS 주입 (Design) ─────────────────────────────────────────────────────────
def _inject_css() -> None:
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap');

:root {
  --bg-card: rgba(255,255,255,0.06);
  --bg-inset: rgba(0,0,0,0.08);
  --border-subtle: rgba(128,128,128,0.2);
  --text-muted: rgba(128,128,128,0.8);
  --track-bg: rgba(128,128,128,0.15);
}

.stApp, .stMarkdown, [data-testid="stMetricLabel"] {
  font-family: 'Noto Sans KR', sans-serif !important;
}

.stMarkdown p, .stMarkdown li {
  line-height: 1.45;
  word-break: keep-all;
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


# ── 투자등급 (CustMgmt: 중립 등급 라벨, 추천 오해 방지) ───────────────────────
def investment_grade(score: float) -> str:
    if score >= 60:
        return "최우수"
    elif score >= 50:
        return "우수"
    elif score >= 40:
        return "보통"
    return "관찰"


def grade_badge_html(score: float) -> str:
    """Design: styled pill badge — accessible colors, no financial jargon."""
    label = investment_grade(score)
    cfg = GRADE_CONFIG[label]
    return (
        f'<span style="background:{cfg["bg"]};color:{cfg["text"]};'
        f'border:1px solid {cfg["border"]};padding:3px 12px;border-radius:12px;'
        f'font-size:0.82rem;font-weight:700;letter-spacing:0.04em;">{label}</span>'
    )


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
    avg_total = df["Total"].mean()
    avg_growth = df["Growth"].mean()
    avg_trend = df["Trend"].mean()
    strong_count = (df["Total"] >= 60).sum()
    good_count = ((df["Total"] >= 50) & (df["Total"] < 60)).sum()
    data_complete_pct = (df["Value"] != 37.5).mean() * 100

    lines = [
        f"**기준일: {ref_date}** | 유니버스 {len(df)}개 종목 분석",
        "",
        f"- 종합점수 평균 **{avg_total:.1f}점** | 성장 평균 **{avg_growth:.1f}점** | 추세 평균 **{avg_trend:.1f}점**",
        f"- 최우수 등급 **{strong_count}개**, 우수 등급 **{good_count}개**",
        f"- Value 데이터 완결률: **{data_complete_pct:.0f}%** (pykrx API 제공 기준)",
        f"- **종합 TOP 5**: {top_names}",
        "",
        "> ⚠️ 본 통계는 자동 생성 데이터이며 시황 판단을 포함하지 않습니다.",
        "> 공시 기준: 분석 시점 t-45일 이전 게재 공시만 반영됩니다.",
    ]
    return "\n".join(lines)


# ── 애널리스트 데이터 (캐시) ──────────────────────────────────────────────────
@st.cache_data(ttl=1800, show_spinner=False)
def _get_analyst_data(code: str) -> tuple:
    consensus = fetch_consensus(code)
    reports = fetch_report_titles(code)
    return consensus, reports


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
                st.markdown(
                    f"**{r['broker']}** `{r['date']}`  \n"
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

    # UX: Full-page onboarding when no data
    if df.empty:
        st.title("📊 QuantLab Screener")
        st.markdown("### 데이터가 아직 없습니다")
        st.info("터미널에서 아래 명령어를 실행해 스코어링 데이터를 생성하세요.")
        st.code("source .venv/bin/activate\npython -m src.main", language="bash")
        st.markdown("생성 완료 후 사이드바의 **데이터 새로고침** 버튼을 클릭하세요.")
        with st.sidebar:
            st.title("📊 QuantLab")
            if st.button("데이터 새로고침"):
                st.cache_data.clear()
                st.rerun()
        st.stop()

    # ── 사이드바 ──────────────────────────────────────────────────────────────
    with st.sidebar:
        st.title("📊 QuantLab")
        st.caption("KOSPI + KOSDAQ 시총 상위 100개 4축 스코어링")
        st.caption(f"📅 데이터 업데이트: {_last_updated()}")
        st.divider()

        st.subheader("필터")
        search = st.text_input(
            "종목명/코드 검색",
            value=st.session_state.search_query,
            placeholder="삼성, 005930 ...",
        )
        st.session_state.search_query = search

        markets = ["전체"] + sorted(df["market"].unique().tolist())
        sel_market = st.selectbox("시장", markets)

        score_min, score_max = st.slider("종합점수 범위", 0, 100, (0, 100), step=5)

        sectors = ["전체"] + sorted(df["sector"].unique().tolist())
        sel_sector = st.selectbox("섹터", sectors)

        # UX: Filter reset button
        if st.button("필터 초기화", use_container_width=True):
            st.session_state.search_query = ""
            st.session_state.tab2_search = ""
            st.rerun()

        st.subheader("📊 유니버스 통계")
        all_total = df["Total"]
        col_s1, col_s2 = st.columns(2)
        col_s1.metric("최고점", f"{all_total.max():.1f}")
        col_s2.metric("최저점", f"{all_total.min():.1f}")
        col_s3, col_s4 = st.columns(2)
        col_s3.metric("중앙값", f"{all_total.median():.1f}")
        col_s4.metric("섹터 수", f"{df['sector'].nunique()}개")

        st.divider()

        # CustMgmt: In-session watchlist
        if st.session_state.watchlist:
            st.subheader(f"⭐ 관심 종목 ({len(st.session_state.watchlist)}개)")
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
    fdf = fdf[(fdf["Total"] >= score_min) & (fdf["Total"] <= score_max)]

    # ── 헤더 요약 ─────────────────────────────────────────────────────────────
    st.title("QuantLab Screener Dashboard")

    hc1, hc2, hc3, hc4, hc5 = st.columns(5)
    hc1.metric("종목 수", f"{len(fdf)}개")
    hc2.metric("평균 종합점수", f"{fdf['Total'].mean():.1f}" if not fdf.empty else "—")
    hc3.metric("평균 성장점수", f"{fdf['Growth'].mean():.1f}" if not fdf.empty else "—")
    hc4.metric("평균 추세점수", f"{fdf['Trend'].mean():.1f}" if not fdf.empty else "—")
    hc5.metric("KOSPI/KOSDAQ",
               f"{(fdf['market']=='KOSPI').sum()}/{(fdf['market']=='KOSDAQ').sum()}")

    # CustMgmt: Data staleness banner
    st.caption(
        f"📋 데이터 기준: {_last_updated()} | "
        "공시 기준: 분석 시점 t-45일 이전 게재 공시만 반영 | "
        "Value·Quality 점수 일부 중립값 적용 (pykrx API 제한)"
    )
    st.divider()

    is_empty = fdf.empty
    tab1, tab2, tab3, tab4 = st.tabs(["📋 종목 랭킹", "🔍 종목 분석", "📈 분포 분석", "💬 시장 코멘트"])

    # ── Tab 1: 랭킹 ───────────────────────────────────────────────────────────
    with tab1:
        st.subheader(f"종목 랭킹 ({len(fdf)}개)")

        st.caption("등급: 최우수(≥60) · 우수(≥50) · 보통(≥40) · 관찰(<40) — 정량 스크리닝 결과, 투자 추천 아님")

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

            display = fdf.reset_index()[
                ["rank", "name", "code", "market", "sector",
                 "Growth", "Value", "Quality", "Trend", "Total"]
            ].copy().sort_values("Total", ascending=False)

            display["종목"] = display["name"] + " (" + display["code"] + ")"
            display["성장"] = display["Growth"].apply(lambda x: f"{color_score(x)} {x:.1f}")
            display["가치"] = display["Value"].apply(lambda x: f"{color_score(x)} {x:.1f}")
            display["펀더멘털"] = display["Quality"].apply(lambda x: f"{color_score(x)} {x:.1f}")
            display["추세"] = display["Trend"].apply(lambda x: f"{color_score(x)} {x:.1f}")
            display["등급"] = display["Total"].apply(investment_grade)

            st.caption("💡 컬럼 헤더 클릭으로 정렬 | 기본: 종합점수 내림차순")
            row_height = 35
            header_height = 38
            tbl_height = len(display) * row_height + header_height
            st.dataframe(
                display[["rank", "종목", "market", "sector", "성장", "가치", "펀더멘털", "추세", "Total", "등급"]]
                .rename(columns={"rank": "순위", "market": "시장", "sector": "섹터", "Total": "종합점수"}),
                use_container_width=True,
                height=tbl_height,
                column_config={
                    "종합점수": st.column_config.ProgressColumn(
                        "종합점수", min_value=0, max_value=100, format="%.1f"
                    )
                },
            )

            st.divider()
            with st.expander("🏆 섹터별 TOP 종목"):
                sector_top = (
                    fdf.reset_index()
                    .sort_values("Total", ascending=False)
                    .groupby("sector", as_index=False)
                    .first()
                    .sort_values("Total", ascending=False)
                )
                cols = st.columns(min(4, len(sector_top)))
                for i, (_, srow) in enumerate(sector_top.iterrows()):
                    with cols[i % len(cols)]:
                        grade = investment_grade(srow["Total"])
                        st.markdown(
                            f"**{srow['sector']}**  \n"
                            f"{srow['name']}  \n"
                            f"{grade} | {srow['Total']:.1f}점"
                        )

    # ── Tab 2: 종목 분석 ──────────────────────────────────────────────────────
    with tab2:
        st.subheader("종목별 4축 분석 및 선별 근거")

        if is_empty:
            st.warning("필터 조건에 맞는 종목이 없습니다. **필터 초기화**를 클릭하세요.")
        else:
            options = fdf.reset_index().apply(
                lambda r: f"{int(r['rank'])}위 {r['name']} ({r['code']})", axis=1
            ).tolist()

            # UX: search-as-you-type in Tab2
            tab2_search = st.text_input(
                "종목 검색",
                value=st.session_state.tab2_search,
                placeholder="이름 또는 코드",
                key="tab2_search_input",
            )
            st.session_state.tab2_search = tab2_search
            filtered_options = (
                [o for o in options if tab2_search.lower() in o.lower()]
                if tab2_search else options
            )
            if not filtered_options:
                filtered_options = options

            sel = st.selectbox("종목 선택", filtered_options)
            sel_idx = options.index(sel) if sel in options else 0
            row = fdf.reset_index().iloc[sel_idx]
            code = row["code"]
            name = row["name"]

            # CustMgmt: watchlist button
            wl = st.session_state.watchlist
            if code in wl:
                if st.button("⭐ 관심 목록에서 제거"):
                    wl.remove(code)
                    st.rerun()
            else:
                if st.button("☆ 관심 목록에 추가"):
                    wl.append(code)
                    st.rerun()

            compare_options = ["없음"] + [o for o in options if o != sel]
            sel_compare = st.selectbox(
                "비교 종목 선택 (선택사항)",
                compare_options,
                key="selected_compare",
            )

            row2 = None
            name2 = None
            if sel_compare != "없음":
                cmp_idx = options.index(sel_compare)
                row2 = fdf.reset_index().iloc[cmp_idx]
                name2 = row2["name"]

            col_radar, col_scores = st.columns([1, 1])

            with col_radar:
                st.plotly_chart(radar_chart(row, name, row2, name2), use_container_width=True)

            with col_scores:
                total = float(row["Total"])
                rank_val = int(row["rank"])

                st.markdown(grade_badge_html(total), unsafe_allow_html=True)
                st.markdown("")
                st.markdown(f"#### {name} 4축 점수")

                # UX: tooltips in single expander (no duplicate captions)
                for axis in AXES:
                    val = float(row[axis])
                    lbl = AXIS_LABELS[axis]
                    color = AXIS_COLORS[axis]
                    tooltip = AXIS_TOOLTIPS[axis]
                    st.markdown(
                        f"**{lbl}** &nbsp;&nbsp; {color_score(val)} **{val:.1f}점**"
                        f'  <span title="{tooltip}" style="cursor:help;color:#999;font-size:0.85em">ℹ️</span>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(score_bar(val, color), unsafe_allow_html=True)

                with st.expander("축 정의 보기"):
                    for axis in AXES:
                        st.caption(f"**{AXIS_LABELS[axis]}**: {AXIS_TOOLTIPS[axis]}")

                st.markdown(
                    f"<div style='margin-top:12px;padding:10px;"
                    f"background:rgba(128,128,128,0.12);border-radius:8px;text-align:center'>"
                    f"<span style='font-size:1.4em;font-weight:700;color:#1f77b4'>"
                    f"종합 {total:.1f}점 / 100점</span><br>"
                    f"<span style='color:var(--text-muted,#666)'>유니버스 {rank_val}위</span></div>",
                    unsafe_allow_html=True,
                )

                axis_sum = sum(float(row[a]) for a in AXES)
                if axis_sum > 0:
                    st.markdown("**📊 종합점수 구성비**")
                    contrib_cols = st.columns(4)
                    for i, axis in enumerate(AXES):
                        pct = float(row[axis]) / axis_sum * 100
                        contrib_cols[i].metric(AXIS_LABELS[axis], f"{pct:.0f}%")

            st.markdown("---")
            st.markdown("**선별 근거**")
            reasons = explain_stock(code, fdf.reset_index())

            summary_text = f" — {reasons['summary']}" if reasons.get("summary") else ""
            st.markdown(
                f"<div style='padding:12px;background:rgba(33,150,243,0.12);border-radius:8px;"
                f"border-left:4px solid #2196F3;margin-bottom:8px;color:inherit;'>"
                f"📌 {reasons['total']}{summary_text}</div>",
                unsafe_allow_html=True,
            )

            for axis, key in [("성장", "growth"), ("가치", "value"), ("펀더멘털", "quality"), ("추세", "trend")]:
                color = AXIS_COLORS[{"성장": "Growth", "가치": "Value", "펀더멘털": "Quality", "추세": "Trend"}[axis]]
                st.markdown(
                    f"<div style='border-left:3px solid {color};padding:7px 12px;margin:4px 0;"
                    f"background:rgba(128,128,128,0.05);border-radius:0 4px 4px 0;font-size:0.88rem;color:inherit;'>"
                    f"<strong>{axis}</strong> — {reasons[key]}</div>",
                    unsafe_allow_html=True,
                )

            st.markdown("**유사 점수 종목** (±10점 이내)")
            similar = fdf[
                (fdf["Total"].between(total - 10, total + 10))
                & (fdf["code"] != code)
            ].head(5).reset_index()[["rank", "name", "code", "Growth", "Value", "Quality", "Trend", "Total"]]
            if not similar.empty:
                st.dataframe(similar, use_container_width=True, hide_index=True)
            else:
                st.caption("유사 점수 종목 없음")

            st.markdown("---")
            _render_analyst_section(code, name)

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
                        title="4축 점수 분포",
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


if __name__ == "__main__":
    main()
