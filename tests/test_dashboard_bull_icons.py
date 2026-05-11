import pandas as pd

from dashboard import app


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
