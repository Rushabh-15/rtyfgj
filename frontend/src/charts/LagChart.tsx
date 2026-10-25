// Timing check: error spread (mean removed) when the outturn is shifted against the forecast.

import { scaleLinear } from "d3-scale";
import { useState } from "react";
import type { LagPoint } from "../api/client";
import { num, signedMinutes } from "../lib/format";
import { Figure, Tooltip, TooltipRow, niceTicks, tickDomain, useWidth } from "./primitives";

interface Props {
  atCutoff: readonly LagPoint[];
  shortLead: readonly LagPoint[];
  cutoff: string;
}

function best(points: readonly LagPoint[]): number {
  return points.reduce((a, b) => (b.sd_mw < a.sd_mw ? b : a), points[0] ?? { shift_minutes: 0, sd_mw: 0 }).shift_minutes;
}

export function LagChart({ atCutoff, shortLead, cutoff }: Props) {
  const [ref, width] = useWidth(480);
  const [active, setActive] = useState<number | null>(null);
  const margin = { top: 24, right: 76, bottom: 40, left: 52 };
  const w = Math.max(120, width - margin.left - margin.right);
  const h = 220;
  const all = [...atCutoff, ...shortLead].map((p) => p.sd_mw);
  const ticks = niceTicks(Math.min(...all), Math.max(...all), 6);
  const x = scaleLinear().domain([-120, 120]).range([0, w]);
  const y = scaleLinear().domain(tickDomain(ticks)).range([h, 0]);
  const series = [
    { name: `At ${cutoff} cutoff`, short: "At cutoff", points: atCutoff, cls: "lag-cutoff" },
    { name: "All runs, under 6 h ahead", short: "Under 6 h", points: shortLead, cls: "lag-short" },
  ];
  const path = (pts: readonly LagPoint[]) =>
    pts.map((p, i) => `${i === 0 ? "M" : "L"}${x(p.shift_minutes)},${y(p.sd_mw)}`).join("");
  const step = atCutoff.length > 1 ? x(atCutoff[1]?.shift_minutes ?? 0) - x(atCutoff[0]?.shift_minutes ?? 0) : w;

  const table = (
    <table className="data-table">
      <thead>
        <tr>
          <th scope="col">Shift, min</th>
          <th scope="col">At cutoff: SD, MW</th>
          <th scope="col">At cutoff: MAE, MW</th>
          <th scope="col">Under 6 h: SD, MW</th>
          <th scope="col">Under 6 h: MAE, MW</th>
        </tr>
      </thead>
      <tbody>
        {atCutoff.map((p, i) => (
          <tr key={p.shift_minutes}>
            <th scope="row">{signedMinutes(p.shift_minutes)}</th>
            <td>{num(p.sd_mw)}</td>
            <td>{num(p.mae_mw)}</td>
            <td>{num(shortLead[i]?.sd_mw ?? 0)}</td>
            <td>{num(shortLead[i]?.mae_mw ?? 0)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );

  const at = active === null ? undefined : atCutoff.find((p) => p.shift_minutes === active);
  const sl = active === null ? undefined : shortLead.find((p) => p.shift_minutes === active);
  return (
    <Figure
      title="Timing check"
      caption={`Error spread with the mean removed, comparing the forecast for each half-hour with the outturn shifted by up to two hours. It is lowest at ${signedMinutes(best(atCutoff))} min at the cutoff and ${signedMinutes(best(shortLead))} min for short leads, not at zero, but the curve is shallow; the app keeps Elexon's hour-start labelling.`}
      table={table}
    >
      <div className="chart" ref={ref}>
        <svg width={width} height={h + margin.top + margin.bottom} role="img" aria-label="Lag scan of error spread against time shift">
          <g transform={`translate(${margin.left},${margin.top})`}>
            <text className="axis-title" x={-margin.left} y={-12}>
              Error spread (SD), MW
            </text>
            {ticks.map((t) => (
              <g key={t} transform={`translate(0,${y(t)})`} aria-hidden="true">
                <line className="grid" x1={0} x2={w} />
                <text className="tick" x={-8} dy="0.32em" textAnchor="end">
                  {num(t)}
                </text>
              </g>
            ))}
            {[-120, -60, 0, 60, 120].map((t) => (
              <text key={t} className="tick" x={x(t)} y={h + 18} textAnchor="middle" aria-hidden="true">
                {signedMinutes(t)}
              </text>
            ))}
            <text className="axis-title" x={w / 2} y={h + 36} textAnchor="middle">
              Outturn shift, minutes
            </text>
            <line className="baseline-v" x1={x(0)} x2={x(0)} y1={0} y2={h} />
            {active !== null ? <line className="crosshair-line" x1={x(active)} x2={x(active)} y1={0} y2={h} /> : null}
            {series.map((s) => {
              const lastPoint = s.points[s.points.length - 1];
              return (
                <g key={s.name} className={s.cls}>
                  <path className="lag-line" d={path(s.points)} />
                  {s.points.map((p) => (
                    <circle
                      key={p.shift_minutes}
                      className="lag-dot"
                      cx={x(p.shift_minutes)}
                      cy={y(p.sd_mw)}
                      r={p.shift_minutes === active ? 5.5 : 4}
                    />
                  ))}
                  {lastPoint ? (
                    <text className="end-label" x={w + 8} y={y(lastPoint.sd_mw)} dy="0.32em">
                      {s.short}
                    </text>
                  ) : null}
                </g>
              );
            })}
            {atCutoff.map((p) => (
              <rect
                key={p.shift_minutes}
                className="hit-area"
                x={x(p.shift_minutes) - step / 2}
                y={0}
                width={step}
                height={h}
                tabIndex={0}
                aria-label={`Shift ${signedMinutes(p.shift_minutes)} min: spread ${num(p.sd_mw)} MW at the cutoff, ${num(shortLead.find((q) => q.shift_minutes === p.shift_minutes)?.sd_mw ?? 0)} MW under 6 h`}
                onPointerEnter={() => {
                  setActive(p.shift_minutes);
                }}
                onPointerLeave={() => {
                  setActive(null);
                }}
                onFocus={() => {
                  setActive(p.shift_minutes);
                }}
                onBlur={() => {
                  setActive(null);
                }}
              />
            ))}
          </g>
        </svg>
        {at && active !== null ? (
          <Tooltip x={margin.left + x(active)} y={margin.top + y(Math.max(at.sd_mw, sl?.sd_mw ?? 0))} width={width}>
            <div className="tooltip-title">Outturn shifted {signedMinutes(active)} min</div>
            <TooltipRow value={`${num(at.sd_mw)} MW`} label={`spread at the ${cutoff} cutoff`} swatch="var(--forecast)" />
            {sl ? <TooltipRow value={`${num(sl.sd_mw)} MW`} label="spread, under 6 h ahead" swatch="var(--ink-2)" /> : null}
          </Tooltip>
        ) : null}
      </div>
      <ul className="legend legend-quiet" aria-label="Legend">
        {series.map((s) => (
          <li key={s.name}>
            <span className={`line-key ${s.cls}-key`} aria-hidden="true" />
            {s.name}
          </li>
        ))}
      </ul>
    </Figure>
  );
}
