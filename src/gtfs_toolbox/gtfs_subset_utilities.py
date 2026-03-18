"""GTFS feed filtering utilities.

Implements common GTFS subsetting and parsing operations for filtering by service period.
"""

# Standard library
from datetime import date, timedelta
from typing import Iterable
import math

# Third-party
import pandas as pd


def parse_compact_date(raw: int | str) -> date:
    """Convert a compact GTFS date value into a Python date object.

    Args:
        raw: Date value in YYYYMMDD format as string or integer.

    Returns:
        Parsed date object.
    """
    text = str(raw)
    return date(int(text[0:4]), int(text[4:6]), int(text[6:8]))


def iter_dates(first_day: date, last_day: date) -> Iterable[date]:
    """Yield all dates in an inclusive date range.

    Args:
        first_day: First date in the range.
        last_day: Last date in the range.

    Returns:
        Iterator over all dates from start to end.
    """
    current_day = first_day
    while current_day <= last_day:
        yield current_day
        current_day += timedelta(days=1)


def service_weekday_name(day_value: date) -> str:
    """Map a date to the corresponding GTFS weekday column name.

    Args:
        day_value: Date for which the weekday column should be determined.

    Returns:
        GTFS weekday column name such as ``monday`` or ``sunday``.
    """
    weekday_names = [
        "monday", "tuesday", "wednesday", "thursday",
        "friday", "saturday", "sunday",
    ]
    return weekday_names[day_value.weekday()]


def services_active_on(calendar: pd.DataFrame,
                       calendar_dates: pd.DataFrame,
                       target_day: date) -> set[str]:
    """Determine which service IDs are active on a specific date.

    Args:
        calendar: GTFS calendar table.
        calendar_dates: GTFS calendar_dates table with service exceptions.
        target_day: Date to evaluate.

    Returns:
        Set of active service IDs for the given date.
    """
    base_services: set[str] = set()
    weekday_key = service_weekday_name(target_day)

    if not calendar.empty:
        running_mask = (
            (calendar["start_date"] <= target_day)
            & (calendar["end_date"] >= target_day)
            & (calendar[weekday_key] == 1)
        )
        base_services = set(calendar.loc[running_mask, "service_id"])

    added_services: set[str] = set()
    removed_services: set[str] = set()

    if not calendar_dates.empty:
        same_date_mask = calendar_dates["date"] == target_day
        added_services = set(
            calendar_dates.loc[
                same_date_mask & (calendar_dates["exception_type"] == 1),
                "service_id",
            ]
        )
        removed_services = set(
            calendar_dates.loc[
                same_date_mask & (calendar_dates["exception_type"] == 2),
                "service_id",
            ]
        )

    return (base_services | added_services) - removed_services


def services_active_between(calendar: pd.DataFrame,
                            calendar_dates: pd.DataFrame,
                            first_day: date,
                            last_day: date) -> set[str]:
    """Collect service IDs active on any day within a date range.

    Args:
        calendar: GTFS calendar table.
        calendar_dates: GTFS calendar_dates table with service exceptions.
        first_day: First date in the range.
        last_day: Last date in the range.

    Returns:
        Set of service IDs active at least once in the interval.
    """
    collected_services: set[str] = set()
    for day_value in iter_dates(first_day, last_day):
        collected_services |= services_active_on(calendar, calendar_dates, day_value)
    return collected_services


def subset_feed_by_date_window(feed: dict[str, pd.DataFrame],
                               start: str | int | date,
                               end: str | int | date,
                               *,
                               prune_stop_times: bool = True,
                               prune_stops: bool = True) -> dict[str, pd.DataFrame]:
    """Subset a GTFS feed to services active within a given date window.

    Args:
        feed: GTFS feed stored as a dictionary of DataFrames.
        start: Start date in YYYYMMDD format or as a date object.
        end: End date in YYYYMMDD format or as a date object.
        prune_stop_times: Whether to remove stop times not linked to retained trips.
        prune_stops: Whether to remove stops not linked to retained stop times.

    Returns:
        Filtered GTFS feed dictionary.
    """
    if not isinstance(start, date):
        start = parse_compact_date(start)
    if not isinstance(end, date):
        end = parse_compact_date(end)

    if end < start:
        raise ValueError("End date can not be earlier than start date")

    needed_tables = ["calendar.txt", "trips.txt", "routes.txt", "stop_times.txt", "stops.txt"]
    calendar_df, trips_df, routes_df, stop_times_df, stops_df = (feed[name] for name in needed_tables)
    calendar_exceptions = feed.get("calendar_dates.txt", pd.DataFrame())

    valid_service_ids = services_active_between(calendar_df, calendar_exceptions, start, end)

    if not trips_df.empty:
        trips_df = trips_df[trips_df["service_id"].isin(valid_service_ids)]

    if not routes_df.empty:
        route_ids = set(trips_df["route_id"])
        routes_df = routes_df[routes_df["route_id"].isin(route_ids)]

    if prune_stop_times and not stop_times_df.empty:
        trip_ids = set(trips_df["trip_id"])
        stop_times_df = stop_times_df[stop_times_df["trip_id"].isin(trip_ids)]

    if prune_stops and not stops_df.empty:
        stop_ids = set(stop_times_df["stop_id"])
        stops_df = stops_df[stops_df["stop_id"].isin(stop_ids)]

    narrowed_feed = dict(feed)
    narrowed_feed["trips.txt"] = trips_df
    narrowed_feed["stop_times.txt"] = stop_times_df
    narrowed_feed["routes.txt"] = routes_df
    narrowed_feed["stops.txt"] = stops_df
    return narrowed_feed


def great_circle_distance_meters(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    """Compute the great-circle distance between two coordinates in meters.

    Args:
        lat_a: Latitude of the first point.
        lon_a: Longitude of the first point.
        lat_b: Latitude of the second point.
        lon_b: Longitude of the second point.

    Returns:
        Distance between both points in meters.
    """
    earth_radius_m = 6371000.0
    phi_a, phi_b = math.radians(lat_a), math.radians(lat_b)
    delta_phi = math.radians(lat_b - lat_a)
    delta_lambda = math.radians(lon_b - lon_a)
    arc_component = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2.0) ** 2
    )
    central_angle = 2.0 * math.atan2(math.sqrt(arc_component), math.sqrt(1.0 - arc_component))
    return earth_radius_m * central_angle
