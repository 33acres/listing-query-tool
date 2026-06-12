import type { AnalyzerConfig, LstepFriend } from "@/types/lstep";
import { filterByPeriod, type DatePeriod } from "./period";

export function estimateRevenue(
  allFriends: LstepFriend[],
  config: AnalyzerConfig,
  period?: DatePeriod,
) {
  const friends = filterByPeriod(allFriends, period);
  const keys = config.purchase_tags === "TBD" ? [] : Object.keys(config.purchase_tags);
  const byProduct = Object.fromEntries(
    keys.map((key) => [
      key,
      { count: 0, unitPrice: config.pricing[key] ?? 0, revenue: 0 },
    ]),
  );

  for (const friend of friends) {
    for (const purchase of friend.purchases) {
      const item = byProduct[purchase];
      if (!item) continue;
      item.count += 1;
      item.revenue = item.count * item.unitPrice;
    }
  }

  return {
    total: Object.values(byProduct).reduce((sum, item) => sum + item.revenue, 0),
    byProduct,
  };
}
