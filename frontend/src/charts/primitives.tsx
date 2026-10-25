// Small shared pieces for the hand-built SVG charts: responsive width, axes, tooltip, figure with table view.

import { useCallback, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";

/** Width of an element, tracked with ResizeObserver (falls back to a fixed width where it is unavailable). */
export function useWidth(fallback = 720): [(node: HTMLElement | null) => void, number] {
  const [width, setWidth] = useState(fallback);
  const observer = useRef<ResizeObserver | null>(null);
  const ref = useCallback(
    (node: HTMLElement | null) => {
      observer.current?.disconnect();
      if (!node) return;
      if (typeof ResizeObserver === "undefined") {
        setWidth(node.clientWidth || fallback);
        return;
      }
      observer.current = new ResizeObserver((entries) => {
        const w = entries[0]?.contentRect.width;
        if (w) setWidth(Math.round(w));
      });
      observer.current.observe(node);
    },
    [fallback],
  );
  useLayoutEffect(() => () => observer.current?.disconnect(), []);
  return [ref, width];
}

export interface Margin {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

interface TickProps<T> {
  ticks: readonly T[];
  position: (t: T) => number;
  label: (t: T) => string;
}

/** Horizontal gridlines with left-hand labels. */
export function YGrid<T>({ ticks, position, label, width }: TickProps<T> & { width: number }) {
  return (
    <g className="axis axis-y" aria-hidden="true">
      {ticks.map((t) => {
        const y = position(t);
        return (
          <g key={String(t)} transform={`translate(0,${y})`}>
            <line className="grid" x1={0} x2={width} />
            <text className="tick" x={-8} dy="0.32em" textAnchor="end">
              {label(t)}
            </text>
          </g>
        );
      })}
    </g>
  );
}

/** Bottom axis: baseline plus tick labels. */
export function XAxis<T>({ ticks, position, label, height, width }: TickProps<T> & { height: number; width: number }) {
  return (
    <g className="axis axis-x" transform={`translate(0,${height})`} aria-hidden="true">
      <line className="baseline" x1={0} x2={width} />
      {ticks.map((t) => (
        <text key={String(t)} className="tick" x={position(t)} y={18} textAnchor="middle">
          {label(t)}
        </text>
      ))}
    </g>
  );
}

/** One tooltip per chart, placed near the pointer and kept inside the chart box. */
export function Tooltip({
  x,
  y,
  width,
  children,
}: {
  x: number;
  y: number;
  width: number;
  children: ReactNode;
}) {
  const flip = x > width * 0.6;
  return (
    <div
      className="tooltip"
      role="status"
      style={{ left: flip ? undefined : x + 14, right: flip ? width - x + 14 : undefined, top: Math.max(0, y - 8) }}
    >
      {children}
    </div>
  );
}

export function TooltipRow({ value, label, swatch }: { value: string; label: string; swatch?: string }) {
  return (
    <div className="tooltip-row">
      {swatch ? <span className="line-key" style={{ background: swatch }} aria-hidden="true" /> : null}
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

/**
 * A chart in a <figure> with a caption and a table twin: the table carries every value the chart shows,
 * so no value is reachable only by hovering.
 */
export function Figure({
  title,
  caption,
  table,
  children,
  wide = false,
}: {
  title: string;
  caption?: ReactNode;
  table: ReactNode;
  children: ReactNode;
  wide?: boolean;
}) {
  const [showTable, setShowTable] = useState(false);
  const id = useId();
  return (
    <figure className={`figure${wide ? " figure-wide" : ""}`} aria-labelledby={`${id}-title`}>
      <div className="figure-head">
        <h3 id={`${id}-title`}>{title}</h3>
        <button
          type="button"
          className="link-button"
          aria-expanded={showTable}
          aria-controls={`${id}-table`}
          onClick={() => {
            setShowTable((v) => !v);
          }}
        >
          {showTable ? "Show chart" : "Show table"}
        </button>
      </div>
      {caption ? <p className="figure-caption">{caption}</p> : null}
      <div hidden={showTable}>{children}</div>
      <div id={`${id}-table`} className="table-scroll" hidden={!showTable}>
        {table}
      </div>
    </figure>
  );
}

/**
 * Nicely rounded ticks that enclose [lo, hi]: the first tick is at or below lo and the last at or above hi,
 * so a scale whose domain runs from the first tick to the last never clips the data.
 */
export function niceTicks(lo: number, hi: number, count: number): number[] {
  const span = hi - lo;
  if (!(span > 0)) return [lo];
  const raw = span / count;
  const power = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * power).find((s) => span / s <= count) ?? power * 10;
  const start = Math.floor(lo / step + 1e-9) * step;
  const end = Math.ceil(hi / step - 1e-9) * step;
  const ticks = [];
  for (let v = start; v <= end + step * 1e-9; v += step) ticks.push(Math.round(v * 1e6) / 1e6);
  return ticks;
}

/** Domain spanning the first to the last tick. */
export function tickDomain(ticks: readonly number[]): [number, number] {
  return [ticks[0] ?? 0, ticks[ticks.length - 1] ?? 1];
}
