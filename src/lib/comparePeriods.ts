import type { AggregatedQuery, ComparedQuery, NormalizedRow, PeriodConfig } from "@/types/ads";
import { aggregateQueries } from "./aggregateQueries";

function diffOrNull(
  current: number | null | undefined,
  previous: number | null | undefined
): number | null {
  if (current == null || previous == null) return null;
  return current - previous;
}

export function comparePeriods(
  rows: NormalizedRow[],
  period: PeriodConfig
): ComparedQuery[] {
  const prevMap = aggregateQueries(rows, period.previousStart, period.previousEnd);
  const currMap = aggregateQueries(rows, period.currentStart, period.currentEnd);

  const allQueries = new Set([...prevMap.keys(), ...currMap.keys()]);
  const results: ComparedQuery[] = [];

  for (const query of allQueries) {
    const prev: AggregatedQuery | null = prevMap.get(query) ?? null;
    const curr: AggregatedQuery | null = currMap.get(query) ?? null;

    results.push({
      query,
      previous: prev,
      current: curr,
      impressionsDiff: diffOrNull(curr?.impressions, prev?.impressions),
      clicksDiff: diffOrNull(curr?.clicks, prev?.clicks),
      costDiff: diffOrNull(curr?.cost, prev?.cost),
      conversionsDiff: diffOrNull(curr?.conversions, prev?.conversions),
      cvrDiff: diffOrNull(curr?.cvr, prev?.cvr),
      cpaDiff: diffOrNull(curr?.cpa, prev?.cpa),
      roasDiff: diffOrNull(curr?.roas, prev?.roas),
    });
  }

  return results;
}

export function buildDefaultPeriod(rows: NormalizedRow[], days = 7): PeriodConfig {
  const dates = rows.map((r) => r.date).filter(Boolean).sort();
  if (dates.length === 0) {
    const today = new Date().toISOString().slice(0, 10);
    return buildPeriodFromEnd(today, days);
  }
  const latestDate = dates[dates.length - 1];
  return buildPeriodFromEnd(latestDate, days);
}

function buildPeriodFromEnd(endDate: string, days: number): PeriodConfig {
  const end = new Date(endDate);
  const currentStart = new Date(end);
  currentStart.setDate(end.getDate() - days + 1);

  const previousEnd = new Date(currentStart);
  previousEnd.setDate(previousEnd.getDate() - 1);
  const previousStart = new Date(previousEnd);
  previousStart.setDate(previousEnd.getDate() - days + 1);

  return {
    mode: days === 7 ? "7d" : days === 14 ? "14d" : days === 30 ? "30d" : "custom",
    currentStart: currentStart.toISOString().slice(0, 10),
    currentEnd: endDate,
    previousStart: previousStart.toISOString().slice(0, 10),
    previousEnd: previousEnd.toISOString().slice(0, 10),
  };
}
