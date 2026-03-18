"""
FastAPI entrypoint for the map UI.
To Start Application try:
#   py -m uvicorn app.app:app --reload --port 8000
#   python -m uvicorn app.app:app --reload --port 8000
"""

# Third-Party
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Local
from app.config import INDEX_HTML
from app.services.od import od_metric, available_periods
from app.services.zones import zones_geojson, zones_index
from app.ui.datapage import DATA_PAGE_HTML
from pathlib import Path

app = FastAPI(title="German Traveltime Quality - Map UI", version="1.0.0")

_ui_static_dir = Path(__file__).resolve().parent / "ui" / "static"
app.mount("/static", StaticFiles(directory=_ui_static_dir), name="static")
app.mount("/data", StaticFiles(directory="data"), name="data")


@app.get("/api/zones/index", response_class=JSONResponse)
def api_zones_index():
    """Return zone_id + zone_name records for the dropdown."""
    return zones_index()


@app.get("/api/zones/geojson", response_class=JSONResponse)
def api_zones_geojson():
    """Return zone polygons as GeoJSON for Leaflet rendering."""
    return zones_geojson()


@app.get("/api/periods")
def api_periods() -> dict[str, object]:
    return {"periods": available_periods()}


@app.get("/about-data", response_class=HTMLResponse)
def about_data():
    """Serve the data information page."""
    return HTMLResponse(DATA_PAGE_HTML)


@app.get("/api/od/metric", response_class=JSONResponse)
def api_od_metric(
    period: str = Query(..., description="e.g. 2026W09"),
    day_type: str = Query(..., description="weekday|saturday|sunday"),
    hour: int = Query(..., ge=0, le=23),
    origin_zone_id: str | None = Query(None),
        metric: str = Query("travel_time", description="travel_time|car_travel_time|transfers|pt_car_ratio")):
    """
    Return choropleth values for a selected metric (travel_time or transfers).

    Response shape:
        { "origin_zone_id": "...", "hour": 8, "metric": "travel_time", "values": { "dest_zone": value } }
    """
    return od_metric(
        period=period,
        day_type=day_type,
        hour=hour,
        origin_zone_id=origin_zone_id,
        metric=metric,
    )


@app.get("/", response_class=HTMLResponse)
def index():
    """Serve the single-page UI (inline CSS/JS)."""
    return HTMLResponse(INDEX_HTML)


@app.get("/healthz")
def healthz():
    """Lightweight health check for local/dev deployments."""
    return {"ok": True}
