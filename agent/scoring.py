"""Deterministic KPIs and the Expansion Opportunity Score.

Every function here is pure: it takes the airport feature table (a DataFrame) and
returns plain dicts/DataFrames. No I/O, no LLM. The agent's tools call these and the
LLM only puts the results into words.
"""
from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pandas as pd

from agent import config as C

# Strain features where a higher raw value means more strain (all of them today).
HIGHER_IS_WORSE = set(C.STRAIN_WEIGHTS)


# ---------------------------------------------------------------- helpers
def latest_year(df: pd.DataFrame) -> int:
    return int(df["faa_latest_year"].iloc[0])


def enpl_col(df: pd.DataFrame) -> str:
    return f"enpl_{latest_year(df)}"


def select_universe(df: pd.DataFrame, states: Iterable[str] | None = None,
                    hub_tiers: Iterable[str] | None = None,
                    min_enplanements: int | None = None) -> pd.DataFrame:
    out = df
    if states:
        out = out[out["state"].isin([s.upper() for s in states])]
    if hub_tiers:
        out = out[out["hub"].isin([h.upper() for h in hub_tiers])]
    if min_enplanements:
        out = out[out[enpl_col(df)] >= min_enplanements]
    return out


def percentile_ranks(frame: pd.DataFrame, cols: Iterable[str]) -> pd.DataFrame:
    """Percentile rank (0-1) of each column within the frame. NaN stays NaN."""
    return frame[list(cols)].rank(pct=True, na_option="keep")


def _weighted_mean(pcts: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """Weighted mean of available (non-NaN) percentiles, re-normalising the weights."""
    w = pd.Series(weights)
    avail = pcts[w.index].notna()
    num = (pcts[w.index].fillna(0) * w).sum(axis=1)
    den = (avail * w).sum(axis=1)
    return (num / den.replace(0, np.nan))


def confidence(row: pd.Series) -> str:
    ot = row.get("ot_flights", np.nan)
    if pd.isna(ot) or ot < C.OT_LOW:
        return "low"
    if ot < C.OT_HIGH or pd.isna(row.get("seats_growth_yoy", np.nan)) or pd.isna(row.get("runways_open", np.nan)):
        return "medium"
    return "high"


# ---------------------------------------------------------------- score
def score_table(df: pd.DataFrame, peer: pd.DataFrame | None = None,
                demand_weights: dict[str, float] | None = None,
                strain_weights: dict[str, float] | None = None,
                demand_share: float | None = None) -> pd.DataFrame:
    """Score every airport in `df` using percentiles computed within `peer` (default: df).

    Returns df plus: pct_<feature>, demand_score, strain_score, expansion_score (0-100),
    confidence, and a weather_delay_per_flight percentile shown separately (not scored).
    """
    peer = df if peer is None else peer
    dw = demand_weights or C.DEMAND_WEIGHTS
    sw = strain_weights or C.STRAIN_WEIGHTS
    share = C.DEMAND_SHARE if demand_share is None else demand_share

    work = pd.concat([peer, df[~df["code"].isin(peer["code"])]]).copy()
    work["log_enpl"] = np.log10(work[enpl_col(work)].clip(lower=1))
    feats = list(dw) + list(sw) + ["weather_delay_per_flight", "cancel_rate", "peak_block_share"]
    for c in feats:
        if c not in work.columns:
            work[c] = np.nan
    pcts = percentile_ranks(work, feats)
    # Strain is scored only when On-Time coverage is at least OT_LOW flights.
    thin = work["ot_flights"].isna() | (work["ot_flights"] < C.OT_LOW)
    ot_strain = [c for c in sw if c != "deps_per_runway"]
    pcts.loc[thin, ot_strain] = np.nan

    work["demand_score"] = 100 * _weighted_mean(pcts, dw)
    work["strain_score"] = 100 * _weighted_mean(pcts, sw)
    work["expansion_score"] = share * work["demand_score"] + (1 - share) * work["strain_score"]
    for c in feats:
        work[f"pct_{c}"] = pcts[c]
    work["confidence"] = work.apply(confidence, axis=1)
    out = work[work["code"].isin(df["code"])].sort_values("expansion_score", ascending=False)
    out["rank"] = range(1, len(out) + 1)
    return out


def score_breakdown(row: pd.Series, demand_weights=None, strain_weights=None) -> dict:
    dw = demand_weights or C.DEMAND_WEIGHTS
    sw = strain_weights or C.STRAIN_WEIGHTS

    def part(weights):
        return [{
            "feature": f, "weight": w,
            "value": _num(row.get(f if f != "log_enpl" else enpl_col(row.to_frame().T))),
            "percentile": _num(row.get(f"pct_{f}")),
        } for f, w in weights.items()]

    return {
        "expansion_score": _num(row["expansion_score"]),
        "demand_score": _num(row["demand_score"]),
        "strain_score": _num(row["strain_score"]),
        "confidence": row["confidence"],
        "demand_components": part(dw),
        "strain_components": part(sw),
        "not_scored": {
            "weather_delay_per_flight": _num(row.get("weather_delay_per_flight")),
            "weather_delay_percentile": _num(row.get("pct_weather_delay_per_flight")),
            "reason": "Weather delay is not addressable by terminal or airfield investment, so it is reported but not scored.",
        },
    }


# ---------------------------------------------------------------- KPIs
def long_haul(row: pd.Series, threshold_mi: int = C.LONG_HAUL_DEFAULT_MI) -> dict:
    ths = sorted(set(C.LONG_HAUL_THRESHOLDS_MI) | {threshold_mi}) if threshold_mi in C.LONG_HAUL_THRESHOLDS_MI else list(C.LONG_HAUL_THRESHOLDS_MI)
    by_th = {}
    for th in ths:
        by_th[th] = {
            "all_departures": _num(row.get(f"long_haul_share_{th}")),
            "passenger_aircraft": _num(row.get(f"long_haul_share_{th}_pax")),
            "freight_aircraft": _num(row.get(f"long_haul_share_{th}_freight")),
        }
    return {
        "code": row["code"],
        "requested_threshold_mi": threshold_mi,
        "threshold_available": threshold_mi in by_th,
        "share_by_threshold": by_th,
        "departures_total": _num(row.get("deps")),
        "avg_distance_mi": _num(row.get("avg_distance_mi")),
        "intl_share_deps": _num(row.get("intl_share_deps")),
        "freight_share_deps": _num(row.get("freight_share_deps")),
    }


def unmet_demand(row: pd.Series) -> dict:
    """Rule-based indicator list. Each driver has a value, a percentile and a verdict."""
    drivers = []

    def add(name, value, pct, fires, why):
        drivers.append({"indicator": name, "value": _num(value), "percentile": _num(pct),
                        "fires": bool(fires), "interpretation": why})

    lf = row.get("load_factor")
    add("load_factor", lf, row.get("pct_load_factor"), pd.notna(lf) and lf >= 0.85,
        "Seats are nearly full on scheduled passenger flights; airlines cannot add passengers without adding capacity.")
    gap = row.get("pax_growth_minus_seat_growth")
    add("pax_growth_minus_seat_growth", gap, None, pd.notna(gap) and gap > 0.01,
        "Passengers grew faster than seats offered; demand is outrunning supply." if pd.notna(gap)
        else "Needs the T-100 2024 file to compute seat growth.")
    d15 = row.get("dep_del15_rate")
    add("dep_del15_rate", d15, row.get("pct_dep_del15_rate"), pd.notna(row.get("pct_dep_del15_rate")) and row["pct_dep_del15_rate"] >= 0.75,
        "Departure delays in the top quartile of peers signal the airfield or gates are saturated.")
    add("taxi_out_mean", row.get("taxi_out_mean"), row.get("pct_taxi_out_mean"),
        pd.notna(row.get("pct_taxi_out_mean")) and row["pct_taxi_out_mean"] >= 0.75,
        "Long taxi-out times mean aircraft queue for runways.")
    add("cancel_rate", row.get("cancel_rate"), row.get("pct_cancel_rate"),
        pd.notna(row.get("pct_cancel_rate")) and row["pct_cancel_rate"] >= 0.75,
        "High cancellation rate removes flights that were sold.")
    add("deps_per_runway", row.get("deps_per_runway"), row.get("pct_deps_per_runway"),
        pd.notna(row.get("pct_deps_per_runway")) and row["pct_deps_per_runway"] >= 0.75,
        "Many departures per runway: little room to add flights without new runway capacity.")

    delay_mix = {k: _num(row.get(k)) for k in
                 ["nas_delay_per_flight", "weather_delay_per_flight", "late_aircraft_per_flight", "carrier_delay_per_flight"]}
    total = sum(v for v in delay_mix.values() if v is not None) or None
    delay_share = {k: (v / total if (total and v is not None) else None) for k, v in delay_mix.items()}
    addressable = None
    if total:
        addressable = (delay_mix["nas_delay_per_flight"] or 0) + (delay_mix["late_aircraft_per_flight"] or 0)
        addressable /= total

    fired = sum(d["fires"] for d in drivers)
    verdict = "strong" if fired >= 4 else "moderate" if fired >= 2 else "weak"
    return {
        "code": row["code"],
        "verdict": verdict,
        "indicators_fired": fired,
        "indicators": drivers,
        "delay_minutes_per_flight": delay_mix,
        "delay_share": delay_share,
        "addressable_delay_share": _num(addressable),
        "confidence": row.get("confidence"),
    }


CONGESTION_METRICS = ["dep_del15_rate", "taxi_out_mean", "nas_delay_per_flight", "late_aircraft_per_flight",
                      "weather_delay_per_flight", "cancel_rate", "peak_block_share", "deps_per_runway", "load_factor"]


def compare(scored: pd.DataFrame, codes: list[str]) -> dict:
    rows = scored.set_index("code").reindex([c.upper() for c in codes])
    metrics = {}
    for m in CONGESTION_METRICS + ["expansion_score", "demand_score", "strain_score", "pax_cagr_2y",
                                   enpl_col(scored), "deps", "runways_open", "ot_flights"]:
        metrics[m] = {c: {"value": _num(rows.loc[c].get(m)), "percentile": _num(rows.loc[c].get(f"pct_{m}"))}
                      for c in rows.index if c in rows.index}
    return {
        "codes": list(rows.index),
        "names": {c: rows.loc[c].get("name") for c in rows.index},
        "hub": {c: rows.loc[c].get("hub") for c in rows.index},
        "confidence": {c: rows.loc[c].get("confidence") for c in rows.index},
        "metrics": metrics,
    }


def _num(v):
    if v is None:
        return None
    try:
        if isinstance(v, (np.generic,)):
            v = v.item()
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        if isinstance(v, (int, float)):
            return round(v, 4) if isinstance(v, float) else v
        return v
    except Exception:
        return None
