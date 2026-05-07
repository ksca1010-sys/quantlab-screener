import pandas as pd

from src.financial_analysis import (
    _build_business_report_brief,
    _summarize_business_section,
    analyze_financial_dataframe,
)


def _row(year, sj_div, account_id, account_nm, amount):
    return {
        "bsns_year": year,
        "sj_div": sj_div,
        "account_id": account_id,
        "account_nm": account_nm,
        "thstrm_amount": str(amount),
    }


def test_analyze_financial_dataframe_builds_tables_and_comments():
    df = pd.DataFrame([
        _row(2023, "IS", "ifrs-full_Revenue", "매출액", 100_000_000_000),
        _row(2024, "IS", "ifrs-full_Revenue", "매출액", 120_000_000_000),
        _row(2023, "IS", "dart_OperatingIncome", "영업이익", 10_000_000_000),
        _row(2024, "IS", "dart_OperatingIncome", "영업이익", 18_000_000_000),
        _row(2023, "IS", "ifrs-full_ProfitLoss", "당기순이익", 8_000_000_000),
        _row(2024, "IS", "ifrs-full_ProfitLoss", "당기순이익", 12_000_000_000),
        _row(2024, "BS", "ifrs-full_Assets", "자산총계", 200_000_000_000),
        _row(2024, "BS", "ifrs-full_Liabilities", "부채총계", 80_000_000_000),
        _row(2024, "BS", "ifrs-full_Equity", "자본총계", 120_000_000_000),
        _row(2024, "BS", "ifrs-full_CurrentAssets", "유동자산", 70_000_000_000),
        _row(2024, "BS", "ifrs-full_CurrentLiabilities", "유동부채", 35_000_000_000),
    ])

    result = analyze_financial_dataframe(df)

    assert result["available"] is True
    assert result["summary"]["latest_year"] == 2024
    assert round(result["summary"]["revenue_yoy"], 1) == 20.0
    assert result["ratios"][-1]["영업이익률"] == 15.0
    assert result["ratios"][-1]["부채비율"] == 66.7
    assert "공시 숫자 요약" in result["overall_comment"]
    assert "매출 1200.0억원" in result["overall_comment"]
    assert result["comments"]


def test_business_report_brief_uses_only_extracted_section_text():
    summaries = [
        _summarize_business_section(
            "4. 매출 및 수주상황",
            "회사는 주요 고객과 장기 공급계약을 체결하고 있습니다. 수주잔고는 제품 납품 일정에 따라 매출로 인식됩니다.",
        ),
        _summarize_business_section(
            "6. 주요계약 및 연구개발활동",
            "연구개발활동은 신규 제품 개발과 기존 제품 성능 개선을 중심으로 진행됩니다.",
        ),
    ]

    brief = _build_business_report_brief(summaries)

    assert any(line.startswith("매출 및 수주:") for line in brief)
    assert any("수주잔고" in line for line in brief)
    assert any("원문 자동 요약 근거가 부족" in line for line in brief)
