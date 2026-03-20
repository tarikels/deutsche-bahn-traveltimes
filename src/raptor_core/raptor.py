"""
Compute public transport journeys with the RAPTOR algorithm.

This module applies the RAPTOR routing algorithm to GTFS-based timetable data
in order to compute earliest-arrival journeys under departure-time, transfer,
and walking constraints. It operates on precomputed RAPTOR indices and
provides the core logic for round-based label propagation, trip scanning,
footpath relaxation, journey backtracking, and conversion of routing results
into readable connection summaries.
"""

# Standard
from bisect import bisect_left
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set, Tuple, Any

# Third-party
import pandas as pd

# Local
from gtfs_toolbox import gtfs_io_utilities


# Short Names for complicated types
LabelEntry = Tuple[int, dict]
RoundLabels = Dict[str, LabelEntry]
DepartureCache = Dict[Tuple[str, int], Tuple[List[int], List[str]]]
TripTimes = Dict[str, Tuple[List[str], List[int], List[int], List[int], str, str]]


@dataclass(frozen=True)
class BoardingDecision:
    """Stores a possible place and time to board a trip."""

    trip_id: str
    departure_time: int
    board_stop_id: str
    board_index: int


@dataclass(frozen=True)
class ActiveRide:
    """Stores the trip currently being ridden while scanning a pattern."""

    trip_id: str
    board_stop_id: str
    board_time: int
    board_index: int


@dataclass
class QueryContext:
    """Resolved routing lookups and query parameters for one RAPTOR run."""

    trip_times: TripTimes
    stops_in_pattern: Dict[str, List[str]]
    footpaths: Dict[str, List[Tuple[str, int, int]]]
    dep_cache: DepartureCache
    patterns_by_stop: Dict[str, Set[str]]
    pattern_route: Dict[str, str]
    origin_ids: Set[str]
    destination_ids: Set[str]
    requested_departure: int
    max_transfers: int
    transfer_slack_sec: int
    avoid_passing_origin_after_boarding: bool


@dataclass
class RoutingState:
    """Mutable state for a multi-round RAPTOR query."""

    best: List[RoundLabels]
    frontier: Set[str]


@dataclass(frozen=True)
class JourneyDraft:
    """Intermediate reconstructed journey before final formatting."""

    destination_stop_id: str
    round_index: int
    arrival_time: int
    first_board_time: int
    transfers: int
    legs: List[dict[str, object]]


def prepare_departure_lookup(indices):
    """
    Precompute departure lookup lists per pattern and stop position. Enables a fast lookup by binary search.

    Args:
        indices: RAPTOR index dictionary.

    Returns:
        None. Updates indices in place with dep_cache.
    """
    trip_times: TripTimes = indices["trip_times"]
    trips_by_pattern: Dict[str, List[str]] = indices["trips_by_pattern"]
    departure_cache: DepartureCache = {}

    for pattern_id, trip_ids in trips_by_pattern.items():
        if not trip_ids:
            continue

        stop_count = len(trip_times[trip_ids[0]][2])
        for stop_index in range(stop_count):
            departures_with_trip: List[Tuple[int, str]] = []
            for trip_id in trip_ids:
                departure = trip_times[trip_id][2][stop_index]
                if departure is not None:
                    departures_with_trip.append((departure, trip_id))

            departures_with_trip.sort(key=lambda item: item[0])
            departure_cache[(pattern_id, stop_index)] = (
                [departure for departure, _ in departures_with_trip],
                [trip_id for _, trip_id in departures_with_trip],
            )

    indices["dep_cache"] = departure_cache


def resolve_stop_ids(stop_label: str, stops_table: pd.DataFrame) -> list[str]:
    """
    Resolve a stop name to all matching stop ids from a GTFS stops table.

    Args:
        stop_label: Human-readable stop name.
        stops_table: GTFS stops.txt table.

    Returns:
        Matching stop ids with duplicates removed while preserving order.
    """
    target = stop_label.strip().casefold()
    names = stops_table["stop_name"].astype(str).str.strip().str.casefold()
    matches = stops_table.loc[names == target, "stop_id"].astype(str).tolist()
    return list(dict.fromkeys(matches))


def route_by_stop_names(indices: Dict[str, object], stops_table: pd.DataFrame, origin_name: str, destination_name: str,
                        departure_time: int, **kwargs) -> tuple[list[dict[str, tuple[int, dict]]], set[str]]:
    """
    Compute a RAPTOR journey after resolving stop names to stop ids.

    Args:
        indices: RAPTOR index dictionary.
        stops_table: GTFS stops.txt table.
        origin_name: Origin stop name.
        destination_name: Destination stop name.
        departure_time: Departure time forwarded to the id-based function.
        **kwargs: Additional keyword arguments forwarded to route_by_stop_ids.

    Returns:
        Result of the id-based RAPTOR query.
    """
    origin_ids = set(resolve_stop_ids(origin_name, stops_table))
    destination_ids = set(resolve_stop_ids(destination_name, stops_table))
    return route_by_stop_ids(indices, origin_ids, destination_ids, departure_time, **kwargs)


def _coerce_departure_time(departure_time: str | int) -> int:
    """Convert GTFS time strings to seconds when needed."""
    if isinstance(departure_time, str):
        return gtfs_io_utilities.gtfs_time_to_seconds(departure_time)
    return int(departure_time)


def _build_query_context(indices: Dict[str, object], origin_ids: Set[str], destination_ids: Set[str],
                         departure_time: str | int, *, max_transfers: int, transfer_slack_sec: int,
                         avoid_passing_origin_after_boarding: bool) -> QueryContext:
    """Resolve indices and parameters into a compact query context.
    Arguments and return explained in route_by_stop_ids.
    """

    return QueryContext(
        trip_times=indices["trip_times"],
        stops_in_pattern=indices["stops_in_pattern"],
        footpaths=indices.get("footpaths", {}),
        dep_cache=indices["dep_cache"],
        patterns_by_stop=indices["patterns_by_stop"],
        pattern_route=indices["pattern_route"],
        origin_ids=set(origin_ids),
        destination_ids=set(destination_ids),
        requested_departure=_coerce_departure_time(departure_time),
        max_transfers=max_transfers,
        transfer_slack_sec=transfer_slack_sec,
        avoid_passing_origin_after_boarding=avoid_passing_origin_after_boarding,
    )


def _initialize_routing_state(context: QueryContext) -> RoutingState:
    """Create the initial RAPTOR round state from the origin stops."""
    best: List[RoundLabels] = [{} for _ in range(context.max_transfers + 1)]
    frontier: Set[str] = set()

    for origin_id in context.origin_ids:
        best[0][origin_id] = (context.requested_departure, {"mode": "start", "k": 0, "prev_stop": None})
        frontier.add(origin_id)

    return RoutingState(best=best, frontier=frontier)


def _should_replace(existing: Optional[LabelEntry], event_time: int, predecessor: dict, round_idx: int) -> bool:
    """
    Return whether a newly found label should replace the current one.

    A label is replaced if no label exists yet, if the new event happens earlier,
    or if both times are equal but the new label comes from a better earlier round.

    Args:
        existing: Current stored label entry, or None if no label exists yet.
        event_time: Time of the newly found event.
        predecessor: Metadata describing how the new label was reached.
        round_idx: Current RAPTOR round index used as fallback for comparison.

    Returns:
        True if the new label should replace the existing one, otherwise False.
    """
    if existing is None:
        return True

    current_time, current_pred = existing
    if event_time < current_time:
        return True
    return event_time == current_time and predecessor.get("k", round_idx) < current_pred.get("k", round_idx)


def _store_label(state: RoutingState, context: QueryContext, round_idx: int, stop_id: str,
                 event_time: int, predecessor: dict, changed_stops: Set[str]) -> None:
    """
    Store a label for one stop in the given round if it improves the current one.
    It compares the new label with the existing one and stores it only if it is better. Improved stops are added
    to the changed set, so they can be processed further.

    Args:
        state: Current mutable routing state of the RAPTOR query.
        context: Query context containing the requested departure time and lookups.
        round_idx: RAPTOR round in which the label should be stored.
        stop_id: Stop for which the label is being updated.
        event_time: New arrival or event time at the stop.
        predecessor: Metadata describing how this label was reached.
        changed_stops: Set collecting stops whose labels improved in this round.

    Returns:
        None. Updates the routing state in place.
    """
    if round_idx > 0 and event_time < context.requested_departure:
        return

    existing = state.best[round_idx].get(stop_id)
    if _should_replace(existing, event_time, predecessor, round_idx):
        state.best[round_idx][stop_id] = (event_time, predecessor)
        changed_stops.add(stop_id)


def _expand_walks(state: RoutingState, context: QueryContext, round_idx: int, seed_stops: Set[str]) -> Set[str]:
    """Relax all outgoing footpaths from the given set of changed stops. Simulates footpaths."""
    changed: Set[str] = set()

    for source_stop in seed_stops:
        label = state.best[round_idx].get(source_stop)
        if label is None:
            continue

        source_time = label[0]
        for target_stop, walk_seconds, min_change_seconds in context.footpaths.get(source_stop, ()): 
            effective_walk = max(walk_seconds or 0, min_change_seconds or 0)
            _store_label(
                state,
                context,
                round_idx,
                target_stop,
                source_time + effective_walk,
                {
                    "mode": "walk",
                    "prev_stop": source_stop,
                    "k": round_idx,
                    "walk_time": effective_walk,
                },
                changed,
            )

    return changed


def _patterns_touched_by_frontier(frontier: Set[str], patterns_by_stop: Dict[str, Set[str]]) -> Set[str]:
    """Collect all patterns that serve at least one changed stop."""
    return {pattern_id for stop_id in frontier for pattern_id in patterns_by_stop.get(stop_id, ())}


def _find_trip_for_boarding(context: QueryContext, pattern_id: str, stop_index: int,
                            earliest_departure: int) -> Optional[BoardingDecision]:
    """Return the first boardable trip at one pattern stop."""
    departures, trip_ids = context.dep_cache.get((pattern_id, stop_index), ([], []))
    if not departures:
        return None

    pos = bisect_left(departures, earliest_departure)
    if pos >= len(departures):
        return None

    trip_id = trip_ids[pos]
    return BoardingDecision(
        trip_id=trip_id,
        departure_time=departures[pos],
        board_stop_id=context.stops_in_pattern[pattern_id][stop_index],
        board_index=stop_index,
    )


def _earliest_boarding_from_label(label: LabelEntry, transfer_slack_sec: int) -> int:
    """Compute the earliest permitted boarding time from a predecessor label."""
    event_time, predecessor = label
    slack = 0 if predecessor.get("mode") == "start" else transfer_slack_sec
    return event_time + slack


def _prefer_boarding_candidate(context: QueryContext, active_ride: Optional[ActiveRide],
                               candidate: Optional[BoardingDecision], stop_index: int) -> Optional[ActiveRide]:
    """Choose whether a newly found boarding opportunity replaces the active ride."""
    if candidate is None:
        return active_ride
    if active_ride is None:
        return ActiveRide(candidate.trip_id, candidate.board_stop_id, candidate.departure_time, candidate.board_index)

    current_departure_here = context.trip_times[active_ride.trip_id][2][stop_index]
    if current_departure_here is None or candidate.departure_time < current_departure_here:
        return ActiveRide(candidate.trip_id, candidate.board_stop_id, candidate.departure_time, candidate.board_index)

    return active_ride


def _ride_arrival_time(context: QueryContext, trip_id: str, stop_index: int) -> Optional[int]:
    """Read the arrival time of one trip at one stop position."""
    return context.trip_times[trip_id][1][stop_index]


def _can_record_arrival(state: RoutingState, context: QueryContext, round_idx: int,
                        ride: ActiveRide, current_stop: str, stop_index: int, arrival_time: Optional[int]) -> bool:
    """Apply all constraints before writing a ride arrival to the round state."""
    if ride.board_index is not None and stop_index <= ride.board_index:
        return False
    if arrival_time is None:
        return False
    if arrival_time < ride.board_time:
        return False
    if (context.avoid_passing_origin_after_boarding and current_stop in context.origin_ids and
            ride.board_stop_id not in context.origin_ids):
        return False

    existing = state.best[round_idx].get(current_stop)
    if existing is not None and arrival_time >= existing[0]:
        return False

    return True


def _scan_pattern_round(state: RoutingState, context: QueryContext, round_idx: int, pattern_id: str,
                        changed_stops: Set[str]) -> None:
    """
    Scan one pattern in the current RAPTOR round and record reachable arrivals.

    The function goes through the stops of the pattern in order. If a stop was
    reachable in the previous round, it tries to board a valid trip there. Once a
    trip is active, it carries that ride forward and stores arrival times at later
    stops in the current round.

    Args:
        state: Current mutable routing state with the best labels per round.
        context: Query data and lookup structures needed during the scan.
        round_idx: Current RAPTOR round that is being filled.
        pattern_id: Pattern whose ordered stop sequence is scanned.
        changed_stops: Set collecting stops that improved in this round.

    Returns:
        None. Updates the routing state in place.
    """
    stop_sequence = context.stops_in_pattern[pattern_id]
    previous_round = state.best[round_idx - 1]

    ride: Optional[ActiveRide] = None
    for stop_index, stop_id in enumerate(stop_sequence):
        previous_label = previous_round.get(stop_id)
        if previous_label is not None:
            candidate = _find_trip_for_boarding(
                context,
                pattern_id,
                stop_index,
                _earliest_boarding_from_label(previous_label, context.transfer_slack_sec),
            )
            ride = _prefer_boarding_candidate(context, ride, candidate, stop_index)

        if ride is None:
            continue

        arrival_time = _ride_arrival_time(context, ride.trip_id, stop_index)
        if not _can_record_arrival(state, context, round_idx, ride, stop_id, stop_index, arrival_time):
            continue

        _store_label(
            state,
            context,
            round_idx,
            stop_id,
            int(arrival_time),
            {
                "mode": "ride",
                "prev_stop": ride.board_stop_id,
                "k": round_idx - 1,
                "route_id": context.pattern_route[pattern_id],
                "trip_id": ride.trip_id,
                "board_stop": ride.board_stop_id,
                "alight_stop": stop_id,
                "board_time": ride.board_time,
                "alight_time": int(arrival_time),
            },
            changed_stops,
        )


def route_by_stop_ids(
    indices: Dict[str, object],
    origin_ids: Set[str],
    destination_ids: Set[str],
    departure_time: str | int,
    *,
    max_transfers: int = 6,
    transfer_slack_sec: int = 180,
    avoid_passing_origin_after_boarding: bool = True
) -> tuple[List[Dict[str, Tuple[int, dict]]], Set[str]]:
    """
    Run a RAPTOR journey computation using stop ids. Raptor Core function.

    Args:
        indices: RAPTOR index dictionary.
        origin_ids: Origin stop ids.
        destination_ids: Destination stop ids.
        departure_time: Departure time as GTFS string or seconds since midnight.
        max_transfers: Maximum number of transfer rounds.
        transfer_slack_sec: Minimum transfer slack between ride legs. Transfer Time.
        avoid_passing_origin_after_boarding: Whether rides may pass an origin stop after boarding somewhere else.

    Returns:
        Per-round best-label structure and the destination stop id set.
    """
    context = _build_query_context(
        indices,
        origin_ids,
        destination_ids,
        departure_time,
        max_transfers=max_transfers,
        transfer_slack_sec=transfer_slack_sec,
        avoid_passing_origin_after_boarding=avoid_passing_origin_after_boarding,
    )
    state = _initialize_routing_state(context)

    state.frontier |= _expand_walks(state, context, 0, state.frontier)

    for round_idx in range(1, context.max_transfers + 1):
        changed_stops: Set[str] = set()
        for pattern_id in _patterns_touched_by_frontier(state.frontier, context.patterns_by_stop):
            _scan_pattern_round(state, context, round_idx, pattern_id, changed_stops)

        if changed_stops:
            changed_stops |= _expand_walks(state, context, round_idx, changed_stops)
        if not changed_stops:
            break

        state.frontier = changed_stops

    return state.best, context.destination_ids


def _rebuild_journey(best: List[RoundLabels], target_stop: str, round_idx: int) -> JourneyDraft:
    """
    Reconstruct a complete journey from the stored RAPTOR labels.
    The function starts at the target stop and follows the predecessor
    information backward until it reaches the start. While doing so, it
    rebuilds all ride and walk legs of the journey in the correct order.

    Args:
        best: Best stop labels stored for all RAPTOR rounds.
        target_stop: Stop where the journey ends.
        round_idx: Round in which the target stop was reached.

    Returns:
        A JourneyDraft containing the reconstructed legs, final arrival time,
        first boarding time and number of transfers.
    """
    legs: List[dict[str, object]] = []
    current_stop = target_stop
    current_round = round_idx

    while True:
        arrival_time, predecessor = best[current_round][current_stop]
        mode = predecessor["mode"]
        if mode == "start":
            break

        if mode == "walk":
            previous_stop = predecessor["prev_stop"]
            depart_time = best[current_round][previous_stop][0]
            legs.append(
                {
                    "mode": "walk",
                    "route_id": None,
                    "trip_id": None,
                    "board_stop_id": previous_stop,
                    "alight_stop_id": current_stop,
                    "board_time": depart_time,
                    "alight_time": arrival_time,
                }
            )
            current_stop = previous_stop
            current_round = predecessor.get("k", current_round)
            continue

        legs.append(
            {
                "mode": "ride",
                "route_id": predecessor["route_id"],
                "trip_id": predecessor["trip_id"],
                "board_stop_id": predecessor["board_stop"],
                "alight_stop_id": predecessor["alight_stop"],
                "board_time": predecessor["board_time"],
                "alight_time": predecessor["alight_time"],
            }
        )
        current_stop = predecessor["board_stop"]
        current_round = predecessor["k"]

    legs.reverse()
    ride_legs = [leg for leg in legs if leg["mode"] == "ride"]
    final_arrival = best[round_idx][target_stop][0]
    first_board_time = ride_legs[0]["board_time"] if ride_legs else (legs[0]["board_time"] if legs else final_arrival)

    return JourneyDraft(
        destination_stop_id=target_stop,
        round_index=round_idx,
        arrival_time=final_arrival,
        first_board_time=first_board_time,
        transfers=max(len(ride_legs) - 1, 0),
        legs=legs,
    )


def _round_targets(best: List[RoundLabels], round_idx: int, destination_stop_ids: Set[str],
                   connections_for_all: bool) -> Iterable[str]:
    """Resolve the target stop ids that should be reconstructed for one round."""
    if connections_for_all:
        return best[round_idx].keys()
    return destination_stop_ids


def _collect_reconstructed_journeys(best: List[RoundLabels], destination_stop_ids: Set[str], connections_for_all: bool
                                    ) -> List[JourneyDraft]:
    """Reconstruct all requested journeys from the RAPTOR label store."""
    journeys: List[JourneyDraft] = []
    for round_idx in range(len(best)):
        for stop_id in _round_targets(best, round_idx, destination_stop_ids, connections_for_all):
            if stop_id in best[round_idx]:
                journeys.append(_rebuild_journey(best, stop_id, round_idx))
    return journeys


def _within_departure_window(journey: JourneyDraft, origin_dep_time: int, wait_window_sec: int) -> bool:
    """Check whether a journey starts within the accepted waiting window."""
    lower_bound = int(origin_dep_time)
    upper_bound = lower_bound + wait_window_sec
    return journey.first_board_time is not None and lower_bound <= int(journey.first_board_time) < upper_bound


def _prune_high_transfer_variants(journeys: List[JourneyDraft]) -> List[JourneyDraft]:
    """Discard destination variants that exceed the best transfer count by more than three. We could also
    set it to 2 or 1 or 0 here, but then faster trips could possibly get discarded."""
    minimum_transfers: Dict[str, int] = {}
    for journey in journeys:
        destination = str(journey.destination_stop_id)
        minimum_transfers[destination] = min(journey.transfers, minimum_transfers.get(destination, journey.transfers))

    return [
        journey
        for journey in journeys
        if journey.transfers <= minimum_transfers.get(str(journey.destination_stop_id), journey.transfers) + 3
    ]


def _journey_sort_key(journey: JourneyDraft, origin_dep_time: Optional[int],
                      wait_window_sec: int) -> Tuple[int, int, int]:
    """
    Return the sorting key used to rank reconstructed journeys.
    The key prefers journeys with the shortest effective travel time. If an
    origin departure time is given, the start of the journey is capped by the
    allowed waiting window so very late boardings are not unfairly favored.
    Ties are then broken by fewer transfers and earlier arrival time.

    Args:
        journey: Reconstructed journey to rank.
        origin_dep_time: Requested departure time at the origin, or None.
        wait_window_sec: Maximum waiting time at the origin used for ranking.

    Returns:
        A tuple used for sorting journeys by travel time, transfers, and arrival.
    """
    if origin_dep_time is not None:
        capped_start = origin_dep_time + wait_window_sec
        effective_start = min(int(journey.first_board_time), capped_start)
        return (journey.arrival_time - effective_start, journey.transfers, journey.arrival_time)
    return (journey.arrival_time - journey.first_board_time, journey.transfers, journey.arrival_time)


def reconstruct_connection(best: list[dict[str, tuple[int, dict]]], destination_stop_ids: set[str], *,
                           connections_for_all: bool = False, origin_dep_time: int | None = None,
                           wait_window_sec: int = 120 * 60) -> list[dict[str, object]] | bool:
    """
    Reconstruct journey legs from the RAPTOR predecessor structure.

    Args:
        best: Per-round best-arrival dictionaries.
        destination_stop_ids: Destination stop ids to reconstruct when not returning all reachable stops.
        connections_for_all: Whether to reconstruct journeys to all reachable stops instead of only the destination.
        origin_dep_time: Earliest requested departure time.
        wait_window_sec: Allowed waiting time at the origin.

    Returns:
        List of reconstructed journeys, or False if no result exists.
    """
    journeys = _collect_reconstructed_journeys(best, destination_stop_ids, connections_for_all)
    if not journeys:
        return False

    if origin_dep_time is not None:
        journeys = [journey for journey in journeys if _within_departure_window(journey, origin_dep_time, 3600)]
        if not journeys:
            return False

    journeys = _prune_high_transfer_variants(journeys)
    journeys.sort(key=lambda journey: _journey_sort_key(journey, origin_dep_time, wait_window_sec))

    return [
        {
            "destination_stop_id": journey.destination_stop_id,
            "k": journey.round_index,
            "arrival_time": journey.arrival_time,
            "first_board_time": journey.first_board_time,
            "total_travel_time": journey.arrival_time - journey.first_board_time,
            "transfers": journey.transfers,
            "legs": journey.legs,
        }
        for journey in journeys
    ]


def best_connection_with_names(*, best: list[dict[str, tuple[int, dict]]], destination_stop_ids: set[str],
                               feed: dict[str, pd.DataFrame], origin_dep_time: int | None = None,
                               wait_window_sec: int = 120 * 60) -> dict[str, Any] | None:
    """
    Return the single best reconstructed connection with resolved stop in readable format. Only
    used for tests.

    Args:
        best: RAPTOR predecessor structure.
        destination_stop_ids: Target stop ids for reconstruction.
        feed: GTFS feed dictionary containing at least stops.txt, trips.txt, routes.txt.
        origin_dep_time: Earliest requested departure time in seconds.
        wait_window_sec: Allowed waiting time at the origin.

    Returns:
        One dict describing the best connection in readable form, or None if
        no connection exists.
    """
    journeys = reconstruct_connection(
        best,
        destination_stop_ids,
        connections_for_all=False,
        origin_dep_time=origin_dep_time,
        wait_window_sec=wait_window_sec,
    )

    if not journeys:
        return None

    # reconstruct_connection already sorts journeys, so the first one is the best
    best_journey = journeys[0]

    stops_df = feed["stops.txt"].copy()
    trips_df = feed["trips.txt"].copy()
    routes_df = feed["routes.txt"].copy()

    stops_df["stop_id"] = stops_df["stop_id"].astype(str)
    trips_df["trip_id"] = trips_df["trip_id"].astype(str)
    routes_df["route_id"] = routes_df["route_id"].astype(str)

    stop_name_by_id = dict(zip(stops_df["stop_id"], stops_df.get("stop_name", stops_df["stop_id"])))

    trip_cols = ["trip_id"]
    for col in ("route_id", "trip_headsign", "trip_short_name"):
        if col in trips_df.columns:
            trip_cols.append(col)
    trips_lookup = trips_df[trip_cols].drop_duplicates("trip_id").set_index("trip_id").to_dict("index")

    route_cols = ["route_id"]
    for col in ("route_short_name", "route_long_name", "route_type"):
        if col in routes_df.columns:
            route_cols.append(col)
    routes_lookup = routes_df[route_cols].drop_duplicates("route_id").set_index("route_id").to_dict("index")

    readable_legs: list[dict[str, Any]] = []

    for leg in best_journey["legs"]:
        board_stop_id = str(leg["board_stop_id"])
        alight_stop_id = str(leg["alight_stop_id"])

        board_stop_name = stop_name_by_id.get(board_stop_id, board_stop_id)
        alight_stop_name = stop_name_by_id.get(alight_stop_id, alight_stop_id)

        if leg["mode"] == "walk":
            readable_legs.append({
                "mode": "walk",
                "from_stop_id": board_stop_id,
                "from_stop_name": board_stop_name,
                "to_stop_id": alight_stop_id,
                "to_stop_name": alight_stop_name,
                "departure_time": gtfs_io_utilities.seconds_to_gtfs_time(leg["board_time"]),
                "arrival_time": gtfs_io_utilities.seconds_to_gtfs_time(leg["alight_time"]),
                "duration_sec": int(leg["alight_time"] - leg["board_time"]),
                "instruction": f"Walk from {board_stop_name} to {alight_stop_name}",
            })
            continue

        trip_id = str(leg["trip_id"]) if leg.get("trip_id") is not None else None
        route_id = str(leg["route_id"]) if leg.get("route_id") is not None else None

        trip_info = trips_lookup.get(trip_id, {}) if trip_id is not None else {}
        if route_id is None and "route_id" in trip_info:
            route_id = str(trip_info["route_id"])

        route_info = routes_lookup.get(route_id, {}) if route_id is not None else {}

        route_short_name = route_info.get("route_short_name")
        route_long_name = route_info.get("route_long_name")
        trip_headsign = trip_info.get("trip_headsign")
        trip_short_name = trip_info.get("trip_short_name")

        line_label = (
            route_short_name
            or trip_short_name
            or route_long_name
            or route_id
            or "unknown line"
        )

        readable_legs.append({
            "mode": "ride",
            "route_id": route_id,
            "trip_id": trip_id,
            "line": line_label,
            "route_short_name": route_short_name,
            "route_long_name": route_long_name,
            "trip_headsign": trip_headsign,
            "trip_short_name": trip_short_name,
            "from_stop_id": board_stop_id,
            "from_stop_name": board_stop_name,
            "to_stop_id": alight_stop_id,
            "to_stop_name": alight_stop_name,
            "departure_time": gtfs_io_utilities.seconds_to_gtfs_time(leg["board_time"]),
            "arrival_time": gtfs_io_utilities.seconds_to_gtfs_time(leg["alight_time"]),
            "duration_sec": int(leg["alight_time"] - leg["board_time"]),
            "instruction": (
                f"Take {line_label}"
                + (f" towards {trip_headsign}" if trip_headsign else "")
                + f" from {board_stop_name} to {alight_stop_name}"
            ),
        })

    return {
        "destination_stop_id": str(best_journey["destination_stop_id"]),
        "destination_stop_name": stop_name_by_id.get(str(best_journey["destination_stop_id"]),
                                                     str(best_journey["destination_stop_id"])),
        "arrival_time": gtfs_io_utilities.seconds_to_gtfs_time(best_journey["arrival_time"]),
        "first_board_time": gtfs_io_utilities.seconds_to_gtfs_time(best_journey["first_board_time"]),
        "total_travel_time_sec": int(best_journey["total_travel_time"]),
        "transfers": int(best_journey["transfers"]),
        "legs": readable_legs,
    }