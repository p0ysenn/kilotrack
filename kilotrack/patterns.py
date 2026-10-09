"""Extract, per route, every distinct ordered stop sequence (trip pattern).

No direction_id exists in this feed, and routes have many branch/variant
patterns (school trips, short-workings, etc.) — rather than picking one
"canonical" sequence per route, we keep every distinct pattern so the trip
calculator can find whichever one actually contains the boarding and
alighting stop in order.
"""

import json
import zipfile

from kilotrack.wolfenbuettel import load_table


def extract_patterns(zf: zipfile.ZipFile, route_ids: set[str]) -> dict:
    trips = load_table(zf, "trips.txt")
    stop_times = load_table(zf, "stop_times.txt", usecols=["trip_id", "stop_id", "stop_sequence"])
    routes = load_table(zf, "routes.txt")

    wf_trips = trips[trips["route_id"].isin(route_ids)]
    st = stop_times[stop_times["trip_id"].isin(wf_trips["trip_id"])].copy()
    st["stop_sequence"] = st["stop_sequence"].astype(int)
    st = st.sort_values(["trip_id", "stop_sequence"])

    seqs = st.groupby("trip_id")["stop_id"].apply(tuple)
    seq_df = wf_trips[["trip_id", "route_id"]].merge(seqs.rename("seq"), left_on="trip_id", right_index=True)

    result = {}
    for route_id, group in seq_df.groupby("route_id"):
        short_name = routes.loc[routes["route_id"] == route_id, "route_short_name"].iloc[0]
        distinct_patterns = sorted({tuple(s) for s in group["seq"]})
        result[route_id] = {
            "short_name": short_name,
            "patterns": [list(p) for p in distinct_patterns],
        }
    return result


def unique_consecutive_pairs(route_patterns: dict) -> set[tuple[str, str]]:
    pairs = set()
    for info in route_patterns.values():
        for pattern in info["patterns"]:
            for a, b in zip(pattern, pattern[1:]):
                pairs.add((a, b))
    return pairs


def save_patterns(route_patterns: dict, path: str) -> None:
    with open(path, "w") as f:
        json.dump(route_patterns, f, indent=1, ensure_ascii=False)


def load_patterns(path: str) -> dict:
    with open(path) as f:
        return json.load(f)
