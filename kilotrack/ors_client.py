"""Thin client for OSRM's public routing API (driving profile, used as a
proxy for bus road distance since no bus profile exists). Uses the public
demo server at router.project-osrm.org — free, no API key, but intended for
light/testing use, so requests are paced gently (see build_segments.py)."""

import requests

OSRM_URL = "http://router.project-osrm.org/route/v1/driving/"


class RoutingError(Exception):
    pass


def route_segments_km(lonlats: list[tuple[float, float]]) -> list[float]:
    """One request through all waypoints in order; returns per-leg distance in km,
    one entry per consecutive pair in `lonlats`."""
    coords = ";".join(f"{lon},{lat}" for lon, lat in lonlats)
    resp = requests.get(OSRM_URL + coords, params={"overview": "false"}, timeout=30)
    if resp.status_code == 429:
        raise RoutingError("rate_limited")
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != "Ok":
        raise RoutingError(data.get("code", "unknown_error"))
    legs = data["routes"][0]["legs"]
    return [leg["distance"] / 1000.0 for leg in legs]
