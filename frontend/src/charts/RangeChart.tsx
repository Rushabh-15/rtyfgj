// Error distribution per group: P10-P90 whisker, P50 dot, mean tick. Rows are groups (forecast level, lead time).

import { scaleLinear } from "d3-scale";
import { useState } from "react";
import type { Breakdown } from "../api/client";
import { gwTick, num, signed } from "../lib/format";
import { Figure, Tooltip, TooltipRow, niceTicks, tickDomain, useWidth } from "./primitives";

interface Props {
  title: string;
  caption: string;
  rows: readonly Breakdown[];
  buffer: number;
  coverage: number;
}

export function RangeChart({ title, caption, rows, buffer, coverage }: Props) {
  const [ref, width] = useWidth(560);
  const [active, setActive] = useState<number | null>(null);
  const present = rows.filter((r) => r.stats);
  const margin = { top: 22, right: 16, bottom: 28, left: 92 };
  const rowH = 34;
  const h = present.length * rowH;
  const height = h + margin.top + margin.bottom;
  const w = Math.max(120, width - margin.left - margin.right);
  const lo = Math.min(0, ...present.map((r) => r.stats?.p10_mw ?? 0));
  const hi = Math.max(buffer, ...present.map((r) => r.stats?.p90_mw ?? 0));
  const ticks = niceTicks(lo, hi, w < 320 ? 3 : 5);
  const x = scaleLinear().domain(tickDomain(ticks)).range([0, w]);

  const table = (
    <table className="data-table">
      <thead>
        <tr>
          <th scope="col">Group</th>
          <th scope="col">Half-hours</th>
          <th scope="col">Mean error</th>
          <th scope="col">MAE</th>
          <th scope="col">P10</th>
          <th scope="col">P50</th>
          <th scope="col">P90</th>
        </tr>
      </thead>
      <tbody>
        {present.map((r) =>
          r.stats ? (
            <tr key={r.label}>
              <th scope="row">{r.label}</th>
              <td>{num(r.stats.n)}</td>
              <td>{signed(r.stats.mean_error_mw)}</td>
              <td>{num(r.stats.mae_mw)}</td>
              <td>{signed(r.stats.p10_mw)}</td>
              <td>{signed(r.stats.p50_mw)}</td>
              <td>{signed(r.stats.p90_mw)}</td>
            </tr>
          ) : null,
        )}
      </tbody>
    </table>
  );

  const a = active === null ? undefined : present[active];
  return (
    <Figure title={title} caption={caption} table={table}>
      <div className="chart" ref={ref}>
        <svg width={width} height={height} role="img" aria-label={`${title}: shortfall P10 to P90 by group`}>
          <g transform={`translate(${margin.left},${margin.top})`}>
            {ticks.map((t) => (
              <g key={t} transform={`translate(${x(t)},0)`} aria-hidden="true">
                <line className={t === 0 ? "baseline-v" : "grid"} y1={0} y2={h} />
                <text className="tick" y={h + 18} textAnchor="middle">
                  {gwTick(t)}
                </text>
              </g>
            ))}
            <line className="buffer-line" x1={x(buffer)} x2={x(buffer)} y1={-10} y2={h} />
            <text className="buffer-label" x={x(buffer)} y={-12} textAnchor={x(buffer) > w - 60 ? "end" : "middle"}>
              {coverage}% buffer
            </text>
            {present.map((r, i) => {
              const s = r.stats;
              if (!s) return null;
              const cy = i * rowH + rowH / 2;
              return (
                <g
                  key={r.label}
                  className={`range-row${active === i ? " is-active" : ""}`}
                  tabIndex={0}
                  aria-label={`${r.label}: P10 ${signed(s.p10_mw)}, median ${signed(s.p50_mw)}, P90 ${signed(s.p90_mw)}, mean ${signed(s.mean_error_mw)} MW, ${s.n} half-hours`}
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
                >
                  <rect className="row-hit" x={-margin.left} y={i * rowH} width={w + margin.left} height={rowH} />
                  <text className="row-label" x={-10} y={cy} dy="0.32em" textAnchor="end">
                    {r.label}
                  </text>
                  <line className="whisker" x1={x(s.p10_mw)} x2={x(s.p90_mw)} y1={cy} y2={cy} />
                  <line className="mean-tick" x1={x(s.mean_error_mw)} x2={x(s.mean_error_mw)} y1={cy - 8} y2={cy + 8} />
                  <circle className="median-dot" cx={x(s.p50_mw)} cy={cy} r={5} />
                </g>
              );
            })}
          </g>
        </svg>
        {a?.stats ? (
          <Tooltip x={margin.left + x(a.stats.p90_mw)} y={margin.top + present.indexOf(a) * rowH} width={width}>
            <div className="tooltip-title">{a.label}</div>
            <TooltipRow value={`${signed(a.stats.p50_mw)} MW`} label="median shortfall" swatch="var(--forecast)" />
            <TooltipRow value={`${signed(a.stats.p10_mw)} to ${signed(a.stats.p90_mw)} MW`} label="P10 to P90" />
            <TooltipRow value={`${signed(a.stats.mean_error_mw)} MW`} label="mean error" swatch="var(--ink)" />
            <TooltipRow value={num(a.stats.n)} label="half-hours" />
          </Tooltip>
        ) : null}
      </div>
      <ul className="legend legend-quiet" aria-label="Legend">
        <li>
          <span className="key-whisker" aria-hidden="true" />
          P10–P90
        </li>
        <li>
          <span className="key-dot" aria-hidden="true" />
          Median
        </li>
        <li>
          <span className="key-tick" aria-hidden="true" />
          Mean
        </li>
      </ul>
    </Figure>
  );
}
