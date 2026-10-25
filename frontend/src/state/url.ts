// The URL is the source of truth for what is on screen, so every view can be linked and reloaded as-is.

import { useCallback, useSyncExternalStore } from "react";

export type View = "day" | "error";

export interface AppState {
  view: View;
  day: string | undefined;
  cutoff: string | undefined;
  coverage: number | undefined;
}

const EVENT = "windcast:navigate";

function read(): AppState {
  const params = new URLSearchParams(window.location.search);
  const coverage = Number(params.get("coverage"));
  return {
    view: params.get("view") === "error" ? "error" : "day",
    day: params.get("day") ?? undefined,
    cutoff: params.get("cutoff") ?? undefined,
    coverage: Number.isFinite(coverage) && coverage > 0 ? coverage : undefined,
  };
}

let cached = typeof window === "undefined" ? undefined : read();
let cachedSearch = typeof window === "undefined" ? "" : window.location.search;

function snapshot(): AppState {
  if (cached === undefined || window.location.search !== cachedSearch) {
    cached = read();
    cachedSearch = window.location.search;
  }
  return cached;
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener("popstate", onChange);
  window.addEventListener(EVENT, onChange);
  return () => {
    window.removeEventListener("popstate", onChange);
    window.removeEventListener(EVENT, onChange);
  };
}

/** Read and update the app state held in the query string (history.replaceState for small moves). */
export function useUrlState(): [AppState, (patch: Partial<AppState>, options?: { push?: boolean }) => void] {
  const state = useSyncExternalStore(subscribe, snapshot, snapshot);
  const update = useCallback((patch: Partial<AppState>, options?: { push?: boolean }) => {
    const next = { ...snapshot(), ...patch };
    const params = new URLSearchParams();
    if (next.view !== "day") params.set("view", next.view);
    if (next.day) params.set("day", next.day);
    if (next.cutoff) params.set("cutoff", next.cutoff);
    if (next.coverage !== undefined) params.set("coverage", String(next.coverage));
    const search = params.toString();
    const url = `${window.location.pathname}${search ? `?${search}` : ""}`;
    if (options?.push) window.history.pushState(null, "", url);
    else window.history.replaceState(null, "", url);
    window.dispatchEvent(new Event(EVENT));
  }, []);
  return [state, update];
}
