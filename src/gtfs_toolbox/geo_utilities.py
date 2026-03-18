"""
Additional geo utilities for loading and merging zone geodata.
"""

# Standard library
from pathlib import Path
from typing import Iterable

# Third-party
import geopandas as gpd
import pandas as pd


SUPPORTED_EXTENSIONS = {".shp", ".gpkg", ".geojson", ".json"}


def load_vector(path: str | Path, *, layer: str | None = None, target_crs: str = "EPSG:4326") -> gpd.GeoDataFrame:
    """
    Load a vector dataset into a GeoDataFrame and reproject to target_crs.

    Args:
        path: Path to a vector file (.shp/.gpkg/.geojson/.json).
        layer: Optional layer name (primarily for GeoPackage).
        target_crs: CRS to reproject to (default EPSG:4326).

    Returns:
        GeoDataFrame in target_crs.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)

    if p.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {p.suffix} (supported: {sorted(SUPPORTED_EXTENSIONS)})")

    gdf = gpd.read_file(p, layer=layer) if layer else gpd.read_file(p)

    if gdf.crs is None:
        raise ValueError(f"Missing CRS in dataset (no .prj or unreadable CRS): {p}")

    if str(gdf.crs).upper() != target_crs.upper():
        gdf = gdf.to_crs(target_crs)

    return gdf


def load_directory(
    directory: str | Path,
    *,
    recursive: bool = False,
    target_crs: str = "EPSG:4326",
) -> dict[str, gpd.GeoDataFrame]:
    """
    Load all supported vector files in a directory.

    Shapefiles are detected by their *.shp file (sidecar files must exist).
    GeoPackages/GeoJSON are loaded as-is (default layer for GPKG unless specified elsewhere).

    Args:
        directory: Folder containing vector files.
        recursive: If True, search subfolders recursively.
        target_crs: CRS to reproject all layers to (default EPSG:4326).

    Returns:
        Dict mapping dataset keys to GeoDataFrames.
        The key is the filename stem (e.g., 'VG1000_KRS' for 'VG1000_KRS.shp').
    """
    base = Path(directory)
    if not base.exists():
        raise FileNotFoundError(base)

    pattern = "**/*" if recursive else "*"
    files = [p for p in base.glob(pattern) if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS]

    # Avoid loading .json twice if you have both .json and .geojson variants; keep it simple for now.
    files = sorted(files)

    if not files:
        raise FileNotFoundError(f"No supported vector files found in: {base}")

    out: dict[str, gpd.GeoDataFrame] = {}
    for p in files:
        key = p.stem
        # Note: for .gpkg with multiple layers, user should call load_vector(..., layer=...)
        out[key] = load_vector(p, target_crs=target_crs)

    return out


def merge_layers(
    layers: Iterable[gpd.GeoDataFrame],
    *,
    target_crs: str = "EPSG:4326",
    reset_index: bool = True,
) -> gpd.GeoDataFrame:
    """
    Merge multiple GeoDataFrames into a single GeoDataFrame via concatenation.

    This is a simple "stack" merge (row-wise concat). It assumes layers represent the
    same conceptual schema (same columns / compatible geometry types).

    Args:
        layers: Iterable of GeoDataFrames.
        target_crs: Ensure output is in this CRS (default EPSG:4326).
        reset_index: If True, reindex the merged GeoDataFrame.

    Returns:
        A single concatenated GeoDataFrame in target_crs.
    """
    layers_list = list(layers)
    if not layers_list:
        raise ValueError("No layers provided for merge_layers().")

    # Ensure consistent CRS
    norm = []
    for gdf in layers_list:
        if gdf.crs is None:
            raise ValueError("One of the layers has no CRS defined.")
        if str(gdf.crs).upper() != target_crs.upper():
            gdf = gdf.to_crs(target_crs)
        norm.append(gdf)

    merged = gpd.GeoDataFrame(
        pd.concat(norm, ignore_index=reset_index),
        crs=target_crs,
    )
    return merged


def load_zones(directory: str | Path, *, recursive: bool = False, target_crs: str = "EPSG:4326", merge: bool = False) \
        -> dict[str, gpd.GeoDataFrame] | gpd.GeoDataFrame:
    """
    High-level API: load all vector layers from a directory.

    Args:
        directory: Folder containing vector datasets.
        recursive: Search subfolders recursively.
        target_crs: Reproject to this CRS (default EPSG:4326).
        merge: If True, return a single concatenated GeoDataFrame.
               If False, return a dict of GeoDataFrames.

    Returns:
        Either:
          - dict[str, GeoDataFrame] if merge=False
          - GeoDataFrame if merge=True
    """
    layers = load_directory(directory, recursive=recursive, target_crs=target_crs)
    if not merge:
        return layers
    return merge_layers(layers.values(), target_crs=target_crs)
