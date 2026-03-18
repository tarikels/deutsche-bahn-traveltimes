"""Top-level public API for gtfs_toolbox."""

from . import gtfs_subset_utilities, gtfs_io_utilities

from .geo_utilities import load_vector, load_directory, merge_layers, load_zones

from .gtfs_io_utilities import (
    load_feed,
    load_single_table,
    load_multiple_tables,
    available_feed_tables,
    identify_feed_source,
    gtfs_time_to_seconds,
    seconds_to_gtfs_time,
    departures_per_stop_period,
)

from .gtfs_subset_utilities import (
    subset_feed_by_date_window,
    great_circle_distance_meters,
)

from .zoning import assign_stops_to_zones, top_n_per_zone


__all__ = [
    # modules
    "gtfs_io_utilities",
    "gtfs_subset_utilities",
    # gtfs_io_utilities functions
    "load_feed",
    "load_single_table",
    "load_multiple_tables",
    "available_feed_tables",
    "identify_feed_source",
    "gtfs_time_to_seconds",
    "seconds_to_gtfs_time",
    "departures_per_stop_period",
    # gtfs_subset_utilities functions
    "subset_feed_by_date_window",
    "great_circle_distance_meters",
    # geo functions
    "load_vector",
    "load_directory",
    "merge_layers",
    "load_zones",
    # zoning
    "assign_stops_to_zones",
    "top_n_per_zone",
]
