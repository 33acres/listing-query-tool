import { parseConfigDate, toMonthKey } from "@/lib/ingest/dateUtils";
import type {
  AnalyzerConfig,
  KpiPeriod,
  LstepFriend,
  PurchaseKey,
} from "@/types/lstep";

function emptyCounts(keys: string[]): Record<PurchaseKey, number> {
  return Object.fromEntries(keys.map((key) => [key, 0]));
}

function buildBucket(
  key: string,
  label: string,
  flow: KpiPeriod["flow"],
  purchaseKeys: string[],
): KpiPeriod {
  return {
    key,
    label,
    flow,
    registrations: 0,
    paid: 0,
    purchases: emptyCounts(purchaseKeys),
    cvr: null,
    teikiRate: null,
    revenue: 0,
  };
}

function addFriendToBucket(
  bucket: KpiPeriod,
  friend: LstepFriend,
  config: AnalyzerConfig,
) {
  bucket.registrations += 1;
  for (const purchase of friend.purchases) {
    bucket.purchases[purchase] = (bucket.purchases[purchase] ?? 0) + 1;
    bucket.revenue += config.pricing[purchase] ?? 0;
  }
}

function finalizeBucket(bucket: KpiPeriod) {
  bucket.paid = Object.values(bucket.purchases).reduce(
    (sum, count) => sum + count,
    0,
  );
  bucket.cvr =
    bucket.registrations > 0 ? bucket.paid / bucket.registrations : null;
  bucket.teikiRate =
    bucket.paid > 0 ? (bucket.purchases.teiki ?? 0) / bucket.paid : null;
}

export function buildMonthlyKpis(
  friends: LstepFriend[],
  config: AnalyzerConfig,
): KpiPeriod[] {
  const purchaseKeys =
    config.purchase_tags === "TBD" ? [] : Object.keys(config.purchase_tags);
  const flowStart = parseConfigDate(config.flow.new_flow_start);

  if (config.kpi_periods?.length) {
    return config.kpi_periods.map((period) => {
      const start = parseConfigDate(period.start);
      const end = period.end
        ? new Date(
            parseConfigDate(period.end).getFullYear(),
            parseConfigDate(period.end).getMonth(),
            parseConfigDate(period.end).getDate(),
            23,
            59,
            59,
            999,
          )
        : new Date(8640000000000000);
      const bucket = buildBucket(
        period.key,
        period.label,
        period.flow === "new" ? "新フロー" : "旧フロー",
        purchaseKeys,
      );

      for (const friend of friends) {
        if (friend.addedAt >= start && friend.addedAt <= end) {
          addFriendToBucket(bucket, friend, config);
        }
      }
      finalizeBucket(bucket);
      return bucket;
    });
  }

  const buckets = new Map<string, KpiPeriod>();

  for (const friend of friends) {
    const key = toMonthKey(friend.addedAt);
    let bucket = buckets.get(key);
    if (!bucket) {
      bucket = buildBucket(
        key,
        `${friend.addedAt.getFullYear()}年${friend.addedAt.getMonth() + 1}月`,
        friend.addedAt >= flowStart ? "新フロー" : "旧フロー",
        purchaseKeys,
      );
      buckets.set(key, bucket);
    }
    addFriendToBucket(bucket, friend, config);
  }

  for (const bucket of buckets.values()) {
    finalizeBucket(bucket);
  }

  return [...buckets.values()].sort((a, b) => a.key.localeCompare(b.key));
}
