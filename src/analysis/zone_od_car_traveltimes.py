"""
Zone-to-zone car travel time pipeline.

Computes a zone OD table for car travel times using representative stop(s) per zone. Should be the same, that is used
for train travel times.

Pipeline:
  1) Load GTFS and VG1000 zones
  2) Filter GTFS to one service day
  3) Assign GTFS stops to zones
  4) Select representative stops per zone
  5) Use representative stop coordinates as car OD points
  6) Request openrouteservice driving-car matrices in blocks
  7) Export long-format OD table as .arrow
"""

from datetime import date
import os
from pathlib import Path
import time

import pandas as pd
import pyarrow as pa
import pyarrow.ipc as ipc
import requests

from gtfs_toolbox import gtfs_subset_utilities, gtfs_io_utilities
from gtfs_toolbox.geo_utilities import load_zones
from gtfs_toolbox.zoning import assign_stops_to_zones, top_n_per_zone


ORS_MATRIX_URL = "https://api.openrouteservice.org/v2/matrix/driving-car"


def chunk_indices(n: int, chunk_size: int) -> list[tuple[int, int]]:
    """
    Split a range [0, n) into contiguous half-open chunks.

    Args:
        n: Total number of elements.
        chunk_size: Maximum chunk length.

    Returns:
        List of (start, end) index tuples.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    return [(i, min(i + chunk_size, n)) for i in range(0, n, chunk_size)]


def request_ors_matrix(coordinates: list[list[float]], *, sources: list[int], destinations: list[int],
                       api_key: str, timeout: int = 120) -> dict:
    """
    Request one car matrix block from openrouteservice.

    Args:
        coordinates: Full coordinate list in [lon, lat] order.
        sources: Source indices within coordinates.
        destinations: Destination indices within coordinates.
        api_key: ORS API key.
        timeout: HTTP timeout in seconds.

    Returns:
        Parsed JSON response.

    Raises:
        RuntimeError: If the request fails.
    """
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
    }

    body = {
        "locations": coordinates,
        "sources": sources,
        "destinations": destinations,
        "metrics": ["duration", "distance"],
    }

    try:
        response = requests.post(
            ORS_MATRIX_URL,
            json=body,
            headers=headers,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"ORS matrix request failed: {exc}") from exc

    if response.status_code != 200:
        raise RuntimeError(
            f"ORS matrix request failed with status {response.status_code}: {response.text}"
        )

    return response.json()


def select_zone_representative_stops(
    gtfs_path: Path,
    shapes_path: Path,
    *,
    vg_layer: str,
    zone_id_col: str,
    zone_name_col: str,
    on: date,
) -> pd.DataFrame:
    """
    Select one representative GTFS stop per zone using the existing project logic.

    The representative stop is the stop with the highest number of departures
    on the selected service day.

    Args:
        gtfs_path: Path to GTFS directory.
        shapes_path: Path to VG1000 directory.
        vg_layer: Key of the VG1000 layer returned by load_zones.
        zone_id_col: Column in VG1000 used as zone id.
        zone_name_col: Column in VG1000 used as human-readable zone name.
        on: Service date.

    Returns:
        DataFrame with one row per represented zone and columns:
            zone_id, zone_name, stop_id, stop_name, stop_lon, stop_lat
    """
    feed = gtfs_io_utilities.load_feed(str(gtfs_path), parse_stop_times=True)
    zones = load_zones(shapes_path, merge=False)[vg_layer]

    day_feed = gtfs_subset_utilities.subset_feed_by_date_window(
        feed, start=on, end=on, prune_stop_times=True, prune_stops=False
    )

    stops = day_feed["stops.txt"].copy()
    stops["stop_id"] = stops["stop_id"].astype(str)
    stops = gtfs_io_utilities.normalize_stop_coordinates(stops)

    stop_zone = assign_stops_to_zones(stops, zones, zone_id_col=zone_id_col)
    dep = gtfs_io_utilities.departures_per_stop_period(day_feed)
    reps = top_n_per_zone(dep, stop_zone, score_col="departures", n=1)

    zones_names = (
        zones[[zone_id_col, zone_name_col]]
        .drop_duplicates(subset=[zone_id_col])
        .rename(columns={zone_id_col: "zone_id", zone_name_col: "zone_name"})
    )
    zones_names["zone_id"] = zones_names["zone_id"].astype(str)

    stop_cols = ["stop_id", "stop_name", "stop_lon", "stop_lat"]
    out = (
        reps.merge(stops[stop_cols], on="stop_id", how="left")
        .merge(zones_names, on="zone_id", how="left")
        .loc[:, ["zone_id", "zone_name", "stop_id", "stop_name", "stop_lon", "stop_lat", "departures"]]
        .sort_values("zone_id", kind="stable")
        .reset_index(drop=True)
    )

    return out


def compute_zone_car_od_one_time(
    gtfs_path: Path,
    shapes_path: Path,
    *,
    vg_layer: str,
    zone_id_col: str,
    zone_name_col: str,
    on: date,
    out_file: Path,
    api_key: str | None = None,
    block_size: int = 50,
    pause_sec: float = 0.2,
    retries: int = 3,
    timeout: int = 120,
    write_csv_debug: bool = False,
) -> pd.DataFrame:
    """
    Compute minimal zone-to-zone car travel times for one service day.

    Representative points are the same GTFS stops used in the PT OD pipeline,
    ensuring direct comparability between public transport and car travel times.

    Args:
        gtfs_path: Path to GTFS directory.
        shapes_path: Path to VG1000 directory.
        vg_layer: Key of the VG1000 layer returned by load_zones.
        zone_id_col: Column in VG1000 used as zone id.
        zone_name_col: Column in VG1000 used as human-readable zone name.
        on: Service date used to determine representative stops.
        out_file: Output path ending with '.arrow'.
        api_key: ORS API key. If None, reads environment variable ORS_API_KEY.
        block_size: Number of origins and destinations per matrix block.
        pause_sec: Sleep between API calls.
        retries: Number of retries per failed block.
        timeout: HTTP timeout in seconds.
        write_csv_debug: If True, also writes a CSV next to the Arrow file.

    Returns:
        Long-format OD DataFrame (also written to out_file).
    """
    if out_file.suffix.lower() != ".arrow":
        raise ValueError(f"out_file must end with '.arrow', got: {out_file}")

    api_key = api_key or os.getenv("ORS_API_KEY")
    if not api_key:
        raise ValueError("Missing ORS API key. Pass api_key=... or set ORS_API_KEY.")

    reps = select_zone_representative_stops(
        gtfs_path=gtfs_path,
        shapes_path=shapes_path,
        vg_layer=vg_layer,
        zone_id_col=zone_id_col,
        zone_name_col=zone_name_col,
        on=on,
    )

    if reps.empty:
        raise ValueError("No representative stops could be selected for the requested date.")

    coordinates = reps[["stop_lon", "stop_lat"]].astype(float).values.tolist()
    n = len(reps)

    origin_chunks = chunk_indices(n, block_size)
    dest_chunks = chunk_indices(n, block_size)

    rows: list[dict[str, object]] = []
    total_blocks = len(origin_chunks) * len(dest_chunks)
    block_no = 0

    for o0, o1 in origin_chunks:
        for d0, d1 in dest_chunks:
            block_no += 1
            print(
                f"[car OD] Block {block_no}/{total_blocks} "
                f"(origins {o0}:{o1}, destinations {d0}:{d1})"
            )

            sources = list(range(o0, o1))
            destinations = list(range(d0, d1))

            result: dict | None = None

            for attempt in range(1, retries + 1):
                try:
                    result = request_ors_matrix(
                        coordinates,
                        sources=sources,
                        destinations=destinations,
                        api_key=api_key,
                        timeout=timeout,
                    )
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt < retries:
                        wait = attempt * 2
                        print(f"[car OD] Retry {attempt}/{retries - 1} after error: {exc}")
                        time.sleep(wait)
                    else:
                        raise RuntimeError(
                            f"Matrix block failed for origins {o0}:{o1}, destinations {d0}:{d1}"
                        ) from last_error

            durations = result.get("durations", [])
            distances = result.get("distances", [])

            for i_src, src_idx in enumerate(sources):
                src = reps.iloc[src_idx]

                for i_dst, dst_idx in enumerate(destinations):
                    dst = reps.iloc[dst_idx]

                    duration_val = None
                    distance_val = None

                    if i_src < len(durations) and i_dst < len(durations[i_src]):
                        duration_val = durations[i_src][i_dst]

                    if i_src < len(distances) and i_dst < len(distances[i_src]):
                        distance_val = distances[i_src][i_dst]

                    rows.append(
                        {
                            "origin_zone_id": str(src["zone_id"]),
                            "origin_zone_name": src["zone_name"],
                            "origin_stop_id": str(src["stop_id"]),
                            "origin_stop_name": src["stop_name"],
                            "dest_zone_id": str(dst["zone_id"]),
                            "dest_zone_name": dst["zone_name"],
                            "dest_stop_id": str(dst["stop_id"]),
                            "dest_stop_name": dst["stop_name"],
                            "car_travel_time_sec": None if duration_val is None else int(round(duration_val)),
                            "car_distance_m": None if distance_val is None else int(round(distance_val)),
                        }
                    )

            if pause_sec > 0:
                time.sleep(pause_sec)

    od = pd.DataFrame(rows)

    if not od.empty:
        od["car_travel_time_sec"] = od["car_travel_time_sec"].astype("Int32")
        od["car_distance_m"] = od["car_distance_m"].astype("Int32")

    out_file.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(od, preserve_index=False)
    with ipc.new_file(str(out_file), table.schema) as writer:
        writer.write(table)

    if write_csv_debug:
        od.to_csv(out_file.with_suffix(".csv"), index=False)

    return od
