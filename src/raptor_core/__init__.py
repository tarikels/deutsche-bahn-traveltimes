"""
Public routing API.

Exposes the index builder and RAPTOR query helpers as a small, stable interface.
"""

from .raptor_indices import build_raptor_indices
from .raptor import (
    prepare_departure_lookup,
    route_by_stop_ids,
    route_by_stop_names,
    reconstruct_connection,
)

__all__ = [
    "build_raptor_indices",
    "prepare_departure_lookup",
    "route_by_stop_ids",
    "route_by_stop_names",
    "reconstruct_connection",
]
