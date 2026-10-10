# Peax: Airport Investment Intelligence Agent

A chat agent that helps investment analysts find US airports where terminal or airfield expansion is most likely to pay off. You ask it questions in plain English (or by voice). It answers with rankings, comparisons and explanations. Every number in those answers is computed by deterministic, unit-tested Python over public FAA and BTS data. Claude decides which analysis to run and explains the result.

- **Design document** (scoring methodology, tradeoffs, where AI is used): [docs/DESIGN.md](docs/DESIGN.md)
- **Real example answers** to the four assignment questions, plus a follow-up conversation: [docs/EXAMPLES.md](docs/EXAMPLES.md)
- **Data sources and ETL notes**: [data/README.md](data/README.md)

## The approach in one paragraph

"Most profitable renovation" cannot be measured directly: there is no public data on airport finances, gate counts or terminal size. So the agent answers a question public data *can* answer: **where would new capacity actually be used?** That is where two things are true at once. **Demand** is pressing: passengers are growing and planes are full. **Strain** is visible: departures are delayed, aircraft queue for the runway, and each runway handles many departures. Each airport gets an **Expansion Opportunity Score** (0 to 100), 50% demand and 50% strain. Each half is built from percentile ranks against all 402 US primary airports. The formula is transparent, the weights can be tuned in the UI, and the agent says plainly that the score is a proxy for profitability, not a measure of it.

## How the assignment requirements are met

| Requirement | How | Where |
|---|---|---|
| Use public APIs to gather aviation data | Two live public APIs are called at question time. FAA NAS Status gives current ground stops and delay programs; it is attached automatically to congestion and unmet demand answers. OpenSky Network counts aircraft near an airport right now. The historical base is public BTS, FAA and OurAirports data. | `agent/live_apis.py`, `etl/` |
| Rank or compare airports with a defined KPI | Expansion Opportunity Score, plus long haul share, unmet demand indicators and a congestion comparison | `agent/scoring.py` |
| Deterministic logic, not only LLM output | Claude never computes. It picks one of 7 tools; Python returns the numbers as JSON; Claude narrates only what the JSON contains. | `agent/tools.py`, `tests/` |
| Explain its reasoning clearly | Every score comes with its components, raw values and percentiles. Delays are split into causes investment can fix (airspace system, late aircraft) and causes it cannot (weather). | `agent/scoring.py`, `agent/prompts.py` |
| Conversational follow-up | Full conversation history is replayed each turn, so "and what about Bradley?" works | `agent/agent.py`, [EXAMPLES Part 2](docs/EXAMPLES.md#part-2-follow-up-conversation) |
| Chat interface (voice is a bonus) | Streamlit chat with speech input and read-aloud output (browser speech APIs, no extra keys) | `app.py` |
| Communicate assumptions, uncertainty and scope | Every tool result carries `assumptions` and `coverage_notes`. Every airport gets a confidence level (high, medium or low) based on data coverage. The UI shows the raw tool output under each answer. | `agent/tools.py`, `app.py` |
| Design document | Scoring methodology, key tradeoffs, where and how AI is used | [docs/DESIGN.md](docs/DESIGN.md) |

## The four assignment questions

Short versions of the agent's real answers. The full answers are in [docs/EXAMPLES.md](docs/EXAMPLES.md).

| Question | Tool | Headline answer |
|---|---|---|
| Which airports in New England are strong candidates for terminal expansion? | `rank_airports` | **BOS** is the lead candidate: score 74.2, high confidence, and the highest strain in the region (31,956 departures per runway, 21.2 min average taxi-out). **PWM** and **PVD** are the demand-led terminal cases. **BGR** ranks #1 (75.7), but the agent flags it as small (437K passengers). |
| Compare LA and Santa Ana airport congestion levels. | `compare_airports` | Almost identical scores (53.6 each). **LAX**'s runways are among the busiest in the US (98.5th percentile for departures per runway). **SNA** has slightly worse delay rates. Passenger numbers fell at both over two years. |
| What is the percentage of long haul flights out of Anchorage airport? | `long_haul_share` | **43.2%** of departures at a 2,500 mile threshold (31% to 49% depending on the threshold). It is mostly cargo: 68.4% of freighter departures are long haul, against 11.5% of passenger departures. |
| What is the unmet flight demand in SFO airport and why? | `unmet_demand` | **Moderate** (2 of 6 indicators). The constraint is the airfield, not seats: departures per runway is at the 96th percentile and taxi-out at the 91st. Seats grew faster than passengers (5.9% vs 4.7%), so travelers are not being turned away. About 67% of delay minutes come from causes added capacity could reduce; weather is only 3%. |

## Architecture

```
 Raw public data (3 GB)            ETL, run once                     One table
 FAA, BTS T-100, BTS On-Time,  ->  etl/ontime_aggregate.py     ->  data/processed/airport_features.csv
 OurAirports                       etl/build_features.py            402 airports x 60 features (committed)

 User question  ->  Claude (agent/agent.py)  ->  picks a tool  ->  Python computes (agent/scoring.py, agent/tools.py)
                                                                    + live FAA / OpenSky (agent/live_apis.py)
                <-  Claude explains, using only the tool JSON   <-  numbers, assumptions, coverage notes
```

| Step | Done by |
|---|---|
| Understand the question, choose the tool and its arguments | Claude |
| Every number, percentile, rank and verdict | Python (deterministic, unit tested) |
| Live API calls | Python |
| Explanation, caveats, follow-up handling | Claude, limited by the system prompt to the tool output |

### The 7 tools

| Tool | Answers |
|---|---|
| `rank_airports` | Which airports in a region, state or hub tier are the best candidates? |
| `compare_airports` | How do these 2 to 6 airports compare on congestion and demand? (adds live FAA status) |
| `airport_profile` | Everything about one airport, with its score breakdown |
| `long_haul_share` | What share of departures is long haul, at 1,500 / 2,500 / 3,000 miles, passenger vs freight? |
| `unmet_demand` | Is there unmet demand, and why? Rule based indicators plus the delay cause mix (adds live FAA status) |
| `live_status` | What is happening at this airport right now? (FAA NAS Status and OpenSky) |
| `explain_methodology` | How is the score built? |

## Data sources

| Source | What it gives | Period |
|---|---|---|
| FAA Commercial Service Enplanements | Passengers boarded per airport, hub size, state | 2023 to 2025 |
| BTS T-100 Segment (All Carriers) | Departures, seats, passengers, freight and distance per route and month, including cargo and foreign carriers | 2024 and 2025 |
| BTS On-Time Reporting Carrier | Every domestic flight of the large US airlines: delays, delay causes, taxi-out time, cancellations (7.0M flights) | 2025 |
| OurAirports | Coordinates and runways (count, length) | Snapshot Oct 2026 |
| FAA NAS Status API (live) | Current ground stops, delay programs, closures | Now |
| OpenSky Network API (live) | Aircraft currently near the airport | Now |

## Main assumptions and limitations

- **Profitability is a proxy.** The score shows where capacity would be used, not what it would earn. Financials, gate counts, terminal size and land availability are not in any public dataset used here.
- **On-Time data covers only large US airlines' domestic flights.** It leaves out cargo and foreign carriers, so delay metrics understate activity at cargo-heavy airports such as ANC. The tools say so in their coverage notes.
- **Scores are relative.** They are percentiles against other airports, so a small, fast-growing airport can rank high. The agent always shows hub tier and passenger volume next to the score.
- **Weather is reported but never scored**, because investment cannot fix it.
- **Live data is context only.** It is shown next to the analysis but never changes a score, so rankings are reproducible.
- **2023 to 2025 was a recovery period**, so some growth is catch-up rather than new demand.

## Setup

Tested on Python 3.9 (macOS). Dependencies are pinned in `requirements.txt`.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`:

| Variable | Needed for | If missing |
|---|---|---|
| `ANTHROPIC_API_KEY` | The chat agent | The chat cannot answer. Tools still run directly with `--tool` (see below). |
| `OPENSKY_CLIENT_ID`, `OPENSKY_CLIENT_SECRET` | The OpenSky part of `live_status` (free account at opensky-network.org, API client credentials) | That one call returns an error message; everything else, including live FAA status, still works. |
| `PEAX_MODEL` (optional) | Choosing the Claude model | Defaults to `claude-opus-5-5`. The model can also be changed in the app sidebar. |

`data/processed/` is committed, so the app runs without the 3 GB of raw files. You only need `data/raw/` to rebuild the features (sources in [data/README.md](data/README.md)):

```bash
python etl/ontime_aggregate.py    # 12 monthly On-Time CSVs -> data/processed/ontime_by_airport.csv
python etl/build_features.py      # everything -> data/processed/airport_features.csv
```

## Run

```bash
streamlit run app.py              # chat UI
python -m agent.cli --examples    # the four assignment questions in the terminal
python -m agent.cli "Compare BOS and BDL congestion"
python -m agent.cli --tool rank_airports '{"region": "new england", "top_n": 5}'   # one tool, no LLM, no API key
pytest                            # unit tests: scoring on synthetic data, tools with the live API stubbed
```

In the app:

- Ask a question, or click one of the example questions in the sidebar.
- Open **Data & assumptions** under any answer to see the exact tool calls and the JSON they returned.
- Use the **scoring weight sliders** in the sidebar to change the demand/strain balance or component weights. Rankings recompute immediately.
- Click **🎤 Speak** to ask by voice, and turn on **Read answers aloud** to hear the answer. Voice uses the browser's speech APIs and works in Chrome.

## Project layout

```
app.py                 Streamlit chat UI with voice in and out
agent/config.py        model, scoring weights, thresholds, region definitions
agent/scoring.py       deterministic KPIs and the Expansion Opportunity Score
agent/tools.py         the 7 tools: schemas for Claude and their Python implementations
agent/live_apis.py     FAA NAS Status and OpenSky clients (cached, never raise)
agent/prompts.py       system prompt
agent/agent.py         Claude tool-use loop with conversation history
agent/cli.py           terminal entry point
etl/                   raw data -> data/processed/
tests/                 scoring tests on synthetic data, tool tests with the live API stubbed
docs/DESIGN.md         methodology, tradeoffs, where AI is used
docs/EXAMPLES.md       real transcripts of the four assignment questions and a follow-up conversation
data/README.md         every dataset: source, period, row count, columns, ETL gotchas
```
