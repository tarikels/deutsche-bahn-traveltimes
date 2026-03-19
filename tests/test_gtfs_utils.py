"""Tests for GTFS utilities."""


# Third-Party
import pandas as pd

# Local
from gtfs_toolbox.gtfs_io_utilities import (
    gtfs_time_to_seconds,
    seconds_to_gtfs_time,
    departures_per_stop_period,
)


def test_gtfs_time_to_seconds():
    print("Testing Works")
    assert gtfs_time_to_seconds("08:15:30") == 8 * 3600 + 15 * 60 + 30
    assert gtfs_time_to_seconds("25:00:00") == 25 * 3600
    assert gtfs_time_to_seconds("") is None
    assert gtfs_time_to_seconds(None) is None


def test_seconds_to_gtfs_time():
    assert seconds_to_gtfs_time(0) == "00:00:00"
    assert seconds_to_gtfs_time(3661) == "01:01:01"
    assert seconds_to_gtfs_time(25 * 3600) == "25:00:00"
    assert seconds_to_gtfs_time(None) is None


def test_departures_per_stop_period_counts_departures():
    feed = {
        "stop_times.txt": pd.DataFrame(
            {
                "stop_id": ["A", "A", "B", "B", "B"],
                "departure_time": ["08:00:00", "09:00:00", "10:00:00", None, ""],
            }
        )
    }

    result = departures_per_stop_period(feed)
    result = result.sort_values("stop_id").reset_index(drop=True)
    assert list(result["stop_id"]) == ["A", "B"]
    assert list(result["departures"]) == [2, 1]
