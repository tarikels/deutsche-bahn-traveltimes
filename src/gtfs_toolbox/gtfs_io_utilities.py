"""GTFS I/O utilities (ZIP or directory).

Provides lightweight functions to discover, validate, and load GTFS tables into
pandas DataFrames, plus small helpers for GTFS date/time normalization and
optional feed export.
"""

# Standard library
from datetime import date, time
import math
from pathlib import Path
from typing import Iterable, Literal, Dict
import zipfile

# Third-party
import pandas as pd

# Local package imports
from . import gtfs_subset_utilities as gtfs_filter

REQUIRED_GTFS_TABLES: set[str] = {
    "stops.txt",
    "routes.txt",
    "trips.txt",
    "stop_times.txt",
    "calendar.txt",
}


def identify_feed_source(path: str | Path) -> Literal["zip", "dir"]:
    """
    Determine whether a GTFS source is a ZIP file or a directory.

    Args:
        path: Path to a GTFS ZIP archive or directory.

    Returns:
        "zip" for ZIP-based feeds or "dir" for directory-based feeds.

    Raises:
        ValueError: If the path is invalid or not a supported GTFS source.
    """
    source_path = Path(path)

    if source_path.is_dir():
        return "dir"
    elif source_path.is_file() and zipfile.is_zipfile(source_path):
        return "zip"
    else:
        raise ValueError(
            f"Path does not exist or is neither a directory nor a valid ZIP file: {source_path}"
        )


def available_feed_tables(path: str | Path) -> set[str]:
    """
    List all GTFS text tables available in a feed source.

    Args:
        path: Path to a GTFS ZIP archive or directory.

    Returns:
        Set of available *.txt table names.

    Raises:
        ValueError: If the feed source type is unsupported.
    """
    source_path = Path(path)
    source_kind = identify_feed_source(source_path)

    if source_kind == "zip":
        with zipfile.ZipFile(source_path, "r") as archive:
            return {Path(member).name for member in archive.namelist() if member.endswith(".txt")}
    elif source_kind == "dir":
        return {entry.name for entry in source_path.glob("*.txt")}
    raise ValueError(f"Unsupported feed type: {source_kind}")


def has_required_tables(table_names: set[str]) -> bool:
    """
    Check whether all required GTFS tables are present.

    Args:
        table_names: Set of available GTFS table filenames.

    Returns:
        True if all required tables are included, otherwise False.
    """
    return REQUIRED_GTFS_TABLES.issubset(table_names)


def get_missing_tables(table_names: set[str]) -> set[str]:
    """
    Return the required GTFS tables that are missing.

    Args:
        table_names: Set of available GTFS table filenames.

    Returns:
        Set of missing required GTFS table names.
    """
    return REQUIRED_GTFS_TABLES.difference(table_names)


def load_single_table(path: str, name: str, encoding: str = "utf-8") -> pd.DataFrame:
    """
    Load one GTFS table from a directory or ZIP feed.

    Args:
        path: Path to GTFS directory or ZIP file.
        name: Table filename such as "stops.txt".
        encoding: CSV encoding.

    Returns:
        Loaded table as pandas.DataFrame.
    """
    source_path = Path(path)
    source_kind = identify_feed_source(source_path)

    if source_kind == "dir":
        table_path = source_path / name
        if not table_path.exists():
            return pd.DataFrame()
        return pd.read_csv(
            table_path,
            encoding=encoding,
        )

    with zipfile.ZipFile(source_path, "r") as archive:
        matches = [member for member in archive.namelist() if Path(member).name == name]
        if not matches:
            return pd.DataFrame()
        member_name = matches[0]
        with archive.open(member_name) as handle:
            return pd.read_csv(handle, encoding=encoding)


def load_multiple_tables(
    path: str,
    names: Iterable[str] | None = None,
) -> dict[str, pd.DataFrame]:
    """
    Load multiple GTFS tables from a feed source.

    Args:
        path: Path to GTFS directory or ZIP file.
        names: Iterable of table filenames, or None to load all available tables.

    Returns:
        Dictionary mapping table names to pandas.DataFrames.
    """
    loaded_tables: dict[str, pd.DataFrame] = {}

    if names is None:
        names = available_feed_tables(path)

    for table_name in names:
        loaded_tables[table_name] = load_single_table(path, table_name)

    return loaded_tables


def gtfs_time_to_seconds(val: str | None) -> int | None:
    """
    Convert a GTFS time string into total seconds since midnight.

    Args:
        val: GTFS time string.

    Returns:
        Integer seconds since 00:00:00, or None for empty/invalid input.
    """
    if val is None:
        return None

    text = str(val).strip()
    if text == "":
        return None

    try:
        hours, minutes, seconds = map(int, text.split(":"))
    except ValueError:
        return None

    return hours * 3600 + minutes * 60 + seconds


def seconds_to_gtfs_time(total_seconds: int | None) -> str | None:
    """
    Convert seconds since midnight to a GTFS time string.

    Args:
        total_seconds: Seconds since 00:00:00.

    Returns:
        Time string in "HH:MM:SS" format, or None for invalid input.
    """
    if total_seconds is None or total_seconds < 0:
        return None

    hours = total_seconds // 3600
    remainder = total_seconds % 3600
    minutes = remainder // 60
    seconds = remainder % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def gtfs_time_to_day_clock(val: str | None) -> time | None:
    """
    Convert a GTFS time string into a Python time object in 24-hour range.

    Args:
        val: GTFS time string.

    Returns:
        Python time object, or None for empty/invalid input.
    """
    if val is None:
        return None

    text = str(val).strip()
    if not text:
        return None

    try:
        hours, minutes, seconds = map(int, text.split(":"))
    except ValueError:
        return None

    hours = hours % 24
    return time(hour=hours, minute=minutes, second=seconds)


def yyyymmdd_to_date(val: int | str | date) -> date:
    """
    Convert a GTFS date value into a Python date object.

    Args:
        val: Date value as date, int, or string.

    Returns:
        Parsed Python date object.
    """
    if isinstance(val, date):
        return val

    text = str(val).strip()
    if not text:
        raise ValueError("Empty date value")

    if "-" in text:
        text = text.replace("-", "")

    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"Invalid date literal: {val!r} (expected YYYYMMDD or YYYY-MM-DD)")

    return date(int(text[0:4]), int(text[4:6]), int(text[6:8]))


def parse_time_fields(
    table: pd.DataFrame,
    cols: Iterable[str] = ("arrival_time", "departure_time"),
) -> pd.DataFrame:
    """
    Parse GTFS time columns into Python time objects.

    Args:
        table: GTFS table as pandas.DataFrame.
        cols: Column names to convert.

    Returns:
        DataFrame with parsed time columns.
    """
    for column in cols:
        if column in table.columns:
            table[column] = table[column].apply(gtfs_time_to_day_clock)
    return table


def append_seconds_columns(
    table: pd.DataFrame,
    cols: Iterable[str] = ("arrival_time", "departure_time"),
) -> pd.DataFrame:
    """
    Add second-based companion columns for GTFS time fields.

    Args:
        table: GTFS table as pandas.DataFrame.
        cols: Column names to convert.

    Returns:
        DataFrame with additional *_seconds columns.
    """
    for column in cols:
        if column in table.columns:
            table[f"{column}_seconds"] = table[column].apply(gtfs_time_to_seconds)
    return table


def parse_date_fields(
    table: pd.DataFrame,
    cols: Iterable[str] = ("start_date", "end_date", "date"),
) -> pd.DataFrame:
    """
    Parse GTFS date columns into Python date objects.

    Args:
        table: GTFS table as pandas.DataFrame.
        cols: Column names to convert.

    Returns:
        DataFrame with parsed date columns.
    """
    for column in cols:
        if column in table.columns:
            table[column] = table[column].apply(yyyymmdd_to_date)
    return table


def normalize_stop_coordinates(stops: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure stop_lat and stop_lon are numeric and valid.

    Args:
        stops: stops.txt table as pandas.DataFrame.

    Returns:
        DataFrame with cleaned coordinate columns.
    """
    cleaned = stops.copy()
    for column in ("stop_lat", "stop_lon"):
        if column not in cleaned.columns:
            return cleaned.iloc[0:0]
        cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce")
    cleaned = cleaned.dropna(subset=["stop_lat", "stop_lon"])
    return cleaned


def build_transfer_walkpaths(
    feed: dict[str, pd.DataFrame],
    radius_m: float = 1500.0,
    walking_speed_mps: float = 0.8,
) -> dict[str, pd.DataFrame]:
    """
    Add walk transfer paths between stops within a distance threshold.

    Args:
        feed: GTFS feed dictionary.
        radius_m: Maximum walking radius in meters.
        walking_speed_mps: Walking speed in meters per second.

    Returns:
        GTFS feed dictionary with updated transfers.txt table.
    """
    if "transfers.txt" not in feed:
        feed["transfers.txt"] = pd.DataFrame(
            columns=[
                "from_stop_id",
                "to_stop_id",
                "transfer_type",
                "min_transfer_time",
                "from_route_id",
                "to_route_id",
                "from_trip_id",
                "to_trip_id",
            ]
        )

    stops_table = feed["stops.txt"]
    transfers_table = feed["transfers.txt"]

    stop_ids = stops_table["stop_id"].astype(str).to_numpy()
    latitudes = stops_table["stop_lat"].astype(float).to_numpy()
    longitudes = stops_table["stop_lon"].astype(float).to_numpy()
    stop_count = len(stop_ids)

    existing_pairs = set(
        zip(
            transfers_table["from_stop_id"].astype(str),
            transfers_table["to_stop_id"].astype(str),
        )
    )
    pending_rows = []

    for left_idx in range(stop_count):
        from_stop = stop_ids[left_idx]
        from_lat = latitudes[left_idx]
        from_lon = longitudes[left_idx]

        lat_margin = radius_m / 111_320.0
        lon_margin = radius_m / (111_320.0 * max(0.1, math.cos(math.radians(from_lat))))
        within_box = (
            (abs(latitudes - from_lat) <= lat_margin)
            & (abs(longitudes - from_lon) <= lon_margin)
        )

        for right_idx in range(left_idx + 1, stop_count):
            if left_idx == right_idx or not within_box[right_idx]:
                continue

            to_stop = stop_ids[right_idx]
            distance_m = gtfs_filter.great_circle_distance_meters(
                from_lat,
                from_lon,
                latitudes[right_idx],
                longitudes[right_idx],
            )

            if distance_m <= radius_m:
                travel_seconds = math.ceil(distance_m / walking_speed_mps)

                if (from_stop, to_stop) not in existing_pairs:
                    pending_rows.append(
                        {
                            "from_stop_id": from_stop,
                            "to_stop_id": to_stop,
                            "transfer_type": 2,
                            "min_transfer_time": travel_seconds,
                            "from_route_id": 0,
                            "to_route_id": 0,
                            "from_trip_id": 0,
                            "to_trip_id": 0,
                        }
                    )
                    existing_pairs.add((from_stop, to_stop))

                if (to_stop, from_stop) not in existing_pairs:
                    pending_rows.append(
                        {
                            "from_stop_id": to_stop,
                            "to_stop_id": from_stop,
                            "transfer_type": 2,
                            "min_transfer_time": travel_seconds,
                            "from_route_id": 0,
                            "to_route_id": 0,
                            "from_trip_id": 0,
                            "to_trip_id": 0,
                        }
                    )
                    existing_pairs.add((to_stop, from_stop))

    if pending_rows:
        transfers_table = pd.concat([transfers_table, pd.DataFrame(pending_rows)], ignore_index=True)

    result_feed = dict(feed)
    result_feed["transfers.txt"] = transfers_table
    return result_feed


def departures_per_stop_period(
    feed: dict,
    *,
    on=None,
    date_from=None,
    date_to=None,
) -> pd.DataFrame:
    """
    Count departures per stop for one service day, a date range, or the full feed.

    Args:
        feed: GTFS feed dictionary.
        on: Single service date.
        date_from: Period start date.
        date_to: Period end date.

    Returns:
        DataFrame with stop_id and departures columns.
    """
    if (on is not None) or (date_from is not None) or (date_to is not None):
        if on is not None:
            if not isinstance(on, date):
                on = yyyymmdd_to_date(on)
            start = end = on
        else:
            if not isinstance(date_from, date):
                date_from = yyyymmdd_to_date(date_from)
            if not isinstance(date_to, date):
                date_to = yyyymmdd_to_date(date_to)
            start, end = date_from, date_to

        feed = gtfs_filter.subset_feed_by_date_window(
            feed,
            start=start,
            end=end,
            prune_stop_times=True,
            prune_stops=False,
        )

    stop_times = feed["stop_times.txt"][["stop_id", "departure_time"]].copy()
    stop_times["stop_id"] = stop_times["stop_id"].astype(str)

    departure_seconds = stop_times["departure_time"].apply(gtfs_time_to_seconds)
    stop_times = stop_times.loc[departure_seconds.notna(), ["stop_id"]]

    return (
        stop_times.groupby("stop_id", as_index=False)
        .size()
        .rename(columns={"size": "departures"})
    )


def load_feed(path: str, *, load_all: bool = True, parse_stop_times: bool = False) -> dict[str, pd.DataFrame]:
    """
    Load and preprocess a GTFS feed from a directory or ZIP archive.

    Args:
        path: Path to GTFS directory or ZIP file.
        load_all: Whether to load all tables instead of only required tables.
        parse_stop_times: Whether to parse stop_times clock fields and add second columns.

    Returns:
        Dictionary mapping GTFS table names to pandas.DataFrames.

    Raises:
        ValueError: If required GTFS tables are missing.
    """
    table_names = available_feed_tables(path)

    if not has_required_tables(table_names):
        raise ValueError(f"Feed is missing required tables: {get_missing_tables(table_names)}")

    tables = load_multiple_tables(path) if load_all else load_multiple_tables(path, REQUIRED_GTFS_TABLES)

    if "calendar.txt" in tables and "calendar_dates.txt" in tables:
        calendar_table = tables["calendar.txt"]
        calendar_dates_table = tables["calendar_dates.txt"]

        if not calendar_table.empty:
            tables["calendar.txt"] = parse_date_fields(calendar_table)
        if not calendar_dates_table.empty:
            tables["calendar_dates.txt"] = parse_date_fields(calendar_dates_table)

    if parse_stop_times and "stop_times.txt" in tables:
        stop_times_table = tables["stop_times.txt"]
        if not stop_times_table.empty:
            tables["stop_times.txt"] = append_seconds_columns(stop_times_table)
            tables["stop_times.txt"] = parse_time_fields(stop_times_table)

    tables["stop_times.txt"]["trip_id"] = tables["stop_times.txt"]["trip_id"].astype("string")
    tables["trips.txt"]["trip_id"] = tables["trips.txt"]["trip_id"].astype("string")
    tables = build_transfer_walkpaths(tables)
    return tables


def export_gtfs(feed: Dict[str, pd.DataFrame], out_zip: str | Path) -> Path:
    """
    Export a GTFS feed dictionary to a ZIP archive of *.txt tables.

    Args:
        feed: GTFS feed dictionary.
        out_zip: Output ZIP path.

    Returns:
        Path to the written ZIP archive.
    """
    import zipfile

    output_path = Path(out_zip)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for table_name, table in feed.items():
            if not table_name.endswith(".txt"):
                continue
            csv_text = table.to_csv(index=False, lineterminator="\n")
            archive.writestr(table_name, csv_text)

    return output_path
