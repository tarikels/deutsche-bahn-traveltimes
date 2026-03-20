"""
Project configuration for the FastAPI + Leaflet map UI.

This module keeps paths and constants centralized to avoid magic values
scattered across the codebase.
"""


from pathlib import Path
from typing import Final


# Repository root (parent of the "app" package directory).
REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]

# Data root
OD_DIR: Final[Path] = REPO_ROOT / "data" / "od"
REGIONAL_OD_DIR: Final[Path] = REPO_ROOT / "data" / "od_regional"
CAR_OD_DIR: Final[Path] = REPO_ROOT / "data" / "car_od"


# VG1000 shapefile bundle
VG1000_DIR: Final[Path] = (
    REPO_ROOT / "data" / "shapefiles_vg1000_germany" / "vg1000_ebenen_1231"
)

# Default zone layer + columns (VG1000_KRS: counties)
VG_LAYER: Final[str] = "VG1000_KRS"
ZONE_ID_COL: Final[str] = "ARS"
ZONE_NAME_COL: Final[str] = "GEN"

# Geometry simplification
SIMPLIFY: Final[bool] = True
SIMPLIFY_TOLERANCE: Final[float] = 0.002

# UI dir and page index
UI_DIR = Path(__file__).resolve().parent / "ui"
INDEX_HTML = (UI_DIR / "index.html").read_text(encoding="utf-8")
