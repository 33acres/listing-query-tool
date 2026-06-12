import type {
  AnalyzerConfig,
  LstepFriend,
  TeikiRateResult,
} from "@/types/lstep";
import { filterByPeriod, type DatePeriod } from "./period";

export function buildTeikiRate(
  allFriends: LstepFriend[],
  config: AnalyzerConfig,
  period?: DatePeriod,
): TeikiRateResult {
  const friends = filterByPeriod(allFriends, period);
  const purchaseKeys =
    config.purchase_tags === "TBD" ? [] : Object.keys(config.purchase_tags);
  const breakdown = Object.fromEntries(purchaseKeys.map((key) => [key, 0]));

  for (const friend of friends) {
    for (const purchase of friend.purchases) {
      breakdown[purchase] = (breakdown[purchase] ?? 0) + 1;
    }
  }

  const teiki = breakdown.teiki ?? 0;
  const tanpin = Object.entries(breakdown)
    .filter(([key]) => key !== "teiki")
    .reduce((sum, [, count]) => sum + count, 0);
  const total = teiki + tanpin;

  return {
    teiki,
    tanpin,
    total,
    rate: total > 0 ? teiki / total : null,
    breakdown,
  };
}
