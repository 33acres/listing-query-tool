import { parseConfigDate, toDateKey } from "@/lib/ingest/dateUtils";
import type {
  AnalysisResult,
  AnalyzerConfig,
  LstepFriend,
} from "@/types/lstep";
import { buildFunnel } from "./funnel";
import { buildMonthlyKpis } from "./kpiMonthly";
import { estimateRevenue } from "./revenue";
import { buildTeikiRate } from "./teikiRate";
import { buildWeeklyLog } from "./weeklyLog";

export function analyzeFriends(
  friends: LstepFriend[],
  config: AnalyzerConfig,
  metadata: Pick<
    AnalysisResult,
    | "fileName"
    | "importedCount"
    | "skippedCount"
    | "discardedColumnCount"
    | "detectedEncoding"
  >,
): AnalysisResult {
  const sortedDates = friends.map((friend) => friend.addedAt).sort((a, b) => +a - +b);
  const newFlowStart = parseConfigDate(config.flow.new_flow_start);
  const lastDate = sortedDates.at(-1) ?? newFlowStart;
  const period = {
    start: newFlowStart,
    end: new Date(
      lastDate.getFullYear(),
      lastDate.getMonth(),
      lastDate.getDate(),
      23,
      59,
      59,
      999,
    ),
  };

  return {
    ...metadata,
    dateRange: {
      start: toDateKey(period.start),
      end: toDateKey(period.end),
    },
    funnel: buildFunnel(friends, config, period),
    monthly: buildMonthlyKpis(friends, config),
    teikiRate: buildTeikiRate(friends, config, period),
    weekly: buildWeeklyLog(
      friends.filter(
        (friend) =>
          friend.addedAt >= period.start && friend.addedAt <= period.end,
      ),
      config,
    ),
    revenue: estimateRevenue(friends, config, period),
  };
}
