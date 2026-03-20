"""
Zone-to-zone travel time pipeline (GTFS + VG1000 + RAPTOR).

Computes a zone OD table for a single service date and a single departure time.
Each zone is represented by one stop (highest departures on that day).

Pipeline:
  1) Load GTFS and VG1000 zones
  2) Filter GTFS to one service day
  3) Ensure stop_times has *_time_seconds columns (RAPTOR precondition)
  4) Assign stops to zones (point-in-polygon)
  5) Select one representative stop per zone (highest departures that day; can be changed)
  6) For each origin zone rep: RAPTOR one-to-all + reconstruct_legs(legs_for_all=True)
  7) Keep the minimal total_travel_time per destination zone
  8) Export CSV
"""

from datetime import date
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.ipc as ipc

from gtfs_toolbox import gtfs_subset_utilities, gtfs_io_utilities
from gtfs_toolbox.geo_utilities import load_zones
from gtfs_toolbox.zoning import assign_stops_to_zones, top_n_per_zone
from raptor_core import prepare_departure_lookup, build_raptor_indices
from raptor_core.raptor import route_by_stop_ids, reconstruct_connection


def compute_zone_od_one_time(
    gtfs_path: Path,
    shapes_path: Path,
    *,
    vg_layer: str,
    zone_id_col: str,
    zone_name_col: str,
    on: date,
    dep_time: str | int,
    out_file: Path,
    max_transfers: int = 5,
    write_csv_debug: bool = False,
) -> pd.DataFrame:
    """
    Compute minimal zone-to-zone travel times for a single date and departure time.

    The result is exported as an Apache Arrow IPC file (.arrow), a compact typed
    columnar format suited for fast downstream analytics and web dashboards.

    Args:
        gtfs_path: Path to GTFS directory.
        shapes_path: Path to VG1000 directory.
        vg_layer: Key of the VG1000 layer returned by load_zones (e.g. 'VG1000_KRS').
        zone_id_col: Column in VG1000 used as zone id (e.g. 'ARS', 'AGS').
        zone_name_col: Column in VG1000 used as human-readable name (e.g. 'GEN').
        on: Service date (Python date).
        dep_time: Departure time as 'HH:MM:SS' or seconds since midnight.
        out_file: Output path ending with '.arrow'.
        max_transfers: RAPTOR transfer limit.
        write_csv_debug: If True, also writes a CSV next to the Arrow file.

    Returns:
        Long-format OD DataFrame (also written to out_file).
    """
    if out_file.suffix.lower() != ".arrow":
        raise ValueError(f"out_file must end with '.arrow', got: {out_file}")

    # Load base data
    feed = gtfs_io_utilities.load_feed(str(gtfs_path), parse_stop_times=True)
    zones = load_zones(shapes_path, merge=False)[vg_layer]

    # Filter to one service day (avoid double filtering later)
    day_feed = gtfs_subset_utilities.subset_feed_by_date_window(
        feed, start=on, end=on, prune_stop_times=True, prune_stops=False
    )

    # RAPTOR expects numeric time columns in stop_times.txt
    day_feed["stop_times.txt"] = gtfs_io_utilities.append_seconds_columns(day_feed["stop_times.txt"].copy())

    # Stop -> zone mapping
    stop_zone = assign_stops_to_zones(day_feed["stops.txt"], zones, zone_id_col=zone_id_col)

    # Representative stop per zone (highest departures on that day)
    dep = gtfs_io_utilities.departures_per_stop_period(day_feed)
    reps = top_n_per_zone(dep, stop_zone, score_col="departures", n=1)

    # important for some zone set specific stations e.g. for berlin: Berlin Hbf, münchen: München Hbf
    reps.loc[reps["zone_id"].astype(str) == "11000", "stop_id"] = "252903"
    #reps.loc[reps["zone_id"].astype(str) == "09162", "stop_id"] = "457881"
    reps.loc[reps["zone_id"].astype(str) == "09162", "stop_id"] = "236164"

    rep_stop_ids = set(reps["stop_id"].astype(str))
    zone_by_stop = dict(zip(reps["stop_id"].astype(str), reps["zone_id"].astype(str)))

    # Names for readable output
    stops_names = day_feed["stops.txt"][["stop_id", "stop_name"]].copy()
    stops_names["stop_id"] = stops_names["stop_id"].astype(str)

    # VG1000 may contain multiple features per zone id (multi-part geometries)
    zones_names = (
        zones[[zone_id_col, zone_name_col]]
        .drop_duplicates(subset=[zone_id_col])
        .rename(columns={zone_id_col: "zone_id", zone_name_col: "zone_name"})
    )
    zones_names["zone_id"] = zones_names["zone_id"].astype(str)

    # Build RAPTOR indices once
    on_yyyymmdd = int(on.strftime("%Y%m%d"))
    indices = build_raptor_indices(day_feed, on_yyyymmdd)
    prepare_departure_lookup(indices)

    dep_sec = gtfs_io_utilities.gtfs_time_to_seconds(dep_time) if isinstance(dep_time, str) else int(dep_time)
    start_hour = int(dep_sec // 3600)

    # Compute OD: one RAPTOR run per origin representative
    rows: list[dict[str, object]] = []
    n_origins = len(reps)

    for i, o_stop in enumerate(reps["stop_id"].astype(str), start=1):
        # Progress feedback
        if i == 1 or i == n_origins or i % max(1, n_origins // 20) == 0:
            pct = int(round(100 * i / n_origins))
            print(f"[zone OD] {pct}% ({i}/{n_origins}) origin zones processed")

        o_zone = zone_by_stop[o_stop]

        connectors, _ = route_by_stop_ids(
            indices=indices,
            origin_ids={o_stop},
            destination_ids=rep_stop_ids,
            departure_time=dep_sec,
            max_transfers=max_transfers,
        )

        journeys = reconstruct_connection(connectors, rep_stop_ids, connections_for_all=True, origin_dep_time=dep_sec)
        if journeys is False:
            continue

        jdf = pd.DataFrame(journeys)
        if jdf.empty:
            continue

        # Keep only representative destinations, pick minimal total_travel_time per dest stop
        jdf = jdf[jdf["destination_stop_id"].isin(rep_stop_ids)].copy()
        if jdf.empty:
            continue

        jdf = jdf.sort_values(["total_travel_time", "transfers", "arrival_time"], kind="stable")
        jdf = jdf.drop_duplicates(subset=["destination_stop_id"], keep="first")

        for _, r in jdf.iterrows():
            d_stop = str(r["destination_stop_id"])
            rows.append(
                {
                    "origin_zone_id": o_zone,
                    "origin_stop_id": o_stop,
                    "dest_zone_id": zone_by_stop[d_stop],
                    "dest_stop_id": d_stop,
                    "start_hour": start_hour,
                    "total_travel_time_sec": int(r["total_travel_time"]),
                    "transfers": int(r["transfers"]),
                }
            )

    od = pd.DataFrame(rows)

    # Add clear names (stops + zones)
    od = (
        od.merge(
            stops_names.rename(columns={"stop_id": "origin_stop_id", "stop_name": "origin_stop_name"}),
            on="origin_stop_id",
            how="left",
        )
        .merge(
            stops_names.rename(columns={"stop_id": "dest_stop_id", "stop_name": "dest_stop_name"}),
            on="dest_stop_id",
            how="left",
        )
        .merge(
            zones_names.rename(columns={"zone_id": "origin_zone_id", "zone_name": "origin_zone_name"}),
            on="origin_zone_id",
            how="left",
        )
        .merge(
            zones_names.rename(columns={"zone_id": "dest_zone_id", "zone_name": "dest_zone_name"}),
            on="dest_zone_id",
            how="left",
        )
        .loc[
            :,
            [
                "origin_zone_id",
                "origin_zone_name",
                "origin_stop_id",
                "origin_stop_name",
                "dest_zone_id",
                "dest_zone_name",
                "dest_stop_id",
                "dest_stop_name",
                "start_hour",
                "total_travel_time_sec",
                "transfers",
            ],
        ]
    )

    # Tighten dtypes (smaller Arrow files, faster downstream reads)
    if not od.empty:
        od["start_hour"] = od["start_hour"].astype("int8")
        od["total_travel_time_sec"] = od["total_travel_time_sec"].astype("int32")
        od["transfers"] = od["transfers"].astype("int8")

    # Export Arrow IPC (.arrow)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(od, preserve_index=False)
    with ipc.new_file(str(out_file), table.schema) as writer:
        writer.write(table)

    # Optional CSV for quick inspection/debugging
    if write_csv_debug:
        od.to_csv(out_file.with_suffix(".csv"), index=False)

    return od
