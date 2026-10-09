"""Bundle route patterns, stop names, and pair distances into a single JS file
the static web page can load via <script src>, which works from file:// (unlike
fetch() of a JSON file, which browsers block under file://).

Usage: python -m kilotrack.export_webdata data/latest.zip
"""

import json
import sys
import zipfile

from kilotrack.patterns import load_patterns
from kilotrack.wolfenbuettel import load_table

PATTERNS_PATH = "data/route_patterns.json"
PAIR_DISTANCES_PATH = "data/pair_distances.csv"
OUT_PATH = "web/data.js"


def main(zip_path: str) -> None:
    route_patterns = load_patterns(PATTERNS_PATH)

    used_stop_ids = {sid for info in route_patterns.values() for p in info["patterns"] for sid in p}

    with zipfile.ZipFile(zip_path) as zf:
        stops = load_table(zf, "stops.txt")
    stop_names = {
        row.stop_id: row.stop_name for row in stops.itertuples() if row.stop_id in used_stop_ids
    }

    pairs = {}
    with open(PAIR_DISTANCES_PATH, newline="") as f:
        import csv

        for row in csv.DictReader(f):
            pairs[f"{row['from_stop_id']}_{row['to_stop_id']}"] = float(row["km"])

    data = {"routes": route_patterns, "stopNames": stop_names, "pairs": pairs}

    with open(OUT_PATH, "w") as f:
        f.write("const KILOTRACK_DATA = ")
        json.dump(data, f, ensure_ascii=False)
        f.write(";\n")

    print(f"Wrote {OUT_PATH}: {len(route_patterns)} routes, {len(stop_names)} stops, {len(pairs)} pairs")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])
