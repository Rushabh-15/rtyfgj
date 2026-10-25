// View 2: how wrong the forecast at the cutoff was, and the buffer that would have covered it.

import type { Accuracy, Meta, Vintages } from "../api/client";
import { Calibration } from "../charts/Calibration";
import { DailyBands } from "../charts/DailyBands";
import { Heatmap } from "../charts/Heatmap";
import { LagChart } from "../charts/LagChart";
import { RangeChart } from "../charts/RangeChart";
import { mw, num, pct, shortDeliveryDate, signed } from "../lib/format";

interface Props {
  meta: Meta;
  accuracy: Accuracy;
  vintages: Vintages | undefined;
  coverage: number;
  refreshing: boolean;
  onCoverage: (coverage: number) => void;
  onSelectDay: (day: string) => void;
}

function levelCaption(accuracy: Accuracy): string {
  const top = [...accuracy.by_level].reverse().find((b) => b.stats);
  const bottom = accuracy.by_level.find((b) => b.stats);
  if (!top?.stats || !bottom?.stats) return "";
  return `The gap grows with the forecast: a median shortfall of ${signed(bottom.stats.p50_mw)} MW when ${bottom.label.replace("–", " to ")} was forecast, ${signed(top.stats.p50_mw)} MW at ${top.label}, where wind fell short in ${pct(top.stats.shortfall_share, 0)} of half-hours. Consistent with curtailment at high output (unverified).`;
}

export function ErrorView({ meta, accuracy, vintages, coverage, refreshing, onCoverage, onSelectDay }: Props) {
  const row = accuracy.buffer.find((b) => b.target_pct === coverage) ?? accuracy.buffer[0];
  const f = accuracy.forecast;
  if (!row) return null;
  const held = row.test_coverage >= row.target_pct / 100;
  const fit = `${shortDeliveryDate(meta.fit_days[0] ?? "")}–${shortDeliveryDate(meta.fit_days[1] ?? "")}`;
  const test = `${shortDeliveryDate(meta.test_days[0] ?? "")}–${shortDeliveryDate(meta.test_days[1] ?? "")}`;

  return (
    <div className={`view view-error${refreshing ? " is-refreshing" : ""}`}>
      <section className="buffer-hero" aria-labelledby="buffer-title">
        <div className="buffer-figure">
          <p className="buffer-lead" id="buffer-title">
            Hold above the forecast
          </p>
          <p className="hero-number">{mw(row.buffer_mw)}</p>
          <p className="buffer-claim">
            to cover wind shortfalls in {row.target_pct}% of half-hours. Fitted on {fit}; applied unchanged to {test}, it
            covered <strong>{pct(row.test_coverage)}</strong> of half-hours (95% interval {pct(row.test_coverage_low)}–
            {pct(row.test_coverage_high)}){held ? "." : ", short of its target."}
          </p>
          <p className="buffer-aside">Refitted on all {meta.delivery_days.length} delivery days: {mw(row.full_month_buffer_mw)}.</p>
        </div>
        <fieldset className="segmented">
          <legend>Cover shortfalls in</legend>
          {accuracy.buffer.map((b) => (
            <label key={b.target_pct} className={b.target_pct === coverage ? "is-on" : undefined}>
              <input
                type="radio"
                name="coverage"
                value={b.target_pct}
                checked={b.target_pct === coverage}
                onChange={() => {
                  onCoverage(b.target_pct);
                }}
              />
              {b.target_pct}%
            </label>
          ))}
        </fieldset>
      </section>

      <dl className="kpis">
        <div>
          <dt>Mean error</dt>
          <dd>{signed(f.mean_error_mw)} MW</dd>
          <p>Forecast above outturn on average; wind fell short in {pct(f.shortfall_share, 0)} of half-hours.</p>
        </div>
        <div>
          <dt>MAE</dt>
          <dd>{num(f.mae_mw)} MW</dd>
          <p>RMSE {num(f.rmse_mw)} MW.</p>
        </div>
        <div>
          <dt>Median shortfall</dt>
          <dd>{signed(f.p50_mw)} MW</dd>
          <p>The systematic gap.</p>
        </div>
        <div className="kpi-wide">
          <dt>P10 to P90</dt>
          <dd>
            {signed(f.p10_mw)} to {signed(f.p90_mw)}
          </dd>
          <p>{num(f.p90_mw - f.p10_mw)} MW wide: the spread around the gap.</p>
        </div>
        <div>
          <dt>Skill against persistence</dt>
          <dd>{pct(accuracy.skill_mae, 0)}</dd>
          <p>
            Lower MAE than holding the last outturn known at the cutoff ({num(accuracy.persistence.mae_mw)} MW).
          </p>
        </div>
      </dl>

      <div className="figure-grid">
        <DailyBands days={accuracy.days} buffer={row.buffer_mw} coverage={row.target_pct} onSelectDay={onSelectDay} />
        <Calibration rows={accuracy.buffer} selected={row.target_pct} />
        <RangeChart
          title="Shortfall by forecast level"
          caption={levelCaption(accuracy)}
          rows={accuracy.by_level}
          buffer={row.buffer_mw}
          coverage={row.target_pct}
        />
        <RangeChart
          title="Shortfall by lead time"
          caption={`Lead time from run publication to the half-hour, at the ${accuracy.cutoff_uk} cutoff. With one cutoff a day, lead time and hour of day move together; the heatmap below separates them.`}
          rows={accuracy.by_lead}
          buffer={row.buffer_mw}
          coverage={row.target_pct}
        />
        {vintages ? (
          <LagChart atCutoff={accuracy.lag_scan} shortLead={vintages.short_lead_lag_scan} cutoff={accuracy.cutoff_uk} />
        ) : null}
        {vintages ? <Heatmap vintages={vintages} /> : null}
        <section className="figure figure-wide limits" aria-labelledby="limits-title">
          <h3 id="limits-title">Read with care</h3>
          <ul>
            <li>
              <strong>Curtailment.</strong> FUELHH is metered output after any curtailment. If the high-wind gap is
              curtailment, the buffer overstates the desk's need at high wind.
            </li>
            <li>
              <strong>Embedded wind.</strong> Both datasets cover metered wind farms only; smaller distribution-connected
              wind shows up as lower demand instead.
            </li>
            <li>
              <strong>Coverage.</strong> WINDFOR runs above NESO's own day-ahead forecast for the same units, so some of the
              gap may be fleet coverage rather than weather.
            </li>
            <li>
              <strong>One month.</strong> {accuracy.days.filter((d) => d.sample === "fit").length} fit days and{" "}
              {accuracy.days.filter((d) => d.sample === "test").length} test days; errors within a day move together, so
              the intervals are wide.
            </li>
          </ul>
        </section>
      </div>
    </div>
  );
}
