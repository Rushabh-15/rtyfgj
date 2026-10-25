import { useAccuracy, useDay, useMeta, useVintages, type Accuracy, type DayView, type Meta } from "./api/client";
import { CutoffTimeline } from "./components/CutoffTimeline";
import { DayViewPanel } from "./components/DayView";
import { ErrorView } from "./components/ErrorView";
import { clockMinutes, dayBefore, shortDeliveryDate, ukDate, ukDayMonth, ukTime } from "./lib/format";
import { useUrlState, type View } from "./state/url";

const DEFAULT_DAY = "2026-01-02";

/** Regular run slots (UK clock time) that were not published on the day bids for `deliveryDay` were made. */
function missingSlots(meta: Meta, deliveryDay: string): string[] {
  const bidDay = dayBefore(deliveryDay);
  return meta.runs.missing
    .map((slot) => `${slot.replace(" ", "T")}:00Z`)
    .filter((iso) => ukDate(iso) === bidDay)
    .map((iso) => ukTime(iso));
}

/** The regular run slot a cutoff selects (latest published strictly before it), as UK clock time. */
function regularRun(meta: Meta, cutoff: string): string | undefined {
  const before = meta.markers.filter((m) => m.kind === "run" && clockMinutes(m.time_uk) < clockMinutes(cutoff));
  return before[before.length - 1]?.time_uk;
}

/**
 * Run in use and a note when the data differs from the regular schedule (a late or missing run). While the data
 * for a new cutoff is loading, the previous cutoff's data is still on screen, so it is ignored here.
 */
function runSummary(meta: Meta, cutoff: string, view: View, day: DayView | undefined, accuracy: Accuracy | undefined) {
  const regular = regularRun(meta, cutoff);
  if (day?.cutoff_uk !== cutoff) day = undefined;
  if (accuracy?.cutoff_uk !== cutoff) accuracy = undefined;
  if (view === "day" && day) {
    const used = day.runs[0]?.publish_time_utc;
    const first = used ? ukTime(used) : undefined;
    let note: string | undefined;
    if (used && first && regular && first !== regular) {
      note =
        clockMinutes(first) < clockMinutes(regular)
          ? `For this day the ${regular} run was not published, so the rule falls back to the ${first} run published on ${ukDayMonth(used)}.`
          : `For this day the ${regular} run was not published; a run published at ${first} on ${ukDayMonth(used)} is the latest before the cutoff.`;
    }
    return { run: first, note };
  }
  if (accuracy) {
    const slots = accuracy.runs_used_utc.map((r) => ({ iso: r, time: ukTime(r) }));
    const exceptions = slots.filter((s) => s.time !== regular);
    const note =
      exceptions.length > 0
        ? `On ${exceptions.map((e) => ukDayMonth(e.iso)).join(", ")} the ${regular ?? "regular"} run was missing, so ${exceptions.map((e) => `the ${e.time} run`).join(" and ")} stood in.`
        : undefined;
    return { run: regular, note };
  }
  return { run: regular, note: undefined };
}

export function App() {
  const [state, update] = useUrlState();
  const meta = useMeta();
  const m = meta.data;
  const cutoff = m && state.cutoff && m.cutoffs_uk.includes(state.cutoff) ? state.cutoff : (m?.default_cutoff_uk ?? "09:00");
  const coverage =
    m && state.coverage && m.coverage_levels_pct.includes(state.coverage) ? state.coverage : (m?.default_coverage_pct ?? 90);
  const selectedDay = m && state.day && m.delivery_days.includes(state.day) ? state.day : (m?.delivery_days[0] ?? DEFAULT_DAY);

  const day = useDay(m ? selectedDay : undefined, cutoff, coverage);
  const accuracy = useAccuracy(cutoff);
  const vintages = useVintages();

  if (meta.isError) {
    return (
      <main className="shell">
        <p className="problem" role="alert">
          The app could not load its data from <code>/api/v1/meta</code> ({meta.error.message}). Check that the API is
          running, then reload.
        </p>
      </main>
    );
  }
  if (!m) {
    return (
      <main className="shell">
        <p className="placeholder">Loading January's forecasts…</p>
      </main>
    );
  }

  const { run, note } = runSummary(m, cutoff, state.view, day.data, accuracy.data);
  const setView = (view: View) => {
    update({ view }, { push: true });
  };

  return (
    <div className="shell">
      <header className="masthead">
        <div>
          <h1 className="wordmark">Wind at cutoff</h1>
          <p className="tagline">
            The GB wind forecast a day-ahead desk had when it bid, against what the wind did. Delivery days{" "}
            {shortDeliveryDate(m.delivery_days[0] ?? "")} to {shortDeliveryDate(m.delivery_days[m.delivery_days.length - 1] ?? "")},
            decisions made in January 2026.
          </p>
        </div>
      </header>

      <CutoffTimeline
        cutoffs={m.cutoffs_uk}
        cutoff={cutoff}
        markers={m.markers}
        missing={state.view === "day" ? missingSlots(m, selectedDay) : []}
        runInUse={run}
        runNote={note}
        onChange={(next) => {
          update({ cutoff: next });
        }}
      />

      <nav className="tabs" aria-label="Views">
        <button type="button" className="tab" aria-current={state.view === "day" ? "page" : undefined} onClick={() => {
            setView("day");
          }}>
          Day view
        </button>
        <button type="button" className="tab" aria-current={state.view === "error" ? "page" : undefined} onClick={() => {
            setView("error");
          }}>
          Error and buffer
        </button>
      </nav>

      <main>
        {state.view === "day" ? (
          <DayViewPanel
            meta={m}
            day={day.data}
            accuracy={accuracy.data}
            selected={selectedDay}
            refreshing={day.isPlaceholderData}
            onSelectDay={(d) => {
              update({ day: d });
            }}
          />
        ) : accuracy.data ? (
          <ErrorView
            meta={m}
            accuracy={accuracy.data}
            vintages={vintages.data}
            coverage={coverage}
            refreshing={accuracy.isPlaceholderData}
            onCoverage={(c) => {
              update({ coverage: c });
            }}
            onSelectDay={(d) => {
              update({ view: "day", day: d }, { push: true });
            }}
          />
        ) : (
          <p className="placeholder">Loading the error analysis…</p>
        )}
        {day.isError || accuracy.isError ? (
          <p className="problem" role="alert">
            Part of the data did not load ({(day.error ?? accuracy.error)?.message}). Choose another day or cutoff, or reload.
          </p>
        ) : null}
      </main>

      <footer className="footer">
        <p>
          Data: Elexon Insights WINDFOR (forecast) and FUELHH fuel type WIND (outturn), downloaded{" "}
          {m.snapshot[0]?.downloaded_utc.slice(0, 10)} and checked against SHA-256 hashes on every build. Errors are forecast
          minus outturn: positive means wind fell short. Delivery days run 23:00 to 23:00 UK time.
        </p>
        <p>
          <a href="/api/docs">API documentation</a>
        </p>
      </footer>
    </div>
  );
}
