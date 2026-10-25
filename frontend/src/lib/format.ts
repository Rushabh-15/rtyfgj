// Formatting helpers. Instants arrive as ISO-8601 UTC strings; people read UK clock time.

const UK = "Europe/London";

const hhmm = new Intl.DateTimeFormat("en-GB", { timeZone: UK, hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const dayMonth = new Intl.DateTimeFormat("en-GB", { timeZone: UK, day: "numeric", month: "short" });
const weekdayDayMonth = new Intl.DateTimeFormat("en-GB", {
  timeZone: UK,
  weekday: "short",
  day: "numeric",
  month: "short",
});
const longDate = new Intl.DateTimeFormat("en-GB", {
  timeZone: UK,
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
});
const isoDate = new Intl.DateTimeFormat("en-CA", { timeZone: UK, year: "numeric", month: "2-digit", day: "2-digit" });
const integer = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });

/** UK calendar date "2026-01-15" of an ISO instant. */
export function ukDate(iso: string): string {
  return isoDate.format(new Date(iso));
}

/** The date before a "YYYY-MM-DD" date (D-1, the day the bids are made). */
export function dayBefore(day: string): string {
  const d = new Date(`${day}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().slice(0, 10);
}

/** "09:30" in UK time for an ISO instant. */
export function ukTime(iso: string): string {
  return hhmm.format(new Date(iso));
}

/** "15 Jan" for an ISO instant (UK date). */
export function ukDayMonth(iso: string): string {
  return dayMonth.format(new Date(iso));
}

/** "Thu 15 Jan" for an ISO instant. */
export function ukWeekdayDate(iso: string): string {
  return weekdayDayMonth.format(new Date(iso));
}

/** A delivery date "2026-01-16" rendered as "Friday 16 January 2026". */
export function longDeliveryDate(day: string): string {
  return longDate.format(new Date(`${day}T12:00:00Z`));
}

/** A delivery date "2026-01-16" rendered as "Fri 16 Jan". */
export function shortDeliveryDate(day: string): string {
  return weekdayDayMonth.format(new Date(`${day}T12:00:00Z`));
}

/** "4,233 MW" */
export function mw(value: number): string {
  return `${integer.format(Math.round(value))} MW`;
}

/** "4,233" with a real minus sign for negatives. */
export function num(value: number): string {
  const rounded = Math.round(value);
  return rounded < 0 ? `−${integer.format(-rounded)}` : integer.format(rounded);
}

/** "+1,749" / "−540": signed, for errors where the sign carries meaning. */
export function signed(value: number): string {
  const rounded = Math.round(value);
  if (rounded === 0) return "0";
  return rounded > 0 ? `+${integer.format(rounded)}` : `−${integer.format(-rounded)}`;
}

/** "91.5%" from a share in [0, 1]. */
export function pct(share: number, digits = 1): string {
  return `${(share * 100).toFixed(digits)}%`;
}

/** "+30", "−60", "0": a signed number of minutes with a real minus sign. */
export function signedMinutes(minutes: number): string {
  return minutes > 0 ? `+${minutes}` : minutes < 0 ? `−${-minutes}` : "0";
}

/** "1 h 30 min" for a duration in minutes. */
export function duration(minutes: number): string {
  const m = Math.round(Math.abs(minutes));
  const h = Math.floor(m / 60);
  const rest = m % 60;
  if (h === 0) return `${rest} min`;
  return rest === 0 ? `${h} h` : `${h} h ${rest} min`;
}

/** Minutes after midnight for an "HH:MM" clock string. */
export function clockMinutes(hhmmValue: string): number {
  const [h = "0", m = "0"] = hhmmValue.split(":");
  return Number(h) * 60 + Number(m);
}

/** Signed axis tick in GW: "+2.5 GW", "−1 GW", "0". */
export function gwTick(valueMw: number): string {
  if (valueMw === 0) return "0";
  const v = valueMw / 1000;
  const magnitude = Number.isInteger(v) ? String(Math.abs(v)) : Math.abs(v).toFixed(1);
  return `${v > 0 ? "+" : "−"}${magnitude} GW`;
}
