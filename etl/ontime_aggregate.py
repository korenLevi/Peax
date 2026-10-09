"""Aggregate the 12 monthly BTS On-Time CSVs into one row per origin airport.

Run once: python etl/ontime_aggregate.py
Input:  data/raw/ontime/2025_MM.csv (110 columns each, ~250 MB)
Output: data/processed/ontime_by_airport.csv

Only the columns listed in USECOLS are read. The *Delay columns are empty
unless the arrival delay was 15 minutes or more, so empty is treated as 0.
"""
from __future__ import annotations

import glob
import os
import sys
import time

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(ROOT, "data", "raw", "ontime")
OUT_PATH = os.path.join(ROOT, "data", "processed", "ontime_by_airport.csv")

USECOLS = [
    "Year", "Month", "Origin", "Dest", "DepDel15", "TaxiOut", "Cancelled",
    "CarrierDelay", "WeatherDelay", "NASDelay", "LateAircraftDelay",
    "DepTimeBlk", "Distance",
]
DELAY_COLS = ["CarrierDelay", "WeatherDelay", "NASDelay", "LateAircraftDelay"]
TOP_BLOCKS = 3  # number of busiest hour blocks used for peak_block_share


def load_month(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, usecols=USECOLS, low_memory=False)
    df[DELAY_COLS] = df[DELAY_COLS].fillna(0.0)
    return df


def aggregate(df: pd.DataFrame) -> pd.DataFrame:
    """Pure function: flight-level frame -> one row per Origin."""
    flown = df[df["Cancelled"] == 0]
    g_all = df.groupby("Origin")
    g_flown = flown.groupby("Origin")

    out = pd.DataFrame({
        "ot_flights": g_all.size(),
        "ot_months": g_all["Month"].nunique(),
        "cancel_rate": g_all["Cancelled"].mean(),
        # DepDel15 is NaN for cancelled flights, so these are over flown flights.
        "dep_del15_rate": g_flown["DepDel15"].mean(),
        "taxi_out_mean": g_flown["TaxiOut"].mean(),
        "carrier_delay_per_flight": g_flown["CarrierDelay"].mean(),
        "weather_delay_per_flight": g_flown["WeatherDelay"].mean(),
        "nas_delay_per_flight": g_flown["NASDelay"].mean(),
        "late_aircraft_per_flight": g_flown["LateAircraftDelay"].mean(),
        "ot_avg_distance": g_all["Distance"].mean(),
    })

    # Share of scheduled departures that fall in the TOP_BLOCKS busiest hour blocks.
    blk = df.groupby(["Origin", "DepTimeBlk"]).size().rename("n").reset_index()
    blk = blk.sort_values(["Origin", "n"], ascending=[True, False])
    top = blk.groupby("Origin").head(TOP_BLOCKS).groupby("Origin")["n"].sum()
    out["peak_block_share"] = top / out["ot_flights"]

    return out.reset_index().rename(columns={"Origin": "code"})


def main() -> int:
    files = sorted(glob.glob(os.path.join(RAW_DIR, "2025_*.csv")))
    if len(files) != 12:
        print(f"expected 12 monthly files in {RAW_DIR}, found {len(files)}", file=sys.stderr)
        return 1

    frames = []
    t0 = time.time()
    for path in files:
        df = load_month(path)
        months = sorted(df["Month"].unique())
        print(f"{os.path.basename(path)}: {len(df):,} rows, Month={months}, {time.time() - t0:.0f}s")
        frames.append(df)

    full = pd.concat(frames, ignore_index=True)
    del frames
    print(f"total flights: {len(full):,}")

    out = aggregate(full)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    out.to_csv(OUT_PATH, index=False)
    print(f"wrote {OUT_PATH}: {len(out)} airports, {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
