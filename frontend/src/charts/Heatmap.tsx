// All forecast vintages: MAE by lead time (rows) and UK hour of day (columns). One sequential hue.

import { useState } from "react";
import type { Vintages } from "../api/client";
import { num, signed } from "../lib/format";
import { Figure, Tooltip, TooltipRow, useWidth } from "./primitives";

const STEPS = ["--seq-100", "--seq-200", "--seq-300", "--seq-400", "--seq-500", "--seq-600"] as const;

function edgesFor(values: number[], count: number): number[] {
  const sorted = [...values].sort((a, b) => a - b);
  const edges: number[] = [];
  for (let i = 1; i < count; i += 1) {
    const q = sorted[Math.floor((i / count) * (sorted.length - 1))] ?? 0;
    edges.push(Math.round(q / 50) * 50);
  }
  return [...new Set(edges)];
}

export function Heatmap({ vintages }: { vintages: Vintages }) {
  const [ref, width] = useWidth(820);
  const [active, setActive] = useState<string | null>(null);
  const leads = [...new Set(vintages.grid.map((c) => c.lead_lo))].sort((a, b) => a - b);
  const narrow = width < 560;
  const margin = { top: 8, right: 8, bottom: 30, left: narrow ? 58 : 70 };
  const w = Math.max(160, width - margin.left - margin.right);
  const cellW = w / 24;
  const cellH = narrow ? 18 : 22;
  const h = leads.length * cellH;
  const edges = edgesFor(vintages.grid.map((c) => c.mae_mw), STEPS.length);
  const bin = (v: number) => {
    const i = edges.findIndex((e) => v < e);
    return STEPS[i === -1 ? edges.length : i] ?? "--seq-600";
  };
  const cells = new Map(vintages.grid.map((c) => [`${c.lead_lo}-${c.hour_uk}`, c]));
  const a = active ? cells.get(active) : undefined;
  const bucket = vintages.grid_lead_bucket_h;

  const table = (
    <table className="data-table">
      <thead>
        <tr>
          <th scope="col">Lead</th>
          {Array.from({ length: 24 }, (_, hour) => (
            <th scope="col" key={hour}>
              {String(hour).padStart(2, "0")}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {leads.map((lead) => (
          <tr key={lead}>
            <th scope="row">
              {lead}–{lead + bucket} h
            </th>
            {Array.from({ length: 24 }, (_, hour) => {
              const c = cells.get(`${lead}-${hour}`);
              return <td key={hour}>{c ? num(c.mae_mw) : "–"}</td>;
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );

  return (
    <Figure
      wide
      title="Error by lead time and hour of day, every forecast run"
      caption={`MAE over all ${num(vintages.pairs)} run and half-hour pairs. Across hours MAE varies by ${num(vintages.hour_effect_mw)} MW, across lead times by ${num(vintages.lead_effect_mw)} MW (leads ${vintages.effect_leads_h[0] ?? 0}–${vintages.effect_leads_h[1] ?? 48} h): when the half-hour falls matters more than how early it was forecast.`}
      table={table}
    >
      <div className="chart" ref={ref}>
        <svg width={width} height={h + margin.top + margin.bottom} role="img" aria-label="Heatmap of MAE by lead time and hour of day">
          <g transform={`translate(${margin.left},${margin.top})`}>
            {leads.map((lead, row) => (
              <text key={lead} className="tick" x={-8} y={row * cellH + cellH / 2} dy="0.32em" textAnchor="end">
                {lead}–{lead + bucket} h
              </text>
            ))}
            {Array.from({ length: 24 }, (_, hour) =>
              hour % (narrow ? 6 : 3) === 0 ? (
                <text key={hour} className="tick" x={hour * cellW + cellW / 2} y={h + 18} textAnchor="middle">
                  {String(hour).padStart(2, "0")}:00
                </text>
              ) : null,
            )}
            {leads.map((lead, row) =>
              Array.from({ length: 24 }, (_, hour) => {
                const key = `${lead}-${hour}`;
                const c = cells.get(key);
                if (!c) return null;
                return (
                  <rect
                    key={key}
                    className={active === key ? "heat-cell is-active" : "heat-cell"}
                    x={hour * cellW + 1}
                    y={row * cellH + 1}
                    width={Math.max(1, cellW - 2)}
                    height={cellH - 2}
                    rx={2}
                    style={{ fill: `var(${bin(c.mae_mw)})` }}
                    tabIndex={hour === 0 && row === 0 ? 0 : -1}
                    aria-label={`Lead ${lead}–${lead + bucket} h, ${String(hour).padStart(2, "0")}:00 UK: MAE ${num(c.mae_mw)} MW`}
                    onPointerEnter={() => {
                      setActive(key);
                    }}
                    onPointerLeave={() => {
                      setActive(null);
                    }}
                    onFocus={() => {
                      setActive(key);
                    }}
                    onBlur={() => {
                      setActive(null);
                    }}
                  />
                );
              }),
            )}
          </g>
        </svg>
        {a ? (
          <Tooltip
            x={margin.left + a.hour_uk * cellW + cellW}
            y={margin.top + leads.indexOf(a.lead_lo) * cellH}
            width={width}
          >
            <div className="tooltip-title">
              {String(a.hour_uk).padStart(2, "0")}:00 UK, {a.lead_lo}–{a.lead_lo + bucket} h ahead
            </div>
            <TooltipRow value={`${num(a.mae_mw)} MW`} label="MAE" />
            <TooltipRow value={`${signed(a.mean_error_mw)} MW`} label="mean error" />
            <TooltipRow value={num(a.n)} label="pairs" />
          </Tooltip>
        ) : null}
      </div>
      <div className="calendar-legend" aria-hidden="true">
        <span className="legend-title">MAE, MW</span>
        {STEPS.slice(0, edges.length + 1).map((s, i) => (
          <span className="legend-step" key={s}>
            <span className="legend-swatch" style={{ background: `var(${s})` }} />
            {i === 0 ? `under ${num(edges[0] ?? 0)}` : i === edges.length ? `${num(edges[edges.length - 1] ?? 0)}+` : `${num(edges[i - 1] ?? 0)}–${num(edges[i] ?? 0)}`}
          </span>
        ))}
      </div>
    </Figure>
  );
}
