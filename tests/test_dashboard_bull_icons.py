import pandas as pd

from dashboard import app


def _dashboard_csv_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "rank": [5, 1],
        "name": ["B", "A"],
        "code": ["2", "000001"],
        "market": ["KOSPI", "KOSPI"],
        "sector": ["Tech", "Tech"],
        "Growth": [20.0, 70.0],
        "Value": [30.0, 60.0],
        "Quality": [40.0, 50.0],
        "Trend": [50.0, 40.0],
        "Total": [35.0, 55.0],
    })


def test_load_data_preserves_explicit_rank_without_reset_collision(tmp_path, monkeypatch):
    csv_path = tmp_path / "stocks_top100.csv"
    _dashboard_csv_frame().to_csv(csv_path, index=False)
    monkeypatch.setattr(app, "CSV_PATH", csv_path)
    app.load_data.clear()

    loaded = app.load_data()

    assert loaded.index.name == "rank"
    assert loaded["universe_rank"].tolist() == [1, 5]
    assert loaded["code"].tolist() == ["000001", "000002"]


def test_plain_df_drops_rank_index_before_csv_download():
    df = _dashboard_csv_frame().set_index(pd.Index([1, 2], name="rank"))

    plain = app._plain_df(df)

    assert plain.index.name is None
    assert plain.columns.tolist().count("rank") == 1


def test_bull_sector_fallback_uses_trend_when_cache_is_missing():
    df = pd.DataFrame({
        "sector": ["전기·전자", "전기·전자", "보험업", "보험업"],
        "name": ["테스", "삼성전자", "삼성화재", "DB손해보험"],
        "Trend": [64.8, 55.0, 50.0, 58.0],
    })

    info = app._derive_sector_strength_from_scores(df)

    assert "전기·전자" in info["bull_sectors"]
    assert app._is_bull_pick("전기·전자", 64.8, set(info["bull_sectors"]))
    assert not app._is_bull_pick("보험업", 58.0, set(info["bull_sectors"]))


def test_initial_sector_strength_falls_back_when_no_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "_SECTOR_CACHE_PATH", tmp_path / "missing.json")
    df = pd.DataFrame({
        "sector": ["운수·창고업"],
        "name": ["현대글로비스"],
        "Trend": [80.0],
    })

    info = app._load_sector_strength_for_initial_render(df)

    assert info["source"] == "trend_fallback"
    assert info["bull_sectors"] == ["운수·창고업"]
