// Shortfall distribution for each delivery day, with the buffer as a reference line and the fit/test split.

import { scaleBand, scaleLinear } from "d3-scale";
import { useState } from "react";
import type { DaySummary } from "../api/client";
import { gwTick, num, shortDeliveryDate, signed } from "../lib/format";
import { Figure, Tooltip, TooltipRow, niceTicks, tickDomain, useWidth } from "./primitives";

interface Props {
  days: readonly DaySummary[];
  buffer: number;
  coverage: number;
  onSelectDay: (day: string) => void;
}

export function DailyBands({ days, buffer, coverage, onSelectDay }: Props) {
  const [ref, width] = useWidth(820);
  const [active, setActive] = useState<number | null>(null);
  const narrow = width < 560;
  const margin = { top: 28, right: 12, bottom: 30, left: 56 };
  const height = narrow ? 260 : 300;
  const w = Math.max(120, width - margin.left - margin.right);
  const h = height - margin.top - margin.bottom;
  const lo = Math.min(0, ...days.map((d) => d.stats.p10_mw));
  const hi = Math.max(buffer, ...days.map((d) => d.stats.p90_mw));
  const ticks = niceTicks(lo, hi, 5);
  const y = scaleLinear().domain(tickDomain(ticks)).range([h, 0]);
  const x = scaleBand()
    .domain(days.map((d) => d.delivery_day))
    .range([0, w])
    .padding(0.3);
  const firstTest = days.find((d) => d.sample === "test")?.delivery_day;
  const split = firstTest ? (x(firstTest) ?? 0) - (x.step() * x.padding()) / 2 : w;
  const labelEvery = narrow ? 7 : 3;

  const table = (
    <table className="data-table">
      <thead>
        <tr>
          <th scope="col">Delivery day</th>
          <th scope="col">Sample</th>
          <th scope="col">Mean error</th>
          <th scope="col">MAE</th>
          <th scope="col">P10</th>
          <th scope="col">P50</th>
          <th scope="col">P90</th>
        </tr>
      </thead>
      <tbody>
        {days.map((d) => (
          <tr key={d.delivery_day}>
            <th scope="row">{shortDeliveryDate(d.delivery_day)}</th>
            <td>{d.sample}</td>
            <td>{signed(d.stats.mean_error_mw)}</td>
            <td>{num(d.stats.mae_mw)}</td>
            <td>{signed(d.stats.p10_mw)}</td>
            <td>{signed(d.stats.p50_mw)}</td>
            <td>{signed(d.stats.p90_mw)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );

  const a = active === null ? undefined : days[active];
  return (
    <Figure
      wide
      title="Shortfall by delivery day"
      caption={`Whiskers span each day's P10 to P90 half-hourly shortfall, dots mark the median. Where a whisker crosses the line, more than 10% of that day's half-hours needed more than the ${coverage}% buffer.`}
      table={table}
    >
      <div className="chart" ref={ref}>
        <svg width={width} height={height} role="img" aria-label="Daily shortfall ranges against the buffer">
          <g transform={`translate(${margin.left},${margin.top})`}>
            <rect className="band-fit" x={0} y={-margin.top + 4} width={split} height={h + margin.top - 4} />
            <text className="band-label" x={6} y={-12}>
              {narrow ? "Fit days" : "Fit: buffer set on these days"}
            </text>
            <text className="band-label" x={split + 6} y={-12}>
              {narrow ? "Test days" : "Test: buffer applied unchanged"}
            </text>
            {ticks.map((t) => (
              <g key={t} transform={`translate(0,${y(t)})`} aria-hidden="true">
                <line className={t === 0 ? "baseline" : "grid"} x1={0} x2={w} />
                <text className="tick" x={-8} dy="0.32em" textAnchor="end">
                  {gwTick(t)}
                </text>
              </g>
            ))}
            <line className="buffer-line" x1={0} x2={w} y1={y(buffer)} y2={y(buffer)} />
            {days.map((d, i) => {
              const cx = (x(d.delivery_day) ?? 0) + x.bandwidth() / 2;
              const beyond = d.stats.p90_mw > buffer;
              return (
                <g
                  key={d.delivery_day}
                  className={`day-band${active === i ? " is-active" : ""}`}
                  tabIndex={0}
                  role="button"
                  aria-label={`${shortDeliveryDate(d.delivery_day)}: median shortfall ${signed(d.stats.p50_mw)} MW, P10 to P90 ${signed(d.stats.p10_mw)} to ${signed(d.stats.p90_mw)} MW. Open the day.`}
                  onPointerEnter={() => {
                    setActive(i);
                  }}
                  onPointerLeave={() => {
                    setActive(null);
                  }}
                  onFocus={() => {
                    setActive(i);
                  }}
                  onBlur={() => {
                    setActive(null);
                  }}
                  onClick={() => {
                    onSelectDay(d.delivery_day);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSelectDay(d.delivery_day);
                    }
                  }}
                >
                  <rect className="row-hit" x={cx - x.step() / 2} y={0} width={x.step()} height={h} />
                  <line className={beyond ? "whisker whisker-beyond" : "whisker"} x1={cx} x2={cx} y1={y(d.stats.p10_mw)} y2={y(d.stats.p90_mw)} />
                  <circle className="median-dot" cx={cx} cy={y(d.stats.p50_mw)} r={4} />
                  {i % labelEvery === 0 ? (
                    <text className="tick" x={cx} y={h + 18} textAnchor="middle">
                      {Number(d.delivery_day.slice(8))}
                    </text>
                  ) : null}
                </g>
              );
            })}
            <text className="buffer-label halo" x={w} y={y(buffer) - 6} textAnchor="end" aria-hidden="true">
              {coverage}% buffer, {num(buffer)} MW
            </text>
          </g>
        </svg>
        {a ? (
          <Tooltip x={margin.left + (x(a.delivery_day) ?? 0)} y={margin.top + y(a.stats.p90_mw)} width={width}>
            <div className="tooltip-title">{shortDeliveryDate(a.delivery_day)}</div>
            <TooltipRow value={`${signed(a.stats.p50_mw)} MW`} label="median shortfall" swatch="var(--forecast)" />
            <TooltipRow value={`${signed(a.stats.p10_mw)} to ${signed(a.stats.p90_mw)} MW`} label="P10 to P90" />
            <TooltipRow value={`${num(a.stats.mae_mw)} MW`} label="MAE" />
          </Tooltip>
        ) : null}
      </div>
    </Figure>
  );
}
