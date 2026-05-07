import pandas as pd

from src import data_loader


class FakeDart:
    def __init__(self):
        self.finstate_years: list[str] = []

    def list(self, corp, start, end, kind, final):
        assert end == "20260317"
        return pd.DataFrame([
            {"report_nm": "사업보고서 (2024.12)", "rcept_dt": "20250318"},
            {"report_nm": "사업보고서 (2025.12)", "rcept_dt": "20260319"},
        ])

    def finstate_all(self, code, year, reprt_code):
        self.finstate_years.append(year)
        return pd.DataFrame([
            {
                "bsns_year": int(year),
                "fs_div": "CFS",
                "sj_div": "IS",
                "account_nm": "매출액",
                "account_id": "ifrs-full_Revenue",
                "thstrm_amount": "1000",
            }
        ])


def test_get_financial_data_uses_only_reports_received_before_45_day_cutoff(monkeypatch):
    fake = FakeDart()
    data_loader.get_financial_data.cache_clear()
    monkeypatch.setattr(data_loader, "_dart_client", lambda: fake)

    result = data_loader.get_financial_data("000001", "2026-05-01")

    assert fake.finstate_years == ["2024"]
    assert result["bsns_year"].tolist() == [2024]
