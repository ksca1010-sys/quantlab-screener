import pandas as pd
import pytest

from src import data_loader, main, universe


def test_build_market_data_uses_dated_krx_fundamentals(monkeypatch):
    universe_df = pd.DataFrame({
        "code": ["000001", "000002"],
        "name": ["A", "B"],
    })
    krx_df = pd.DataFrame({
        "code": ["000001"],
        "per": [8.0],
        "pbr": [0.7],
        "dividend_yield": [3.2],
    })
    monkeypatch.setattr(data_loader, "fetch_krx_fundamentals_by_date", lambda as_of_date: krx_df)

    result = main._build_market_data(universe_df, "2024-01-15")

    row = result[result["code"] == "000001"].iloc[0]
    assert row["per"] == 8.0
    assert row["pbr"] == 0.7
    assert row["dividend_yield"] == 3.2
    assert row["market_data_source"] == "krx_fundamental_by_date"


def test_build_market_data_preserves_krx_cache_source(monkeypatch):
    universe_df = pd.DataFrame({
        "code": ["000001"],
        "name": ["A"],
    })
    krx_df = pd.DataFrame({
        "code": ["000001"],
        "per": [8.0],
        "pbr": [0.7],
        "dividend_yield": [3.2],
        "market_data_source": ["krx_fundamental_cache"],
    })
    monkeypatch.setattr(data_loader, "fetch_krx_fundamentals_by_date", lambda as_of_date: krx_df)

    result = main._build_market_data(universe_df, "2024-01-15")

    assert result["market_data_source"].iloc[0] == "krx_fundamental_cache"


def test_fetch_krx_fundamentals_uses_disk_cache_before_pykrx(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    data_loader.fetch_krx_fundamentals_by_date.cache_clear()
    cache_dir = tmp_path / "krx_fundamentals"
    cache_dir.mkdir()
    (cache_dir / "20240115_ALL.csv").write_text(
        "code,per,pbr,dividend_yield\n1,9.1,0.8,2.5\n",
        encoding="utf-8",
    )

    class BrokenKrx:
        def get_market_fundamental_by_ticker(self, *args, **kwargs):
            pytest.fail("pykrx should not be called when dated cache exists")

    monkeypatch.setattr(data_loader, "krx", BrokenKrx())

    result = data_loader.fetch_krx_fundamentals_by_date("2024-01-15")

    assert result["code"].tolist() == ["000001"]
    assert result["per"].tolist() == [9.1]
    assert result["market_data_source"].tolist() == ["krx_fundamental_cache"]


def test_fetch_krx_fundamentals_saves_successful_pykrx_result(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    data_loader.fetch_krx_fundamentals_by_date.cache_clear()

    class FakeKrx:
        def get_market_fundamental_by_ticker(self, date, market):
            assert date == "20240115"
            if market == "KOSPI":
                return pd.DataFrame({
                    "PER": [10.0],
                    "PBR": [1.1],
                    "DIV": [2.0],
                }, index=pd.Index(["000001"], name="티커"))
            return pd.DataFrame()

    monkeypatch.setattr(data_loader, "krx", FakeKrx())

    result = data_loader.fetch_krx_fundamentals_by_date("2024-01-15")
    saved = pd.read_csv(tmp_path / "krx_fundamentals" / "20240115_ALL.csv", dtype={"code": str})

    assert result["market_data_source"].tolist() == ["krx_fundamental_by_date"]
    assert saved["code"].tolist() == ["000001"]
    assert saved["per"].tolist() == [10.0]


def test_historical_market_data_does_not_fallback_to_current_naver(monkeypatch):
    universe_df = pd.DataFrame({"code": ["000001"], "name": ["A"]})
    monkeypatch.setattr(data_loader, "fetch_krx_fundamentals_by_date", lambda as_of_date: pd.DataFrame())
    monkeypatch.setattr(data_loader, "fetch_naver_fundamentals", lambda code: pytest.fail("current Naver fallback must not be used"))

    class FixedTimestamp(pd.Timestamp):
        @classmethod
        def today(cls):
            return cls("2026-05-09")

    monkeypatch.setattr(main.pd, "Timestamp", FixedTimestamp)

    result = main._build_market_data(universe_df, "2024-01-15")

    assert pd.isna(result["per"].iloc[0])
    assert result["market_data_source"].iloc[0] == "unavailable_asof"


def test_latest_market_data_can_fallback_to_current_naver(monkeypatch):
    universe_df = pd.DataFrame({"code": ["000001"], "name": ["A"]})
    monkeypatch.setattr(data_loader, "fetch_krx_fundamentals_by_date", lambda as_of_date: pd.DataFrame())
    monkeypatch.setattr(
        data_loader,
        "fetch_naver_fundamentals",
        lambda code: {"per": 11.0, "pbr": 1.2, "dividend_yield": 2.3},
    )

    class FixedTimestamp(pd.Timestamp):
        @classmethod
        def today(cls):
            return cls("2026-05-11")

    monkeypatch.setattr(main.pd, "Timestamp", FixedTimestamp)

    result = main._build_market_data(universe_df, "2026-05-11")

    assert result["per"].iloc[0] == 11.0
    assert result["market_data_source"].iloc[0] == "naver_current_fallback"


def test_historical_universe_refuses_current_fdr_fallback(monkeypatch):
    class BrokenKrx:
        def get_market_cap_by_ticker(self, *args, **kwargs):
            raise RuntimeError("KRX unavailable")

    class FixedTimestamp(pd.Timestamp):
        @classmethod
        def today(cls):
            return cls("2026-05-11")

    monkeypatch.setattr(universe.pd, "Timestamp", FixedTimestamp)
    monkeypatch.setitem(__import__("sys").modules, "pykrx", type("PykrxModule", (), {"stock": BrokenKrx()})())
    monkeypatch.setattr(universe.fdr, "StockListing", lambda market: pytest.fail("historical fallback to FDR is forbidden"))

    with pytest.raises(RuntimeError, match="point-in-time"):
        universe._fetch_listing_with_marcap("2024-01-15")


def test_load_universe_regenerates_when_cached_as_of_date_differs(tmp_path, monkeypatch):
    path = tmp_path / "universe.yaml"
    monkeypatch.setattr(universe, "UNIVERSE_PATH", path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """
as_of_date: '2024-01-01'
kospi_top: 200
kosdaq_top: 100
stocks:
  - code: '000001'
    name: Old
    market: KOSPI
    sector: 기타
    market_cap: 1
""",
        encoding="utf-8",
    )

    fresh = pd.DataFrame({
        "code": ["000002"],
        "name": ["New"],
        "market": ["KOSPI"],
        "sector": ["기타"],
        "market_cap": [2],
    })
    monkeypatch.setattr(universe, "build_universe", lambda as_of_date, kospi_top, kosdaq_top: fresh)

    result = universe.load_universe(refresh=False, as_of_date="2024-01-02")

    assert result["code"].tolist() == ["000002"]
