import type { ClassificationResult, Regime } from "./types";

export type ResultFilter = "all" | Regime | "review" | "error";

export function matchesFilter(r: ClassificationResult, f: ResultFilter): boolean {
  if (f === "all") return true;
  if (f === "error") return Boolean(r.error);
  if (r.error) return false;
  if (f === "review") return r.needs_review;
  return r.verdict === f;
}

export type ResultCounts = Record<ResultFilter, number>;

export function countResults(results: ClassificationResult[]): ResultCounts {
  const filters: ResultFilter[] = ["all", "ban", "restriction", "advantage", "none", "review", "error"];
  return Object.fromEntries(filters.map((f) => [f, results.filter((r) => matchesFilter(r, f)).length])) as ResultCounts;
}
