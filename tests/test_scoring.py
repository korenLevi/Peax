import numpy as np
import pandas as pd
import pytest

from agent import config as C
from agent import scoring


def make_df():
    rows = [
        # code, enpl, cagr, lf, seats_g, d15, taxi, nas, late, deps, runways, ot, weather
        ("AAA", 10_000_000, 0.10, 0.90, 0.05, 0.25, 22.0, 5.0, 7.0, 150_000, 2, 100_000, 0.4),
        ("BBB", 5_000_000, 0.03, 0.80, 0.02, 0.15, 15.0, 2.0, 4.0, 80_000, 4, 50_000, 0.5),
        ("CCC", 1_000_000, 0.00, 0.70, -0.01, 0.10, 11.0, 1.0, 3.0, 20_000, 3, 3_000, 0.3),
        ("DDD", 200_000, 0.20, 0.60, np.nan, 0.30, 25.0, 6.0, 8.0, 5_000, 1, 500, 0.9),
    ]
    df = pd.DataFrame(rows, columns=["code", "enpl_2025", "pax_cagr_2y", "load_factor", "seats_growth_yoy",
                                     "dep_del15_rate", "taxi_out_mean", "nas_delay_per_flight",
                                     "late_aircraft_per_flight", "deps", "runways_open", "ot_flights",
                                     "weather_delay_per_flight"])
    df["faa_latest_year"] = 2025
    df["deps_per_runway"] = df["deps"] / df["runways_open"]
    df["cancel_rate"] = 0.01
    df["name"] = df["code"]
    df["state"] = ["MA", "CA", "CT", "AK"]
    df["hub"] = ["L", "M", "S", "N"]
    df["pax_yoy"] = df["pax_cagr_2y"]
    df["pax_growth_minus_seat_growth"] = df["pax_yoy"] - df["seats_growth_yoy"]
    for th in C.LONG_HAUL_THRESHOLDS_MI:
        df[f"long_haul_share_{th}"] = 0.3
        df[f"long_haul_share_{th}_pax"] = 0.2
        df[f"long_haul_share_{th}_freight"] = 0.6
    df["carrier_delay_per_flight"] = 4.0
    df["peak_block_share"] = 0.25
    return df


def test_weights_sum_to_one():
    assert abs(sum(C.DEMAND_WEIGHTS.values()) - 1) < 1e-9
    assert abs(sum(C.STRAIN_WEIGHTS.values()) - 1) < 1e-9


def test_score_range_and_order():
    s = scoring.score_table(make_df())
    assert s["expansion_score"].between(0, 100).all()
    # AAA is the most strained and has strong demand; it must rank first.
    assert s.iloc[0]["code"] == "AAA"
    assert list(s["rank"]) == [1, 2, 3, 4]


def test_percentiles_within_peer_group():
    df = make_df()
    sub = df[df["code"].isin(["AAA", "BBB"])]
    s = scoring.score_table(sub)
    assert s.set_index("code").loc["AAA", "pct_load_factor"] == 1.0
    assert s.set_index("code").loc["BBB", "pct_load_factor"] == 0.5


def test_thin_ontime_coverage_drops_delay_metrics():
    s = scoring.score_table(make_df()).set_index("code")
    assert s.loc["DDD", "confidence"] == "low"
    assert np.isnan(s.loc["DDD", "pct_dep_del15_rate"])
    # strain still defined from departures per runway alone
    assert not np.isnan(s.loc["DDD", "strain_score"])
    assert s.loc["CCC", "confidence"] == "medium"
    assert s.loc["AAA", "confidence"] == "high"


def test_weather_not_in_score():
    df = make_df()
    base = scoring.score_table(df).set_index("code")["expansion_score"]
    df2 = df.copy()
    df2["weather_delay_per_flight"] *= 10
    again = scoring.score_table(df2).set_index("code")["expansion_score"]
    pd.testing.assert_series_equal(base, again)


def test_more_strain_raises_score():
    df = make_df()
    df2 = df.copy()
    df2.loc[df2["code"] == "BBB", ["dep_del15_rate", "taxi_out_mean", "nas_delay_per_flight"]] = [0.40, 30.0, 9.0]
    before = scoring.score_table(df).set_index("code").loc["BBB", "expansion_score"]
    after = scoring.score_table(df2).set_index("code").loc["BBB", "expansion_score"]
    assert after > before


def test_unmet_demand_rules():
    s = scoring.score_table(make_df()).set_index("code")
    r = s.loc["AAA"].copy()
    r["code"] = "AAA"
    out = scoring.unmet_demand(r)
    fired = {d["indicator"] for d in out["indicators"] if d["fires"]}
    assert "load_factor" in fired and "pax_growth_minus_seat_growth" in fired
    assert out["verdict"] in {"moderate", "strong"}
    assert abs(sum(v for v in out["delay_share"].values() if v) - 1) < 1e-6


def test_long_haul_thresholds():
    df = make_df()
    r = df.iloc[0]
    out = scoring.long_haul(r, 2500)
    assert out["threshold_available"]
    assert set(out["share_by_threshold"]) == set(C.LONG_HAUL_THRESHOLDS_MI)
    assert out["share_by_threshold"][2500]["freight_aircraft"] == 0.6
    out2 = scoring.long_haul(r, 9999)
    assert not out2["threshold_available"]


def test_compare_shape():
    s = scoring.score_table(make_df())
    out = scoring.compare(s, ["aaa", "BBB"])
    assert out["codes"] == ["AAA", "BBB"]
    assert out["metrics"]["taxi_out_mean"]["AAA"]["value"] == 22.0
    assert out["metrics"]["taxi_out_mean"]["AAA"]["percentile"] is not None
