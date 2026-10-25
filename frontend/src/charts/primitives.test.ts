import { describe, expect, it } from "vitest";
import { niceTicks, tickDomain } from "./primitives";

describe("niceTicks", () => {
  it.each([
    [-2540, 6480, 5],
    [0, 21353, 5],
    [1555, 2003, 6],
    [-0.3, 0.7, 4],
    [12, 13, 3],
  ])("encloses [%d, %d] with equal round steps", (lo, hi, count) => {
    const ticks = niceTicks(lo, hi, count);
    const [first, last] = tickDomain(ticks);
    expect(first).toBeLessThanOrEqual(lo);
    expect(last).toBeGreaterThanOrEqual(hi);
    const steps = ticks.slice(1).map((t, i) => t - (ticks[i] ?? 0));
    for (const s of steps) expect(s).toBeCloseTo(steps[0] ?? 0, 9);
    expect(ticks.length).toBeLessThanOrEqual(count + 2);
  });

  it("gives the Day view a 0-25 GW scale for January's highest value", () => {
    expect(niceTicks(0, 21353, 5)).toEqual([0, 5000, 10000, 15000, 20000, 25000]);
  });

  it("handles an empty range", () => {
    expect(niceTicks(5, 5, 3)).toEqual([5]);
  });
});
