// One delivery day, half-hour by half-hour: the forecast the desk had at the cutoff against what the wind did.

import { scaleLinear, scaleUtc } from "d3-scale";
import { useState, type KeyboardEvent, type PointerEvent } from "react";
import type { DayView } from "../api/client";
import { Figure, Tooltip, TooltipRow, XAxis, YGrid, niceTicks, tickDomain, useWidth } from "../charts/primitives";
import { num, signed, ukTime } from "../lib/format";

const HALF_HOUR = 30 * 60 * 1000;

function stepPath(xs: number[], ys: number[], end: number): string {
  if (xs.length === 0) return "";
  let d = `M${xs[0]},${ys[0]}`;
  for (let i = 0; i < xs.length; i += 1) {
    const next = i + 1 < xs.length ? xs[i + 1] : end;
    d += `H${next}`;
    if (i + 1 < ys.length) d += `V${ys[i + 1]}`;
  }
  return d;
}

/**
 * @param yMax the top of the scale, fixed across days and cutoffs (the highest value in the month) so that
 *   flicking between days compares like with like.
 */
export function DayChart({ day, yMax }: { day: DayView; yMax: number }) {
  const [ref, width] = useWidth(820);
  const [active, setActive] = useState<number | null>(null);
  const narrow = width < 560;
  const margin = { top: 12, right: narrow ? 12 : 84, bottom: 34, left: 48 };
  const height = narrow ? 260 : 340;
  const w = Math.max(120, width - margin.left - margin.right);
  const h = height - margin.top - margin.bottom;

  const start = Date.parse(day.window_utc[0] ?? "");
  const end = Date.parse(day.window_utc[1] ?? "");
  const x = scaleUtc().domain([start, end]).range([0, w]);
  const max = Math.max(yMax, ...day.periods.flatMap((p) => [p.forecast_mw, p.actual_mw]));
  const yTicks = niceTicks(0, max, 5);
  const y = scaleLinear().domain(tickDomain(yTicks)).range([h, 0]);

  const xs = day.periods.map((p) => x(Date.parse(p.start_utc)));
  const forecast = day.periods.map((p) => y(p.forecast_mw));
  const outturn = day.periods.map((p) => y(p.actual_mw));
  const plan = day.periods.map((p) => y(Math.max(0, p.procure_for_mw)));
  const gap = day.periods
    .map((p, i) => {
      const x0 = xs[i] ?? 0;
      const x1 = xs[i + 1] ?? w;
      return `M${x0},${y(p.forecast_mw)}H${x1}V${y(p.actual_mw)}H${x0}Z`;
    })
    .join("");

  const hourTicks: number[] = [];
  const tickHours = narrow ? 6 : 3;
  for (let t = start; t <= end; t += tickHours * 2 * HALF_HOUR) hourTicks.push(t);
  const last = day.periods.length - 1;
  const endForecast = forecast[last] ?? 0;
  const endOutturn = outturn[last] ?? 0;
  const labelsFit = !narrow && Math.abs(endForecast - endOutturn) >= 14;
  const run = day.runs[0]?.publish_time_utc;

  function pick(event: PointerEvent<SVGRectElement>) {
    const box = event.currentTarget.getBoundingClientRect();
    const i = Math.floor(((event.clientX - box.left) / box.width) * day.periods.length);
    setActive(Math.min(day.periods.length - 1, Math.max(0, i)));
  }

  function keys(event: KeyboardEvent<HTMLDivElement>) {
    const n = day.periods.length;
    const moves: Record<string, (i: number) => number> = {
      ArrowRight: (i) => Math.min(n - 1, i + 1),
      ArrowLeft: (i) => Math.max(0, i - 1),
      Home: () => 0,
      End: () => n - 1,
    };
    const move = moves[event.key];
    if (move) {
      event.preventDefault();
      setActive((i) => move(i ?? 0));
    } else if (event.key === "Escape") {
      setActive(null);
    }
  }

  const p = active === null ? undefined : day.periods[active];
  const activeX = active === null ? 0 : (xs[active] ?? 0) + x(start + HALF_HOUR) / 2;

  const table = (
    <table className="data-table">
      <thead>
        <tr>
          <th scope="col">Half-hour (UK)</th>
          <th scope="col">SP</th>
          <th scope="col">Forecast, MW</th>
          <th scope="col">Outturn, MW</th>
          <th scope="col">Shortfall, MW</th>
          <th scope="col">Run (UTC)</th>
          <th scope="col">Lead, h</th>
          <th scope="col">Within buffer</th>
        </tr>
      </thead>
      <tbody>
        {day.periods.map((row) => (
          <tr key={row.start_utc}>
            <th scope="row">{ukTime(row.start_utc)}</th>
            <td>{row.settlement_period}</td>
            <td>{num(row.forecast_mw)}</td>
            <td>{num(row.actual_mw)}</td>
            <td>{signed(row.error_mw)}</td>
            <td>{row.publish_time_utc.slice(11, 16)}</td>
            <td>{row.lead_hours.toFixed(1)}</td>
            <td>{row.covered ? "yes" : "no"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );

  return (
    <Figure
      title="Forecast at the cutoff vs outturn"
      caption={
        <>
          Each hourly WINDFOR value covers the two half-hours starting at its label. The shaded gap is the error; the
          dashed line is the forecast minus the {day.coverage_pct}% buffer ({num(day.buffer_mw)} MW).
        </>
      }
      table={table}
    >
      <ul className="legend" aria-label="Legend">
        <li>
          <span className="line-key" style={{ background: "var(--forecast)" }} aria-hidden="true" />
          Forecast at cutoff{run ? ` (${run.slice(11, 16)} run)` : ""}
        </li>
        <li>
          <span className="line-key" style={{ background: "var(--outturn)" }} aria-hidden="true" />
          Outturn (FUELHH wind)
        </li>
        <li>
          <span className="line-key line-key-dashed" aria-hidden="true" />
          Plan for: forecast − buffer
        </li>
      </ul>
      <div
        className="chart"
        ref={ref}
        tabIndex={0}
        role="application"
        aria-label="Half-hourly chart. Use the left and right arrow keys to read each half-hour."
        onKeyDown={keys}
        onBlur={() => {
          setActive(null);
        }}
      >
        <svg width={width} height={height} aria-hidden="true">
          <g transform={`translate(${margin.left},${margin.top})`}>
            <YGrid ticks={yTicks} position={y} label={(t) => (t === 0 ? "0" : `${t / 1000} GW`)} width={w} />
            <path className="gap-wash" d={gap} />
            <path className="series-plan" d={stepPath(xs, plan, w)} />
            <path className="series-outturn" d={stepPath(xs, outturn, w)} />
            <path className="series-forecast" d={stepPath(xs, forecast, w)} />
            <XAxis ticks={hourTicks} position={(t) => x(t)} label={(t) => ukTime(new Date(t).toISOString())} height={h} width={w} />
            {labelsFit ? (
              <g className="end-labels">
                <text x={w + 8} y={endForecast} dy="0.32em">
                  Forecast
                </text>
                <text x={w + 8} y={endOutturn} dy="0.32em">
                  Outturn
                </text>
              </g>
            ) : null}
            {p ? (
              <g className="crosshair">
                <line x1={activeX} x2={activeX} y1={0} y2={h} />
                <circle cx={activeX} cy={y(p.forecast_mw)} r={4} className="dot-forecast" />
                <circle cx={activeX} cy={y(p.actual_mw)} r={4} className="dot-outturn" />
              </g>
            ) : null}
            <rect
              className="hit-area"
              width={w}
              height={h}
              onPointerMove={pick}
              onPointerLeave={() => {
                setActive(null);
              }}
            />
          </g>
        </svg>
        {p ? (
          <Tooltip x={margin.left + activeX} y={margin.top + Math.min(y(p.forecast_mw), y(p.actual_mw))} width={width}>
            <div className="tooltip-title">
              {ukTime(p.start_utc)}–{ukTime(new Date(Date.parse(p.start_utc) + HALF_HOUR).toISOString())} UK, SP{" "}
              {p.settlement_period}
            </div>
            <TooltipRow value={`${num(p.forecast_mw)} MW`} label={`forecast, ${p.lead_hours.toFixed(1)} h ahead`} swatch="var(--forecast)" />
            <TooltipRow value={`${num(p.actual_mw)} MW`} label="outturn" swatch="var(--outturn)" />
            <TooltipRow
              value={`${signed(p.error_mw)} MW`}
              label={p.error_mw > 0 ? (p.covered ? "shortfall, within buffer" : "shortfall, beyond buffer") : "surplus"}
            />
          </Tooltip>
        ) : null}
      </div>
    </Figure>
  );
}
