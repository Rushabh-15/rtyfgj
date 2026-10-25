# GB wind data memo, January 2026

_Written before the build (24 October 2026) from the raw pull now in `data/snapshot/`, and confirmed with the decisions
noted at the end. Numbers in the build supersede the rounded figures here; see `docs/analysis.md`._

Both feeds are clean. At the recommended cutoff the desk's forecast ran 1.75 GW above outturn on average
(MAE 2.04 GW).

## Findings

- **Forecasts per day:** 8, published at 02:30, 04:30, 07:30, 09:30, 11:30, 15:30, 18:30 and 22:30 UTC.
- **Time step:** [WINDFOR](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream) hourly,
  [FUELHH](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream) half-hourly, without
  exception.
- **Targets before publishTime:** yes, about a fifth of rows (4,081 of 19,856); each run starts at 21:00 UTC the day
  before publication. Past hours hold a frozen value, so they are dropped.
- **Duplicates, revisions, gaps:** none, except 15 January's 11:30 run, which never arrived; a run appeared at 12:25.
  Each hour is forecast by 15–23 runs.
- **Timestamps:** UTC (`Z`); FUELHH startTime is the period start. WINDFOR fits outturn best about 30 minutes before
  its label (unverified).
- **Forecast − actual:** +1.51 GW (+13%) at the shortest horizon; 0.4–0.65 GW when the forecast is under 12 GW and
  3.4 GW over 18 GW. The same fleet plus curtailment fits that pattern (unverified).

**Gate closures (UK, D−1):** EPEX 60-min 09:20 and 30-min 15:30; Nord Pool hourly 09:50 and half-hourly 14:30
([EPEX](https://www.epexspot.com/en/tradingproducts),
[Nord Pool](https://www.nordpoolgroup.com/497dea/globalassets/download-center/rules-and-regulations/product-specifications-gb-18.04.23.pdf)).
Delivery starts 23:00 on D−1
([§2.2.6](https://www.nordpoolgroup.com/49a505/globalassets/download-center/rules-and-regulations/day-ahead-market-regulations---gb-market.pdf);
EPEX unverified).

- **Cutoff:** the latest WINDFOR run published by 09:00 UK on D−1, which is the 07:30 UTC run every day.
- **Windows:** delivery 2026-01-01 23:00 to 2026-02-01 23:00 UTC (1,488 half-hours); the data needed is FUELHH in
  that window plus the forecasts published 1–31 January.

## Assumptions

- Decisions are dated 1–31 January 2026 (unverified with the client).
- publishTime is when the desk first sees a forecast (unverified).
- An hourly value covers half-hours H and H+30 (unverified; shifting it moves MAE by 1.7%).
- FUELHH WIND, metered after curtailment, is the right actual (unverified).
- Gate closures applied in January 2026 as documented (unverified).

## Open questions, and the answers that shaped the build

| Question | Decision |
| --- | --- |
| Which auction does the desk use, when is its forecast frozen, and do days start at 23:00? | No single auction: default cutoff 09:00 UK on D−1, adjustable 03:00–16:00, run in use shown. Days run 23:00–23:00 UK, fixed. |
| Is the high-wind gap curtailment, and should the app also show a bias-corrected error? | Describe it as consistent with curtailment, unverified. No bias correction; show mean error beside MAE and break errors down by forecast level. |
| Which hour does a WINDFOR value cover? [Elexon's wind page](https://bmrs.elexon.co.uk/wind-generation) says 20:00–20:00; the data, 21:00–21:00. | startTime is the start of the hour (covers H and H+30); a 30-minute shift stays available as configuration. |

Corrections at confirmation: the cutoff rule is the latest run published **strictly before** the cutoff (not "by");
keep every forecast run in the snapshot, not only 07:30, for the adjustable cutoff and the all-vintage analysis; the
NESO comparison uses the 09:30 run because NESO scores the forecast published 09:00–10:00.
