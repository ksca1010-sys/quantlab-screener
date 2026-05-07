"""DART 재무제표와 사업보고서 기반 종목 분석."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

import pandas as pd


_ACCOUNT_SPECS = {
    "revenue": {
        "label": "매출액",
        "ids": ["Revenue", "Sales"],
        "names": ["매출액", "영업수익", "수익(매출액)"],
        "divs": ("IS", "CIS"),
    },
    "operating_income": {
        "label": "영업이익",
        "ids": ["OperatingIncome", "OperatingProfit"],
        "names": ["영업이익"],
        "divs": ("IS", "CIS"),
    },
    "net_income": {
        "label": "순이익",
        "ids": ["ProfitLoss"],
        "names": ["당기순이익", "분기순이익"],
        "divs": ("IS", "CIS"),
    },
    "assets": {
        "label": "자산총계",
        "ids": ["Assets"],
        "names": ["자산총계"],
        "divs": ("BS",),
    },
    "liabilities": {
        "label": "부채총계",
        "ids": ["Liabilities"],
        "names": ["부채총계"],
        "divs": ("BS",),
    },
    "equity": {
        "label": "자본총계",
        "ids": ["Equity"],
        "names": ["자본총계"],
        "divs": ("BS",),
    },
    "cash": {
        "label": "현금및현금성자산",
        "ids": ["CashAndCashEquivalents"],
        "names": ["현금및현금성자산", "현금 및 현금성자산"],
        "divs": ("BS",),
    },
    "current_assets": {
        "label": "유동자산",
        "ids": ["CurrentAssets"],
        "names": ["유동자산"],
        "divs": ("BS",),
    },
    "current_liabilities": {
        "label": "유동부채",
        "ids": ["CurrentLiabilities"],
        "names": ["유동부채"],
        "divs": ("BS",),
    },
}

_BUSINESS_SECTION_KEYWORDS = {
    "사업 구조": ("사업의 개요", "주요 제품", "서비스", "제품"),
    "매출 및 수주": ("매출", "수주", "계약", "고객"),
    "원재료·생산설비": ("원재료", "생산설비", "생산능력", "CAPA", "CAPEX"),
    "연구개발": ("연구개발", "R&D", "신제품", "개발"),
}


def _to_float(value: Any) -> float:
    if value is None:
        return float("nan")
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return float("nan")


def _match_account(df: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    work = df[df["sj_div"].isin(spec["divs"])].copy() if "sj_div" in df.columns else df.copy()
    if work.empty:
        return work

    matched = pd.DataFrame()
    if "account_id" in work.columns:
        for pat in spec["ids"]:
            rows = work[work["account_id"].str.endswith(f"_{pat}", na=False)]
            if rows.empty:
                rows = work[work["account_id"].str.contains(pat, na=False, case=False)]
            if not rows.empty:
                matched = rows
                break

    if matched.empty and "account_nm" in work.columns:
        for name in spec["names"]:
            rows = work[work["account_nm"] == name]
            if rows.empty:
                rows = work[work["account_nm"].str.contains(name, na=False)]
            if not rows.empty:
                matched = rows
                break

    return matched


def _extract_yearly(df: pd.DataFrame, key: str) -> pd.Series:
    if df.empty or "bsns_year" not in df.columns:
        return pd.Series(dtype=float)
    spec = _ACCOUNT_SPECS[key]
    rows = _match_account(df, spec)
    if rows.empty or "thstrm_amount" not in rows.columns:
        return pd.Series(dtype=float)
    return (
        rows.groupby("bsns_year")["thstrm_amount"]
        .first()
        .map(_to_float)
        .sort_index()
    )


def _safe_div(a: float, b: float, multiplier: float = 100.0) -> float:
    if pd.isna(a) or pd.isna(b) or b == 0:
        return float("nan")
    return a / b * multiplier


def _yoy(series: pd.Series) -> float:
    valid = series.dropna()
    if len(valid) < 2:
        return float("nan")
    prev = float(valid.iloc[-2])
    cur = float(valid.iloc[-1])
    if prev == 0:
        return float("nan")
    return (cur - prev) / abs(prev) * 100


def _cagr(series: pd.Series) -> float:
    valid = series.dropna()
    if len(valid) < 2:
        return float("nan")
    first = float(valid.iloc[0])
    last = float(valid.iloc[-1])
    years = len(valid) - 1
    if first <= 0 or last <= 0 or years <= 0:
        return float("nan")
    return ((last / first) ** (1 / years) - 1) * 100


def _won_to_eok(value: float) -> float:
    return value / 100_000_000 if pd.notna(value) else float("nan")


def _fmt_pct(value: float) -> str:
    return "—" if pd.isna(value) else f"{value:+.1f}%"


def _clean_text(text: str) -> str:
    return " ".join(str(text).replace("\xa0", " ").split())


def _split_sentences(text: str) -> list[str]:
    clean = _clean_text(text)
    if not clean:
        return []
    parts = []
    buf = []
    for ch in clean:
        buf.append(ch)
        if ch in ".。!?":
            sentence = "".join(buf).strip()
            if len(sentence) >= 20:
                parts.append(sentence)
            buf = []
    tail = "".join(buf).strip()
    if len(tail) >= 20:
        parts.append(tail)
    return parts if parts else ([clean[:220] + "..."] if len(clean) > 220 else [clean])


def _fetch_section_text(url: str) -> str:
    """DART 섹션 URL의 화면 텍스트를 가져온다."""
    if not url:
        return ""
    try:
        import requests
        from bs4 import BeautifulSoup

        resp = requests.get(url, timeout=8)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        return _clean_text(soup.get_text(" "))
    except Exception:
        return ""


def _summarize_business_section(title: str, text: str) -> dict[str, str]:
    """사업보고서 원문 섹션을 짧은 근거 문장으로 줄인다."""
    clean = _clean_text(text)
    if not clean:
        return {"title": title, "summary": "원문 텍스트를 자동 추출하지 못했습니다. 링크 원문 확인이 필요합니다."}

    title_text = f"{title} {clean}"
    picked: list[str] = []
    for keywords in _BUSINESS_SECTION_KEYWORDS.values():
        for sentence in _split_sentences(clean):
            if any(k.lower() in sentence.lower() for k in keywords):
                picked.append(sentence)
                break
    if not picked:
        picked = _split_sentences(title_text)[:2]

    summary = " ".join(picked[:2])
    if len(summary) > 420:
        summary = summary[:420].rsplit(" ", 1)[0] + "..."
    return {"title": title, "summary": summary}


def _build_business_report_brief(section_summaries: list[dict[str, str]]) -> list[str]:
    """사업보고서 섹션 요약을 보고자료 문단으로 정리한다."""
    if not section_summaries:
        return ["사업보고서 원문 섹션 텍스트를 자동 추출하지 못했습니다. 링크 원문에서 사업 구조, 매출 및 수주, 생산설비, 연구개발 항목을 확인해야 합니다."]

    report_lines = []
    for topic, keywords in _BUSINESS_SECTION_KEYWORDS.items():
        matched = [
            item for item in section_summaries
            if any(k in item.get("title", "") for k in keywords)
        ]
        if not matched:
            matched = [
                item for item in section_summaries
                if any(k.lower() in item.get("summary", "").lower() for k in keywords)
            ]
        if matched:
            report_lines.append(f"{topic}: {matched[0]['summary']}")
        else:
            report_lines.append(f"{topic}: 원문 자동 요약 근거가 부족합니다. 해당 항목은 링크 원문 확인이 필요합니다.")
    return report_lines


def _latest_numeric(row: dict[str, Any], key: str) -> float:
    value = row.get(key)
    return float(value) if value is not None and pd.notna(value) else float("nan")


def _build_overall_comment(
    latest_year: int,
    latest_annual: dict[str, Any],
    latest_ratios: dict[str, Any],
    revenue_cagr: float,
    revenue_yoy: float,
    op_yoy: float,
    net_yoy: float,
) -> str:
    """핵심 재무제표 항목으로 종합 요약 문장을 만든다."""
    revenue = _latest_numeric(latest_annual, "매출액(억원)")
    operating_income = _latest_numeric(latest_annual, "영업이익(억원)")
    net_income = _latest_numeric(latest_annual, "순이익(억원)")
    cash = _latest_numeric(latest_annual, "현금(억원)")
    op_margin = _latest_numeric(latest_ratios, "영업이익률")
    roe = _latest_numeric(latest_ratios, "ROE")
    debt = _latest_numeric(latest_ratios, "부채비율")
    current = _latest_numeric(latest_ratios, "유동비율")

    available_signals = [
        pd.notna(v)
        for v in (revenue, operating_income, net_income, revenue_cagr, revenue_yoy, op_margin, roe, debt, current)
    ]
    if sum(available_signals) < 3:
        return "재무제표 전체 총론을 만들기에는 핵심 항목이 부족합니다. 매출, 이익, 자본, 부채 항목이 추가 확보되기 전까지는 정량 판단을 보류해야 합니다."

    scale = f"{latest_year}년 기준 매출 {revenue:.1f}억원" if pd.notna(revenue) else f"{latest_year}년 기준"
    earnings = []
    if pd.notna(operating_income):
        earnings.append(f"영업이익 {operating_income:.1f}억원")
    if pd.notna(net_income):
        earnings.append(f"순이익 {net_income:.1f}억원")
    if pd.notna(cash):
        earnings.append(f"현금 {cash:.1f}억원")
    base = f"{scale}"
    if earnings:
        base += ", " + ", ".join(earnings)

    trend_parts = []
    if pd.notna(revenue_cagr):
        trend_parts.append(f"매출 CAGR은 {_fmt_pct(revenue_cagr)}")
    if pd.notna(revenue_yoy):
        trend_parts.append(f"최근 매출 YoY는 {_fmt_pct(revenue_yoy)}")
    if pd.notna(op_yoy):
        trend_parts.append(f"영업이익 YoY는 {_fmt_pct(op_yoy)}")
    if pd.notna(net_yoy):
        trend_parts.append(f"순이익 YoY는 {_fmt_pct(net_yoy)}")

    ratio_parts = []
    if pd.notna(op_margin):
        ratio_parts.append(f"영업이익률 {op_margin:.1f}%")
    if pd.notna(roe):
        ratio_parts.append(f"ROE {roe:.1f}%")
    if pd.notna(debt):
        ratio_parts.append(f"부채비율 {debt:.1f}%")
    if pd.notna(current):
        ratio_parts.append(f"유동비율 {current:.1f}%")

    sentences = [
        f"{base}입니다.",
        "이 총론은 업종 상대평가가 아닌 공시 숫자 요약입니다.",
    ]
    if trend_parts:
        sentences.append(", ".join(trend_parts) + "입니다.")
    if ratio_parts:
        sentences.append(f"{latest_year}년 주요 비율은 " + ", ".join(ratio_parts) + "입니다.")
    return " ".join(sentences)


def analyze_financial_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    """DART 재무제표 DataFrame을 분석 가능한 테이블과 코멘트로 변환."""
    if df.empty:
        return {"available": False, "reason": "DART 재무제표 데이터가 없습니다."}

    series = {key: _extract_yearly(df, key) for key in _ACCOUNT_SPECS}
    years = sorted({int(y) for s in series.values() for y in s.index})
    if not years:
        return {"available": False, "reason": "분석 가능한 연도별 재무 항목이 없습니다."}

    annual_rows = []
    ratio_rows = []
    for year in years:
        revenue = series["revenue"].get(year, float("nan"))
        op = series["operating_income"].get(year, float("nan"))
        net = series["net_income"].get(year, float("nan"))
        assets = series["assets"].get(year, float("nan"))
        liabilities = series["liabilities"].get(year, float("nan"))
        equity = series["equity"].get(year, float("nan"))
        cash = series["cash"].get(year, float("nan"))
        cur_assets = series["current_assets"].get(year, float("nan"))
        cur_liab = series["current_liabilities"].get(year, float("nan"))

        annual_rows.append({
            "연도": year,
            "매출액(억원)": round(_won_to_eok(revenue), 1) if pd.notna(revenue) else None,
            "영업이익(억원)": round(_won_to_eok(op), 1) if pd.notna(op) else None,
            "순이익(억원)": round(_won_to_eok(net), 1) if pd.notna(net) else None,
            "자산총계(억원)": round(_won_to_eok(assets), 1) if pd.notna(assets) else None,
            "부채총계(억원)": round(_won_to_eok(liabilities), 1) if pd.notna(liabilities) else None,
            "자본총계(억원)": round(_won_to_eok(equity), 1) if pd.notna(equity) else None,
            "현금(억원)": round(_won_to_eok(cash), 1) if pd.notna(cash) else None,
        })
        ratio_rows.append({
            "연도": year,
            "영업이익률": round(_safe_div(op, revenue), 1) if pd.notna(_safe_div(op, revenue)) else None,
            "순이익률": round(_safe_div(net, revenue), 1) if pd.notna(_safe_div(net, revenue)) else None,
            "ROE": round(_safe_div(net, equity), 1) if pd.notna(_safe_div(net, equity)) else None,
            "부채비율": round(_safe_div(liabilities, equity), 1) if pd.notna(_safe_div(liabilities, equity)) else None,
            "유동비율": round(_safe_div(cur_assets, cur_liab), 1) if pd.notna(_safe_div(cur_assets, cur_liab)) else None,
        })

    latest_year = years[-1]
    latest_ratios = ratio_rows[-1]
    revenue_cagr = _cagr(series["revenue"])
    revenue_yoy = _yoy(series["revenue"])
    op_yoy = _yoy(series["operating_income"])
    net_yoy = _yoy(series["net_income"])
    overall_comment = _build_overall_comment(
        latest_year,
        annual_rows[-1],
        latest_ratios,
        revenue_cagr,
        revenue_yoy,
        op_yoy,
        net_yoy,
    )

    comments: list[str] = []
    if pd.notna(revenue_cagr):
        if revenue_cagr >= 10:
            comments.append(f"매출 CAGR {_fmt_pct(revenue_cagr)}로 최근 연도 기준 성장성이 강합니다.")
        elif revenue_cagr >= 0:
            comments.append(f"매출 CAGR {_fmt_pct(revenue_cagr)}로 완만한 성장 또는 안정 구간입니다.")
        else:
            comments.append(f"매출 CAGR {_fmt_pct(revenue_cagr)}로 외형 축소가 확인됩니다.")
    if pd.notna(op_yoy):
        comments.append(f"최근 영업이익 YoY는 {_fmt_pct(op_yoy)}입니다.")
    if latest_ratios.get("영업이익률") is not None:
        margin = float(latest_ratios["영업이익률"])
        if margin >= 15:
            comments.append(f"{latest_year}년 영업이익률 {margin:.1f}%로 수익성이 높은 편입니다.")
        elif margin >= 5:
            comments.append(f"{latest_year}년 영업이익률 {margin:.1f}%로 보통 수준입니다.")
        else:
            comments.append(f"{latest_year}년 영업이익률 {margin:.1f}%로 수익성 방어 여부 확인이 필요합니다.")
    if latest_ratios.get("부채비율") is not None:
        debt = float(latest_ratios["부채비율"])
        if debt <= 100:
            comments.append(f"{latest_year}년 부채비율 {debt:.1f}%로 재무 레버리지는 낮은 편입니다.")
        elif debt <= 200:
            comments.append(f"{latest_year}년 부채비율 {debt:.1f}%로 재무 부담은 관리 범위입니다.")
        else:
            comments.append(f"{latest_year}년 부채비율 {debt:.1f}%로 레버리지 리스크 점검이 필요합니다.")
    if not comments:
        comments.append("핵심 재무비율 계산에 필요한 항목이 부족합니다.")

    return {
        "available": True,
        "annual": annual_rows,
        "ratios": ratio_rows,
        "summary": {
            "latest_year": latest_year,
            "revenue_yoy": revenue_yoy,
            "revenue_cagr": revenue_cagr,
            "operating_income_yoy": op_yoy,
            "net_income_yoy": net_yoy,
        },
        "overall_comment": overall_comment,
        "comments": comments,
    }


def fetch_business_report_sections(code: str, as_of_date: str) -> dict[str, Any]:
    """
    DART 사업보고서 섹션 링크를 조회한다.
    # 공시 시차 45일 룰: 분석 시점 t에서 t-45일 이전 접수 보고서만 사용해 look-ahead bias를 방지한다.
    """
    from src.data_loader import _dart_client

    cutoff = pd.Timestamp(as_of_date) - timedelta(days=45)
    start = (cutoff - pd.DateOffset(months=18)).strftime("%Y%m%d")
    end = cutoff.strftime("%Y%m%d")
    dart = _dart_client()

    reports = dart.list(corp=code, start=start, end=end, kind="A", final=True)
    if reports is None or reports.empty:
        return {"available": False, "reason": "45일 공시 시차 기준 내 사업보고서를 찾지 못했습니다."}

    reports = reports[reports["report_nm"].str.contains("사업보고서", na=False)].copy()
    if reports.empty:
        return {"available": False, "reason": "45일 공시 시차 기준 내 사업보고서를 찾지 못했습니다."}

    latest = reports.sort_values("rcept_dt", ascending=False).iloc[0]
    rcp_no = str(latest["rcept_no"])
    sections = dart.sub_docs(rcp_no, match="사업의 내용")
    if sections is None or sections.empty:
        sections = dart.sub_docs(rcp_no)

    wanted = ["사업의 개요", "주요 제품", "원재료", "생산설비", "매출 및 수주상황", "연구개발"]
    rows = []
    if sections is not None and not sections.empty:
        for _, row in sections.iterrows():
            title = str(row.get("title", "")).strip()
            if "사업의 내용" in title or any(w in title for w in wanted):
                rows.append({"title": title, "url": str(row.get("url", ""))})
    section_summaries = []
    for row in rows[:6]:
        text = _fetch_section_text(row.get("url", ""))
        section_summaries.append(_summarize_business_section(row.get("title", "DART 섹션"), text))

    return {
        "available": True,
        "report_name": str(latest["report_nm"]),
        "rcept_dt": str(latest["rcept_dt"]),
        "rcept_no": rcp_no,
        "cutoff": end,
        "sections": rows[:8],
        "section_summaries": section_summaries,
        "report_brief": _build_business_report_brief(section_summaries),
    }


def get_financial_statement_review(code: str, as_of_date: str) -> dict[str, Any]:
    """45일 시차 적용 DART 재무제표와 사업보고서 링크를 함께 반환."""
    from src.data_loader import get_financial_data

    financials = analyze_financial_dataframe(get_financial_data(code, as_of_date))
    try:
        business = fetch_business_report_sections(code, as_of_date)
    except Exception as e:
        business = {"available": False, "reason": f"사업보고서 조회 실패: {e}"}
    return {"financials": financials, "business": business}
