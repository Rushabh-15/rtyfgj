// A fetch replacement that answers /api requests from fixtures written by `windcast fixtures`: real API
// responses for the committed snapshot (a backend test fails if they drift), so the UI is tested on real data.

import type { Accuracy, DayView, Meta } from "../api/client";

const files = import.meta.glob<{ default: unknown }>("./fixtures/*.json", { eager: true });

function fixture(name: string): unknown {
  return files[`./fixtures/${name}`]?.default;
}

export function fixtureName(url: string): string | undefined {
  const u = new URL(url, "http://app.test");
  const cutoff = u.searchParams.get("cutoff")?.replace(":", "-");
  if (u.pathname === "/api/v1/meta") return "meta.json";
  if (u.pathname === "/api/v1/vintages") return "vintages.json";
  if (u.pathname === "/api/v1/accuracy") return `accuracy_${cutoff ?? ""}.json`;
  const day = /^\/api\/v1\/days\/([\d-]+)$/.exec(u.pathname)?.[1];
  if (day) return `day_${day}_${cutoff ?? ""}_${u.searchParams.get("coverage") ?? ""}.json`;
  return undefined;
}

export interface FakeApi {
  fetch: (input: RequestInfo | URL) => Promise<Response>;
  /** Requests with no fixture: each would show the user an error, so tests expect none. */
  misses: string[];
  requests: string[];
}

export function fakeApi(options: { failMeta?: boolean } = {}): FakeApi {
  const api: FakeApi = {
    misses: [],
    requests: [],
    fetch: (input) => {
      const url = input instanceof Request ? input.url : String(input);
      api.requests.push(url);
      if (options.failMeta && url.includes("/meta")) {
        return Promise.resolve(Response.json({ detail: "Service unavailable" }, { status: 503 }));
      }
      const name = fixtureName(url);
      const body = name ? fixture(name) : undefined;
      if (body === undefined) {
        api.misses.push(url);
        return Promise.resolve(Response.json({ detail: `no fixture for ${url}` }, { status: 404 }));
      }
      return Promise.resolve(Response.json(body));
    },
  };
  return api;
}

export const meta = fixture("meta.json") as Meta;
export const accuracyAt = (cutoff: string) => fixture(`accuracy_${cutoff.replace(":", "-")}.json`) as Accuracy;
export const dayAt = (day: string, cutoff: string, coverage = 90) =>
  fixture(`day_${day}_${cutoff.replace(":", "-")}_${coverage}.json`) as DayView;
