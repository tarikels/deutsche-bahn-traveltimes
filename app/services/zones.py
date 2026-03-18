"""
Zone data access helpers.

Provides cached loading and serialization of VG1000 polygons for fast
client delivery (GeoJSON) and lightweight dropdown population.
"""

# Standard library
from functools import lru_cache
from typing import Any

# Local
from src.gtfs_toolbox.geo_utilities import load_zones
from app.config import (
    SIMPLIFY,
    SIMPLIFY_TOLERANCE,
    VG1000_DIR,
    VG_LAYER,
    ZONE_ID_COL,
    ZONE_NAME_COL,
)


@lru_cache(maxsize=1)
def zones_gdf():
    """
    Load VG1000 zones once and normalize them for web mapping.

    Returns:
        GeoDataFrame with columns: zone_id, zone_name, geometry
    """
    layers = load_zones(VG1000_DIR, merge=False)
    if VG_LAYER not in layers:
        available = ", ".join(sorted(layers.keys()))
        raise KeyError(f"Layer '{VG_LAYER}' not found. Available: {available}")

    gdf = layers[VG_LAYER].copy()

    # Keep a minimal schema for the UI
    gdf = gdf[[ZONE_ID_COL, ZONE_NAME_COL, "geometry"]].rename(
        columns={ZONE_ID_COL: "zone_id", ZONE_NAME_COL: "zone_name"}
    )
    gdf["zone_id"] = gdf["zone_id"].astype(str)
    gdf["zone_name"] = gdf["zone_name"].astype(str)

    # Normalize CRS for Leaflet (lat/lon)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    else:
        gdf = gdf.to_crs("EPSG:4326")

    # Simplification reduces payload + rendering cost in the browser
    if SIMPLIFY:
        gdf["geometry"] = gdf["geometry"].simplify(
            SIMPLIFY_TOLERANCE, preserve_topology=True
        )

    return gdf


@lru_cache(maxsize=1)
def zones_geojson() -> dict[str, Any]:
    """
    Return the full zone layer as GeoJSON.
    """
    return zones_gdf().__geo_interface__


@lru_cache(maxsize=1)
def zones_index() -> list[dict[str, str]]:
    """
    Return a lightweight zone list for the dropdown.
    """
    gdf = zones_gdf()
    return (
        gdf[["zone_id", "zone_name"]]
        .sort_values(["zone_name", "zone_id"])
        .to_dict(orient="records")
    )
