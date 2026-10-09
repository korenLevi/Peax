"""Build one feature row per FAA primary airport from the raw datasets.

Run: python etl/build_features.py
Reads:  data/raw/faa/*.xlsx, data/raw/t100/t100_segment_{2025,2024}.zip,
        data/raw/ourairports/*.csv, data/processed/ontime_by_airport.csv
Writes: data/processed/airport_features.csv

All numbers the agent reports come from this table. Run ontime_aggregate.py first.
"""
from __future__ import annotations

import os
import re
import sys
import zipfile

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
PROCESSED = os.path.join(ROOT, "data", "processed")
OUT_PATH = os.path.join(PROCESSED, "airport_features.csv")

LONG_HAUL_THRESHOLDS_MI = (1500, 2500, 3000)
LONG_RUNWAY_FT = 7000

T100_USECOLS = [
    "DEPARTURES_PERFORMED", "SEATS", "PASSENGERS", "FREIGHT", "DISTANCE",
    "ORIGIN", "AIRCRAFT_CONFIG", "MONTH", "CLASS", "DATA_SOURCE",
]


# ---------------------------------------------------------------- FAA
def load_faa(path: str) -> tuple[pd.DataFrame, int]:
    """Return (frame, year). Year comes from the 'CY xx Enplanements' header."""
    df = pd.read_excel(path, sheet_name=0, dtype=str, keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    df = df[df["Rank"].str.strip() != ""]  # drops the summary rows at the bottom
    cur_col = [c for c in df.columns if re.fullmatch(r"CY \d{2} Enplanements", c)][0]
    year = 2000 + int(re.search(r"\d{2}", cur_col).group(0))
    out = pd.DataFrame({
        "code": df["Locid"].str.strip(),
        "name": df["Airport Name"].str.strip(),
        "city": df["City"].str.strip(),
        "state": df["ST"].str.strip(),
        "faa_region": df["RO"].str.strip(),
        "service_level": df["S/L"].str.strip(),
        "hub": df["Hub"].str.strip(),
        f"enpl_{year}": pd.to_numeric(df[cur_col], errors="coerce"),
    })
    return out, year


def build_faa() -> pd.DataFrame:
    frames = {}
    for fn in sorted(os.listdir(os.path.join(RAW, "faa"))):
        if fn.endswith(".xlsx"):
            df, year = load_faa(os.path.join(RAW, "faa", fn))
            frames[year] = df
            print(f"FAA {fn}: year {year}, {len(df)} rows")
    years = sorted(frames)
    latest = years[-1]
    base = frames[latest]
    base = base[base["service_level"] == "P"].copy()  # primary airports only
    for y in years[:-1]:
        base = base.merge(frames[y][["code", f"enpl_{y}"]], on="code", how="left")
    y0, y1, y2 = years[-3], years[-2], years[-1]
    base["pax_yoy"] = base[f"enpl_{y2}"] / base[f"enpl_{y1}"] - 1
    base["pax_cagr_2y"] = (base[f"enpl_{y2}"] / base[f"enpl_{y0}"]) ** 0.5 - 1
    base["faa_latest_year"] = latest
    return base


# ---------------------------------------------------------------- T-100
def read_t100(zip_path: str) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as z:
        name = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
        with z.open(name) as f:
            return pd.read_csv(f, usecols=T100_USECOLS)


def t100_features(t: pd.DataFrame, suffix: str = "") -> pd.DataFrame:
    """Pure function: T-100 segment rows -> one row per ORIGIN."""
    t = t[t["DEPARTURES_PERFORMED"] > 0].copy()
    t["intl"] = t["DATA_SOURCE"].str[0].eq("I")
    t["freight_cfg"] = t["AIRCRAFT_CONFIG"].eq(2)
    t["dep_miles"] = t["DEPARTURES_PERFORMED"] * t["DISTANCE"]

    g = t.groupby("ORIGIN")
    out = pd.DataFrame({
        "deps": g["DEPARTURES_PERFORMED"].sum(),
        "seats": g["SEATS"].sum(),
        "pax": g["PASSENGERS"].sum(),
        "freight_lbs": g["FREIGHT"].sum(),
        "avg_distance_mi": g["dep_miles"].sum() / g["DEPARTURES_PERFORMED"].sum(),
    })
    out["intl_share_deps"] = t[t["intl"]].groupby("ORIGIN")["DEPARTURES_PERFORMED"].sum() / out["deps"]
    out["freight_share_deps"] = t[t["freight_cfg"]].groupby("ORIGIN")["DEPARTURES_PERFORMED"].sum() / out["deps"]

    # Load factor only on scheduled passenger service in passenger-configured aircraft.
    sched_pax = t[(t["AIRCRAFT_CONFIG"] == 1) & (t["CLASS"] == "F")]
    gs = sched_pax.groupby("ORIGIN")
    out["load_factor"] = gs["PASSENGERS"].sum() / gs["SEATS"].sum()
    out["sched_pax_deps"] = gs["DEPARTURES_PERFORMED"].sum()

    for th in LONG_HAUL_THRESHOLDS_MI:
        lh = t[t["DISTANCE"] >= th]
        out[f"long_haul_share_{th}"] = lh.groupby("ORIGIN")["DEPARTURES_PERFORMED"].sum() / out["deps"]
        for label, mask in (("pax", ~t["freight_cfg"]), ("freight", t["freight_cfg"])):
            sub = t[mask]
            denom = sub.groupby("ORIGIN")["DEPARTURES_PERFORMED"].sum()
            num = sub[sub["DISTANCE"] >= th].groupby("ORIGIN")["DEPARTURES_PERFORMED"].sum()
            out[f"long_haul_share_{th}_{label}"] = num / denom

    monthly = t.groupby(["ORIGIN", "MONTH"])["DEPARTURES_PERFORMED"].sum()
    out["seasonality_peak_ratio"] = monthly.groupby("ORIGIN").max() / monthly.groupby("ORIGIN").mean()
    out["t100_months"] = monthly.groupby("ORIGIN").size()

    share_cols = [c for c in out.columns if "share" in c]
    out[share_cols] = out[share_cols].fillna(0.0)
    out = out.reset_index().rename(columns={"ORIGIN": "code"})
    if suffix:
        out = out.rename(columns={c: f"{c}{suffix}" for c in out.columns if c != "code"})
    return out


# ---------------------------------------------------------------- OurAirports
US_COUNTRIES = ["US", "PR", "VI", "GU", "MP", "AS"]
# FAA/OurAirports code -> code used in BTS files, where the two still disagree.
BTS_CODE_OVERRIDES = {"DJT": "PBI"}  # West Palm Beach was renamed; BTS kept PBI


def build_ourairports(faa_codes: pd.Series) -> pd.DataFrame:
    """One row per FAA code. FAA uses its own location ids (local_code in OurAirports),
    which differ from the IATA code BTS uses for a few airports (IWA vs AZA, GPI vs FCA).
    We resolve each FAA code to an OurAirports row and carry the IATA code as bts_code."""
    ap = pd.read_csv(os.path.join(RAW, "ourairports", "airports.csv"),
                     usecols=["ident", "type", "name", "latitude_deg", "longitude_deg",
                              "iso_country", "iso_region", "iata_code", "local_code"])
    ap = ap[ap["iso_country"].isin(US_COUNTRIES)]
    ap = ap[ap["type"].isin(["large_airport", "medium_airport", "small_airport"])]
    order = {"large_airport": 0, "medium_airport": 1, "small_airport": 2}
    ap = ap.assign(_o=ap["type"].map(order)).sort_values("_o")

    by_local = ap[ap["local_code"].notna()].drop_duplicates("local_code").set_index("local_code")
    by_iata = ap[ap["iata_code"].notna()].drop_duplicates("iata_code").set_index("iata_code")
    rows = []
    for code in faa_codes:
        if code in by_local.index:
            r = by_local.loc[code]
        elif code in by_iata.index:
            r = by_iata.loc[code]
        else:
            rows.append({"code": code, "bts_code": code})
            continue
        bts = r["iata_code"] if isinstance(r["iata_code"], str) else code
        rows.append({"code": code, "bts_code": bts, "ident": r["ident"],
                     "latitude_deg": r["latitude_deg"], "longitude_deg": r["longitude_deg"]})
    ap = pd.DataFrame(rows)
    ap["bts_code"] = ap["code"].map(BTS_CODE_OVERRIDES).fillna(ap["bts_code"])

    rw = pd.read_csv(os.path.join(RAW, "ourairports", "runways.csv"),
                     usecols=["airport_ident", "length_ft", "closed", "le_ident"])
    rw = rw[(rw["closed"] == 0) & rw["length_ft"].notna()]
    rg = rw.groupby("airport_ident")
    rw_feats = pd.DataFrame({
        "runways_open": rg.size(),
        "runways_7000ft_plus": rw[rw["length_ft"] >= LONG_RUNWAY_FT].groupby("airport_ident").size(),
        "longest_runway_ft": rg["length_ft"].max(),
    }).fillna({"runways_7000ft_plus": 0})

    out = ap.merge(rw_feats, left_on="ident", right_index=True, how="left")
    return pd.DataFrame({
        "code": out["code"],
        "bts_code": out["bts_code"],
        "icao": out["ident"],
        "lat": out["latitude_deg"],
        "lon": out["longitude_deg"],
        "runways_open": out["runways_open"],
        "runways_7000ft_plus": out["runways_7000ft_plus"],
        "longest_runway_ft": out["longest_runway_ft"],
    })


# ---------------------------------------------------------------- main
def main() -> int:
    faa = build_faa()
    print(f"FAA primary airports: {len(faa)}")

    oa = build_ourairports(faa["code"])
    df = faa.merge(oa, on="code", how="left")
    # BTS files are keyed by IATA code; FAA by its own location id. Join T-100/On-Time on bts_code.
    bts_key = lambda t: t.rename(columns={"code": "bts_code"})

    t25 = t100_features(read_t100(os.path.join(RAW, "t100", "t100_segment_2025.zip")))
    print(f"T-100 2025 origins: {len(t25)}")
    df = df.merge(bts_key(t25), on="bts_code", how="left")

    p24 = os.path.join(RAW, "t100", "t100_segment_2024.zip")
    df["has_t100_2024"] = os.path.exists(p24)
    if df["has_t100_2024"].iloc[0]:
        t24 = t100_features(read_t100(p24), suffix="_2024")[["code", "deps_2024", "seats_2024", "pax_2024"]]
        df = df.merge(bts_key(t24), on="bts_code", how="left")
        df["seats_growth_yoy"] = df["seats"] / df["seats_2024"] - 1
        df["deps_growth_yoy"] = df["deps"] / df["deps_2024"] - 1
        print(f"T-100 2024 origins: {len(t24)}")
    else:
        df["seats_growth_yoy"] = np.nan
        df["deps_growth_yoy"] = np.nan
        print("T-100 2024 not found: seat/departure growth left empty")

    ot_path = os.path.join(PROCESSED, "ontime_by_airport.csv")
    if os.path.exists(ot_path):
        ot = pd.read_csv(ot_path)
        df = df.merge(bts_key(ot), on="bts_code", how="left")
    else:
        print("WARNING: ontime_by_airport.csv missing, run etl/ontime_aggregate.py first")
        df["ot_flights"] = np.nan

    df["deps_per_runway"] = df["deps"] / df["runways_open"]
    df["pax_per_runway"] = df[f"enpl_{int(df['faa_latest_year'].iloc[0])}"] / df["runways_open"]
    df["pax_growth_minus_seat_growth"] = df["pax_yoy"] - df["seats_growth_yoy"]

    for src, col in [("T-100", "deps"), ("OurAirports", "runways_open"), ("On-Time", "ot_flights")]:
        missing = df.loc[df[col].isna(), "code"].tolist()
        print(f"{src}: {len(missing)} FAA airports unmatched {missing[:15]}{' ...' if len(missing) > 15 else ''}")

    df = df.sort_values(f"enpl_{int(df['faa_latest_year'].iloc[0])}", ascending=False)
    os.makedirs(PROCESSED, exist_ok=True)
    df.to_csv(OUT_PATH, index=False)
    print(f"wrote {OUT_PATH}: {len(df)} airports x {df.shape[1]} columns")
    return 0


if __name__ == "__main__":
    sys.exit(main())
