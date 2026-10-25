// Buffer back-test: does a buffer fitted for N% coverage on early January deliver N% on late January?

import { scaleLinear } from "d3-scale";
import { useState } from "react";
import type { BufferRow } from "../api/client";
import { num, pct } from "../lib/format";
import { Figure, Tooltip, TooltipRow, useWidth } from "./primitives";

export function Calibration({ rows, selected }: { rows: readonly BufferRow[]; selected: number }) {
  const [ref, width] = useWidth(480);
  const [active, setActive] = useState<number | null>(null);
  const margin = { top: 24, right: 24, bottom: 40, left: 48 };
  const w = Math.max(160, width - margin.left - margin.right);
  const h = 230;
  const x = scaleLinear().domain([40, 100]).range([0, w]);
  const y = scaleLinear().domain([0, 100]).range([h, 0]);
  const ticks = [40, 60, 80, 100];
  const yTicks = [0, 25, 50, 75, 100];

  const table = (
    <table className="data-table">
      <thead>
        <tr>
          <th scope="col">Target</th>
          <th scope="col">Buffer, MW</th>
          <th scope="col">Fit coverage</th>
          <th scope="col">Test coverage</th>
          <th scope="col">95% interval</th>
          <th scope="col">Refit on all days, MW</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.target_pct}>
            <th scope="row">{r.target_pct}%</th>
            <td>{num(r.buffer_mw)}</td>
            <td>{pct(r.fit_coverage)}</td>
            <td>{pct(r.test_coverage)}</td>
            <td>
              {pct(r.test_coverage_low)}–{pct(r.test_coverage_high)}
            </td>
            <td>{num(r.full_month_buffer_mw)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );

  const a = rows.find((r) => r.target_pct === active);
  const s = rows.find((r) => r.target_pct === selected);
  return (
    <Figure
      title="Does the buffer hold out of sample?"
      caption="Each buffer was fitted on the first half of the month for a target share of half-hours, then applied unchanged to the second half. On the diagonal it delivers what it promised; whiskers are 95% intervals from resampling whole days."
      table={table}
    >
      <div className="chart" ref={ref}>
        <svg width={width} height={h + margin.top + margin.bottom} role="img" aria-label="Realised test coverage against target coverage">
          <g transform={`translate(${margin.left},${margin.top})`}>
            <text className="axis-title" x={-margin.left} y={-12}>
              Covered on test days
            </text>
            {yTicks.map((t) => (
              <g key={t} transform={`translate(0,${y(t)})`} aria-hidden="true">
                <line className={t === 0 ? "baseline" : "grid"} x1={0} x2={w} />
                <text className="tick" x={-8} dy="0.32em" textAnchor="end">
                  {t}%
                </text>
              </g>
            ))}
            {ticks.map((t) => (
              <text key={t} className="tick" x={x(t)} y={h + 18} textAnchor="middle" aria-hidden="true">
                {t}%
              </text>
            ))}
            <text className="axis-title" x={w / 2} y={h + 36} textAnchor="middle">
              Target coverage
            </text>
            <line className="diagonal" x1={x(40)} y1={y(40)} x2={x(100)} y2={y(100)} />
            {rows.map((r) => {
              const cx = x(r.target_pct);
              const on = r.target_pct === selected;
              return (
                <g
                  key={r.target_pct}
                  className={`calibration-point${on ? " is-selected" : ""}${active === r.target_pct ? " is-active" : ""}`}
                  tabIndex={0}
                  aria-label={`Target ${r.target_pct}%: buffer ${num(r.buffer_mw)} MW covered ${pct(r.test_coverage)} of test half-hours (95% interval ${pct(r.test_coverage_low)} to ${pct(r.test_coverage_high)})`}
                  onPointerEnter={() => {
                    setActive(r.target_pct);
                  }}
                  onPointerLeave={() => {
                    setActive(null);
                  }}
                  onFocus={() => {
                    setActive(r.target_pct);
                  }}
                  onBlur={() => {
                    setActive(null);
                  }}
                >
                  <rect className="row-hit" x={cx - 14} y={0} width={28} height={h} />
                  <line className="whisker" x1={cx} x2={cx} y1={y(r.test_coverage_low * 100)} y2={y(r.test_coverage_high * 100)} />
                  <circle className="median-dot" cx={cx} cy={y(r.test_coverage * 100)} r={on ? 6 : 4.5} />
                </g>
              );
            })}
            {s ? (
              <text
                className="point-label point-label-strong halo"
                x={x(s.target_pct) - 12}
                y={y(s.test_coverage * 100)}
                dy="0.32em"
                textAnchor="end"
                aria-hidden="true"
              >
                {pct(s.test_coverage)}
              </text>
            ) : null}
          </g>
        </svg>
        {a ? (
          <Tooltip x={margin.left + x(a.target_pct)} y={margin.top + y(a.test_coverage_high * 100)} width={width}>
            <div className="tooltip-title">Target {a.target_pct}%</div>
            <TooltipRow value={`${num(a.buffer_mw)} MW`} label="buffer, fitted 2–16 Jan" />
            <TooltipRow value={pct(a.test_coverage)} label="covered, 17 Jan–1 Feb" swatch="var(--forecast)" />
            <TooltipRow value={`${pct(a.test_coverage_low)}–${pct(a.test_coverage_high)}`} label="95% interval" />
          </Tooltip>
        ) : null}
      </div>
    </Figure>
  );
}
