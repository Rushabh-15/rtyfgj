// Typed access to the FastAPI backend. Types come from src/api/schema.d.ts, generated from the OpenAPI schema.

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import type { components } from "./schema";

export type Meta = components["schemas"]["Meta"];
export type DayView = components["schemas"]["DayView"];
export type Period = components["schemas"]["Period"];
export type Accuracy = components["schemas"]["Accuracy"];
export type Vintages = components["schemas"]["Vintages"];
export type ErrorStats = components["schemas"]["ErrorStats"];
export type Breakdown = components["schemas"]["Breakdown"];
export type BufferRow = components["schemas"]["BufferRow"];
export type LagPoint = components["schemas"]["LagPoint"];
export type DaySummary = components["schemas"]["DaySummary"];
export type Marker = components["schemas"]["Marker"];

export class ApiError extends Error {
  constructor(
    readonly url: string,
    readonly status: number,
    detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // keep the status text
    }
    throw new ApiError(url, response.status, detail);
  }
  return (await response.json()) as T;
}

const forever = { staleTime: Infinity, gcTime: Infinity } as const;

export function useMeta() {
  return useQuery({ queryKey: ["meta"], queryFn: () => getJson<Meta>("/api/v1/meta"), ...forever });
}

export function useDay(day: string | undefined, cutoff: string, coverage: number) {
  return useQuery({
    queryKey: ["day", day, cutoff, coverage],
    queryFn: () =>
      getJson<DayView>(
        `/api/v1/days/${encodeURIComponent(day ?? "")}?cutoff=${encodeURIComponent(cutoff)}&coverage=${coverage}`,
      ),
    enabled: day !== undefined,
    placeholderData: keepPreviousData,
    ...forever,
  });
}

export function useAccuracy(cutoff: string) {
  return useQuery({
    queryKey: ["accuracy", cutoff],
    queryFn: () => getJson<Accuracy>(`/api/v1/accuracy?cutoff=${encodeURIComponent(cutoff)}`),
    placeholderData: keepPreviousData,
    ...forever,
  });
}

export function useVintages() {
  return useQuery({ queryKey: ["vintages"], queryFn: () => getJson<Vintages>("/api/v1/vintages"), ...forever });
}
