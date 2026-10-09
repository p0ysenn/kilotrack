"""Phase 1: load a GTFS zip, filter to routes serving Wolfenbüttel, report what's there.

Usage: python -m kilotrack.inspect_gtfs data/<feed>.zip
"""

import sys
import zipfile

import pandas as pd

from kilotrack.wolfenbuettel import load_table, wolfenbuettel_route_ids, wolfenbuettel_stops


def main(zip_path: str) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        print(f"Files in feed: {sorted(zf.namelist())}\n")

        route_ids = wolfenbuettel_route_ids(zf)
        routes = load_table(zf, "routes.txt")
        wf_routes = routes[routes["route_id"].isin(route_ids)]
        agency = load_table(zf, "agency.txt")
        merged = wf_routes.merge(agency, on="agency_id", how="left")
        print(f"Routes serving Wolfenbüttel: {len(wf_routes)}")
        print(
            merged[["route_id", "agency_id", "agency_name", "route_short_name", "route_type"]]
            .sort_values("route_short_name")
            .to_string(index=False)
        )

        trips = load_table(zf, "trips.txt")
        wf_trips = trips[trips["route_id"].isin(route_ids)]
        print(f"\nTrips: {len(wf_trips)}")

        if "shapes.txt" in zf.namelist():
            shapes = load_table(zf, "shapes.txt")
            wf_shape_ids = set(wf_trips["shape_id"].dropna())
            wf_shapes = shapes[shapes["shape_id"].isin(wf_shape_ids)]
            print(f"shapes.txt present. Shape_ids: {len(wf_shape_ids)}, points: {len(wf_shapes)}")
        else:
            print("No shapes.txt in this feed — segment distances need a routing-engine fallback (OSRM/ORS).")

        stop_times = load_table(zf, "stop_times.txt")
        wf_stop_times = stop_times[stop_times["trip_id"].isin(wf_trips["trip_id"])]
        print(f"\nstop_times rows: {len(wf_stop_times)}")

        wf_stops = wolfenbuettel_stops(zf)
        print(f"Wolfenbüttel-area stops (seed set): {len(wf_stops)}")
        all_stop_ids = set(wf_stop_times["stop_id"])
        print(f"All stops touched by these routes (incl. outside Wolfenbüttel): {len(all_stop_ids)}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])
