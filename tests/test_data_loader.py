import pandas as pd

from src import data_loader


class FakeDart:
    def __init__(self):
        self.api_key = "fake-key"

    def list(self, corp, start, end, kind, final):
        assert end == "20260317"
        return pd.DataFrame([
            {"report_nm": "사업보고서 (2024.12)", "rcept_dt": "20250318", "rcept_no": "202503180001"},
            {"report_nm": "사업보고서 (2025.12)", "rcept_dt": "20260319", "rcept_no": "202603190001"},
        ])

    def find_corp_code(self, code):
        return "00123456"


def _fake_finstate_request(api_key, corp_code, bsns_year, reprt_code, fs_div):
    if fs_div == "OFS":
        return pd.DataFrame()
    return pd.DataFrame([
        {
            "rcept_no": "202503180001",
            "bsns_year": bsns_year,
            "fs_div": fs_div,
            "sj_div": "IS",
            "account_nm": "매출액",
            "account_id": "ifrs-full_Revenue",
            "thstrm_amount": "1000",
        }
    ])


def test_get_financial_data_uses_only_reports_received_before_45_day_cutoff(tmp_path, monkeypatch):
    fake = FakeDart()
    calls: list[tuple[str, str]] = []

    def request_spy(api_key, corp_code, bsns_year, reprt_code, fs_div):
        calls.append((bsns_year, fs_div))
        return _fake_finstate_request(api_key, corp_code, bsns_year, reprt_code, fs_div)

    data_loader.get_financial_data.cache_clear()
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(data_loader, "_dart_client", lambda: fake)
    monkeypatch.setattr(data_loader, "_request_finstate_all", request_spy)

    result = data_loader.get_financial_data("000001", "2026-05-01")

    assert calls == [("2024", "CFS"), ("2024", "OFS")]
    assert result["bsns_year"].tolist() == [2024]
    assert result["source_rcept_dt"].tolist() == ["20250318"]
    assert result["source_rcept_no"].tolist() == ["202503180001"]


def test_get_financial_data_excludes_year_when_finstate_receipt_does_not_match(tmp_path, monkeypatch):
    fake = FakeDart()

    def mismatched_request(api_key, corp_code, bsns_year, reprt_code, fs_div):
        if fs_div == "OFS":
            return pd.DataFrame()
        return pd.DataFrame([
            {
                "rcept_no": "209912310999",
                "bsns_year": bsns_year,
                "fs_div": fs_div,
                "sj_div": "IS",
                "account_nm": "매출액",
                "account_id": "ifrs-full_Revenue",
                "thstrm_amount": "1000",
            }
        ])

    data_loader.get_financial_data.cache_clear()
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(data_loader, "_dart_client", lambda: fake)
    monkeypatch.setattr(data_loader, "_request_finstate_all", mismatched_request)

    result = data_loader.get_financial_data("000001", "2026-05-01")

    assert result.empty
