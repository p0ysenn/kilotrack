"""Phase 2: build the pair-distance cache and route patterns.

Usage: python -m kilotrack.build_segments data/latest.zip

Uses OSRM's public demo server (no API key). Resumable: patterns whose every
consecutive pair is already in data/pair_distances.csv are skipped, so
re-running after an interruption just continues. Each remaining pattern
costs exactly one request (all its waypoints sent together), regardless of
pattern length.
"""

import csv
import os
import sys
import time
import zipfile

from kilotrack.ors_client import RoutingError, route_segments_km
from kilotrack.patterns import extract_patterns, save_patterns
from kilotrack.wolfenbuettel import load_table, wolfenbuettel_route_ids

PATTERNS_PATH = "data/route_patterns.json"
PAIR_DISTANCES_PATH = "data/pair_distances.csv"
REQUEST_DELAY_SECONDS = 1.5  # be polite to the shared public demo server


def load_cached_pairs(path: str) -> dict[tuple[str, str], float]:
    cached = {}
    if not os.path.exists(path):
        return cached
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            cached[(row["from_stop_id"], row["to_stop_id"])] = float(row["km"])
    return cached


def main(zip_path: str) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        route_ids = wolfenbuettel_route_ids(zf)
        route_patterns = extract_patterns(zf, route_ids)
        stops = load_table(zf, "stops.txt")

    save_patterns(route_patterns, PATTERNS_PATH)
    print(f"Saved {len(route_patterns)} routes' patterns to {PATTERNS_PATH}")

    all_patterns = [tuple(p) for info in route_patterns.values() for p in info["patterns"]]
    cached = load_cached_pairs(PAIR_DISTANCES_PATH)

    def pattern_pairs(pattern):
        return list(zip(pattern, pattern[1:]))

    todo = [p for p in set(all_patterns) if any(pair not in cached for pair in pattern_pairs(p))]
    print(f"{len(set(all_patterns))} distinct patterns total, {len(todo)} have at least one uncached pair.")

    stop_coords = {row.stop_id: (float(row.stop_lon), float(row.stop_lat)) for row in stops.itertuples()}

    file_exists = os.path.exists(PAIR_DISTANCES_PATH)
    with open(PAIR_DISTANCES_PATH, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["from_stop_id", "to_stop_id", "km"])

        for i, pattern in enumerate(todo, 1):
            lonlats = [stop_coords[sid] for sid in pattern]
            try:
                kms = route_segments_km(lonlats)
            except RoutingError as e:
                print(f"Rate limited or error on pattern {i}/{len(todo)} ({e}) — backing off 30s and retrying once.")
                time.sleep(30)
                try:
                    kms = route_segments_km(lonlats)
                except RoutingError as e2:
                    print(f"Still failing after backoff ({e2}); stopping at {i - 1}/{len(todo)} patterns.")
                    break

            for pair, km in zip(pattern_pairs(pattern), kms):
                if pair not in cached:
                    writer.writerow([pair[0], pair[1], km])
                    cached[pair] = km
            f.flush()

            if i % 20 == 0 or i == len(todo):
                print(f"{i}/{len(todo)} patterns fetched")
            time.sleep(REQUEST_DELAY_SECONDS)

    print("Done.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])
