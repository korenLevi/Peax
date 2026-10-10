# Peax: Airport Investment Intelligence Agent

A chat agent (text or voice) that helps analysts find US airports where expansion would pay off. Claude understands the question and explains the answer; every number comes from deterministic, tested Python over public FAA and BTS data.

**More:** [Design document](docs/DESIGN.md) · [Real example answers](docs/EXAMPLES.md) · [Data notes](data/README.md)

## The idea

There is no public data on airport profits, so the agent answers the closest question public data can: **where would new capacity actually be used?** Two signals have to be present together:

- **Demand:** passengers are growing and planes are full
- **Strain:** flights are delayed, aircraft queue for the runway, runways are heavily used

Each of the 402 US primary airports gets an **Expansion Opportunity Score** (0 to 100), half demand and half strain. Every input is a percentile rank against all other airports. Weather delay is shown but never scored, because investment cannot fix it.

## The four questions

| Question | Answer (short) |
|---|---|
| New England terminal expansion candidates? | **BOS** leads: highest strain in the region, high confidence. **PWM** and **PVD** are the demand-led cases. |
| LAX vs Santa Ana congestion? | Near-identical scores. LAX runways are among the busiest in the US; SNA has slightly worse delays. |
| Long haul share out of Anchorage? | **43%** at 2,500 miles, mostly cargo (68% of freighters vs 12% of passenger flights). |
| Unmet demand at SFO, and why? | **Moderate.** The bottleneck is the airfield (runway use, taxi-out), not seats; weather is only 3% of delay. |

## How it works

```
question -> Claude picks one of 7 tools -> Python computes from a precomputed 402-airport table
                                           + live FAA delays / OpenSky aircraft (public APIs)
         <- Claude explains, using only the tool output (numbers, assumptions, confidence)
```

- **Deterministic:** Claude never calculates. The score, percentiles and verdicts live in `agent/scoring.py` and are unit tested.
- **Transparent:** every answer can expand to show the raw tool output. Scoring weights are adjustable with sliders.
- **Honest about uncertainty:** each airport has a confidence level based on data coverage, and every tool result lists its assumptions.
- **Live context:** current FAA delay programs appear next to congestion answers, but never change a score.

## Limitations

- The score is a proxy for profitability. Financials, gate counts and land availability are not in public data.
- Delay data covers only the large US airlines' domestic flights, so cargo-heavy airports such as ANC look less congested than they are.
- Scores are relative, so a small, fast-growing airport can rank high. The agent always shows airport size next to the score.

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # add ANTHROPIC_API_KEY (OpenSky keys optional)

streamlit run app.py              # chat UI (voice works in Chrome)
python -m agent.cli --examples    # the four questions in the terminal
pytest
```

The processed data is in the repo, so no download is needed. To rebuild it from raw files, see [data/README.md](data/README.md).
