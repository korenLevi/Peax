# Airport Investment Intelligence Agent: Design

## 1. Problem framing

The firm invests in US airport modernization and wants to find airports where added terminal or airfield capacity would be used. We do not observe airport finances, so "most profitable" is approximated by two questions that public data can answer:

1. Is demand pressing on the airport? (passengers growing, seats full)
2. Is the airport already strained by the capacity it has? (delays, taxi queues, departures per runway)

An airport that scores high on both is where new capacity is most likely to be absorbed. That is the whole idea; everything else is plumbing.

## 2. Data sources

| Source | What we take | Period | How it is used |
|---|---|---|---|
| FAA Commercial Service Enplanements (3 Excel files) | Enplanements per airport, hub class, state | CY2023 to CY2025 | Universe (402 primary airports), growth, scale |
| BTS T-100 Segment, All Carriers | Departures, seats, passengers, freight, distance, aircraft config, service class, domestic/international flag | 2025, plus 2024 for seat and departure growth | Load factor, long haul mix, freight share, departures per runway |
| BTS On-Time Reporting Carrier (12 monthly files, 7.0M flights) | DepDel15, TaxiOut, Cancelled, delay cause minutes, departure time block | 2025 | Congestion and delay mix |
| OurAirports | Coordinates, runways (open, length) | Snapshot 2026-10-09 | Runway counts, ICAO code, bounding box for live data |
| FAA NAS Status API (live) | Current ground stops, delay programs, closures | Now | Attached as `live_now` to `compare_airports` and `unmet_demand`, and used by `live_status`; never scored |
| OpenSky Network API (live) | Aircraft state vectors near the airport | Now | Live activity count, not scored |

ETL runs once (`etl/ontime_aggregate.py`, `etl/build_features.py`) and writes `data/processed/airport_features.csv`, one row per FAA primary airport with 60 columns. The agent reads only that small table, so a chat turn never touches the 3 GB of raw files.

## 3. Scoring methodology

### Expansion Opportunity Score (0 to 100)

```
expansion_score = 0.5 * demand_score + 0.5 * strain_score
```

Each component is a weighted mean of percentile ranks of its features within a peer group (default: all US primary airports; the user can switch to the filtered selection or a hub tier).

| Component | Feature | Weight | Why |
|---|---|---|---|
| Demand | `pax_cagr_2y` (FAA enplanements, 2-year CAGR) | 0.35 | Growth is the strongest signal that capacity will be used |
| Demand | `load_factor` (T-100 scheduled passenger service) | 0.30 | Full seats mean airlines cannot grow without adding flights |
| Demand | `seats_growth_yoy` (T-100, 2025 vs 2024) | 0.15 | Airlines adding seats is revealed demand |
| Demand | `log_enpl` (log10 of latest enplanements) | 0.20 | Scale guard so a 200K passenger airport with 40 percent growth does not top the list by itself |
| Strain | `dep_del15_rate` | 0.25 | Share of departures delayed 15+ minutes |
| Strain | `taxi_out_mean` | 0.25 | Minutes from gate to wheels up; direct queue signal |
| Strain | `nas_delay_per_flight` | 0.20 | Airport/airspace system delay minutes |
| Strain | `late_aircraft_per_flight` | 0.10 | Knock-on delay, partly a gate/turnaround constraint |
| Strain | `deps_per_runway` | 0.20 | Annual departures per open runway |

Weights are in `agent/config.py` and can be changed from the UI sidebar; the ranking recomputes deterministically.

### Deliberate exclusions

- **Weather delay** is reported but never scored. Terminal or taxiway investment does not change the weather. For SFO this matters: its delay mix is shown with an "addressable share" (NAS + late aircraft) so the analyst sees how much of the pain investment could remove.
- **Cancellations** are shown in comparisons but not scored, because they mix weather, crew and airline decisions.

### Confidence

| Level | Rule |
|---|---|
| high | 5,000+ On-Time flights, all sources present |
| medium | 1,000 to 5,000 On-Time flights, or the T-100 2024 file is missing (seat growth unknown) |
| low | fewer than 1,000 On-Time flights; delay features are dropped and strain uses only departures per runway |

Missing features are dropped and the remaining weights are renormalised, so an airport is never penalised for missing data; it is flagged instead.

### Other deterministic KPIs

- **Long haul share**: departures weighted share of segments at or above 1,500 / 2,500 / 3,000 miles, split into passenger and freight aircraft. The threshold is the single biggest driver of the answer (ANC: 49 percent at 1,500 mi, 31 percent at 3,000 mi), so all three are always returned.
- **Unmet demand**: six rule based indicators (load factor at or above 0.85, passengers outgrowing seats, delay rate, taxi out, cancellations and departures per runway in the top quartile) plus the delay cause mix. Verdict is strong / moderate / weak by the number of indicators that fire.
- **Congestion comparison**: side by side values with national percentiles.

## 4. Where AI is used, and where it is not

| Step | Who does it |
|---|---|
| Understand the question, pick tools and arguments (region, codes, thresholds) | Claude (`claude-opus-5-5` by default, configurable) |
| Compute every number, rank, percentile and verdict | Python (`agent/scoring.py`, `agent/tools.py`), unit tested |
| Explain the result, state assumptions and confidence, handle follow-ups | Claude, constrained by the system prompt to use only tool output |
| Live API calls | Python (`agent/live_apis.py`). FAA NAS status is attached automatically to congestion and unmet demand answers; OpenSky is called on "right now" questions. Results reach Claude as data |

The system prompt forbids numbers that do not come from a tool result. Every tool response carries `assumptions` and `coverage_notes`, and the UI shows the raw tool JSON under each answer so an analyst can audit the narrative against the data. Conversation history is kept client side and replayed each turn, which is what makes follow-ups like "and what about BDL?" work.

## 5. Key tradeoffs

| Decision | Alternative | Why we chose this |
|---|---|---|
| Precompute features once, chat reads a 400 row table | Query raw files per question | Sub-second tool calls, reproducible numbers, raw data stays out of git |
| Percentile ranks within a peer group | Absolute thresholds | Robust to outliers and units; the cost is that scores are relative and depend on the peer group, which the tool reports |
| Weighted additive score | Learned model | No ground truth for "profitable expansion" exists; a transparent formula that the analyst can tune beats a black box |
| Claude narrates, Python computes | Let the LLM read the table and reason | Removes arithmetic hallucination; the LLM still adds value by choosing the right lens and explaining |
| Rule based unmet demand indicators | LLM judgement | The "why" has to be auditable |
| Browser speech APIs for voice | Cloud speech services | No extra keys or cost; works in Chrome, which is enough for a demo |
| On-Time data despite its coverage gap | Skip delay data | It is the only public source of delay cause; the gap is surfaced as a coverage note and a confidence level |

## 6. Assumptions and limitations

- Profitability is a proxy. We have no airport financials, gate counts, land availability or capital plans.
- On-Time data covers large US carriers' domestic flights only. Cargo heavy airports such as ANC look calmer than they are; the tools say so.
- Runway counts from OurAirports are a weak proxy for airfield capacity; official FAA capacity benchmarks (ASPM) need an account and were not used.
- FAA uses its own location ids while BTS uses IATA codes. The ETL resolves them through OurAirports (for example IWA to AZA, GPI to FCA) and one manual override (DJT to PBI). Two tiny airports stay unmatched.
- Growth is measured over 2023 to 2025, a recovery period, so some growth reflects catch up rather than new demand.
- Live APIs are snapshots and are never part of the score. They are shown next to the historical analysis so the analyst sees today's conditions without the ranking changing from one hour to the next.

## 7. Next steps if this went beyond one day

FAA ASPM capacity benchmarks, gate counts from airport master plans, FAA CATS financial reports for an actual profitability proxy, and an evaluation set of analyst-graded answers to tune prompts and weights.
