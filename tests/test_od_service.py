"""Tests for service od functions."""

# Third-Party
import pandas as pd

# Local
from app.services.od import od_metric


def test_od_metric_returns_empty_for_unknown_metric():
    result = od_metric(
        period="2026W09",
        day_type="weekday",
        hour=8,
        origin_zone_id="11000",
        metric="unknown_metric",
    )
    assert result["values"] == {}
    assert result["mode"] == "od"


def test_od_metric_origin_avg_with_monkeypatched_loader(monkeypatch):
    mock_df = pd.DataFrame(
        {
            "origin_zone_id": ["1", "1", "2"],
            "dest_zone_id": ["2", "3", "1"],
            "total_travel_time_sec": [3600, 7200, 4000],
            "origin_stop_id": ["S1", "S1", "S2"],
            "origin_stop_name": ["Stop 1", "Stop 1", "Stop 2"],
        }
    )

    monkeypatch.setattr("app.services.od._load_hour_df", lambda period, day_type, hour: mock_df)

    result = od_metric(
        period="2026W09",
        day_type="weekday",
        hour=8,
        origin_zone_id=None,
        metric="travel_time",
    )

    assert result["mode"] == "origin_avg"
    assert result["values"]["1"] == 5400
    assert result["values"]["2"] == 4000


def test_od_metric_for_selected_origin(monkeypatch):
    mock_df = pd.DataFrame(
        {
            "origin_zone_id": ["1", "1", "1"],
            "dest_zone_id": ["2", "3", "3"],
            "total_travel_time_sec": [5000, 7000, 6500],
            "origin_stop_id": ["S1", "S1", "S1"],
            "origin_stop_name": ["Stop 1", "Stop 1", "Stop 1"],
            "dest_stop_id": ["S2", "S3a", "S3b"],
            "dest_stop_name": ["Stop 2", "Stop 3a", "Stop 3b"],
        }
    )

    monkeypatch.setattr("app.services.od._load_hour_df", lambda period, day_type, hour: mock_df)

    result = od_metric(
        period="2026W09",
        day_type="weekday",
        hour=8,
        origin_zone_id="1",
        metric="travel_time",
    )

    assert result["mode"] == "od"
    assert result["values"]["2"] == 5000
    assert result["values"]["3"] == 6500
