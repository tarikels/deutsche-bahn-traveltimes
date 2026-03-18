"""
GTFS zoning utilities.

This module provides lightweight helpers to (1) assign GTFS stops to polygon zones
(e.g., VG1000 layers) using a spatial join and (2) select the top-N stops per zone
based on an arbitrary score (e.g., departures in a day/period).

"""

# Third-party
import geopandas as gpd
import pandas as pd


def assign_stops_to_zones(
    stops: pd.DataFrame,
    zones: gpd.GeoDataFrame,
    *,
    zone_id_col: str,
    predicate: str = "within",
) -> pd.DataFrame:
    """
    Assign each GTFS stop to a zone polygon (point-in-polygon via spatial join).

    Args:
        stops: stops.txt DataFrame with columns stop_id, stop_lon, stop_lat.
        zones: Polygon GeoDataFrame (any CRS; will be converted to EPSG:4326).
        zone_id_col: Zone identifier column in zones (e.g., 'ARS', 'AGS').
        predicate: 'within' (default) or 'intersects' to include boundary points.

    Returns:
        DataFrame with columns: stop_id, zone_id (unmatched stops dropped).
    """
    pts = gpd.GeoDataFrame(
        stops[["stop_id", "stop_lon", "stop_lat"]].copy(),
        geometry=gpd.points_from_xy(stops["stop_lon"], stops["stop_lat"]),
        crs="EPSG:4326",
    )

    if zones.crs is None or str(zones.crs).upper() != "EPSG:4326":
        zones = zones.to_crs("EPSG:4326")

    j = gpd.sjoin(pts, zones[[zone_id_col, "geometry"]], how="left", predicate=predicate)
    out = j[["stop_id", zone_id_col]].rename(columns={zone_id_col: "zone_id"}).dropna()
    out["stop_id"] = out["stop_id"].astype(str)
    out["zone_id"] = out["zone_id"].astype(str)
    return out


def top_n_per_zone(
    stop_scores: pd.DataFrame,
    stop_zone: pd.DataFrame,
    *,
    score_col: str,
    n: int = 1)\
        -> pd.DataFrame:
    """
    Keep top-N stops per zone by a score column.

    Args:
        stop_scores: DataFrame with columns stop_id and score_col.
        stop_zone: DataFrame with columns stop_id, zone_id.
        score_col: Column used for ranking (higher is better).
        n: Number of stops to keep per zone.

    Returns:
        DataFrame with columns: zone_id, stop_id, score_col
    """
    m = stop_scores[["stop_id", score_col]].merge(stop_zone, on="stop_id", how="inner")
    m = m.sort_values(["zone_id", score_col, "stop_id"], ascending=[True, False, True], kind="stable")
    return m.groupby("zone_id", as_index=False).head(n)[["zone_id", "stop_id", score_col]].reset_index(drop=True)
