import type {
  AnalyzerConfig,
  FunnelResult,
  FunnelStep,
  LstepFriend,
} from "@/types/lstep";
import { filterByPeriod, type DatePeriod } from "./period";

function rate(numerator: number | null, denominator: number | null): number | null {
  if (numerator === null || denominator === null || denominator === 0) return null;
  return numerator / denominator;
}

export function buildFunnel(
  allFriends: LstepFriend[],
  config: AnalyzerConfig,
  period?: DatePeriod,
): FunnelResult {
  const friends = filterByPeriod(allFriends, period);
  const counts = {
    registered: friends.length,
    started: friends.filter((friend) =>
      config.project === "std"
        ? friend.step0Branch === "treat" || friend.steps.has("STEP0A")
        : friend.steps.has("STEP0A") || friend.steps.has("STEP0B"),
    ).length,
    step1: friends.filter((friend) => friend.steps.has("STEP1")).length,
    paymentClick: friends.filter(
      (friend) => friend.paymentClicks.tanpin || friend.paymentClicks.teiki,
    ).length,
    paid: friends.filter((friend) => friend.status.paid).length,
    monshinSubmitted: friends.filter(
      (friend) => friend.status.monshinSubmitted,
    ).length,
    shinsatsuDone: friends.some(
      (friend) => friend.status.shinsatsuDone !== null,
    )
      ? friends.filter((friend) => friend.status.shinsatsuDone).length
      : null,
    shipped: friends.filter((friend) => friend.status.shipped).length,
  };

  const definitions: Array<{
    key: FunnelStep["key"];
    label: string;
    count: number | null;
    note?: string;
  }> = [
    { key: "registered", label: "LINE登録", count: counts.registered },
    { key: "started", label: "診察スタート", count: counts.started },
    { key: "step1", label: "STEP1到達", count: counts.step1 },
    { key: "paymentClick", label: "決済クリック", count: counts.paymentClick },
    { key: "paid", label: "決済完了", count: counts.paid },
    { key: "monshinSubmitted", label: "問診票提出", count: counts.monshinSubmitted },
    {
      key: "shinsatsuDone",
      label: "ビデオ診察完了",
      count: counts.shinsatsuDone,
      note: counts.shinsatsuDone === null ? "TBD: config確定まで未計測" : undefined,
    },
    { key: "shipped", label: "発送済", count: counts.shipped },
  ];

  const steps = definitions.map((definition, index) => {
    const previous = index === 0 ? null : definitions[index - 1].count;
    return {
      ...definition,
      conversionFromPrevious:
        index === 0 ? null : rate(definition.count, previous),
      conversionFromRegistered:
        index === 0 ? 1 : rate(definition.count, counts.registered),
    };
  });

  return {
    steps,
    needsFollowCount: friends.filter((friend) => friend.status.needsFollow).length,
  };
}
