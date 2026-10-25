# Time plan (16 hours)

Correctness first: the core rule and the analysis (sections 1 and 2) come before any interface, so the numbers are
right even if polish runs short. Each block ends with something that can be checked.

| Hours | Block | Done when |
| ---: | --- | --- |
| 0.0–1.0 | **Data memo.** Pull WINDFOR and FUELHH for the window, save raw responses with hashes, profile runs, gaps, timestamps; agree cutoff, delivery day and alignment with the client | Memo confirmed; snapshot and manifest committed |
| 1.0–2.0 | **1. Core rule.** Time conventions (UTC instants, UK clock times, 23:00–23:00 delivery days), snapshot loader, `select_forecasts` (strictly before the cutoff, past rows excluded) | Golden day reproduces the hand check |
| 2.0–3.5 | **1. Tests.** Hypothesis properties, late-run fallback, DST edge cases, pandas `merge_asof` and DuckDB `ASOF JOIN` cross-checks, data contracts | Three implementations agree on every cutoff |
| 3.5–5.5 | **2. Analysis.** Bias, MAE, RMSE, P10/P50/P90 by lead time and forecast level; all-vintage grid; persistence; buffer fit and out-of-sample coverage with day-block bootstrap; lag scan | `docs/analysis.md` generated; numbers cross-checked by a second calculation |
| 5.5–6.5 | **Precompute.** Every cutoff × both alignments to deterministic JSON | Rebuild is byte-identical |
| 6.5–8.0 | **API.** FastAPI read-only endpoints, validation errors, caching, OpenAPI schema; end-to-end test snapshot → API | API tests green |
| 8.0–11.0 | **3. Front end.** Decision timeline with the run in use, day view, error and buffer view; table view for every chart; phone and dark mode | App renders real data; component tests pass against API fixtures |
| 11.0–12.5 | **Container and CI.** Multi-stage Dockerfile, compose, GitHub Actions (backend, frontend, image + Playwright smoke), deploy | CI green from a fresh clone; deployed URL answers |
| 12.5–14.0 | **4. Validation.** Period counts, zero post-cutoff forecasts, lag scan, persistence, 20 periods read back from Elexon, NESO comparison | `docs/validation.md` with pass/fail and numbers |
| 14.0–15.0 | **5. Write-up.** README (decision log, assumptions, limitations, problems, AI use), video scripts | Reviewed against the brief |
| 15.0–16.0 | **Record and submit.** Two videos, final smoke test of every submitted URL from a signed-out browser | Links open signed out |

## If time runs short, cut in this order

1. The all-vintage heatmap and the timing chart in the app (they stay in `docs/analysis.md`).
2. Dark mode and the phone layout polish (the layout still must not break).
3. The second alignment's precomputed tables (keep the configuration switch, document the 1.7%).
4. The daily smoke test of the deployed URL (keep the one after each deployment).

Never cut: the strict-before rule and its tests, the out-of-sample buffer test, the validation checklist, the
README's assumptions and limitations.
