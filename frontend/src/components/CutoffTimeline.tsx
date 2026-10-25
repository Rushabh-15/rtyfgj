// The decision timeline for D-1: forecast publications, auction gate closures and the adjustable cutoff.
// This is the one bold element of the interface; everything else stays quiet around it.

import { useId, useState } from "react";
import type { Marker } from "../api/client";
import { useWidth } from "../charts/primitives";
import { clockMinutes, duration } from "../lib/format";

const DOMAIN_START = 2 * 60; // 02:00 UK on D-1
const DOMAIN_END = 17 * 60; // 17:00

interface Props {
  cutoffs: readonly string[];
  cutoff: string;
  markers: readonly Marker[];
  /** Regular slots (UK HH:MM) not published on the bid day shown, drawn as missing. */
  missing: readonly string[];
  /** UK clock time of the run actually used (HH:MM), with a note when it differs from the regular slot. */
  runInUse: string | undefined;
  runNote: string | undefined;
  onChange: (cutoff: string) => void;
}

function shortGateLabel(label: string): string {
  return label
    .replace("EPEX GB 60-min auction", "EPEX 60-min")
    .replace("EPEX GB 30-min auction", "EPEX 30-min")
    .replace("Nord Pool GB hourly auction", "Nord Pool hourly")
    .replace("Nord Pool GB half-hourly auction", "Nord Pool half-hourly");
}

export function CutoffTimeline({ cutoffs, cutoff, markers, missing, runInUse, runNote, onChange }: Props) {
  const [ref, width] = useWidth(960);
  const [focused, setFocused] = useState(false);
  const id = useId();
  const narrow = width < 640;
  const margin = { left: narrow ? 12 : 20, right: narrow ? 12 : 20 };
  const inner = Math.max(200, width - margin.left - margin.right);
  const x = (minutes: number) => margin.left + ((minutes - DOMAIN_START) / (DOMAIN_END - DOMAIN_START)) * inner;

  const cutoffMin = clockMinutes(cutoff);
  const index = Math.max(0, cutoffs.indexOf(cutoff));
  const runs = markers.filter((m) => m.kind === "run" && clockMinutes(m.time_uk) >= DOMAIN_START && clockMinutes(m.time_uk) <= DOMAIN_END);
  const gates = markers.filter((m) => m.kind === "gate");
  const runMin = runInUse ? clockMinutes(runInUse) : undefined;
  // A run published outside the regular slots (15 Jan 12:25) gets its own dot when it is the one in use.
  const offSchedule =
    runMin !== undefined && runInUse && !runs.some((r) => clockMinutes(r.time_uk) === runMin)
      ? { minutes: runMin, label: runInUse }
      : undefined;
  const nextGate = gates.find((g) => clockMinutes(g.time_uk) > cutoffMin);
  const missedGates = gates.filter((g) => clockMinutes(g.time_uk) <= cutoffMin);

  const trackY = 70;
  const hourStep = narrow ? 180 : 120;
  const hours: number[] = [];
  for (let m = DOMAIN_START; m <= DOMAIN_END; m += 60) if ((m - DOMAIN_START) % hourStep === 0) hours.push(m);
  const thumb = 28;
  const first = clockMinutes(cutoffs[0] ?? "03:00");
  const last = clockMinutes(cutoffs[cutoffs.length - 1] ?? "16:00");

  return (
    <section className="timeline" aria-labelledby={`${id}-title`}>
      <div className="timeline-copy">
        <h2 id={`${id}-title`} className="timeline-headline">
          <span className="headline-small">Bidding at</span> <span className="figure-cutoff">{cutoff}</span>{" "}
          <span className="headline-small">with the</span>{" "}
          <span className="figure-run">{runInUse ?? "–"}</span> <span className="headline-small">forecast</span>
        </h2>
        <p className="timeline-note" aria-live="polite">
          {runMin !== undefined ? (
            <>
              The latest WINDFOR run published before the cutoff, {duration(cutoffMin - runMin)} earlier.{" "}
            </>
          ) : null}
          {nextGate ? (
            <>
              {shortGateLabel(nextGate.label)} closes {duration(clockMinutes(nextGate.time_uk) - cutoffMin)} later, at{" "}
              {nextGate.time_uk}.
            </>
          ) : (
            <>Every GB day-ahead gate has closed by this cutoff.</>
          )}
          {missedGates.length > 0 && nextGate ? <> Already closed: {missedGates.map((g) => shortGateLabel(g.label)).join(", ")}.</> : null}
          {runNote ? <> {runNote}</> : null}
        </p>
      </div>

      <div className="timeline-plot" ref={ref}>
        <svg width={width} height={150} role="img" aria-label={`Day before delivery, 02:00 to 17:00 UK. Cutoff ${cutoff}.`}>
          <text className="timeline-row-label" x={margin.left} y={16}>
            Forecast runs published
          </text>
          {runs.map((r) => {
            const m = clockMinutes(r.time_uk);
            const used = runMin === m;
            const absent = missing.includes(r.time_uk);
            const later = m >= cutoffMin;
            const cls = `run${later ? " run-later" : ""}${absent ? " run-missing" : ""}`;
            return (
              <g key={r.time_uk} transform={`translate(${x(m)},40)`} className={cls}>
                <circle r={used ? 6 : 4.5} className={used ? "run-dot run-used" : "run-dot"} />
                <text y={-10} textAnchor="middle" className="run-label">
                  {r.time_uk}
                </text>
                {absent ? <title>Not published on this day</title> : null}
              </g>
            );
          })}
          <line className="timeline-track" x1={margin.left} x2={margin.left + inner} y1={trackY} y2={trackY} />
          {hours.map((m) => (
            <g key={m} transform={`translate(${x(m)},${trackY})`}>
              <line className="timeline-tick" y1={0} y2={5} />
              <text className="tick" y={19} textAnchor="middle">
                {String(Math.floor(m / 60)).padStart(2, "0")}:00
              </text>
            </g>
          ))}
          {gates.map((g, i) => {
            const m = clockMinutes(g.time_uk);
            const gx = x(m);
            const row = i % 2;
            const closed = m <= cutoffMin;
            // On a phone only the times fit; the names are listed under the plot.
            const label = narrow ? g.time_uk : `${g.time_uk} ${shortGateLabel(g.label)}`;
            // Gates come in close pairs (09:20/09:50, 14:30/15:30): the first label runs left of its tick and the
            // second right of its own, so neither crosses the other's tick. Kept inside the plot at the edges.
            const estimate = label.length * 6.6;
            let anchor: "start" | "end" = row === 0 ? "end" : "start";
            if (anchor === "end" && gx - estimate < 0) anchor = "start";
            if (anchor === "start" && gx + estimate > width) anchor = "end";
            return (
              <g key={g.time_uk} transform={`translate(${gx},0)`} className={closed ? "gate gate-closed" : "gate"}>
                <line className="gate-tick" y1={trackY + 24} y2={trackY + 48 + row * 16} />
                <text className="gate-label" x={anchor === "end" ? -5 : 5} y={trackY + 46 + row * 16} textAnchor={anchor}>
                  {label}
                </text>
              </g>
            );
          })}
          <g transform={`translate(${x(cutoffMin)},0)`} className="cutoff-mark" aria-hidden="true">
            <rect className="cutoff-wash" x={-x(cutoffMin) + margin.left} y={26} width={x(cutoffMin) - margin.left} height={trackY - 26} />
            <line className="cutoff-line" y1={24} y2={trackY + 18} />
            <circle className={focused ? "cutoff-knob is-focused" : "cutoff-knob"} cy={trackY} r={9} />
          </g>
          {offSchedule ? (
            // Drawn over the cutoff line: an off-schedule run is usually just before the cutoff that selects it.
            <g transform={`translate(${x(offSchedule.minutes)},40)`} className="run run-off-schedule">
              <circle r={6} className="run-dot run-used" />
              {narrow ? null : (
                <text y={-10} textAnchor="middle" className="run-label halo">
                  {offSchedule.label}
                </text>
              )}
            </g>
          ) : null}
        </svg>
        <input
          className="timeline-range"
          type="range"
          min={0}
          max={cutoffs.length - 1}
          step={1}
          value={index}
          aria-label="Decision cutoff, UK time on the day before delivery"
          aria-valuetext={`${cutoff} UK${runInUse ? `, uses the ${runInUse} run` : ""}`}
          style={{ left: x(first) - thumb / 2, width: x(last) - x(first) + thumb, top: trackY - 22 }}
          onFocus={() => {
            setFocused(true);
          }}
          onBlur={() => {
            setFocused(false);
          }}
          onChange={(e) => {
            const next = cutoffs[Number(e.target.value)];
            if (next) onChange(next);
          }}
        />
      </div>
      {narrow ? (
        <ul className="gate-key" aria-label="Day-ahead gate closures">
          {gates.map((g) => (
            <li key={g.time_uk} className={clockMinutes(g.time_uk) <= cutoffMin ? "gate-closed" : undefined}>
              <strong>{g.time_uk}</strong> {shortGateLabel(g.label)}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
