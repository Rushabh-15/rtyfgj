// The app against real API responses (fixtures from the committed snapshot): what a desk user sees and does.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { mw, pct } from "./lib/format";
import { accuracyAt, dayAt, fakeApi, meta, type FakeApi } from "./test/fakeApi";

let api: FakeApi;

function open(search = "", options: { failMeta?: boolean } = {}) {
  window.history.replaceState(null, "", `/${search}`);
  api = fakeApi(options);
  vi.stubGlobal("fetch", api.fetch);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  );
}

const hero = (name: RegExp) => screen.findByRole("heading", { level: 2, name });

beforeEach(() => {
  window.history.replaceState(null, "", "/");
});

afterEach(() => {
  vi.unstubAllGlobals();
  expect(api.misses, "requests without a fixture").toEqual([]);
});

describe("decision cutoff", () => {
  it("opens on the first delivery day at 09:00 with the 07:30 run", async () => {
    open();
    expect(await hero(/Bidding at 09:00 with the 07:30 forecast/)).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: /2 January 2026/ })).toBeInTheDocument();
    expect(screen.getByText(/1 h 30 min earlier/)).toBeInTheDocument();
    expect(meta.default_cutoff_uk).toBe("09:00");
  });

  it("moving the cutoff selects the latest run published before it", async () => {
    open();
    await hero(/with the 07:30 forecast/);
    const slider = screen.getByRole("slider", { name: /Decision cutoff/ });
    fireEvent.change(slider, { target: { value: String(meta.cutoffs_uk.indexOf("12:00")) } });
    expect(await hero(/Bidding at 12:00 with the 11:30 forecast/)).toBeInTheDocument();
    expect(new URLSearchParams(window.location.search).get("cutoff")).toBe("12:00");
  });

  it("does not use a run published exactly at the cutoff", async () => {
    open("?cutoff=09:30");
    expect(await hero(/Bidding at 09:30 with the 07:30 forecast/)).toBeInTheDocument();
    expect(dayAt("2026-01-02", "09:30").runs[0]?.publish_time_utc).toBe("2026-01-01T07:30:00Z");
  });

  it("falls back to the previous run when the expected one is missing", async () => {
    const { container } = open("?day=2026-01-16&cutoff=12:00");
    expect(await hero(/Bidding at 12:00 with the 09:30 forecast/)).toBeInTheDocument();
    expect(screen.getByText(/the 11:30 run was not published, so the rule falls back to the 09:30 run/)).toBeInTheDocument();
    expect([...container.querySelectorAll(".run-missing .run-label")].map((t) => t.textContent)).toEqual(["11:30"]);
  });

  it("uses a run published off schedule when it is the latest before the cutoff", async () => {
    open("?day=2026-01-16&cutoff=12:30");
    expect(await hero(/Bidding at 12:30 with the 12:25 forecast/)).toBeInTheDocument();
    expect(screen.getByText(/a run published at 12:25 on 15 Jan is the latest before the cutoff/)).toBeInTheDocument();
  });
});

describe("day view", () => {
  it("lists every half-hour of the 23:00-23:00 delivery day in the table view", async () => {
    open();
    await hero(/with the 07:30 forecast/);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Show table" }));
    const rows = within(screen.getByRole("table")).getAllByRole("row");
    expect(rows).toHaveLength(1 + 48);
    const first = within(rows[1] as HTMLElement).getAllByRole("cell");
    expect(within(rows[1] as HTMLElement).getByRole("rowheader")).toHaveTextContent("23:00");
    expect(first[0]).toHaveTextContent("47");
  });

  it("picks another day from the calendar", async () => {
    open();
    await hero(/with the 07:30 forecast/);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("gridcell", { name: /^Fri 16 Jan/ }));
    expect(await screen.findByRole("heading", { name: /16 January 2026/ })).toBeInTheDocument();
    expect(new URLSearchParams(window.location.search).get("day")).toBe("2026-01-16");
  });
});

describe("error and buffer view", () => {
  it("leads with the buffer and its out-of-sample coverage", async () => {
    open("?view=error");
    const row = accuracyAt("09:00").buffer.find((b) => b.target_pct === 90);
    expect(row).toBeDefined();
    if (!row) return;
    expect(await screen.findByText(mw(row.buffer_mw))).toHaveClass("hero-number");
    expect(screen.getByText(pct(row.test_coverage), { selector: ".buffer-claim strong" })).toBeInTheDocument();
  });

  it("changes the coverage target", async () => {
    open("?view=error");
    const row = accuracyAt("09:00").buffer.find((b) => b.target_pct === 95);
    if (!row) throw new Error("no 95% row");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("radio", { name: "95%" }));
    expect(await screen.findByText(mw(row.buffer_mw))).toHaveClass("hero-number");
    expect(new URLSearchParams(window.location.search).get("coverage")).toBe("95");
  });

  it("names the day a run was missing", async () => {
    open("?view=error&cutoff=12:00");
    expect(await screen.findByText(/On 15 Jan the 11:30 run was missing, so the 09:30 run stood in/)).toBeInTheDocument();
  });

  it("is reached from the tab and keeps the cutoff", async () => {
    open("?cutoff=12:00");
    await hero(/Bidding at 12:00/);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Error and buffer" }));
    expect(await screen.findByText("Hold above the forecast")).toBeInTheDocument();
    const params = new URLSearchParams(window.location.search);
    expect(params.get("view")).toBe("error");
    expect(params.get("cutoff")).toBe("12:00");
  });
});

describe("failures", () => {
  it("says what failed when the API is down", async () => {
    open("", { failMeta: true });
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not load its data from \/api\/v1\/meta/);
  });

  it("falls back to the default cutoff for a cutoff outside the range", async () => {
    open("?cutoff=17:00");
    expect(await hero(/Bidding at 09:00/)).toBeInTheDocument();
    expect(api.requests.some((r) => r.includes("17"))).toBe(false);
  });
});
