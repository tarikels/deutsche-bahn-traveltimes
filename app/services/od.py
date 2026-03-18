"""
OD (origin-destination) data access for the map UI.

This module loads precomputed zone-to-zone data from Arrow files stored
under: data/od/<period>/day_type=<day_type>/hour=<HH>.arrow

The API returns a compact mapping:
  { dest_zone_id: travel_time_seconds, ... }
"""

# Standard library
from functools import lru_cache
from pathlib import Path
import re

# Third-party
import pandas as pd
import pyarrow.feather as feather

# Local
from app.config import OD_DIR, CAR_OD_DIR


def _od_file(period: str, day_type: str, hour: int) -> Path:
    """
    Build the Arrow file path for a given selection.

    Supports both folder conventions:
      - period=<period> vs <period>
      - day_type=<day_type> vs day_typ=<day_type>
    """
    candidates = [
        OD_DIR / period / f"day_type={day_type}" / f"hour={hour:02d}.arrow",
        OD_DIR / period / f"day_typ={day_type}" / f"hour={hour:02d}.arrow",
        OD_DIR / f"period={period}" / f"day_type={day_type}" / f"hour={hour:02d}.arrow",
        OD_DIR / f"period={period}" / f"day_typ={day_type}" / f"hour={hour:02d}.arrow",
    ]

    for p in candidates:
        if p.exists():
            return p

    # Fall back to the most likely default for error messages/logging.
    return candidates[0]


def available_periods() -> list[str]:
    """
    Return sorted list of periods (e.g. 2026W09) that exist under OD_DIR.
    Supports both conventions:
      - OD_DIR/<period>/...
      - OD_DIR/period=<period>/...
    """
    periods: set[str] = set()

    _PERIOD_RE = re.compile(r"^\d{4}W\d{2}$")

    if not OD_DIR.exists():
        return []

    for p in OD_DIR.iterdir():
        if not p.is_dir():
            continue

        name = p.name

        # convention: OD_DIR/2026W09
        if _PERIOD_RE.match(name):
            periods.add(name)
            continue

        # convention: OD_DIR/period=2026W09
        if name.startswith("period="):
            cand = name.split("=", 1)[1]
            if _PERIOD_RE.match(cand):
                periods.add(cand)

    return sorted(periods)


def _load_car_hour_df(hour: int) -> pd.DataFrame:
    """
    Load the precomputed car OD table and apply an hour-based congestion factor.

    The current car OD export is stored directly in the car_od directory
    as a single Arrow file.

    Hour-based factors:
        - Peak hours (07-09, 15-18): 1.2
        - Night hours (22-05): 1.0
        - All other hours: 1.1

    Args:
        hour: Requested hour of day (0..23).

    Returns:
        DataFrame with adjusted car OD data, or an empty DataFrame if the file
        does not exist.
    """
    path = CAR_OD_DIR / "car_od.arrow"
    if not path.exists():
        return pd.DataFrame()

    df = pd.read_feather(path)

    if "car_travel_time_sec" not in df.columns:
        return df

    if 7 <= hour <= 9 or 15 <= hour <= 18:
        factor = 1.2
    elif hour >= 22 or hour <= 5:
        factor = 1.0
    else:
        factor = 1.1

    df["car_travel_time_sec"] = (
        pd.to_numeric(df["car_travel_time_sec"], errors="coerce") * factor
    ).round()

    return df


@lru_cache(maxsize=48)
def _load_hour_df(period: str, day_type: str, hour: int) -> pd.DataFrame:
    """
    Load one Arrow file into a DataFrame and normalize column dtypes.

    The result is cached (LRU) to avoid repeated disk I/O while interacting with
    the UI controls.

    Args:
        period: Calendar week folder name, e.g. "2026W09".
        day_type: Day type folder name, e.g. "weekday".
        hour: Departure hour (0..23).

    Returns:
        DataFrame containing OD rows. Empty DataFrame if file is missing.
    """
    path = _od_file(period, day_type, hour)
    if not path.exists():
        return pd.DataFrame()

    table = feather.read_table(path)
    df = table.to_pandas()

    # Normalize identifiers as strings (stable keys in JSON and in the UI).
    for col in ("origin_zone_id", "dest_zone_id"):
        if col in df.columns:
            df[col] = df[col].astype(str)

    return df


def od_metric(*, period: str, day_type: str, hour: int, origin_zone_id: str | None, metric: str) -> dict[str, object]:
    """
    Return a zone-based metric mapping for a single origin zone.

    The function reads the precomputed OD Arrow file for the requested
    metric and hour and returns the minimal metric value per destination
    zone for the selected origin zone, or average values if no origin
    zone is selected.

    Supported metrics:
        - "travel_time": uses column "total_travel_time_sec"
        - "transfers": uses column "transfers"
        - "car_travel_time": uses column "car_travel_time_sec"
        - "pt_car_ratio": uses the ratio "total_travel_time_sec / car_travel_time_sec"

    Args:
        period: Calendar week folder name, e.g. "2026W09".
        day_type: Day type folder name, e.g. "weekday", "saturday", "sunday".
        hour: Departure hour (0..23).
        origin_zone_id: Selected origin zone id. If None, returns average values.
        metric: Metric identifier ("travel_time", "transfers", "car_travel_time" or "pt_car_ratio").
    Returns:
        Dict with keys:
            - origin_zone_id: str | None
            - hour: int
            - metric: str
            - values: dict[str, int | float] mapping zone_id -> metric value
    """
    # if no zone is selected return average to all other zones in traveltimes and transfers
    if metric == "car_travel_time":
        df = _load_car_hour_df(hour)
    elif metric == "pt_car_ratio":
        pt_df = _load_hour_df(period, day_type, hour)
        car_df = _load_car_hour_df(hour)

        if pt_df.empty or car_df.empty:
            df = pd.DataFrame()
        else:
            pt_cols = ["origin_zone_id", "dest_zone_id", "total_travel_time_sec"]
            for c in ("origin_stop_id", "origin_stop_name", "dest_stop_id", "dest_stop_name"):
                if c in pt_df.columns:
                    pt_cols.append(c)

            car_cols = ["origin_zone_id", "dest_zone_id", "car_travel_time_sec"]

            pt_sub = pt_df.loc[:, [c for c in pt_cols if c in pt_df.columns]].copy()
            car_sub = car_df.loc[:, [c for c in car_cols if c in car_df.columns]].copy()

            df = pt_sub.merge(car_sub, on=["origin_zone_id", "dest_zone_id"], how="inner")
            df["total_travel_time_sec"] = pd.to_numeric(df["total_travel_time_sec"], errors="coerce")
            df["car_travel_time_sec"] = pd.to_numeric(df["car_travel_time_sec"], errors="coerce")
            df = df.dropna(subset=["total_travel_time_sec", "car_travel_time_sec"])
            df = df.loc[df["car_travel_time_sec"] > 0].copy()
            df["pt_car_ratio"] = df["total_travel_time_sec"] / df["car_travel_time_sec"]
    else:
        df = _load_hour_df(period, day_type, hour)

    if not origin_zone_id:
        if df.empty:
            return {"origin_zone_id": None, "hour": hour, "metric": metric, "values": {}, "mode": "origin_avg",
                    "origin_stations": {}}

        if metric == "travel_time":
            value_col = "total_travel_time_sec"
        elif metric == "transfers":
            value_col = "transfers"
        elif metric == "car_travel_time":
            value_col = "car_travel_time_sec"
        elif metric == "pt_car_ratio":
            value_col = "pt_car_ratio"
        else:
            return {"origin_zone_id": None, "hour": hour, "metric": metric, "values": {}, "mode": "origin_avg",
                    "origin_stations": {}}

        required = {"origin_zone_id", "dest_zone_id", value_col}
        if required.difference(df.columns):
            return {"origin_zone_id": None, "hour": hour, "metric": metric, "values": {}, "mode": "origin_avg",
                    "origin_stations": {}}

        cols = ["origin_zone_id", "dest_zone_id", value_col]
        for c in ("origin_stop_id", "origin_stop_name"):
            if c in df.columns:
                cols.append(c)

        sub = df.loc[:, cols].copy()
        sub[value_col] = pd.to_numeric(sub[value_col], errors="coerce")
        sub = sub.dropna(subset=[value_col])

        sub = sub.loc[sub["origin_zone_id"] != sub["dest_zone_id"]]

        g = sub.groupby("origin_zone_id", sort=False)[value_col].mean()
        # get average as float for transfers int for travel time
        if metric == "transfers" or metric == "pt_car_ratio":
            values = {str(zid): float(v) for zid, v in g.items()}
        else:
            values = {str(zid): int(round(v)) for zid, v in g.items()}

        origin_stations = {}
        if "origin_stop_id" in sub.columns:
            tmp = (
                sub[["origin_zone_id", "origin_stop_id", "origin_stop_name"]]
                .dropna(subset=["origin_zone_id", "origin_stop_id"])
                .drop_duplicates(subset=["origin_zone_id"], keep="first")
            )

            origin_stations = {
                str(r["origin_zone_id"]): {"stop_id": str(r["origin_stop_id"]), "stop_name": str(r["origin_stop_name"])}
                for _, r in tmp.iterrows()
            }

        return {
            "origin_zone_id": None,
            "hour": hour,
            "metric": metric,
            "values": values,
            "mode": "origin_avg",
            "origin_stations": origin_stations,
        }

    if df.empty:
        return {
            "origin_zone_id": str(origin_zone_id),
            "hour": hour,
            "metric": metric,
            "values": {},
            "mode": "od",
            "origin_station": None,
            "dest_stations": {},
        }

    origin_zone_id = str(origin_zone_id)

    if metric == "travel_time":
        value_col = "total_travel_time_sec"
    elif metric == "transfers":
        value_col = "transfers"
    elif metric == "car_travel_time":
        value_col = "car_travel_time_sec"
    elif metric == "pt_car_ratio":
        value_col = "pt_car_ratio"
    else:
        # Fail-safe: unknown metric yields empty payload.
        return {"origin_zone_id": origin_zone_id, "hour": hour, "metric": metric, "values": {}, "mode": "od",
                "origin_station": None, "dest_stations": {}}

    required = {"origin_zone_id", "dest_zone_id", value_col}
    missing = required.difference(df.columns)
    if missing:
        return {"origin_zone_id": origin_zone_id, "hour": hour, "metric": metric, "values": {}, "mode": "od",
                "origin_station": None, "dest_stations": {}}

    cols = ["origin_zone_id", "dest_zone_id", value_col]
    for c in ("origin_stop_id", "origin_stop_name", "dest_stop_id", "dest_stop_name"):
        if c in df.columns:
            cols.append(c)

    sub = df.loc[df["origin_zone_id"] == origin_zone_id, cols].copy()
    if sub.empty:
        return {"origin_zone_id": origin_zone_id, "hour": hour, "metric": metric, "values": {}, "mode": "od",
                "origin_station": None, "dest_stations": {}}

    # Ensure numeric comparison and drop invalid rows.
    sub[value_col] = pd.to_numeric(sub[value_col], errors="coerce")
    sub = sub.dropna(subset=[value_col])

    # If multiple rows per destination exist, keep the minimal value.
    sub = sub.sort_values(["dest_zone_id", value_col], kind="stable")
    sub = sub.drop_duplicates(subset=["dest_zone_id"], keep="first")

    origin_station = None
    if "origin_stop_id" in sub.columns:
        r0 = sub.iloc[0]
        origin_station = {
            "stop_id": str(r0["origin_stop_id"]),
            "stop_name": str(r0.get("origin_stop_name", "")),
        }

    dest_stations = {}
    if "dest_stop_id" in sub.columns:
        for _, r in sub.iterrows():
            dest_stations[str(r["dest_zone_id"])] = {
                "stop_id": str(r["dest_stop_id"]),
                "stop_name": str(r.get("dest_stop_name", "")),
            }

    if metric == "pt_car_ratio":
        values = {str(zid): float(v) for zid, v in zip(sub["dest_zone_id"], sub[value_col])}
    else:
        values = {str(zid): int(v) for zid, v in zip(sub["dest_zone_id"], sub[value_col])}

    return {
        "origin_zone_id": origin_zone_id,
        "hour": hour,
        "metric": metric,
        "values": values,
        "mode": "od",
        "origin_station": origin_station,
        "dest_stations": dest_stations,
    }
