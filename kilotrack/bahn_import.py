"""Resolve a bahn.de / DB Navigator "Verbindung teilen" share link into its
legs (line, boarding/alighting stop, intermediate stops).

Uses the DB Navigator app's internal backend (app.services-bahn.de/mob) —
the same unofficial API the Android/iOS app uses. The public bahn.de website
API (www.bahn.de/web/api) is blocked by Akamai bot management and returns
errors for plain HTTP clients, so this one is used instead. Unofficial and
undocumented; may change without notice.

Requests go through curl_cffi with Chrome TLS impersonation, not plain
`requests` — Akamai TLS-fingerprints the /mob host too and returns
452 OPS_BLOCKED for a plain-requests fingerprint from a datacenter/CI IP,
even with correct headers. A real Chrome fingerprint passes.

Flow:
  1. GET  /mob/angebote/verbindung/{vbid}  -> {"GH": "<recon context>", ...}
  2. POST /mob/angebote/recon              -> {"verbindung": {...}, "angebote": {...}}
  3. verbindung["verbindungsAbschnitte"] is the list of legs.
"""

import re
import time
import uuid

from curl_cffi import requests

BASE = "https://app.services-bahn.de/mob"
SHARE_MEDIA = "application/x.db.vendo.mob.verbindungteilen.v1+json"
JOURNEY_MEDIA = "application/x.db.vendo.mob.verbindungssuche.v9+json"

VBID_RE = re.compile(r"vbid=([0-9a-fA-F-]{8,})")
UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)


class BahnImportError(Exception):
    pass


def extract_vbid(text: str) -> str:
    text = text.strip()
    m = VBID_RE.search(text)
    if m:
        return m.group(1)
    m = UUID_RE.search(text)
    if m:
        return m.group(0)
    raise BahnImportError(f"Could not find a vbid in: {text!r}")


def _headers(media: str) -> dict:
    return {
        "Accept": media,
        "Content-Type": media,
        "Accept-Language": "de",
        "User-Agent": "DBNavigator/Android/26.9.0",
        "X-App-Version": "26.9.0",
        "X-Correlation-ID": f"{uuid.uuid4()}_{uuid.uuid4()}",
    }


def resolve_share_link(vbid: str) -> dict:
    """vbid -> full connection JSON ({"verbindung": {...}, "angebote": {...}})."""
    lookup_resp = requests.get(
        f"{BASE}/angebote/verbindung/{vbid}", headers=_headers(SHARE_MEDIA), timeout=12, impersonate="chrome"
    )
    if lookup_resp.status_code != 200:
        raise BahnImportError(f"Share lookup failed: HTTP {lookup_resp.status_code} {lookup_resp.text[:300]}")
    share = lookup_resp.json()
    recon = share.get("GH")
    if not recon:
        raise BahnImportError(f"No recon context ('GH') in share response: {share!r}")

    time.sleep(2)  # /mob rate-limits aggressively; pace consecutive calls

    body = {
        "autonomeReservierung": False,
        "einstiegsTypList": ["STANDARD"],
        "fahrverguenstigungen": {
            "deutschlandTicketVorhanden": False,
            "nurDeutschlandTicketVerbindungen": False,
        },
        "klasse": "KLASSE_2",
        "verbindungHin": {"kontext": recon},
        "reisendenProfil": {
            "reisende": [{"ermaessigungen": ["KEINE_ERMAESSIGUNG KLASSENLOS"], "reisendenTyp": "ERWACHSENER"}]
        },
        "reservierungsKontingenteVorhanden": False,
    }
    recon_resp = requests.post(
        f"{BASE}/angebote/recon", json=body, headers=_headers(JOURNEY_MEDIA), timeout=15, impersonate="chrome"
    )
    if recon_resp.status_code != 200:
        raise BahnImportError(f"Recon failed: HTTP {recon_resp.status_code} {recon_resp.text[:300]}")
    return recon_resp.json()


def parse_legs(connection: dict) -> list[dict]:
    """Full connection JSON -> list of legs, walking legs included
    (typ == 'FUSSWEG'), bus legs have produkt_gattung == 'BUS'."""
    vb = connection.get("verbindung", connection)
    legs = []
    for a in vb.get("verbindungsAbschnitte", []):
        is_walking = a.get("typ") == "FUSSWEG"
        origin = a.get("abgangsOrt", {})
        dest = a.get("ankunftsOrt", {})
        halte = a.get("halte", [])
        legs.append(
            {
                "is_walking": is_walking,
                "produkt_gattung": a.get("produktGattung"),
                "line_name": a.get("mitteltext") or a.get("kurztext") or "",
                "from_name": origin.get("name"),
                "from_eva": origin.get("evaNr"),
                "to_name": dest.get("name"),
                "to_eva": dest.get("evaNr"),
                "departure": a.get("abgangsDatum"),
                "arrival": a.get("ankunftsDatum"),
                "intermediate_stops": [
                    {"name": h.get("ort", {}).get("name"), "eva": h.get("ort", {}).get("evaNr")}
                    for h in halte
                ],
            }
        )
    return legs


def import_trip(share_link_or_text: str) -> list[dict]:
    vbid = extract_vbid(share_link_or_text)
    connection = resolve_share_link(vbid)
    return parse_legs(connection)


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python -m kilotrack.bahn_import '<bahn.de share link or pasted text>'")
        sys.exit(1)

    legs = import_trip(sys.argv[1])
    for leg in legs:
        kind = "FUSSWEG" if leg["is_walking"] else leg["produkt_gattung"]
        print(f"[{kind}] {leg['line_name']!r}: {leg['from_name']} -> {leg['to_name']}")
        print(f"   {leg['departure']} -> {leg['arrival']}")
        if leg["intermediate_stops"]:
            names = [s["name"] for s in leg["intermediate_stops"]]
            print(f"   via: {', '.join(names)}")
