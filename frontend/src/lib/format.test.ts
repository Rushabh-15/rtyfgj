import { describe, expect, it } from "vitest";
import {
  clockMinutes,
  dayBefore,
  duration,
  gwTick,
  longDeliveryDate,
  mw,
  num,
  pct,
  shortDeliveryDate,
  signed,
  signedMinutes,
  ukDate,
  ukDayMonth,
  ukTime,
  ukWeekdayDate,
} from "./format";

describe("UK time", () => {
  it("shows GMT in winter and BST in summer", () => {
    expect(ukTime("2026-01-15T07:30:00Z")).toBe("07:30");
    expect(ukTime("2026-06-15T07:30:00Z")).toBe("08:30");
  });

  it("puts 23:00 UK on the previous calendar day", () => {
    expect(ukTime("2026-01-01T23:00:00Z")).toBe("23:00");
    expect(ukWeekdayDate("2026-01-01T23:00:00Z")).toBe("Thu 1 Jan");
    expect(ukDayMonth("2026-01-15T09:30:00Z")).toBe("15 Jan");
  });

  it("gives the UK date of an instant and the bid day before delivery", () => {
    expect(ukDate("2026-01-15T23:30:00Z")).toBe("2026-01-15");
    expect(ukDate("2026-06-15T23:30:00Z")).toBe("2026-06-16");
    expect(dayBefore("2026-01-16")).toBe("2026-01-15");
    expect(dayBefore("2026-03-01")).toBe("2026-02-28");
  });

  it("formats delivery dates without shifting them across midnight", () => {
    expect(shortDeliveryDate("2026-01-16")).toBe("Fri 16 Jan");
    expect(longDeliveryDate("2026-02-01")).toMatch(/Sunday,? 1 February 2026/);
  });
});

describe("numbers", () => {
  it("uses a real minus sign and explicit plus for errors", () => {
    expect(signed(1749.4)).toBe("+1,749");
    expect(signed(-540)).toBe("−540");
    expect(signed(0.4)).toBe("0");
    expect(num(-4105.2)).toBe("−4,105");
    expect(mw(4233.2)).toBe("4,233 MW");
  });

  it("formats shares, durations, clock times and ticks", () => {
    expect(pct(0.915)).toBe("91.5%");
    expect(pct(0.85, 0)).toBe("85%");
    expect(duration(90)).toBe("1 h 30 min");
    expect(duration(120)).toBe("2 h");
    expect(duration(20)).toBe("20 min");
    expect(clockMinutes("09:20")).toBe(560);
    expect(gwTick(2500)).toBe("+2.5 GW");
    expect(gwTick(-2000)).toBe("−2 GW");
    expect(gwTick(0)).toBe("0");
    expect(signedMinutes(-60)).toBe("−60");
    expect(signedMinutes(30)).toBe("+30");
  });
});
