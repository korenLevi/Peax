"""Paths, model, and scoring constants shared by the ETL outputs and the agent."""
from __future__ import annotations

import os

from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT, ".env"))

FEATURES_PATH = os.path.join(ROOT, "data", "processed", "airport_features.csv")

MODEL = os.environ.get("PEAX_MODEL", "claude-opus-5-5")
MAX_TOOL_ROUNDS = 8

# Scoring weights. Each group sums to 1. Score = DEMAND_SHARE * demand + (1 - DEMAND_SHARE) * strain.
DEMAND_SHARE = 0.5
DEMAND_WEIGHTS = {
    "pax_cagr_2y": 0.35,        # FAA enplanement growth, 2-year CAGR
    "load_factor": 0.30,        # T-100 scheduled passenger load factor
    "seats_growth_yoy": 0.15,   # T-100 seat growth (NaN when 2024 file is missing)
    "log_enpl": 0.20,           # scale: log of latest enplanements
}
STRAIN_WEIGHTS = {
    "dep_del15_rate": 0.25,          # share of departures delayed 15+ min
    "taxi_out_mean": 0.25,           # minutes, airfield congestion
    "nas_delay_per_flight": 0.20,    # NAS (airspace/airport system) delay minutes
    "late_aircraft_per_flight": 0.10,
    "deps_per_runway": 0.20,         # annual departures per open runway
}

# Confidence thresholds on On-Time flight counts.
OT_HIGH = 5000
OT_LOW = 1000

LONG_HAUL_DEFAULT_MI = 2500
LONG_HAUL_THRESHOLDS_MI = (1500, 2500, 3000)

REGIONS = {
    "new england": ["CT", "ME", "MA", "NH", "RI", "VT"],
    "mid-atlantic": ["NY", "NJ", "PA", "DE", "MD", "DC"],
    "southeast": ["VA", "WV", "NC", "SC", "GA", "FL", "KY", "TN", "AL", "MS"],
    "midwest": ["OH", "MI", "IN", "IL", "WI", "MN", "IA", "MO", "ND", "SD", "NE", "KS"],
    "southwest": ["TX", "OK", "AR", "LA", "NM", "AZ"],
    "mountain west": ["CO", "UT", "WY", "MT", "ID", "NV"],
    "pacific": ["CA", "OR", "WA"],
    "alaska": ["AK"],
    "hawaii": ["HI"],
    "territories": ["PR", "VI", "GU", "AS", "MP"],
}

HUB_LABELS = {"L": "Large hub", "M": "Medium hub", "S": "Small hub", "N": "Nonhub"}
