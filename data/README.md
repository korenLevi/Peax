# Data

This folder holds the inputs for the Peax ETL.

- `raw/` contains the source files exactly as downloaded. It is listed in `.gitignore` and is never committed.
- `processed/` contains ETL output. It is committed to git.

All row counts below were checked on 2026-10-09.

```
raw/
  faa/          cy2023.xlsx, cy2024.xlsx, cy2025.xlsx
  t100/         t100_segment_2025.zip (optional: t100_segment_2024.zip)
  ontime/       2025_01.csv ... 2025_12.csv
  ourairports/  airports.csv, runways.csv
  lookups/      aircraft_config.csv, service_class.csv
processed/
  ontime_by_airport.csv    output of etl/ontime_aggregate.py, one row per origin (352 airports)
  airport_features.csv     output of etl/build_features.py, one row per FAA primary airport (402 x 57)
```

## Processed files

`processed/airport_features.csv` is the only file the agent reads. Key columns:

- Identity: `code` (FAA location id), `bts_code` (IATA code used by BTS), `icao`, `name`, `state`, `hub` (L/M/S/N), `lat`, `lon`
- FAA: `enpl_2023`, `enpl_2024`, `enpl_2025`, `pax_yoy`, `pax_cagr_2y`
- T-100: `deps`, `seats`, `pax`, `freight_lbs`, `load_factor`, `intl_share_deps`, `freight_share_deps`, `avg_distance_mi`, `long_haul_share_{1500,2500,3000}` (and `_pax` / `_freight` splits), `seasonality_peak_ratio`, `seats_growth_yoy`, `deps_growth_yoy` (empty until the 2024 file exists)
- On-Time: `ot_flights`, `dep_del15_rate`, `taxi_out_mean`, `cancel_rate`, `nas_delay_per_flight`, `weather_delay_per_flight`, `late_aircraft_per_flight`, `carrier_delay_per_flight`, `peak_block_share`
- OurAirports: `runways_open`, `runways_7000ft_plus` (open runways of 7,000 ft or more, a widebody/long-haul proxy; shorter runways still serve narrowbody jets), `longest_runway_ft`
- Derived: `deps_per_runway`, `pax_per_runway`, `pax_growth_minus_seat_growth`

FAA location ids and BTS codes differ for a few airports (IWA vs AZA, GPI vs FCA, DJT vs PBI). `build_features.py` resolves them through OurAirports `local_code` plus one manual override, and joins BTS files on `bts_code`.

### Optional: T-100 for 2024

Download the same T-100 Segment (All Carriers) table for year 2024 and save it as `raw/t100/t100_segment_2024.zip`. Rerun `etl/build_features.py`; `seats_growth_yoy` and `deps_growth_yoy` fill in and confidence moves from medium to high for well covered airports.

## 1. FAA commercial service enplanements

| File | Source | Period | Data rows |
|---|---|---|---|
| `raw/faa/cy2023.xlsx` | https://www.faa.gov/airports/planning_capacity/passenger_allcargo_stats/passenger/cy23_commercial_service_enplanements | Calendar year 2023 (compared with 2022) | 502 |
| `raw/faa/cy2024.xlsx` | https://www.faa.gov/airports/planning_capacity/passenger_allcargo_stats/passenger/cy24_commercial_service_enplanements | Calendar year 2024 (compared with 2023) | 513 (plus 6 summary rows) |
| `raw/faa/cy2025.xlsx` | https://www.faa.gov/airports/planning_capacity/passenger_allcargo_stats/passenger/arp-cy2025-commercial-service-enplanements.xlsx | Calendar year 2025 (compared with 2024) | 516 (plus 6 summary rows) |

One sheet per file. The header is on row 1 of the sheet.

Columns (the two enplanement columns change with the year):

```
cy2023.xlsx: Rank, RO, ST, Locid, City, Airport Name, S/L, Hub, CY 23 Enplanements, CY 22 Enplanements, % Change
cy2024.xlsx: Rank, RO, ST, Locid, City, Airport Name, S/L, Hub, CY 24 Enplanements, CY 23 Enplanements, % Change
cy2025.xlsx: Rank, RO, ST, Locid, City, Airport Name, S/L, Hub, CY 25 Enplanements, CY 24 Enplanements, % Change
```

ETL gotchas:

- The 2024 and 2025 files have 6 summary rows at the end ("Large Count", "Medium Count", "Small Count", "Nonhub Count", "Nonprimary Commercial Service", "Total Primary Airports"). In these rows `Locid` holds a number and `Rank` is empty. Keep only rows where `Rank` is not empty.
- The `Hub` column contains the literal text `None` for nonprimary airports. pandas turns that into NaN by default, so read with `keep_default_na=False`. Hub values are `L`, `M`, `S`, `N` and `None`.
- The sheet name has a trailing space (`"ChangeinRevenuePassengerEnplan "`). Read the first sheet by index (`sheet_name=0`), not by name.
- Find the year from the enplanements header text (for example `CY 25 Enplanements`), not from the file name.

```python
df = pd.read_excel("data/raw/faa/cy2025.xlsx", sheet_name=0, dtype=str, keep_default_na=False)
df = df[df["Rank"] != ""]
```

## 2. BTS T-100 Segment (All Carriers)

| File | Source | Period | Rows |
|---|---|---|---|
| `raw/t100/t100_segment_2025.zip` | https://transtats.bts.gov/DL_SelectFields.aspx?QO_fu146_anzr=Nv4+Pn44vr45&gnoyr_VQ=FMG | 2025, months 1 to 12 | 571,205 |

The zip holds one file, `T_T100_SEGMENT_ALL_CARRIER.csv`. Read it directly from the zip. Column names are BTS database names:

```
DEPARTURES_SCHEDULED, DEPARTURES_PERFORMED, SEATS, PASSENGERS, FREIGHT, DISTANCE, AIR_TIME,
UNIQUE_CARRIER, ORIGIN_AIRPORT_ID, ORIGIN, ORIGIN_STATE_ABR, DEST_AIRPORT_ID, DEST, DEST_STATE_ABR,
DEST_COUNTRY, AIRCRAFT_TYPE, AIRCRAFT_CONFIG, YEAR, MONTH, CLASS, DATA_SOURCE
```

Values seen in the 2025 data:

- `DATA_SOURCE`: `DU`, `DF`, `IU`, `IF`
- `CLASS`: `F`, `G`, `L`, `P`
- `AIRCRAFT_CONFIG`: `1`, `2`, `3`, `4`

ETL gotchas:

- `DATA_SOURCE` has two letters. Domestic vs international is the first character (`D` or `I`). Do not compare the whole value to `"D"` or `"I"`.

### Lookup tables

| File | Source | Rows |
|---|---|---|
| `raw/lookups/aircraft_config.csv` | https://transtats.bts.gov/Download_Lookup.asp?Y11x72=Y_NVePeNSg_PbaSVT | 6 |
| `raw/lookups/service_class.csv` | https://transtats.bts.gov/Download_Lookup.asp?Y11x72=Y_fReiVPR_PYNff | 14 |

Both have the columns `Code, Description`. They cover every `AIRCRAFT_CONFIG` and `CLASS` code in the T-100 data. Read `Code` as a string so that `"1"` matches `AIRCRAFT_CONFIG`.

## 3. BTS On-Time Reporting Carrier On-Time Performance

| Files | Source | Period | Rows |
|---|---|---|---|
| `raw/ontime/2025_01.csv` ... `2025_12.csv` | https://transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_2025_{1..12}.zip | 2025, one file per month | 7,001,619 in total |

Rows per file:

| File | Rows | File | Rows |
|---|---|---|---|
| 2025_01.csv | 539,747 | 2025_07.csv | 631,428 |
| 2025_02.csv | 504,884 | 2025_08.csv | 602,378 |
| 2025_03.csv | 600,872 | 2025_09.csv | 562,439 |
| 2025_04.csv | 583,950 | 2025_10.csv | 605,844 |
| 2025_05.csv | 605,648 | 2025_11.csv | 570,550 |
| 2025_06.csv | 611,575 | 2025_12.csv | 582,304 |

The month in each file name was checked against its `Month` column.

Columns used by the ETL:

```
Year, Month, Origin, Dest, DepDel15, TaxiOut, Cancelled,
CarrierDelay, WeatherDelay, NASDelay, LateAircraftDelay
```

Full header (109 named columns plus an empty one at the end):

```
Year, Quarter, Month, DayofMonth, DayOfWeek, FlightDate, Reporting_Airline, DOT_ID_Reporting_Airline,
IATA_CODE_Reporting_Airline, Tail_Number, Flight_Number_Reporting_Airline, OriginAirportID,
OriginAirportSeqID, OriginCityMarketID, Origin, OriginCityName, OriginState, OriginStateFips,
OriginStateName, OriginWac, DestAirportID, DestAirportSeqID, DestCityMarketID, Dest, DestCityName,
DestState, DestStateFips, DestStateName, DestWac, CRSDepTime, DepTime, DepDelay, DepDelayMinutes,
DepDel15, DepartureDelayGroups, DepTimeBlk, TaxiOut, WheelsOff, WheelsOn, TaxiIn, CRSArrTime, ArrTime,
ArrDelay, ArrDelayMinutes, ArrDel15, ArrivalDelayGroups, ArrTimeBlk, Cancelled, CancellationCode,
Diverted, CRSElapsedTime, ActualElapsedTime, AirTime, Flights, Distance, DistanceGroup, CarrierDelay,
WeatherDelay, NASDelay, SecurityDelay, LateAircraftDelay, FirstDepTime, TotalAddGTime, LongestAddGTime,
DivAirportLandings, DivReachedDest, DivActualElapsedTime, DivArrDelay, DivDistance,
Div1Airport ... Div5TailNum (7 columns for each of Div1 to Div5: Airport, AirportID, AirportSeqID,
WheelsOn, TotalGTime, LongestGTime, WheelsOff, TailNum)
```

ETL gotchas:

- BTS ships each month as a zip that holds `On_Time_Reporting_Carrier_On_Time_Performance_(1987_present)_2025_{N}.csv` (with parentheses in the name) next to `readme.html`. Here the CSVs were extracted by hand and renamed to `2025_MM.csv`, so there is no zip and no readme. If you download a month again, read the CSV member from the zip by its `.csv` extension and skip `readme.html`.
- Each file has 110 columns and is about 230 to 290 MB, so always read with `usecols`.
- Every header line and data line ends with a trailing comma. Without `usecols`, pandas adds an empty column called `Unnamed: 109`.

```python
cols = ["Year", "Month", "Origin", "Dest", "DepDel15", "TaxiOut", "Cancelled",
        "CarrierDelay", "WeatherDelay", "NASDelay", "LateAircraftDelay"]
df = pd.read_csv("data/raw/ontime/2025_01.csv", usecols=cols)
```

## 4. OurAirports

| File | Source | Period | Rows |
|---|---|---|---|
| `raw/ourairports/airports.csv` | https://davidmegginson.github.io/ourairports-data/airports.csv | Snapshot downloaded 2026-10-09 | 86,226 |
| `raw/ourairports/runways.csv` | https://davidmegginson.github.io/ourairports-data/runways.csv | Snapshot downloaded 2026-10-09 | 48,330 |

`airports.csv` columns:

```
id, ident, type, name, latitude_deg, longitude_deg, elevation_ft, continent, iso_country, iso_region,
municipality, scheduled_service, icao_code, iata_code, gps_code, local_code, home_link, wikipedia_link, keywords
```

`runways.csv` columns:

```
id, airport_ref, airport_ident, length_ft, width_ft, surface, lighted, closed, le_ident, le_latitude_deg,
le_longitude_deg, le_elevation_ft, le_heading_degT, le_displaced_threshold_ft, he_ident, he_latitude_deg,
he_longitude_deg, he_elevation_ft, he_heading_degT, he_displaced_threshold_ft
```

ETL gotchas:

- Join FAA and BTS three-letter codes to `airports.iata_code`, then join runways on `runways.airport_ident = airports.ident` (for example `BOS` maps to `KBOS`, `ANC` maps to `PANC`).
- OurAirports is a live dataset, so row counts change each time it is downloaded.
