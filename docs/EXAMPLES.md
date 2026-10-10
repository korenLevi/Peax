# Example answers

Real output from the agent, captured on 2026-10-10 12:03 UTC with the default model (`claude-opus-5-5`) and default scoring weights. Nothing below was edited except that headings inside answers were demoted so they nest under each question. Each answer lists the deterministic tools Claude called; every number in the answer comes from those tool results.

Commands used:

```bash
python -m agent.cli --examples      # part 1, a fresh conversation per question
```

Part 2 is one continuous conversation, to show follow-up handling and the live APIs.

Answers that call `compare_airports` or `unmet_demand` end with a short live FAA NAS status line ("right now"). That line comes from the public FAA API at request time and is never part of the score, so it will differ on every run. The scored numbers do not change between runs.

## Part 1: the four assignment questions

---

### Q: Which airports in New England are strong candidates for terminal expansion?

**Tool calls:** `rank_airports({"region": "new england", "top_n": 10})`

**Short answer:** Boston Logan (BOS) is the strongest candidate when you factor in scale. It ranks #2 in New England with a score of 74.2 and high confidence, and it shows the most capacity strain in the region. Burlington (BTV) and Portland, ME (PWM) are the best small-hub candidates with high confidence. The #1 airport, Bangor (BGR), is small (437K enplanements). Tweed/New Haven (HVN) is growing fastest, but its score has low confidence.

**New England ranking** (percentiles compared with all US primary airports; 16 airports in the region; top 10 shown)

| # | Airport | Hub tier | 2025 enplanements | Score | Demand / Strain | 2-yr pax growth (CAGR) | Load factor | Dep. delay ≥15 min | Taxi-out (min) | Deps per runway | Confidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | BGR Bangor Intl | Nonhub | 437,108 | 75.7 | 73.6 / 77.8 | 10.6% | 80.2% | 21.0% | 18.5 | 6,150 (1 rwy) | Medium |
| 2 | BOS Boston Logan | Large | 21,021,153 | 74.2 | 63.8 / 84.6 | 2.6% | 81.7% | 22.7% | 21.2 | 31,956 (6 rwys) | High |
| 3 | HVN Tweed/New Haven | Small | 737,789 | 73.2 | 75.5 / 71.0 | 22.7% | 76.0% | n/a | n/a | 6,095 (1 rwy) | **Low** |
| 4 | BTV Burlington | Small | 709,881 | 71.4 | 63.8 / 79.0 | 4.5% | 81.3% | 20.7% | 21.7 | 4,974 (2 rwys) | High |
| 5 | PWM Portland Jetport | Small | 1,287,041 | 66.8 | 74.3 / 59.2 | 7.5% | 82.4% | 18.2% | 16.5 | 7,419 (2 rwys) | High |
| 6 | PVD T.F. Green | Small | 2,117,401 | 63.7 | 71.2 / 56.1 | 10.5% | 78.1% | 19.5% | 14.8 | 11,104 (2 rwys) | High |
| 7 | ACK Nantucket | Nonhub | 152,789 | 61.0 | 40.3 / 81.7 | 5.4% | 63.7% | 22.9% | 19.5 | 5,987 | Medium |
| 8 | BID Block Island | Nonhub | 19,914 | 58.5 | 48.6 / 68.5 | 14.5% | 46.3% | n/a | n/a | 5,414 | Low |
| 9 | BDL Bradley | Medium | 3,283,397 | 58.1 | 60.5 / 55.7 | 2.6% | 80.4% | 18.6% | 15.2 | 15,789 | High |
| 10 | HYA Cape Cod Gateway | Nonhub | 33,895 | 54.7 | 54.4 / 55.0 | 39.3% | 43.2% | 22.3% | 18.7 | 3,074 | Low |

**What drives each score**
- **BOS:** Strain drives the score. It has New England's longest taxi-outs except BTV, the highest departures per runway by far, and a high delay rate. But passenger growth is slow (2.6%), so the case rests on congestion more than growth. Long taxi-outs and heavy runway use point mostly to **airfield** constraints (taxiways, runway use), not only the terminal.
- **BTV:** Both demand and strain are solid. Taxi-out is the longest in the region and the load factor is high (81.3%).
- **PWM and PVD:** Demand drives these scores. PWM has the region's highest load factor (82.4%), and PVD grew 10.5% a year. Both have moderate strain. This pattern fits **terminal capacity added ahead of demand** better than a fix for current congestion.
- **BGR:** Grew 10.6% a year with strong strain. Note that departures per runway are measured against a single runway. The airport is small in absolute terms.
- **HVN:** Grew the fastest (22.7%), but there is no on-time data for it. Its strain score uses only departures per runway, so it is less reliable.
- **ACK, BID and HYA:** These are small, seasonal nonhubs with low load factors. Their rank comes mainly from strain or growth on a tiny base, so they are weak candidates for terminal investment.

**Assumptions and caveats**
- The score is a proxy: half demand pressure, half capacity strain. Profitability is not observed. The score also doesn't separate terminal from airfield needs. It has no gate counts, terminal floor area or curb data, so terminal sizing isn't available. Load factor and passenger growth are the closest demand-side proxies for terminal pressure.
- Weather delay is left out of the score because investment can't fix it.
- Low confidence means fewer than 1,000 on-time flights in the data. For those airports (HVN, BID, HYA), strain uses only departures per runway.
- Delay data (BTS On-Time) covers only large US carriers' domestic flights. That understates activity at airports with a lot of international or cargo traffic, including BOS.
- Data period: FAA enplanements for 2023–2025, and BTS T-100 and On-Time data for 2025.
- This ranking didn't include live FAA status. I can pull it if you want a current-conditions check.

**Possible next steps:** I can re-run the ranking with a minimum enplanements filter (for example 1M) or limited to small, medium and large hubs. I can also check unmet demand for BOS, PVD or PWM to see whether their delays come from capacity or from weather and airline causes.

---

### Q: Compare LA and Santa Ana airport congestion levels.

**Tool calls:** `compare_airports({"codes": ["LAX", "SNA"]})`

#### LAX vs SNA congestion comparison

LAX (Los Angeles International) and SNA (John Wayne/Orange County) have almost the same overall score. LAX is about 6.6 times larger by passengers, and its runways are among the busiest in the country. Delays at both airports are moderate, and SNA's delay figures are slightly worse. At both, the main pressure point is how hard the runways are used, not the delay rates. I took "LA" to mean LAX. Tell me if you meant Burbank, Long Beach or Ontario instead.

#### Scale and score (2025, high confidence for both)

| | LAX | SNA |
|---|---|---|
| Hub tier | Large (L) | Medium (M) |
| Enplanements 2025 | 36,497,303 | 5,521,729 |
| Departures | 273,957 | 51,256 |
| Open runways | 4 | 2 |
| Expansion score | 53.56 | 53.60 |
| Demand score | 52.26 | 51.94 |
| Capacity strain score | 54.86 | 55.27 |
| 2-year passenger annual growth rate | −5.6% (6th pct) | −1.6% (13th pct) |

#### Congestion metrics
Percentiles compare each airport with all US primary airports. A higher percentile means more strain.

| Metric | LAX | SNA | Busier on this metric |
|---|---|---|---|
| Departures per runway | 68,489 (98.5th) | 25,628 (91st) | LAX |
| Load factor | 81.6% (85th) | 79.9% (73rd) | LAX |
| Mean taxi-out time (min) | 17.7 (66th) | 16.1 (43rd) | LAX |
| Departures delayed 15+ min | 18.1% (36th) | 19.2% (48th) | SNA |
| FAA system (NAS) delay per flight (min) | 2.64 (34th) | 3.29 (48th) | SNA |
| Delay from late-arriving aircraft per flight (min) | 4.53 (29th) | 5.67 (47th) | SNA |
| Weather delay per flight (min) | 0.36 (13th) | 0.64 (21st) | SNA |
| Cancellation rate | 0.69% (15th) | 1.05% (29th) | SNA |
| Share of flights in the peak time block | 24.4% (4th) | 25.2% (6th) | Both low |

#### What drives this
- **LAX:** The strain comes from the airfield. It has the highest runway use of the pair, the longest taxi-out times and the fuller planes. Taxiway, apron and gate investment can address this kind of constraint. Delays and cancellations are below the median, though.
- **SNA:** Delays are worse than at LAX but still near the median (around the 47th–48th percentile). Its runway use is also high (91st percentile) given it has only two runways.
- **Both:** Weather delay is low at both airports, so weather is not a main constraint. Flights are spread fairly evenly through the day, so neither has a sharp peak-hour problem.
- **Demand is the weak point:** Passenger numbers fell over two years at both airports, LAX more sharply. This holds back both scores, even though the strain readings are high.

#### Caveats
- **Proxy only:** The score measures demand pressure × capacity strain. It does not observe profitability.
- **Delay data coverage:** Delay figures come from BTS On-Time data, which covers only large US carriers' domestic flights. This likely understates activity at LAX, which has heavy international and cargo traffic. Load factor and departures come from T-100 data, which covers all carriers.
- **Not in the data:** Regulatory limits such as noise or curfew caps, gate counts and land availability aren't included. These matter a lot for whether either airport can physically expand.

**Live FAA status (separate from the scored analysis above):** SNA has no FAA delay program active right now. LAX shows a notice closing the airport to non-scheduled transient general aviation (private and charter flights) unless prior permission is arranged. This is not a delay program for airline flights. Its listed dates (May 27–28) don't match the October update time, so it may be a stale entry.

I can also run `long_haul_share` or `unmet_demand` on either airport, or rank all Southern California airports with a minimum enplanements filter.

---

### Q: What is the percentage of long haul flights out of Anchorage airport?

**Tool calls:** `long_haul_share({"code": "ANC", "threshold_mi": 2500})`

**43.2% of departures from Ted Stevens Anchorage International (ANC) are long haul, using a 2,500-mile threshold.** Most of that comes from cargo. 68.4% of freighter departures are long haul, compared with 11.5% of passenger departures.

**Share of long-haul departures by threshold (BTS T-100, 2025, all carriers including cargo and international)**

| Threshold (great-circle segment distance) | All departures | Passenger aircraft | Freight aircraft |
|---|---|---|---|
| ≥ 1,500 mi | 49.1% | 19.3% | 72.9% |
| **≥ 2,500 mi** | **43.2%** | **11.5%** | **68.4%** |
| ≥ 3,000 mi | 31.0% | 4.3% | 52.4% |

**Context**
- Total departures: 87,988
- Average segment distance: 1,915.5 mi
- Freight share of departures: 55.7%
- International share of departures: 16.0%

**Why the answer depends on these choices**
- **Threshold:** I used 2,500 miles. At 1,500 miles the share rises to about 49%, and at 3,000 miles it falls to about 31%.
- **Passenger vs. freight:** The overall figure is mostly cargo. If you only care about passenger flights, the long-haul share is about 12% at 2,500 miles.
- **How shares are counted:** Shares are weighted by departures performed, not by seats or tonnage.

**Data notes**
- T-100 covers all carriers, including cargo and international, so it captures ANC's freighter traffic. Delay metrics for ANC come from a different source (BTS On-Time), which covers only large US carriers' domestic passenger flights. That source would understate activity at a cargo-heavy airport like ANC.
- This tool doesn't return a confidence level or live FAA status. I can pull those with `airport_profile` or `live_status`. Running `unmet_demand` would show whether ANC's capacity is under strain, if you're considering it for investment.

---

### Q: What is the unmet flight demand in SFO airport and why?

**Tool calls:** `unmet_demand({"code": "SFO"})`, `airport_profile({"code": "SFO"})`

**SFO (San Francisco International) has moderate unmet demand: 2 of 6 indicators fired. Confidence is high.** The pressure is on the airfield, not on seats. Aircraft wait a long time to take off, and each runway handles a very high number of departures. Seats are fairly full, but airlines have been adding seats faster than passengers have grown, so travelers aren't being turned away. This is unmet demand inferred from indicators. It is not measured directly.

**Indicators (2025; percentile is the share of US primary airports SFO is higher than)**

| Indicator | SFO value | Percentile | Fired? | What it means |
|---|---|---|---|---|
| Departures per runway | 47,528 (4 runways open) | 96th | **Yes** | Little room to add flights without more runway capacity |
| Average taxi-out time | 21.2 min | 91st | **Yes** | Aircraft are lining up for the runways |
| Load factor | 82.3% | 89th | No | Seats are fairly full but below the tool's cutoff |
| Passenger growth minus seat growth | −1.24 pts | n/a | No | Seats grew 5.9% and passengers grew 4.7%. Supply is keeping up. |
| Departures delayed 15+ min | 18.9% | 45th | No | Near the middle of US airports |
| Cancellation rate | 0.75% | 17th | No | Low |

**Why: what causes SFO's delays (minutes per flight)**

| Cause | Min/flight | Share | Can capacity investment fix it? |
|---|---|---|---|
| Late-arriving aircraft | 5.55 | 42% | Partly. These are knock-on delays, often from other airports. |
| Airline-caused | 3.97 | 30% | Mostly no. This is airline operations. |
| National air traffic system (NAS) | 3.16 | 24% | Yes, through runway, taxiway and flow capacity |
| Weather | 0.40 | 3% | No |

- The tool counts **66.6%** of delay as addressable by capacity investment (air traffic system plus late-aircraft delays).
- Recorded weather delay is low: 0.40 min per flight, 13th percentile.

**Context**
- SFO is a large hub with 26.25M enplanements in 2025, up 4.7% on 2024. Growth over two years averaged 4.2% a year.
- Its Expansion Opportunity Score is 69.3, ranking 42nd of 402 primary airports. That breaks down as:
  - **Demand: 72.2.** Driven by size (98th percentile) and load factor (89th). Growth is only about average (47th percentile).
  - **Strain: 66.3.** Driven by departures per runway (96th) and taxi-out time (91th). Delay rates are mid-range.
- International flights are 20.9% of departures and the average trip is 1,913 miles.

**What this means for investment:** The binding constraint is runway and airfield throughput (taxi-out time and departures per runway), not terminal seats. Projects that improve runway and taxiway flow fit the data better than terminal expansion. Since seats are growing faster than passengers, there's no sign yet of passengers being priced or crowded out.

**Caveats**
- **Delay data is incomplete:** the on-time data covers only large US airlines' domestic flights. Foreign carriers and cargo are left out. SFO is 20.9% international, so delays and congestion are probably understated.
- **Cause labels:** the delay-cause categories may file some weather-related air traffic restrictions under the air traffic system (NAS) rather than weather. The tool doesn't separate these, so the 3% weather share may be a lower bound.
- **Not available:** profitability, gate counts, and whether more airfield is physically or legally feasible. The score is a stand-in built from demand pressure and capacity strain.

**Right now:** no FAA delay program is active at SFO (FAA status as of 12:03 GMT, Oct 10, 2026). This is not scored and doesn't change the verdict.


## Part 2: follow-up conversation

---

### Q: Which New England airports should we look at for terminal expansion?

**Tool calls:** `rank_airports({"region": "new england", "top_n": 10})`

**Verdict:** Start with **BOS (Boston Logan)**. It is the strongest case: it scores near the top of the region, the data has high confidence, and it is by far the largest airport. Next come **PWM (Portland Jetport)** and **PVD (Rhode Island T.F. Green)**, where passenger demand is the main driver, and **BTV (Burlington)**, where congestion is the main driver. **BGR (Bangor)** and **HVN (Tweed/New Haven)** rank highly too, but they are small and their data is less reliable, so treat them as watch-list airports rather than lead candidates.

**New England ranking** (16 airports in the region; percentiles compare against all US primary airports)

| Rank | Airport | Hub tier | 2025 enplanements | Expansion score | Demand / Strain | Confidence | Key values |
|---|---|---|---|---|---|---|---|
| 1 | BGR Bangor (ME) | Nonhub | 437,108 | 75.7 | 73.6 / 77.8 | Medium | 2-yr growth 10.6%, load factor 80.2%, 21.0% of departures delayed 15+ min, 1 runway |
| 2 | **BOS Boston Logan (MA)** | Large | 21,021,153 | 74.2 | 63.8 / **84.6** | High | 31,956 departures per runway (6 runways), average taxi-out 21.2 min, 22.7% delayed, load factor 81.7%, 2-yr growth only 2.6% |
| 3 | HVN Tweed/New Haven (CT) | Small | 737,789 | 73.2 | 75.5 / 71.0 | **Low** | 2-yr growth 22.7%, load factor 76.0%, no delay data |
| 4 | BTV Burlington (VT) | Small | 709,881 | 71.4 | 63.8 / 79.0 | High | Average taxi-out 21.7 min, 20.7% delayed, load factor 81.3% |
| 5 | PWM Portland (ME) | Small | 1,287,041 | 66.8 | **74.3** / 59.2 | High | Load factor 82.4% (highest here), 2-yr growth 7.5% |
| 6 | PVD Providence (RI) | Small | 2,117,401 | 63.7 | 71.2 / 56.1 | High | 2-yr growth 10.5%, 11,104 departures per runway |
| 7 | ACK Nantucket (MA) | Nonhub | 152,789 | 61.0 | 40.3 / 81.7 | Medium | Congested, but load factor only 63.7% |
| 9 | BDL Hartford Bradley (CT) | Medium | 3,283,397 | 58.1 | 60.5 / 55.7 | High | Flat growth (2.6%), moderate strain |

BID (Block Island) and HYA (Cape Cod Gateway) are left out. Both have under 35,000 enplanements and low confidence.

**What drives the scores**
- **BOS:** The case is congestion, not growth. It has the region's highest strain score (84.6), driven by very heavy runway use and long taxi-outs. Some of that strain is on the airfield (taxiways, runways) rather than in the terminal. The 81.7% load factor still points to real demand pressure.
- **PWM and PVD:** The case is demand. Full planes and fast growth suggest terminal capacity would be used. Current congestion is moderate, so the case rests on growth continuing.
- **BTV:** The case is mostly congestion (long taxi-outs, a high delay rate) at a small airport with modest growth.
- **BGR and HVN:** Their percentile scores are high mainly because of fast growth from a small base. HVN is low confidence: its strain score uses only departures per runway because it has too few flights in the on-time data.

**Caveats**
- **The score is a proxy, not a profitability measure.** It is 50% demand pressure and 50% capacity strain. Revenue and profitability are not in the data.
- **The score is not terminal-specific.** It cannot separate terminal needs from airfield needs. Gate counts, terminal floor area and land availability are not in the data. For a terminal case, load factor and passenger growth are the nearest proxies.
- **Weather delay is excluded** because investment can't fix it.
- **Delay data is incomplete.** The on-time data covers only large US carriers' domestic flights. That understates activity at airports with a lot of international traffic (relevant for BOS) and leaves HVN and BID without delay figures.
- **Data period:** FAA enplanements for 2023–2025; BTS traffic and on-time data for 2025.

**Next steps:** I can re-run the ranking with a scale filter (for example a 1,000,000-enplanement minimum, or small/medium/large hubs only), or pull the unmet-demand indicators for BOS, PWM and PVD to test the terminal case specifically.

---

### Q: What about Bradley specifically, why is it lower?

**Tool calls:** `airport_profile({"code": "BDL"})`, `unmet_demand({"code": "BDL"})`

**Short answer:** Bradley International (BDL) ranks lower because its passenger numbers have stopped growing and the airport isn't congested, even though it is a big airport with fairly full planes. Overall it scores 58.1, which ranks 119th of 402 US primary airports. It has high confidence, meaning the data is complete. The unmet-demand check finds only weak evidence of demand going unserved: 1 of 6 warning signs is triggered.

**Demand score: 60.5.** Size and full planes help; growth holds it back.

| Factor (weight in score) | 2025 value | Percentile* | Effect |
|---|---|---|---|
| Passenger growth over 2 years, per year (35%) | 2.6% | 38th | Holds it back |
| Load factor, share of seats filled (30%) | 80.4% | 77th | Helps |
| Seat growth over the year (15%) | 2.75% | 46th | Neutral |
| Size, 3,283,397 passengers boarded (20%) | — | 87th | Helps |

\*Percentiles compare BDL with all US primary airports.

- Passengers boarded went from 3,122,212 in 2023 to 3,285,194 in 2024 and 3,283,397 in 2025, so 2025 was flat (−0.05%).
- Airlines added seats 2.75% and flights 3.7% in 2025. Seat growth beat passenger growth by 2.8 points. That points to spare capacity rather than demand going unserved.

**Strain score: 55.7.** The runways are busy, but there is little queuing or delay.

| Factor (weight in score) | 2025 value | Percentile | Effect |
|---|---|---|---|
| Flights departing 15+ min late (25%) | 18.6% | 41st | Below median |
| Average taxi-out time (25%) | 15.2 min | 29th | Short, so little runway queuing |
| Air traffic system delay per flight (20%) | 4.6 min | 78th | Fairly high |
| Delay from late-arriving aircraft, per flight (10%) | 6.2 min | 55th | Neutral |
| Departures per runway (20%) | 15,788.5 | 85th | High; the only warning sign triggered |

**Compared with the airports above it**
- **Boston Logan (BOS)** has about twice the departures per runway (31,956) and a 21.2-minute average taxi-out, so its strain score is 84.6.
- **Portland Jetport (PWM)** and **Providence (PVD)** are smaller but growing much faster (7.5% and 10.5% a year over 2 years), which gives them higher demand scores.
- BDL has neither the congestion nor the growth.

**Where BDL's delays come from:** about 66% of delay minutes come from causes that added capacity could reduce. Air traffic system delay is 28% and late-arriving aircraft 38%. Airline-caused delay is 30%, and investment won't fix that. Weather is 4% and isn't scored.

**What would change the picture**
- **Busy runways:** The runway number is the one real signal. BDL has 2 open runways, and only one is over 7,000 ft (longest 9,510 ft). Any case for BDL is more about the airfield than the terminal.
- **A return to growth:** If passenger growth picks up while planes stay about 80% full, the terminal case gets stronger. 2025 data does not show that yet.

**Caveats**
- **The score measures need, not returns.** It is a proxy built from demand pressure and congestion. Profitability isn't in the data.
- **Delay data leaves out cargo.** It covers only large US carriers' domestic flights. About 10.3% of BDL's departures are freight flights, so delay measures may understate activity there.
- **No terminal data.** Gate counts and terminal capacity aren't in the data, so I can't test gate crowding directly.

**Live now (not part of the score):** No FAA delay program is active at BDL right now.

---

### Q: Is there anything going on at BOS right now?

**Tool calls:** `live_status({"code": "BOS"})`

**Short answer:** Nothing unusual is happening at Boston Logan (BOS) right now. The FAA has no delay program active there, such as a ground stop or ground delay.

| Live indicator | Value |
|---|---|
| FAA airspace system status (updated Sat Oct 10 2026, 12:05 GMT) | No FAA delay program active |
| Aircraft tracked near BOS (OpenSky) | 30 in total: 13 on the ground, 17 in the air |

**Caveats**
- **One moment only:** This is a snapshot from when I checked. It is not part of the expansion score and doesn't change the 2025 findings.
- **The 2025 picture is still the same:** BOS's strain score is 84.6, the highest in New England. That reflects congestion across the whole of 2025: 31,956 departures per runway, an average taxi-out of 21.2 min, and 22.7% of departures delayed 15+ min. A quiet moment today doesn't change it.
- **Aircraft count is approximate:** OpenSky only sees aircraft with transponders inside a 0.3-degree box around the airport, and its coverage depends on volunteer receivers. So the 30 is a rough count, not a full traffic figure.

I can also pull the full unmet-demand breakdown for BOS. It would show how much of its delay could be fixed with more capacity and how much comes from weather.
