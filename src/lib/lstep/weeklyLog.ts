import { startOfWeekMonday, toDateKey } from "@/lib/ingest/dateUtils";
import type {
  AnalyzerConfig,
  LstepFriend,
  WeeklyLogEntry,
} from "@/types/lstep";
import { buildTeikiRate } from "./teikiRate";

export function buildWeeklyLog(
  friends: LstepFriend[],
  config: AnalyzerConfig,
): WeeklyLogEntry[] {
  const buckets = new Map<string, LstepFriend[]>();

  for (const friend of friends) {
    const key = toDateKey(startOfWeekMonday(friend.addedAt));
    const bucket = buckets.get(key) ?? [];
    bucket.push(friend);
    buckets.set(key, bucket);
  }

  return [...buckets.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([weekStart, weeklyFriends]) => {
      const teiki = buildTeikiRate(weeklyFriends, config);
      const needsFollowMeasured = weeklyFriends.some(
        (friend) => friend.status.needsFollow !== null,
      );
      return {
        weekStart,
        registrations: weeklyFriends.length,
        paid: teiki.total,
        teikiRate: teiki.rate,
        needsFollow: needsFollowMeasured
          ? weeklyFriends.filter(
              (friend) => friend.status.needsFollow === true,
            ).length
          : null,
      };
    });
}
