"""Tests for RAPTOR."""

# Third-Party
import pandas as pd

# Local
from raptor_core.raptor import resolve_stop_ids, reconstruct_connection


def test_resolve_stop_ids_returns_all_matching_ids():
    stops = pd.DataFrame(
        {
            "stop_id": ["1", "2", "3"],
            "stop_name": ["Berlin Hbf", "Berlin Hbf", "Leipzig Hbf"],
        }
    )

    result = resolve_stop_ids("Berlin Hbf", stops)
    assert result == ["1", "2"]


def test_reconstruct_connection_returns_false_for_empty_result():
    best = [{} for _ in range(3)]
    result = reconstruct_connection(best, {"X"})
    assert result is False


def test_reconstruct_connection_rebuilds_simple_ride():
    best = [
        {
            "A": (8 * 3600, {"mode": "start", "k": 0, "prev_stop": None}),
        },
        {
            "B": (
                9 * 3600,
                {
                    "mode": "ride",
                    "prev_stop": "A",
                    "k": 0,
                    "route_id": "R1",
                    "trip_id": "T1",
                    "board_stop": "A",
                    "alight_stop": "B",
                    "board_time": 8 * 3600,
                    "alight_time": 9 * 3600,
                },
            )
        },
    ]

    result = reconstruct_connection(best, {"B"})
    assert result is not False
    assert len(result) == 1
    assert result[0]["destination_stop_id"] == "B"
    assert result[0]["transfers"] == 0
    assert result[0]["total_travel_time"] == 3600
    assert result[0]["legs"][0]["trip_id"] == "T1"
