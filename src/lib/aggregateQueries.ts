import type { NormalizedRow, AggregatedQuery } from "@/types/ads";

export function aggregateQueries(
  rows: NormalizedRow[],
  startDate: string,
  endDate: string
): Map<string, AggregatedQuery> {
  const map = new Map<string, AggregatedQuery>();

  for (const row of rows) {
    if (row.date < startDate || row.date > endDate) continue;

    const existing = map.get(row.query);
    if (!existing) {
      map.set(row.query, {
        query: row.query,
        impressions: row.impressions,
        clicks: row.clicks,
        cost: row.cost,
        conversions: row.conversions,
        cvr: null,
        cpa: null,
        revenue: row.revenue,
        roas: null,
      });
    } else {
      existing.impressions += row.impressions;
      existing.clicks += row.clicks;
      existing.cost += row.cost;
      existing.conversions += row.conversions;
      if (row.revenue !== null) {
        existing.revenue = (existing.revenue ?? 0) + row.revenue;
      }
    }
  }

  // 集計後にCVR/CPA/ROASを再計算
  for (const agg of map.values()) {
    agg.cvr = agg.clicks > 0 ? agg.conversions / agg.clicks : null;
    agg.cpa = agg.conversions > 0 ? agg.cost / agg.conversions : null;
    agg.roas =
      agg.revenue !== null && agg.cost > 0 ? agg.revenue / agg.cost : null;
  }

  return map;
}
