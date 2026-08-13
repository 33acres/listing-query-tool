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

function countMeasured(
  friends: LstepFriend[],
  read: (friend: LstepFriend) => boolean | null,
): number | null {
  return friends.some((friend) => read(friend) !== null)
    ? friends.filter((friend) => read(friend) === true).length
    : null;
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
    paid: countMeasured(friends, (friend) => friend.status.paid),
    monshinSubmitted: countMeasured(
      friends,
      (friend) => friend.status.monshinSubmitted,
    ),
    shinsatsuDone: countMeasured(
      friends,
      (friend) => friend.status.shinsatsuDone,
    ),
    shipped: countMeasured(friends, (friend) => friend.status.shipped),
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
    {
      key: "paid",
      label: "決済完了",
      count: counts.paid,
      note: config.status_notes?.paid,
    },
    {
      key: "monshinSubmitted",
      label: "問診票提出",
      count: counts.monshinSubmitted,
      note: config.status_notes?.monshin_submitted,
    },
    {
      key: "shinsatsuDone",
      label: "ビデオ診察完了",
      count: counts.shinsatsuDone,
      note:
        config.status_notes?.shinsatsu_done ??
        (counts.shinsatsuDone === null ? "未計測" : undefined),
    },
    {
      key: "shipped",
      label: "発送済",
      count: counts.shipped,
      note: config.status_notes?.shipped,
    },
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
    needsFollowCount: countMeasured(
      friends,
      (friend) => friend.status.needsFollow,
    ),
  };
}
