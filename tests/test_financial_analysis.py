import pandas as pd

from src.financial_analysis import analyze_financial_dataframe


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
        _row(2023, "IS", "ifrs-full_Revenue", "매출액", 1000),
        _row(2024, "IS", "ifrs-full_Revenue", "매출액", 1200),
        _row(2023, "IS", "dart_OperatingIncome", "영업이익", 100),
        _row(2024, "IS", "dart_OperatingIncome", "영업이익", 180),
        _row(2023, "IS", "ifrs-full_ProfitLoss", "당기순이익", 80),
        _row(2024, "IS", "ifrs-full_ProfitLoss", "당기순이익", 120),
        _row(2024, "BS", "ifrs-full_Assets", "자산총계", 2000),
        _row(2024, "BS", "ifrs-full_Liabilities", "부채총계", 800),
        _row(2024, "BS", "ifrs-full_Equity", "자본총계", 1200),
        _row(2024, "BS", "ifrs-full_CurrentAssets", "유동자산", 700),
        _row(2024, "BS", "ifrs-full_CurrentLiabilities", "유동부채", 350),
    ])

    result = analyze_financial_dataframe(df)

    assert result["available"] is True
    assert result["summary"]["latest_year"] == 2024
    assert round(result["summary"]["revenue_yoy"], 1) == 20.0
    assert result["ratios"][-1]["영업이익률"] == 15.0
    assert result["ratios"][-1]["부채비율"] == 66.7
    assert result["comments"]
