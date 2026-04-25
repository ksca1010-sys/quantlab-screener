"""
QuantLab Screener Dashboard
실행: streamlit run dashboard/app.py
"""
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.explainer import explain_stock

# ── 설정 ─────────────────────────────────────────────────────────────────────
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


# ── 데이터 로드 ───────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_data() -> pd.DataFrame:
    if not CSV_PATH.exists():
        return pd.DataFrame()
    df = pd.read_csv(CSV_PATH, index_col=0)
    df = df.reset_index(drop=True)
    df.index = df.index + 1
    df.index.name = "rank"
    return df


# ── 차트 헬퍼 ─────────────────────────────────────────────────────────────────
def radar_chart(row: pd.Series, name: str) -> go.Figure:
    cats = [AXIS_LABELS[a] for a in AXES] + [AXIS_LABELS[AXES[0]]]
    vals = [float(row[a]) for a in AXES] + [float(row[AXES[0]])]

    fig = go.Figure(
        go.Scatterpolar(
            r=vals,
            theta=cats,
            fill="toself",
            fillcolor="rgba(33, 150, 243, 0.2)",
            line=dict(color="#2196F3", width=2),
            name=name,
        )
    )
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        showlegend=False,
        margin=dict(l=30, r=30, t=30, b=30),
        height=320,
    )
    return fig


def score_bar(value: float, color: str, max_val: float = 100) -> str:
    """HTML 프로그레스 바 반환."""
    pct = min(value / max_val * 100, 100)
    return (
        f'<div style="background:#eee;border-radius:4px;height:8px;width:100%">'
        f'<div style="background:{color};height:8px;border-radius:4px;width:{pct:.0f}%"></div>'
        f"</div>"
    )


def color_score(val: float) -> str:
    if val >= 60:
        return "🟢"
    elif val >= 40:
        return "🔵"
    elif val >= 20:
        return "🟡"
    else:
        return "🔴"


# ── 메인 ─────────────────────────────────────────────────────────────────────
def main() -> None:
    df = load_data()

    # ── 사이드바 ──────────────────────────────────────────────────────────────
    with st.sidebar:
        st.title("📊 QuantLab")
        st.caption("KOSPI + KOSDAQ 시총 상위 100개 4축 스코어링")
        st.divider()

        if df.empty:
            st.error("output/stocks_top100.csv 없음\n`python -m src.main` 먼저 실행하세요.")
            return

        # 필터
        st.subheader("필터")
        markets = ["전체"] + sorted(df["market"].unique().tolist())
        sel_market = st.selectbox("시장", markets)

        score_min, score_max = st.slider(
            "종합점수 범위", 0, 100, (0, 100), step=5
        )

        sectors = ["전체"] + sorted(df["sector"].unique().tolist())
        sel_sector = st.selectbox("섹터", sectors)

        st.divider()
        st.caption(f"데이터 기준일: config/universe.yaml 참조")
        if st.button("데이터 새로고침"):
            st.cache_data.clear()
            st.rerun()

    if df.empty:
        st.error("output/stocks_top100.csv 없음. `python -m src.main` 먼저 실행하세요.")
        return

    # 필터 적용
    fdf = df.copy()
    if sel_market != "전체":
        fdf = fdf[fdf["market"] == sel_market]
    if sel_sector != "전체":
        fdf = fdf[fdf["sector"] == sel_sector]
    fdf = fdf[(fdf["Total"] >= score_min) & (fdf["Total"] <= score_max)]

    # ── 헤더 요약 ─────────────────────────────────────────────────────────────
    st.title("QuantLab Screener Dashboard")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("종목 수", f"{len(fdf)}개")
    c2.metric("평균 종합점수", f"{fdf['Total'].mean():.1f}")
    c3.metric("평균 성장점수", f"{fdf['Growth'].mean():.1f}")
    c4.metric("평균 추세점수", f"{fdf['Trend'].mean():.1f}")
    c5.metric("KOSPI/KOSDAQ", f"{(fdf['market']=='KOSPI').sum()}/{(fdf['market']=='KOSDAQ').sum()}")

    st.divider()

    # ── 탭 ────────────────────────────────────────────────────────────────────
    tab1, tab2, tab3 = st.tabs(["📋 종목 랭킹", "🔍 종목 분석", "📈 분포 분석"])

    # ── Tab 1: 랭킹 테이블 ────────────────────────────────────────────────────
    with tab1:
        st.subheader(f"종목 랭킹 ({len(fdf)}개)")

        display = fdf.reset_index()[
            ["rank", "name", "code", "market", "sector",
             "Growth", "Value", "Quality", "Trend", "Total"]
        ].copy()

        display["시장"] = display["market"]
        display["종목"] = display["name"] + " (" + display["code"] + ")"
        display["성장"] = display["Growth"].apply(lambda x: f"{color_score(x)} {x:.1f}")
        display["가치"] = display["Value"].apply(lambda x: f"{color_score(x)} {x:.1f}")
        display["펀더멘털"] = display["Quality"].apply(lambda x: f"{color_score(x)} {x:.1f}")
        display["추세"] = display["Trend"].apply(lambda x: f"{color_score(x)} {x:.1f}")
        display["종합"] = display["Total"].apply(lambda x: f"**{x:.1f}**")

        st.dataframe(
            display[["rank", "종목", "시장", "sector", "성장", "가치", "펀더멘털", "추세", "Total"]]
            .rename(columns={"rank": "순위", "sector": "섹터", "Total": "종합점수"}),
            use_container_width=True,
            height=500,
            column_config={
                "종합점수": st.column_config.ProgressColumn(
                    "종합점수", min_value=0, max_value=100, format="%.1f"
                )
            },
        )

    # ── Tab 2: 종목 분석 ──────────────────────────────────────────────────────
    with tab2:
        st.subheader("종목별 4축 분석 및 선별 근거")

        # 종목 선택
        options = fdf.reset_index().apply(
            lambda r: f"{int(r['rank'])}위 {r['name']} ({r['code']})", axis=1
        ).tolist()

        if not options:
            st.info("필터 조건에 맞는 종목이 없습니다.")
        else:
            sel = st.selectbox("종목 선택", options)
            sel_idx = options.index(sel)
            row = fdf.reset_index().iloc[sel_idx]
            code = row["code"]
            name = row["name"]

            # 레이더 차트 + 점수 바
            col_radar, col_scores = st.columns([1, 1])

            with col_radar:
                st.plotly_chart(radar_chart(row, name), use_container_width=True)

            with col_scores:
                st.markdown(f"#### {name} 4축 점수")
                for axis in AXES:
                    val = float(row[axis])
                    lbl = AXIS_LABELS[axis]
                    color = AXIS_COLORS[axis]
                    st.markdown(
                        f"**{lbl}** &nbsp;&nbsp; {color_score(val)} **{val:.1f}점**",
                        unsafe_allow_html=True,
                    )
                    st.markdown(score_bar(val, color), unsafe_allow_html=True)
                    st.markdown("")

                total = float(row["Total"])
                rank = int(row["rank"])
                st.markdown(
                    f"<div style='margin-top:12px;padding:10px;background:#f0f2f6;"
                    f"border-radius:8px;text-align:center'>"
                    f"<span style='font-size:1.4em;font-weight:bold;color:#1f77b4'>"
                    f"종합 {total:.1f}점 / 100점</span><br>"
                    f"<span style='color:#666'>유니버스 {rank}위</span></div>",
                    unsafe_allow_html=True,
                )

            # 선별 근거
            st.divider()
            st.markdown("#### 선별 근거")
            reasons = explain_stock(code, fdf.reset_index())

            st.markdown(
                f"<div style='padding:12px;background:#e8f4fd;border-radius:8px;"
                f"border-left:4px solid #2196F3;margin-bottom:12px'>"
                f"📌 {reasons['total']}</div>",
                unsafe_allow_html=True,
            )

            r1, r2 = st.columns(2)
            with r1:
                st.markdown("**성장 (Growth)**")
                st.info(reasons["growth"])
                st.markdown("**가치 (Value)**")
                st.info(reasons["value"])
            with r2:
                st.markdown("**펀더멘털 (Quality)**")
                st.info(reasons["quality"])
                st.markdown("**추세 (Trend)**")
                st.info(reasons["trend"])

            # 유사 종목 비교
            st.divider()
            st.markdown("#### 유사 점수 종목 비교 (±10점 이내)")
            similar = fdf[
                (fdf["Total"].between(total - 10, total + 10))
                & (fdf.reset_index()["code"].values != code)
            ].head(5).reset_index()[["rank","name","code","Growth","Value","Quality","Trend","Total"]]
            if not similar.empty:
                st.dataframe(similar, use_container_width=True, hide_index=True)
            else:
                st.caption("유사 점수 종목 없음")

    # ── Tab 3: 분포 분석 ──────────────────────────────────────────────────────
    with tab3:
        st.subheader("점수 분포 분석")

        col_a, col_b = st.columns(2)

        with col_a:
            # 4축 점수 분포 박스플롯
            box_data = []
            for axis in AXES:
                for _, r in fdf.iterrows():
                    box_data.append({"축": AXIS_LABELS[axis], "점수": r[axis]})
            box_df = pd.DataFrame(box_data)
            fig_box = px.box(
                box_df, x="축", y="점수", color="축",
                color_discrete_map={v: AXIS_COLORS[k] for k, v in AXIS_LABELS.items()},
                title="4축 점수 분포",
            )
            fig_box.update_layout(showlegend=False, height=350)
            st.plotly_chart(fig_box, use_container_width=True)

        with col_b:
            # 종합점수 히스토그램
            fig_hist = px.histogram(
                fdf, x="Total", nbins=20,
                title="종합점수 분포",
                color_discrete_sequence=["#2196F3"],
                labels={"Total": "종합점수", "count": "종목 수"},
            )
            fig_hist.update_layout(height=350)
            st.plotly_chart(fig_hist, use_container_width=True)

        col_c, col_d = st.columns(2)

        with col_c:
            # 성장 vs 추세 산점도
            fig_scatter = px.scatter(
                fdf.reset_index(), x="Growth", y="Trend",
                hover_data=["name", "code", "Total"],
                color="Total",
                color_continuous_scale="RdYlGn",
                title="성장 vs 추세 (색상=종합점수)",
                labels={"Growth": "성장점수", "Trend": "추세점수"},
            )
            fig_scatter.update_layout(height=350)
            st.plotly_chart(fig_scatter, use_container_width=True)

        with col_d:
            # 시장별 평균 점수
            mkt_avg = fdf.groupby("market")[AXES + ["Total"]].mean().round(1)
            mkt_avg.columns = [AXIS_LABELS.get(c, c) for c in mkt_avg.columns]
            fig_bar = px.bar(
                mkt_avg.reset_index().melt(id_vars="market"),
                x="variable", y="value", color="market",
                barmode="group",
                title="시장별 평균 점수",
                labels={"variable": "축", "value": "평균점수", "market": "시장"},
            )
            fig_bar.update_layout(height=350)
            st.plotly_chart(fig_bar, use_container_width=True)


if __name__ == "__main__":
    main()
