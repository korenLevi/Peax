"""Live public APIs: OpenSky (aircraft currently near an airport) and FAA NAS Status.

Both are best-effort. Failures return a dict with an "error" key instead of raising,
so the agent can tell the user the live layer is unavailable and continue with the
historical data.
"""
from __future__ import annotations

import os
import time
import xml.etree.ElementTree as ET

import requests

OPENSKY_TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
OPENSKY_STATES_URL = "https://opensky-network.org/api/states/all"
FAA_NAS_URL = "https://nasstatus.faa.gov/api/airport-status-information"

CACHE_TTL_S = 300
BBOX_DEG = 0.3  # about 20 nautical miles at mid latitudes

_cache: dict[str, tuple[float, object]] = {}


def _cached(key: str, fn):
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < CACHE_TTL_S:
        return hit[1]
    val = fn()
    _cache[key] = (now, val)
    return val


# ---------------------------------------------------------------- OpenSky
def _opensky_token() -> str | None:
    cid, sec = os.environ.get("OPENSKY_CLIENT_ID"), os.environ.get("OPENSKY_CLIENT_SECRET")
    if not cid or not sec:
        return None

    def fetch():
        r = requests.post(OPENSKY_TOKEN_URL, data={
            "grant_type": "client_credentials", "client_id": cid, "client_secret": sec}, timeout=20)
        r.raise_for_status()
        return r.json().get("access_token")

    return _cached("opensky_token", fetch)


def opensky_aircraft_near(lat: float, lon: float, code: str) -> dict:
    """Count aircraft state vectors inside a bounding box around the airport."""
    def fetch():
        token = _opensky_token()
        if not token:
            return {"error": "OPENSKY_CLIENT_ID / OPENSKY_CLIENT_SECRET not set"}
        params = {"lamin": lat - BBOX_DEG, "lamax": lat + BBOX_DEG,
                  "lomin": lon - BBOX_DEG, "lomax": lon + BBOX_DEG}
        r = requests.get(OPENSKY_STATES_URL, params=params,
                         headers={"Authorization": f"Bearer {token}"}, timeout=30)
        if r.status_code != 200:
            return {"error": f"OpenSky HTTP {r.status_code}", "body": r.text[:200]}
        states = r.json().get("states") or []
        on_ground = sum(1 for s in states if s[8])
        return {
            "aircraft_in_box": len(states),
            "on_ground": on_ground,
            "airborne": len(states) - on_ground,
            "bbox_deg": BBOX_DEG,
            "snapshot_unix": r.json().get("time"),
        }

    try:
        return _cached(f"opensky:{code}", fetch)
    except Exception as e:  # network, auth, JSON
        return {"error": f"OpenSky request failed: {type(e).__name__}: {e}"[:300]}


# ---------------------------------------------------------------- FAA NAS Status
def _faa_xml() -> ET.Element:
    def fetch():
        r = requests.get(FAA_NAS_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        r.raise_for_status()
        return ET.fromstring(r.content)
    return _cached("faa_nas", fetch)


def faa_nas_status(code: str) -> dict:
    """Return every current delay/closure program that names this airport."""
    try:
        root = _faa_xml()
    except Exception as e:
        return {"error": f"FAA NAS Status request failed: {type(e).__name__}: {e}"[:300]}

    events = []
    for dtype in root.iter("Delay_type"):
        name = (dtype.findtext("Name") or "").strip()
        for el in dtype.iter():
            arpt = el.findtext("ARPT")
            if arpt and arpt.strip().upper() == code.upper():
                detail = {child.tag: (child.text or "").strip() for child in el if child.text and child.tag != "ARPT"}
                events.append({"type": name, "program": el.tag, **detail})
    return {
        "update_time": (root.findtext("Update_Time") or "").strip(),
        "active_events": events,
        "status": "delays or closures reported" if events else "no FAA delay program active",
    }
