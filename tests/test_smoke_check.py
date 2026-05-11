from __future__ import annotations

import pandas as pd
import pytest

from scripts import smoke_check


def _valid_output_frame(as_of_date: str, market_data_source: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "rank": [1],
            "name": ["A"],
            "code": ["1"],
            "market": ["KOSPI"],
            "sector": ["Tech"],
            "Growth": [80.0],
            "Value": [70.0],
            "Quality": [60.0],
            "Trend": [50.0],
            "Total": [65.0],
            "as_of_date": [as_of_date],
            "market_data_source": [market_data_source],
        }
    )


def test_smoke_rejects_current_naver_source_for_historical_csv(tmp_path, monkeypatch):
    out = tmp_path / "stocks_top100.csv"
    _valid_output_frame("2024-01-15", "naver_current_fallback").to_csv(out, index=False)

    monkeypatch.setattr(smoke_check.pd.Timestamp, "today", lambda: pd.Timestamp("2026-05-11"))

    with pytest.raises(AssertionError, match="historical as_of_date"):
        smoke_check.check_output_csv(out)


def test_smoke_allows_krx_cache_source_for_historical_csv(tmp_path, monkeypatch):
    out = tmp_path / "stocks_top100.csv"
    _valid_output_frame("2024-01-15", "krx_fundamental_cache").to_csv(out, index=False)

    monkeypatch.setattr(smoke_check.pd.Timestamp, "today", lambda: pd.Timestamp("2026-05-11"))

    smoke_check.check_output_csv(out)


def test_streamlit_shell_rejects_error_markers(monkeypatch):
    monkeypatch.setattr(
        smoke_check,
        "_read_url_text",
        lambda url, timeout=10.0: "<html>Streamlit ValueError: cannot insert rank</html>",
    )

    with pytest.raises(AssertionError, match="error markers"):
        smoke_check.check_streamlit_shell("https://example.test")


def test_deployed_health_allows_streamlit_auth_redirect(monkeypatch):
    monkeypatch.setattr(smoke_check, "_is_streamlit_auth_redirect", lambda base_url, timeout=10.0: True)
    monkeypatch.setattr(
        smoke_check,
        "_read_url_text",
        lambda url, timeout=10.0: pytest.fail("auth-gated app should not fetch shell"),
    )

    smoke_check.check_deployed_health("https://example.streamlit.app")
