# Kilotrack

Bus-kilometer tracker for KVG Braunschweig lines around Wolfenbüttel. Full goal, data
sources, and phased plan: see the "Bus Kilometer Tracker" project description from the
session that started this project (also mirrored in Claude's project memory).

## Setup

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Layout

- `data/latest.zip` — the GTFS feed in use (gitignored, not committed). It's a
  nationwide gtfs.de feed, not KVG-specific, and has NO `shapes.txt`.
- `kilotrack/wolfenbuettel.py` — the route filter. Do NOT filter by `agency_name`
  ("KVG" matches unrelated operators nationwide in this feed, and agency_name here
  is per fare-association/Verbund, not per operator). Instead filters by geo-bbox +
  stop name to find genuine Wolfenbüttel stops, then takes all routes touching them.
- `kilotrack/inspect_gtfs.py` — Phase 1 report: `python -m kilotrack.inspect_gtfs data/latest.zip`

## Layout (cont.)

- `kilotrack/patterns.py` — extracts every distinct ordered stop sequence (trip
  pattern) per route from GTFS. No `direction_id` in this feed and routes have many
  branch/variant patterns, so we keep all patterns rather than one canonical sequence
  per route+direction.
- `kilotrack/ors_client.py` — routing client. Despite the name, this wraps OSRM's
  public demo server (`router.project-osrm.org`), not OpenRouteService — ORS kept
  returning `403 Quota exceeded` even on trivial requests despite the dashboard
  showing full quota, never resolved, so we switched. OSRM needs no API key/signup.
  Batches a whole pattern's stops into one multi-waypoint request (`legs[]` gives
  per-consecutive-pair distance), not one request per pair.
- `kilotrack/build_segments.py` — Phase 2 builder: `python -m kilotrack.build_segments data/latest.zip`.
  Resumable via `data/pair_distances.csv` (from_stop_id, to_stop_id, km cache).
- `data/route_patterns.json` — per-route list of distinct stop-id sequences (gitignored, regenerable).
- `data/pair_distances.csv` — cached road distance per consecutive stop pair (gitignored, regenerable).

## Status

Phase 1 done: 31 routes serving Wolfenbüttel identified (420/421, 604-658, 710,
730-752, 790-799, 802/806, 659), 2384 trips, 38952 stop_times rows. No shapes.txt,
so segment distances use an OSRM routing fallback, not shape-based measurement.

Phase 2 done: 250 distinct trip patterns extracted, 1127 unique consecutive stop-pair
distances fetched via OSRM (0.022–23.637 km, mean 1.44 km, no gaps).

Static web calculator done (skipped the CLI, went straight to a browser UI): see
`web/index.html` — two fields (Von/Nach), no line selector. It searches every route's
patterns for one containing both stop names in order, picks the shortest match as the
primary result, and lists other lines that also connect those stops as alternatives.
Self-contained, opens via file:// or a static server (plain `http.server`), no build
step, no backend. Data is baked into `web/data.js` (not fetched, since fetch() of
local JSON is blocked under file://) — regenerate with
`python -m kilotrack.export_webdata data/latest.zip` after any Phase 2 re-run.
`.claude/launch.json` serves `web/` on port 8743 for local preview.

Not yet done: trip logging/totals (original Phase 4).

A multi-transfer connection search (find all routes with under 3 transfers between
two stops, not just direct) and a bahn.de share-link import UI were both built and
then **removed again at user request** — not because they didn't work, but the user
asked to drop them. If reviving either: multi-transfer search is straightforward
client-side (name-level ride graph, DFS, dedupe by line-sequence — ask if details are
needed, this exact approach was validated performant on the real data). The bahn.de
import is currently blocked server-side regardless — see below, that part is still
relevant.

## bahn.de trip import (Phase 6) — standalone module, not wired into the web page

- `kilotrack/bahn_import.py` — resolves a bahn.de/DB Navigator "Verbindung teilen"
  share link (the `vbid=` param) into its legs. Test with:
  `python -m kilotrack.bahn_import "<share link or pasted text>"`. This is a
  standalone CLI-testable module only — no web UI currently calls it (removed).
- Uses `app.services-bahn.de/mob` (DB Navigator's internal backend), NOT
  `www.bahn.de/web/api` — the latter is Akamai-bot-blocked for non-browser clients.
- **Must use `curl_cffi` with `impersonate="chrome"`, not plain `requests`** — as of
  ~Oct 2026 DB's Akamai edge TLS-fingerprints the `/mob` host too and returns
  `452 OPS_BLOCKED` for any plain-requests/curl fingerprint from a datacenter/CI IP,
  even with all the right headers. A spoofed Chrome TLS fingerprint passes. Verified
  this empirically in this session (452 with plain `requests` → proper
  `VERBINDUNG_NOT_FOUND` JSON with `curl_cffi`, both from the same sandboxed/CI IP).
- `/mob` also rate-limits aggressively (429 + `Retry-After`, but the limit reportedly
  stays tripped for minutes regardless of the header) — pace requests, don't retry
  in a tight loop.
- Flow: GET `/mob/angebote/verbindung/{vbid}` → `{"GH": "<recon ctx>"}` → POST
  `/mob/angebote/recon` with `{"verbindungHin": {"kontext": GH}, ...}` →
  `{"verbindung": {"verbindungsAbschnitte": [...legs...]}}`. Each leg:
  `typ=="FUSSWEG"` is a walking leg (skip); otherwise `produktGattung=="BUS"`
  identifies a bus leg (vs ICE/IC/RE/S/U/STR/SCHIFF for other modes).
- **Currently blocked (2026-10-09):** `POST /mob/angebote/recon` (the step that
  returns actual legs) returns `452 OPS_BLOCKED` for every server-side attempt —
  tried plain `requests`, `curl_cffi` with `chrome`/`chrome_android`/`chrome99_android`/
  `chrome131_android` impersonation, with sandbox disabled (same outbound IP,
  same result). The lookup step (`GET /angebote/verbindung/{vbid}`) works fine;
  only `/recon` is blocked. This matches a documented, very recent (~Oct 2026)
  finding in the Besser-Bahn reference project: some DB/Akamai-protected endpoints
  now block *every* Python/curl TLS fingerprint regardless of impersonation —
  only the real app's native network stack (dart:io for their Flutter app) gets
  through, which isn't something fingerprint spoofing can fix.
- Also tried calling the DB API directly from browser JS (a small Flask proxy +
  client-side fetch were built at the time) — confirmed dead end, and for a
  DIFFERENT reason: no CORS support at all (`OPTIONS` preflight returns plain
  `405`, no `Access-Control-Allow-Origin`), verified with a real Chromium browser
  (`net::ERR_FAILED` on the actual GET). That Flask proxy (`kilotrack/webserver.py`)
  and the web UI for it have since been removed at user request; if reviving this
  feature, any resolution attempt will need to go through a server again (browser
  calls are a dead end regardless of the /recon block).
- Not yet done: matching DB's stop names/EVA numbers to our GTFS stop_ids (our
  gtfs.de stop_ids are NOT EVA numbers for bus stops — likely needs name-based
  fuzzy matching against our ~659 Wolfenbüttel-area stops), and wiring this into
  the trip log once that exists.
- **Parked (2026-10-09):** `/recon` stays blocked server-side; no web UI currently
  exposes this. Options not yet tried if revisiting: a community HAFAS mirror (e.g.
  v6.db.transport.rest — different service, may not be blocked the same way),
  or manual trip entry via the connection finder instead of automatic import.
  Worth re-testing periodically in case DB's block eases.
