"""Tool definitions for the agent and their deterministic implementations.

Every tool returns {"data": ..., "assumptions": [...], "coverage_notes": [...], "as_of": ...}.
The LLM never computes numbers; it only calls these and narrates the result.
"""
from __future__ import annotations

import functools
import json

import pandas as pd

from agent import config as C
from agent import live_apis, scoring

AS_OF = "FAA CY2023-CY2025 enplanements; BTS T-100 and On-Time calendar year 2025; OurAirports snapshot 2026-10-09"

GENERAL_ASSUMPTIONS = [
    "Profitability is not observed. The score uses demand pressure x capacity strain as a proxy for where added capacity would be used.",
    "Scores and percentiles are relative to a peer group, not absolute. The 'peer_group' field in each ranking says which group was used (default: all US primary airports).",
]
COVERAGE_NOTES = [
    "BTS On-Time data covers only large US carriers' domestic flights (no cargo, no foreign carriers), so delay metrics understate activity at cargo or international heavy airports.",
    "T-100 covers all carriers including cargo and international; FAA enplanements cover revenue passengers boarding.",
]


@functools.lru_cache(maxsize=1)
def load_features() -> pd.DataFrame:
    return pd.read_csv(C.FEATURES_PATH)


class ScoringParams:
    """Weights the UI can override; defaults come from config."""
    def __init__(self, demand_weights=None, strain_weights=None, demand_share=None):
        self.demand_weights = demand_weights or C.DEMAND_WEIGHTS
        self.strain_weights = strain_weights or C.STRAIN_WEIGHTS
        self.demand_share = C.DEMAND_SHARE if demand_share is None else demand_share


def _scored(params: ScoringParams, peer: pd.DataFrame | None = None) -> pd.DataFrame:
    df = load_features()
    return scoring.score_table(df, peer=peer, demand_weights=params.demand_weights,
                               strain_weights=params.strain_weights, demand_share=params.demand_share)


def _wrap(data, assumptions=(), coverage=()):
    return {"data": data, "assumptions": GENERAL_ASSUMPTIONS + list(assumptions),
            "coverage_notes": COVERAGE_NOTES + list(coverage), "as_of": AS_OF}


def _resolve_states(states, region):
    if region:
        key = region.strip().lower()
        if key not in C.REGIONS:
            return None, f"Unknown region '{region}'. Known: {sorted(C.REGIONS)}"
        return C.REGIONS[key], None
    return ([s.upper() for s in states] if states else None), None


def _row_summary(r: pd.Series, year: int) -> dict:
    return {
        "code": r["code"], "name": r["name"], "state": r["state"], "hub": C.HUB_LABELS.get(r["hub"], r["hub"]),
        "expansion_score": scoring._num(r["expansion_score"]),
        "demand_score": scoring._num(r["demand_score"]),
        "strain_score": scoring._num(r["strain_score"]),
        "confidence": r["confidence"],
        f"enplanements_{year}": scoring._num(r[f"enpl_{year}"]),
        "pax_cagr_2y": scoring._num(r["pax_cagr_2y"]),
        "load_factor": scoring._num(r["load_factor"]),
        "dep_del15_rate": scoring._num(r["dep_del15_rate"]),
        "taxi_out_mean": scoring._num(r["taxi_out_mean"]),
        "deps_per_runway": scoring._num(r["deps_per_runway"]),
        "runways_open": scoring._num(r["runways_open"]),
    }


# ---------------------------------------------------------------- tool implementations
def rank_airports(params: ScoringParams, states=None, region=None, hub_tiers=None,
                  top_n=10, peer_group="all", min_enplanements=None) -> dict:
    df = load_features()
    states, err = _resolve_states(states, region)
    if err:
        return _wrap({"error": err})
    sel = scoring.select_universe(df, states, hub_tiers, min_enplanements)
    if sel.empty:
        return _wrap({"error": "No primary airports match the filter", "states": states, "hub_tiers": hub_tiers})
    peer = sel if peer_group == "selection" else df
    scored = scoring.score_table(sel, peer=peer, demand_weights=params.demand_weights,
                                 strain_weights=params.strain_weights, demand_share=params.demand_share)
    year = scoring.latest_year(df)
    rows = [_row_summary(r, year) for _, r in scored.head(top_n).iterrows()]
    return _wrap({
        "filter": {"states": states, "hub_tiers": hub_tiers, "min_enplanements": min_enplanements},
        "airports_in_selection": len(sel),
        "peer_group": "selection" if peer_group == "selection" else "all US primary airports",
        "weights": {"demand_share": params.demand_share, "demand": params.demand_weights, "strain": params.strain_weights},
        "ranking": rows,
    }, assumptions=[
        f"Expansion score = {params.demand_share:.0%} demand + {1 - params.demand_share:.0%} strain, each a weighted mean of percentile ranks.",
        "Weather delay is excluded from the score because investment cannot fix it.",
        "Low confidence means fewer than 1,000 On-Time flights: strain uses only departures per runway there.",
    ])


def airport_profile(params: ScoringParams, code: str) -> dict:
    scored = _scored(params)
    code = code.upper()
    if code not in set(scored["code"]):
        return _wrap({"error": f"{code} is not an FAA primary airport in the dataset"})
    r = scored.set_index("code").loc[code]
    r["code"] = code
    year = scoring.latest_year(scored)
    keep = ["name", "city", "state", "hub", "icao", "lat", "lon", "runways_open", "runways_7000ft_plus", "longest_runway_ft",
            f"enpl_{year - 2}", f"enpl_{year - 1}", f"enpl_{year}", "pax_yoy", "pax_cagr_2y",
            "deps", "seats", "pax", "freight_lbs", "load_factor", "intl_share_deps", "freight_share_deps",
            "avg_distance_mi", "seasonality_peak_ratio", "seats_growth_yoy", "deps_growth_yoy",
            "ot_flights", "dep_del15_rate", "taxi_out_mean", "cancel_rate", "nas_delay_per_flight",
            "weather_delay_per_flight", "late_aircraft_per_flight", "carrier_delay_per_flight", "peak_block_share",
            "deps_per_runway", "pax_per_runway", "rank"]
    facts = {k: scoring._num(r.get(k)) for k in keep}
    facts["hub"] = C.HUB_LABELS.get(facts["hub"], facts["hub"])
    facts["rank_among_all_primary"] = f"{int(r['rank'])} of {len(scored)}"
    return _wrap({"code": code, "facts": facts, "score": scoring.score_breakdown(r, params.demand_weights, params.strain_weights)},
                 coverage=[] if r["confidence"] != "low" else ["On-Time coverage is thin for this airport; delay metrics are unreliable."])


LIVE_NOW_NOTE = "live_now is the FAA NAS status at request time; it is context only and not part of any score."


def _live_context(code: str) -> dict:
    """Current FAA NAS status for one airport. One cached XML fetch serves all airports."""
    return live_apis.faa_nas_status(code)


def compare_airports(params: ScoringParams, codes: list[str]) -> dict:
    scored = _scored(params)
    codes = [c.upper() for c in codes]
    missing = [c for c in codes if c not in set(scored["code"])]
    if missing:
        return _wrap({"error": f"Not in dataset: {missing}"})
    data = scoring.compare(scored, codes)
    data["live_now"] = {c: _live_context(c) for c in codes}
    return _wrap(data, assumptions=[
        "Percentiles are among all US primary airports.",
        "Congestion is read from departure delays, taxi-out time, NAS delay, peak concentration and departures per runway.",
        LIVE_NOW_NOTE,
    ])


def long_haul_share(params: ScoringParams, code: str, threshold_mi: int = C.LONG_HAUL_DEFAULT_MI) -> dict:
    df = load_features()
    code = code.upper()
    if code not in set(df["code"]):
        return _wrap({"error": f"{code} is not in the dataset"})
    r = df.set_index("code").loc[code]
    r["code"] = code
    data = scoring.long_haul(r, threshold_mi)
    notes = [f"Long haul is defined by great-circle segment distance; shares are weighted by departures performed. Thresholds available: {list(C.LONG_HAUL_THRESHOLDS_MI)} miles."]
    if not data["threshold_available"]:
        notes.append(f"Requested threshold {threshold_mi} mi is not precomputed; nearest available thresholds are reported.")
    return _wrap(data, assumptions=notes, coverage=["Based on T-100 (all carriers, including cargo and international)."])


def unmet_demand(params: ScoringParams, code: str) -> dict:
    scored = _scored(params)
    code = code.upper()
    if code not in set(scored["code"]):
        return _wrap({"error": f"{code} is not in the dataset"})
    r = scored.set_index("code").loc[code]
    r["code"] = code
    data = scoring.unmet_demand(r)
    data["context"] = {"name": r["name"], "hub": C.HUB_LABELS.get(r["hub"], r["hub"]),
                       "pax_yoy": scoring._num(r["pax_yoy"]), "pax_cagr_2y": scoring._num(r["pax_cagr_2y"]),
                       "seats_growth_yoy": scoring._num(r.get("seats_growth_yoy")),
                       "runways_open": scoring._num(r["runways_open"]), "runways_7000ft_plus": scoring._num(r["runways_7000ft_plus"])}
    data["live_now"] = _live_context(code)
    return _wrap(data, assumptions=[
        "Unmet demand is inferred, not observed: it is read from full seats, passengers outgrowing seats, and congestion indicators.",
        "Delay share tells where the constraint sits: NAS and late-aircraft delay are addressable by capacity; weather delay is not.",
        LIVE_NOW_NOTE,
    ])


def live_status(params: ScoringParams, code: str) -> dict:
    df = load_features()
    code = code.upper()
    if code not in set(df["code"]):
        return _wrap({"error": f"{code} is not in the dataset"})
    r = df.set_index("code").loc[code]
    faa = live_apis.faa_nas_status(code)
    sky = live_apis.opensky_aircraft_near(float(r["lat"]), float(r["lon"]), code) if pd.notna(r["lat"]) else {"error": "no coordinates"}
    return _wrap({"code": code, "faa_nas_status": faa, "opensky": sky}, assumptions=[
        "Live data is a snapshot at request time and is not part of the score.",
        "OpenSky counts transponder-equipped aircraft in a 0.3 degree box; coverage depends on volunteer receivers.",
    ])


def explain_methodology(params: ScoringParams) -> dict:
    return _wrap({
        "score": "expansion_score = demand_share * demand_score + (1 - demand_share) * strain_score, each 0-100",
        "demand_share": params.demand_share,
        "demand_weights": params.demand_weights,
        "strain_weights": params.strain_weights,
        "percentiles": "Each feature is converted to a percentile rank within the peer group; missing features are dropped and weights renormalised.",
        "confidence": {"high": f">= {C.OT_HIGH} On-Time flights, all sources present",
                       "medium": f"{C.OT_LOW}-{C.OT_HIGH} On-Time flights, or T-100 2024 missing",
                       "low": f"< {C.OT_LOW} On-Time flights; strain uses only departures per runway"},
        "not_in_score": ["weather delay", "cancellations", "financials", "gate counts", "official runway capacity (ASPM)"],
        "long_haul_thresholds_mi": list(C.LONG_HAUL_THRESHOLDS_MI),
        "sources": ["FAA CY enplanements", "BTS T-100 Segment All Carriers", "BTS On-Time Reporting Carrier", "OurAirports", "FAA NAS Status API", "OpenSky Network API"],
    })


# ---------------------------------------------------------------- schemas
TOOL_SCHEMAS = [
    {"name": "rank_airports",
     "description": "Rank FAA primary airports by the deterministic Expansion Opportunity Score. Filter by US states or a named region (new england, mid-atlantic, southeast, midwest, southwest, mountain west, pacific, alaska, hawaii) and by hub tier (L, M, S, N). Returns the top airports with score components and confidence.",
     "input_schema": {"type": "object", "properties": {
         "states": {"type": "array", "items": {"type": "string"}, "description": "Two-letter state codes"},
         "region": {"type": "string", "description": "Named region, alternative to states"},
         "hub_tiers": {"type": "array", "items": {"type": "string", "enum": ["L", "M", "S", "N"]}},
         "top_n": {"type": "integer", "default": 10},
         "peer_group": {"type": "string", "enum": ["all", "selection"], "default": "all", "description": "Percentiles against all US primary airports (default, comparable across questions) or only within the filtered selection"},
         "min_enplanements": {"type": "integer", "description": "Drop airports below this many annual enplanements"},
     }, "required": []}},
    {"name": "airport_profile",
     "description": "Full fact sheet for one airport: enplanements and growth, T-100 traffic, load factor, runways, delays, and the score breakdown with percentiles.",
     "input_schema": {"type": "object", "properties": {"code": {"type": "string", "description": "FAA/IATA 3-letter code"}}, "required": ["code"]}},
    {"name": "compare_airports",
     "description": "Side-by-side congestion and demand metrics for 2 to 6 airports with percentiles among all US primary airports, plus the live FAA NAS status of each airport right now (live_now, not scored).",
     "input_schema": {"type": "object", "properties": {"codes": {"type": "array", "items": {"type": "string"}, "minItems": 2}}, "required": ["codes"]}},
    {"name": "long_haul_share",
     "description": "Share of departures that are long haul for one airport, at 1500/2500/3000 mile thresholds, split into passenger and freight aircraft.",
     "input_schema": {"type": "object", "properties": {"code": {"type": "string"}, "threshold_mi": {"type": "integer", "default": 2500}}, "required": ["code"]}},
    {"name": "unmet_demand",
     "description": "Rule-based unmet demand indicators for one airport (load factor, passengers vs seats growth, delays, cancellations, runway use), the delay mix that explains why, and the live FAA NAS status right now (live_now, not scored).",
     "input_schema": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}},
    {"name": "live_status",
     "description": "Live snapshot: FAA NAS Status delay/closure programs for the airport right now and OpenSky count of aircraft near it. Not part of the score.",
     "input_schema": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}},
    {"name": "explain_methodology",
     "description": "Return the scoring formula, weights, confidence rules, data sources and what the score does not capture.",
     "input_schema": {"type": "object", "properties": {}, "required": []}},
]

IMPLEMENTATIONS = {
    "rank_airports": rank_airports,
    "airport_profile": airport_profile,
    "compare_airports": compare_airports,
    "long_haul_share": long_haul_share,
    "unmet_demand": unmet_demand,
    "live_status": live_status,
    "explain_methodology": explain_methodology,
}


def run_tool(name: str, args: dict, params: ScoringParams | None = None) -> dict:
    params = params or ScoringParams()
    fn = IMPLEMENTATIONS.get(name)
    if fn is None:
        return {"error": f"unknown tool {name}"}
    try:
        return fn(params, **args)
    except TypeError as e:
        return {"error": f"bad arguments for {name}: {e}"}
    except Exception as e:
        return {"error": f"{name} failed: {type(e).__name__}: {e}"}


def to_json(obj) -> str:
    return json.dumps(obj, default=_default, ensure_ascii=False)


def _default(o):
    try:
        return o.item()
    except Exception:
        return str(o)
