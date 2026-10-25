# Video scripts

Two parts, recorded separately, each under five minutes at a natural pace (about 130 words a minute). _Italics_ say
what is on screen. Numbers are the 09:00 cutoff unless stated; they come from `docs/analysis.md` and
`docs/validation.md`.

## Part 1: for the trading desk (about 4 minutes spoken, ~510 words; leaves a minute for clicks and pauses)

**0:00 Why this exists** _(App, Error and buffer tab, hero visible.)_
When you bid day-ahead, you buy against a wind forecast. This app answers two questions for January 2026: how wrong
was the forecast you actually had at bidding time, and how much should you hold to cover it?

**0:20 The buffer** _(Point at 4,233 MW.)_
The answer to the second question first. Hold 4,233 megawatts above the forecast-implied volume and you cover wind
shortfalls in nine half-hours out of ten. That figure was set on the first half of January only. Applied unchanged to
the second half, it covered 91.5% of half-hours. So it held out of sample, but on sixteen test days the honest range
is 78 to 100%.

**0:55 Does it hold at other levels?** _(Calibration chart; click 80%, 95%, 50%.)_
Each dot is a buffer sized on the first half and tested on the second; on the diagonal it does what it promised. 80,
90 and 95% hold. The 50% buffer does not: it covered only a third of half-hours, because the forecast's bias grew in the
windier second half. A buffer near the median is a bet that the bias stays put; the upper levels absorb it.

**1:30 What the error looks like** _(KPI tiles, then Shortfall by delivery day.)_
On average the forecast ran 1,749 megawatts above what the wind delivered, and wind came in short in 85% of
half-hours. This isn't noise around zero: it's a systematic gap plus a spread around it. Each whisker here is one
delivery day; the shaded days are where the buffer was fitted.

**2:00 Where it comes from** _(Shortfall by forecast level.)_
The gap grows with the forecast. When under 6 gigawatts was forecast, the median shortfall was about 1.1 gigawatts.
When 18 or more was forecast, wind fell short every single half-hour, by 3.3 gigawatts in the middle. Outturn never
went above 17.8 gigawatts all month. That pattern is consistent with curtailment, but this data can't confirm it. If
it is curtailment, the buffer overstates what you need on the windiest days.

**2:40 The decision timeline** _(Drag the orange cutoff from 09:00 to 12:00, then back.)_
This strip is the day before delivery. At 09:00, twenty minutes before EPEX's hourly auction closes, the latest
forecast is the 07:30 run, and the app says so. Move the cutoff and the run follows the rule: the latest run published
before that moment. At 12:00 that's the 11:30 run.

**3:05 When a run is late** _(Day view, 16 January, cutoff 12:00.)_
On 15 January the 11:30 run never arrived. Bidding at 12:00 for the 16th, the app falls back to the 09:30 run and
tells you why; the missing slot is struck through.

**3:25 One bad day** _(Calendar: click 28 January.)_
The calendar shades each day by error. The 28th was the worst: the forecast was 5.3 gigawatts high all day. NESO's
own report blames an IT problem that stopped weather updates on the 27th. The dashed line is what you'd have planned
for with the buffer, and the table view lists every half-hour.

**3:55 Can you trust the numbers?** _(Validation doc, checks 9 to 11.)_
Twenty random half-hours match Elexon's own records exactly. The forecast beats simply holding the last known outturn
by half. And on NESO's published accuracy measure the forecast scores worse than NESO's figure, for reasons the
validation note explains: a different forecast product, and exclusions this data can't make.

**4:20 What it can't tell you**
It's one winter month, and the curtailment question needs balancing data outside this brief. With a few more months,
the next step is a buffer that scales with the forecast level.

## Part 2: for the tech lead (about 4 minutes spoken, ~510 words)

**0:00 Data findings** _(docs/data-memo.md, then `windcast check` output.)_
Two Elexon feeds. WINDFOR: 272 runs, eight a day, hourly values. FUELHH: half-hourly outturn. Three things shaped the
build. A fifth of WINDFOR rows target hours before their own publishTime, and those values are frozen copies, so they
are dropped. The 11:30 run on 15 January is missing and a run appears at 12:25. And hourly forecasts have to be mapped
onto half-hours. Everything runs on a committed snapshot of the raw responses with SHA-256 hashes; a re-pull was byte
identical, and eight data contracts run on every build.

**0:45 The cutoff rule** _(selection.py, select_forecasts.)_
The core is one pure function. For each half-hour, find the hourly value that covers it, then the latest run published
strictly before the cutoff, via a bisect on publish times. Strictly matters: at a 09:30 cutoff the run published at
09:30 is not used. Because it's a rule, not a slot, the late-run fallback falls out for free. UK time is handled with
zoneinfo, and clock-change days have 46 and 50 periods; there are tests for both.

**1:25 How it's tested** _(Test files, then validation table.)_
Hypothesis checks the properties: never a run at or after the cutoff, always the most recent one that isn't, past rows
never used, input order irrelevant. A golden day, the 16th, was checked by hand from the raw JSON. And two independent
implementations, pandas merge_asof and a DuckDB ASOF join, agree with the pure function on random inputs and on all 27
cutoffs. The served tables are rebuilt in CI and compared byte for byte.

**2:10 Architecture** _(README diagram, then /api/docs.)_
Ingest writes the snapshot. A standard-library transform precomputes every cutoff for both alignments, 58 small JSON
files. FastAPI serves them read-only with ETags and cache headers. The React and TypeScript front end uses types
generated from the OpenAPI schema, and its tests run against real API responses that a backend test keeps current.
A three-stage Docker image rebuilds the tables from the snapshot, so the build fails if a contract breaks.

**2:55 CI and deployment** _(GitHub Actions run, then the live app.)_
CI runs lint, strict types and tests for both halves, builds the image, runs the contracts inside it and a Playwright
smoke test on desktop and phone. Vercel's container runtime builds the same Dockerfile. It's the same recipe but not
the same bytes, so the smoke test runs again against the live URL after each production deploy.

**3:25 Trade-offs and what I flagged** _(README, Problems with the plan.)_
Precomputing beats computing per request: the inputs are fixed and small. The hour-start alignment follows Elexon's own
labels; shifting by 30 minutes would cut MAE only 1.7%, so it's a config switch, not the default. The lag scan's
minimum is not at zero: it's minus 60 at the cutoff, minus 30 at short leads, on a very flat curve. I report that as a
failed check with the numbers, plus a criterion that would still catch a timezone bug. On NESO's metric we get 8.95%
against their 4.99%: about two points is the forecast product, the rest matches exclusions we can't apply, and that
part is unverified. And the buffer back-test resamples whole days, because half-hours within a day aren't independent.

**4:30 Next**
With balancing data I'd test the curtailment explanation, and with more months, fit a buffer by forecast level.
