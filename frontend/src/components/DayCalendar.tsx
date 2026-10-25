// Month calendar of delivery days, shaded by that day's MAE at the current cutoff. Doubles as the day picker.

import { useRef } from "react";
import type { DaySummary } from "../api/client";
import { num, shortDeliveryDate, signed } from "../lib/format";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const STEPS = ["--seq-100", "--seq-200", "--seq-300", "--seq-400", "--seq-500"] as const;
export const MAE_EDGES = [1000, 1500, 2000, 3000]; // bin edges in MW

export function maeStep(maeMw: number): number {
  const i = MAE_EDGES.findIndex((edge) => maeMw < edge);
  return i === -1 ? STEPS.length - 1 : i;
}

function isoDay(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function binLabel(i: number): string {
  if (i === 0) return `under ${num(MAE_EDGES[0] ?? 0)}`;
  if (i === STEPS.length - 1) return `${num(MAE_EDGES[MAE_EDGES.length - 1] ?? 0)}+`;
  return `${num(MAE_EDGES[i - 1] ?? 0)}–${num(MAE_EDGES[i] ?? 0)}`;
}

interface Props {
  days: readonly string[];
  summaries: readonly DaySummary[] | undefined;
  selected: string;
  onSelect: (day: string) => void;
}

export function DayCalendar({ days, summaries, selected, onSelect }: Props) {
  const grid = useRef<HTMLDivElement>(null);
  const byDay = new Map(summaries?.map((s) => [s.delivery_day, s]));
  const first = new Date(`${days[0] ?? "2026-01-02"}T00:00:00Z`);
  const last = new Date(`${days[days.length - 1] ?? "2026-02-01"}T00:00:00Z`);
  const start = new Date(first);
  start.setUTCDate(first.getUTCDate() - ((first.getUTCDay() + 6) % 7)); // back to Monday
  const cells: Date[] = [];
  for (let d = new Date(start); d <= last || cells.length % 7 !== 0; d.setUTCDate(d.getUTCDate() + 1)) {
    cells.push(new Date(d));
  }
  const inRange = new Set(days);

  function move(delta: number) {
    const next = days[days.indexOf(selected) + delta];
    if (!next) return;
    onSelect(next);
    requestAnimationFrame(() => {
      grid.current?.querySelector<HTMLButtonElement>(`[data-day="${next}"]`)?.focus();
    });
  }

  return (
    <div className="calendar">
      <div className="calendar-grid" role="grid" aria-label="Delivery days, shaded by mean absolute error" ref={grid}>
        <div role="row" className="calendar-row">
          {WEEKDAYS.map((w) => (
            <span role="columnheader" key={w} className="calendar-weekday">
              {w}
            </span>
          ))}
        </div>
        {Array.from({ length: cells.length / 7 }, (_, row) => (
          <div role="row" className="calendar-row" key={row}>
            {cells.slice(row * 7, row * 7 + 7).map((d) => {
              const day = isoDay(d);
              if (!inRange.has(day)) return <span role="gridcell" key={day} className="calendar-cell is-outside" />;
              const s = byDay.get(day);
              const isSelected = day === selected;
              const label = s
                ? `${shortDeliveryDate(day)}: MAE ${num(s.stats.mae_mw)} MW, mean error ${signed(s.stats.mean_error_mw)} MW (${s.sample} day)`
                : shortDeliveryDate(day);
              const stepIndex = s ? maeStep(s.stats.mae_mw) : undefined;
              return (
                <button
                  type="button"
                  role="gridcell"
                  key={day}
                  data-day={day}
                  data-step={stepIndex}
                  aria-selected={isSelected}
                  aria-label={label}
                  title={label}
                  tabIndex={isSelected ? 0 : -1}
                  className={`calendar-cell${isSelected ? " is-selected" : ""}`}
                  style={stepIndex !== undefined ? { background: `var(${STEPS[stepIndex] ?? "--seq-100"})` } : undefined}
                  onClick={() => {
                    onSelect(day);
                  }}
                  onKeyDown={(e) => {
                    const delta = ({ ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 } as Record<string, number>)[e.key];
                    if (delta !== undefined) {
                      e.preventDefault();
                      move(delta);
                    }
                  }}
                >
                  <span className="calendar-date">{d.getUTCDate()}</span>
                </button>
              );
            })}
          </div>
        ))}
      </div>
      <div className="calendar-legend">
        <span className="legend-title">MAE, MW</span>
        {STEPS.map((s, i) => (
          <span key={s} className="legend-step">
            <span className="legend-swatch" style={{ background: `var(${s})` }} aria-hidden="true" />
            {binLabel(i)}
          </span>
        ))}
      </div>
    </div>
  );
}
