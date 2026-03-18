"""
Build RAPTOR query indices from GTFS tables.

This module converts raw GTFS tables (pandas.DataFrames) into the core
precomputed lookup structures required by the RAPTOR routing algorithm,
including service calendars/exceptions, trip stop-time sequences, route-level
trip buckets, stop-sequence patterns, stop/pattern position maps, and optional
footpath adjacency from transfers/pathways.
"""

# Standard
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Set, Tuple

# Third-Party
import pandas as pd

# Local
from gtfs_toolbox import gtfs_io_utilities

# Short Names for complicated types
TripRecord = Tuple[List[str], List[int], List[int], List[int], str, str]
ServiceWindow = Tuple[Set[int], Optional[date], Optional[date]]
ExceptionLookup = Dict[Tuple[date, str], int]
TransferGraph = Dict[str, List[Tuple[str, int, int]]]


@dataclass(frozen=True)
class ServiceCatalog:
    """Stores regular weekday rules and date-specific service exceptions."""

    weekday_lookup: Dict[str, ServiceWindow]
    exception_lookup: ExceptionLookup


@dataclass(frozen=True)
class DayTripSelection:
    """Stores all trips running on one service day, grouped by route."""

    service_day: date
    route_to_trip_ids: Dict[str, List[str]]


def _normalize_service_day(on: date | str | int) -> date:
    """Convert a date-like input e.g. 20260224 into a datetime.date instance."""
    return gtfs_io_utilities.yyyymmdd_to_date(on)


def _ordered_active_weekdays(record: pd.Series) -> Set[int]:
    """Extract active weekday indices from one calendar.txt row."""
    weekday_columns = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

    return {idx for idx, column_name in enumerate(weekday_columns) if int(record.get(column_name, 0)) == 1}


def create_service_lookup(feed: Dict[str, pd.DataFrame]) -> Tuple[Dict[str, ServiceWindow], ExceptionLookup]:
    """
    Create GTFS service lookup tables from calendar.txt and
    calendar_dates.txt.

    Args:
        feed: GTFS feed dictionary.

    Returns:
        Tuple of weekday/date-range lookup and exception lookup.
    """
    calendar_table = feed.get("calendar.txt", pd.DataFrame())
    calendar_dates_table = feed.get("calendar_dates.txt", pd.DataFrame())

    weekday_lookup: Dict[str, ServiceWindow] = {}
    for _, row in calendar_table.iterrows():
        service_id = str(row["service_id"])
        weekday_lookup[service_id] = (_ordered_active_weekdays(row), row.get("start_date"), row.get("end_date"))

    exception_lookup: ExceptionLookup = {}
    for _, row in calendar_dates_table.iterrows():
        state = +1 if int(row["exception_type"]) == 1 else -1
        exception_lookup[(row["date"], str(row["service_id"]))] = state

    return weekday_lookup, exception_lookup


def service_runs_on_date(on: date | str | int, service_id: str | int, weekday_lookup: Dict[str, ServiceWindow],
                         exception_lookup: ExceptionLookup) -> bool:
    """
    Check whether a GTFS service is active on the given date.

    Args:
        on: Service day.
        service_id: GTFS service identifier.
        weekday_lookup: Regular weekday/date-range lookup.
        exception_lookup: Per-date service overrides.

    Returns:
        True when the service runs on the given day, otherwise False.
    """
    current_day = _normalize_service_day(on)
    service_key = str(service_id)

    override = exception_lookup.get((current_day, service_key))
    if override is not None:
        return override == +1

    service_window = weekday_lookup.get(service_key)
    if service_window is None:
        return False

    active_weekdays, start_day, end_day = service_window
    if start_day and current_day < start_day:
        return False
    if end_day and current_day > end_day:
        return False

    return current_day.weekday() in active_weekdays


def _prepare_trip_stop_frame(feed: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Build a sorted stop-time table enriched with trip-level metadata.
    This helper merges stop_times.txt with the relevant columns from
    trips.txt so each stop event also carries its route and service
    information. The resulting frame is used as a normalized working table
    for constructing trip-based lookup structures.
    """
    stop_times = feed["stop_times.txt"].copy()
    trips = feed["trips.txt"][["trip_id", "route_id", "service_id"]].copy()

    stop_times["trip_id"] = stop_times["trip_id"].astype(str)
    stop_times["stop_id"] = stop_times["stop_id"].astype(str)
    stop_times["stop_sequence"] = stop_times["stop_sequence"].astype(int)
    trips["trip_id"] = trips["trip_id"].astype(str)

    merged = stop_times.merge(trips, on="trip_id", how="left")
    return merged.sort_values(["trip_id", "stop_sequence"])


def _trip_record_from_group(group: pd.DataFrame) -> TripRecord:
    """
    Convert all stop-time rows of a single trip into the standard
    trip record structure used by the routing logic.
    """
    return (group["stop_id"].tolist(), [int(value) for value in group["arrival_time_seconds"].tolist()],
            [int(value) for value in group["departure_time_seconds"].tolist()], group["stop_sequence"].tolist(),
            str(group["route_id"].iloc[0]), str(group["service_id"].iloc[0]))


def create_trip_stop_lookup(feed: Dict[str, pd.DataFrame]) -> Dict[str, TripRecord]:
    """
    Build the per-trip stop/time lookup used by routing and index generation.
    """
    merged = _prepare_trip_stop_frame(feed)
    trip_lookup: Dict[str, TripRecord] = {}

    for trip_id, group in merged.groupby("trip_id"):
        trip_lookup[str(trip_id)] = _trip_record_from_group(group)

    return trip_lookup


def _first_valid_departure(departures: Iterable[int | None]) -> Optional[int]:
    """Return the first non-null departure value from a trip schedule."""
    for departure in departures:
        if departure is not None:
            return int(departure)
    return None


def group_active_trips_by_route(trip_lookup: Dict[str, TripRecord], on: date | int | str,
                                weekday_lookup: Dict[str, ServiceWindow],
                                exception_lookup: ExceptionLookup,) -> Dict[str, List[str]]:
    """
    Group active trip ids by route and order each route by first departure.

    Args:
        trip_lookup: Per-trip stop/time lookup.
        on: Service day.
        weekday_lookup: Regular weekday/date-range lookup.
        exception_lookup: Per-date service overrides.

    Returns:
        Route-to-trip mapping ordered by first departure time.
    """
    route_buckets: Dict[str, List[Tuple[str, int]]] = {}

    for trip_id, (_stops, _arrivals, departures, _seq, route_id, service_id) in trip_lookup.items():
        if not service_runs_on_date(on, service_id, weekday_lookup, exception_lookup):
            continue

        first_departure = _first_valid_departure(departures)
        if first_departure is None:
            continue

        route_buckets.setdefault(route_id, []).append((trip_id, first_departure))

    return {
        route_id: [trip_id for trip_id, _ in sorted(entries, key=lambda entry: entry[1])]
        for route_id, entries in route_buckets.items()
    }


def _shift_trip_record_to_next_day(record: TripRecord) -> TripRecord:
    """
    Duplicate one trip record with all times shifted by 24 hours.
    We need this to ensure that also Trips with late starting time are handled correctly
    """
    stop_ids, arrivals, departures, sequence, route_id, service_id = record
    return (
        stop_ids,
        [None if value is None else int(value) + 24 * 3600 for value in arrivals],
        [None if value is None else int(value) + 24 * 3600 for value in departures],
        sequence,
        route_id,
        service_id,
    )


def _expand_to_consecutive_service_days(trip_lookup: Dict[str, TripRecord], selections: List[DayTripSelection],
                                        suffixes: List[str]) -> Tuple[Dict[str, TripRecord], Dict[str, List[str]]]:
    """
    Merge trip selections from consecutive service days into one combined set.

    Trips from later days can be copied with a suffix and shifted forward in
    time so all trips share one continuous timeline across midnight.

    Args:
        trip_lookup: Mapping of trip IDs to trip records.
        selections: Daily trip selections to combine.
        suffixes: Trip ID suffixes for each selection.

    Returns:
        Expanded trip lookup and merged route-to-trip mapping.
    """
    expanded_trip_lookup: Dict[str, TripRecord] = dict(trip_lookup)
    combined_routes: Dict[str, List[str]] = {}

    for selection, suffix in zip(selections, suffixes):
        for route_id, trip_ids in selection.route_to_trip_ids.items():
            target_ids: List[str] = []
            for trip_id in trip_ids:
                normalized_trip_id = str(trip_id)
                if suffix:
                    expanded_trip_id = f"{normalized_trip_id}{suffix}"
                    expanded_trip_lookup[expanded_trip_id] \
                        = _shift_trip_record_to_next_day(trip_lookup[normalized_trip_id])
                    target_ids.append(expanded_trip_id)
                else:
                    target_ids.append(normalized_trip_id)
            combined_routes.setdefault(route_id, []).extend(target_ids)

    for route_id, trip_ids in combined_routes.items():
        combined_routes[route_id] = sorted(
            trip_ids,
            key=lambda trip_id: _first_valid_departure(expanded_trip_lookup[trip_id][2]) or 10**18,
        )

    return expanded_trip_lookup, combined_routes


def create_route_patterns(trip_lookup: Dict[str, TripRecord], trips_by_route: Dict[str, List[str]]) \
        -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, list[str]], dict[str, str]]:
    """
    Group active trips into route patterns based on their stop sequence.
    Trips with the same ordered stop list are assigned to the same pattern.

    Args:
        trip_lookup: Per-trip stop/time lookup.
        trips_by_route: Active trip ids grouped by route.

    Returns:
        Pattern stop lists, trips by pattern, patterns by route, and the
        pattern-to-route mapping.
    """
    pattern_stops: Dict[str, List[str]] = {}
    trips_by_pattern: Dict[str, List[str]] = {}
    patterns_by_route: Dict[str, List[str]] = {}
    pattern_route: Dict[str, str] = {}

    for route_id, trip_ids in trips_by_route.items():
        known_sequences: Dict[Tuple[str, ...], str] = {}
        for trip_id in trip_ids:
            sequence_key = tuple(trip_lookup[trip_id][0])
            pattern_id = known_sequences.get(sequence_key)
            if pattern_id is None:
                pattern_id = f"{route_id}|{hash(sequence_key)}"
                known_sequences[sequence_key] = pattern_id
                pattern_stops[pattern_id] = list(sequence_key)
                trips_by_pattern[pattern_id] = []
                patterns_by_route.setdefault(route_id, []).append(pattern_id)
                pattern_route[pattern_id] = route_id
            trips_by_pattern[pattern_id].append(trip_id)

    return pattern_stops, trips_by_pattern, patterns_by_route, pattern_route


def _append_transfer_rows(rows: pd.DataFrame, *, adjacency: TransferGraph, source_col: str, target_col: str,
                          duration_col: str, fallback_seconds: int) -> None:
    """
    Add transfer edges from a table to the stop adjacency mapping.
    This helper reads transfer-like rows, extracts source stops, target stops,
    and walking durations and appends them to the shared adjacency structure.

    Args:
        rows: Table containing transfer relations between stops.
        adjacency: Mapping that stores outgoing transfer edges per stop.
        source_col: Column name for the origin stop ID.
        target_col: Column name for the destination stop ID.
        duration_col: Column name for the transfer duration in seconds.
        fallback_seconds: Default duration used when no valid duration is given.

    Returns:
        None. The adjacency mapping is updated in place.
    """
    if rows.empty or source_col not in rows.columns or target_col not in rows.columns:
        return

    if duration_col not in rows.columns:
        rows[duration_col] = fallback_seconds

    rows[duration_col] = rows[duration_col].fillna(fallback_seconds).astype(int)
    for _, row in rows.iterrows():
        source_stop = str(row[source_col])
        target_stop = str(row[target_col])
        duration_seconds = int(row.get(duration_col, fallback_seconds) or fallback_seconds)
        adjacency.setdefault(source_stop, []).append((target_stop, duration_seconds, fallback_seconds))


def read_transfer_graph(feed: dict[str, pd.DataFrame], default_change_sec: int = 120) -> TransferGraph:
    """
    Read transfers and pathways into stop-based footpath adjacency lists.

    Args:
        feed: GTFS feed dictionary.
        default_change_sec: Fallback change time in seconds.

    Returns:
        Stop-to-footpath adjacency mapping.
    """
    adjacency: TransferGraph = {}
    transfers = feed.get("transfers.txt", pd.DataFrame()).copy()
    pathways = feed.get("pathways.txt", pd.DataFrame()).copy()

    _append_transfer_rows(
        transfers,
        adjacency=adjacency,
        source_col="from_stop_id",
        target_col="to_stop_id",
        duration_col="min_transfer_time",
        fallback_seconds=default_change_sec)

    _append_transfer_rows(
        pathways,
        adjacency=adjacency,
        source_col="from_stop_id",
        target_col="to_stop_id",
        duration_col="traversal_time",
        fallback_seconds=default_change_sec)

    return adjacency


def create_patterns_per_stop(pattern_stops: dict[str, list[str]]) -> dict[str, set[str]]:
    """
    Build a lookup from each stop to all route patterns that pass through it.

    This makes it easy to see which patterns serve a given stop without
    scanning all pattern stop lists again.

    Args:
        pattern_stops: Mapping from pattern id to ordered stop ids.

    Returns:
        Mapping from stop id to all patterns serving that stop.
    """
    patterns_per_stop: Dict[str, Set[str]] = {}
    for pattern_id, stop_ids in pattern_stops.items():
        for stop_id in stop_ids:
            patterns_per_stop.setdefault(stop_id, set()).add(pattern_id)
    return patterns_per_stop


def _select_day_trips(trip_lookup: Dict[str, TripRecord], service_catalog: ServiceCatalog,
                      service_day: date) -> DayTripSelection:
    """Resolve the active trip set for one service day."""
    return DayTripSelection(
        service_day=service_day,
        route_to_trip_ids=group_active_trips_by_route(
            trip_lookup,
            service_day,
            service_catalog.weekday_lookup,
            service_catalog.exception_lookup,
        ),
    )


def build_raptor_indices(feed: dict[str, pd.DataFrame], on: date | str | int) -> dict[str, object]:
    """
    Build RAPTOR lookup structures for the requested day and the following day.

    Args:
        feed: GTFS feed dictionary.
        on: Base service day.

    Returns:
        Dictionary with all lookup structures required by the routing engine in raptor.py.
    """
    base_day = _normalize_service_day(on)
    service_catalog = ServiceCatalog(*create_service_lookup(feed))
    trip_lookup = create_trip_stop_lookup(feed)

    day0 = _select_day_trips(trip_lookup, service_catalog, base_day)
    day1 = _select_day_trips(trip_lookup, service_catalog, base_day + timedelta(days=1))

    expanded_trip_lookup, combined_routes = _expand_to_consecutive_service_days(
        trip_lookup,
        [day0, day1],
        ["", "__D1"],
    )

    pattern_stops, pattern_trips, route_patterns, pattern_to_route = create_route_patterns(
        expanded_trip_lookup,
        combined_routes,
    )

    return {
        "trip_times": expanded_trip_lookup,
        "stops_in_pattern": pattern_stops,
        "trips_by_pattern": pattern_trips,
        "pattern_route": pattern_to_route,
        "patterns_by_stop": create_patterns_per_stop(pattern_stops),
        "footpaths": read_transfer_graph(feed),
    }
