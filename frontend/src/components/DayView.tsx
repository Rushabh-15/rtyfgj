// View 1: one delivery day at the chosen cutoff.

import type { Accuracy, DayView as DayData, Meta } from "../api/client";
import { duration, longDeliveryDate, num, pct, shortDeliveryDate, signed, ukTime, ukWeekdayDate } from "../lib/format";
import { DayCalendar } from "./DayCalendar";
import { DayChart } from "./DayChart";

interface Props {
  meta: Meta;
  day: DayData | undefined;
  accuracy: Accuracy | undefined;
  selected: string;
  refreshing: boolean;
  onSelectDay: (day: string) => void;
}

function addMinutes(iso: string, minutes: number): string {
  return new Date(Date.parse(iso) + minutes * 60_000).toISOString();
}

function sampleNote(meta: Meta, sample: string): string {
  const [from, to] = sample === "fit" ? meta.fit_days : meta.test_days;
  const range = `${shortDeliveryDate(from ?? "")} to ${shortDeliveryDate(to ?? "")}`;
  return sample === "fit"
    ? `A fit day: the buffer was set on ${range}.`
    : `A test day: the buffer, set on the first half of the month, was applied unchanged to ${range}.`;
}

export function DayViewPanel({ meta, day, accuracy, selected, refreshing, onSelectDay }: Props) {
  const index = meta.delivery_days.indexOf(selected);
  const prev = meta.delivery_days[index - 1];
  const next = meta.delivery_days[index + 1];
  const worst = day?.periods.reduce((a, b) => (b.error_mw > a.error_mw ? b : a));
  const covered = day?.periods.filter((p) => p.covered).length ?? 0;
  const run = day?.runs[0];

  return (
    <div className={`view view-day${refreshing ? " is-refreshing" : ""}`}>
      <aside className="day-side">
        <div className="day-nav">
          <button
            type="button"
            className="icon-button"
            disabled={!prev}
            aria-label="Previous delivery day"
            onClick={() => {
              if (prev) onSelectDay(prev);
            }}
          >
            ‹
          </button>
          <h2 className="day-title">{longDeliveryDate(selected)}</h2>
          <button
            type="button"
            className="icon-button"
            disabled={!next}
            aria-label="Next delivery day"
            onClick={() => {
              if (next) onSelectDay(next);
            }}
          >
            ›
          </button>
        </div>
        {day ? (
          <p className="day-window">
            Delivery {ukTime(day.window_utc[0] ?? "")} {ukWeekdayDate(day.window_utc[0] ?? "")} to{" "}
            {ukTime(day.window_utc[1] ?? "")} {ukWeekdayDate(day.window_utc[1] ?? "")}, UK time.
          </p>
        ) : null}
        <DayCalendar days={meta.delivery_days} summaries={accuracy?.days} selected={selected} onSelect={onSelectDay} />
        {day ? <p className="day-sample">{sampleNote(meta, day.sample)}</p> : null}
      </aside>

      <div className="day-main">
        {day ? (
          <>
            <dl className="day-stats">
              <div>
                <dt>Mean error</dt>
                <dd>{signed(day.stats.mean_error_mw)} MW</dd>
                <p>MAE {num(day.stats.mae_mw)} MW</p>
              </div>
              <div>
                <dt>Largest shortfall</dt>
                <dd>{worst ? `${signed(worst.error_mw)} MW` : "–"}</dd>
                <p>{worst ? `Half-hour from ${ukTime(worst.start_utc)}` : null}</p>
              </div>
              <div>
                <dt>Within the {day.coverage_pct}% buffer</dt>
                <dd>
                  {covered} of {day.periods.length}
                </dd>
                <p>
                  half-hours ({pct(day.covered_share, 0)}), holding {num(day.buffer_mw)} MW
                </p>
              </div>
              <div>
                <dt>Forecast run used</dt>
                <dd>{run ? `${run.publish_time_utc.slice(11, 16)} UTC` : "–"}</dd>
                <p>
                  {run
                    ? `${ukWeekdayDate(run.publish_time_utc)}, ${duration((Date.parse(day.cutoff_utc) - Date.parse(run.publish_time_utc)) / 60000)} before the cutoff`
                    : null}
                </p>
              </div>
              <div>
                <dt>Persistence baseline</dt>
                <dd>{num(day.persistence.value_mw)} MW</dd>
                <p>
                  Outturn {ukTime(day.persistence.period_start_utc)}–{ukTime(addMinutes(day.persistence.period_start_utc, 30))}{" "}
                  {ukWeekdayDate(day.persistence.period_start_utc)}, the last before the cutoff, held all day
                </p>
              </div>
            </dl>
            <DayChart day={day} yMax={meta.chart_max_mw} />
          </>
        ) : (
          <p className="placeholder">Loading the day…</p>
        )}
      </div>
    </div>
  );
}
