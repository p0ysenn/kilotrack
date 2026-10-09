"""Identify the GTFS routes that actually serve Wolfenbüttel.

The nationwide GTFS feed (gtfs.de "latest.zip") has no shapes.txt, and its
agency_name values are per fare-association (Verbund), not per operator —
"KVG" also matches several unrelated operators elsewhere in Germany, and
plain substring search for "Wolfenbüttel" also hits unrelated places
(e.g. a hamlet "Wolfenbüttel" in Dithmarschen, "Wolfenbrück" near
Schwäbisch Hall). So routes are identified by: trips that stop at a stop
named like Wolfenbüttel AND located within the Braunschweig/Wolfenbüttel/
Salzgitter area — not by agency name.
"""

import zipfile

import pandas as pd

# Bounding box around Braunschweig/Wolfenbüttel/Salzgitter, wide enough to
# include the Stadtbus network and nearby feeder routes, narrow enough to
# exclude same-named places elsewhere in Germany.
BBOX_LAT = (51.9, 52.35)
BBOX_LON = (10.1, 10.85)


def load_table(zf: zipfile.ZipFile, name: str, usecols: list[str] | None = None) -> pd.DataFrame:
    with zf.open(name) as f:
        return pd.read_csv(f, dtype=str, usecols=usecols)


def wolfenbuettel_stops(zf: zipfile.ZipFile) -> pd.DataFrame:
    stops = load_table(zf, "stops.txt")
    stops["stop_lat"] = stops["stop_lat"].astype(float)
    stops["stop_lon"] = stops["stop_lon"].astype(float)
    in_bbox = stops["stop_lat"].between(*BBOX_LAT) & stops["stop_lon"].between(*BBOX_LON)
    named = stops["stop_name"].str.contains("Wolfenb", case=False, na=False)
    return stops[in_bbox & named]


def wolfenbuettel_route_ids(zf: zipfile.ZipFile) -> set[str]:
    wf_stops = wolfenbuettel_stops(zf)
    stop_times = load_table(zf, "stop_times.txt", usecols=["trip_id", "stop_id"])
    trips = load_table(zf, "trips.txt", usecols=["trip_id", "route_id"])
    wf_trip_ids = set(stop_times[stop_times["stop_id"].isin(wf_stops["stop_id"])]["trip_id"])
    return set(trips[trips["trip_id"].isin(wf_trip_ids)]["route_id"])
