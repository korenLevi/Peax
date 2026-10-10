# Peax: Airport Investment Intelligence Agent

An AI agent that helps analysts find US airports where terminal or airfield expansion would be most used. Deterministic scoring over FAA, BTS and OurAirports data; Claude turns questions into tool calls and explains the results. Design notes: [docs/DESIGN.md](docs/DESIGN.md). Example answers: [docs/EXAMPLES.md](docs/EXAMPLES.md). Data notes: [data/README.md](data/README.md).

## Setup

Tested on Python 3.9 (macOS). Dependencies are pinned in `requirements.txt`.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in ANTHROPIC_API_KEY, OPENSKY_CLIENT_ID, OPENSKY_CLIENT_SECRET
```

Raw data goes in `data/raw/` (see `data/README.md` for sources). `data/processed/` is committed, so the chat works without the raw files.

## Build features (only when raw data changes)

```bash
python etl/ontime_aggregate.py    # 12 monthly On-Time CSVs -> data/processed/ontime_by_airport.csv
python etl/build_features.py      # everything -> data/processed/airport_features.csv
```

## Run

```bash
streamlit run app.py              # chat UI with voice in/out (Chrome)
python -m agent.cli --examples    # the four assignment questions in the terminal
python -m agent.cli "Compare BOS and BDL congestion"
python -m agent.cli --tool rank_airports '{"region": "new england", "top_n": 5}'   # a tool without the LLM
pytest                            # unit tests (scoring + tools, no network)
```

## Layout

```
app.py                 Streamlit chat + voice
agent/config.py        model, weights, thresholds, regions
agent/scoring.py       deterministic KPIs and Expansion Opportunity Score
agent/tools.py         tool schemas + implementations (rank, profile, compare, long haul, unmet demand, live status)
agent/live_apis.py     FAA NAS Status and OpenSky
agent/agent.py         Claude tool-use loop with conversation history
agent/cli.py           terminal entry point
etl/                   raw -> processed
tests/                 scoring tests on synthetic data, tool tests with the live API stubbed
docs/DESIGN.md         methodology, tradeoffs, where AI is used
docs/EXAMPLES.md       real transcripts of the four assignment questions and a follow-up conversation
```
