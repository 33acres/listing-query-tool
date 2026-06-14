import { parseConfigDate } from "@/lib/ingest/dateUtils";
import { isTruthyCell } from "@/lib/ingest/numberUtils";
import type {
  AnalyzerConfig,
  FriendStatus,
  StatusKey,
} from "@/types/lstep";

interface StatusInput {
  mark: string;
  purchases: Set<string>;
  raw: Record<string, string | undefined>;
  addedAt: Date;
}

function includes(values: string[] | undefined, target: string): boolean {
  return (values ?? []).includes(target);
}

function isAvailable(
  config: AnalyzerConfig,
  key: StatusKey,
): boolean {
  return config.status_availability?.[key] !== "unavailable";
}

function isAfterMeasurementStart(
  input: StatusInput,
  config: AnalyzerConfig,
  key: StatusKey,
): boolean {
  const availableFrom = config.status_available_from?.[key];
  return !availableFrom || input.addedAt >= parseConfigDate(availableFrom);
}

function hasStatusTag(
  input: StatusInput,
  config: AnalyzerConfig,
  key: StatusKey,
): boolean {
  const configured = config.status_tags?.[key];
  const columns = Array.isArray(configured)
    ? configured
    : configured
      ? [configured]
      : [];
  return columns.some((column) => isTruthyCell(input.raw[column]));
}

function resolveStatus(
  positive: boolean,
  input: StatusInput,
  config: AnalyzerConfig,
  key: StatusKey,
): boolean | null {
  if (!isAvailable(config, key)) return null;
  if (positive) return true;
  return isAfterMeasurementStart(input, config, key) ? false : null;
}

export function deriveStatus(
  input: StatusInput,
  config: AnalyzerConfig,
): FriendStatus {
  const paidByTag = hasStatusTag(input, config, "paid");
  const monshinByTag = hasStatusTag(input, config, "monshin_submitted");
  const shinsatsuByTag = hasStatusTag(input, config, "shinsatsu_done");
  const shippedByTag = hasStatusTag(input, config, "shipped");
  const configuredShinsatsuMarks = Array.isArray(config.status_rules.shinsatsu_done)
    ? config.status_rules.shinsatsu_done
    : [];
  const shinsatsuMeasured =
    Boolean(config.status_tags?.shinsatsu_done) || configuredShinsatsuMarks.length > 0;

  const paid = resolveStatus(
    paidByTag ||
      input.purchases.size > 0 ||
      includes(config.status_rules.paid_marks, input.mark),
    input,
    config,
    "paid",
  );
  const monshinSubmitted = resolveStatus(
    monshinByTag ||
      includes(config.status_rules.monshin_submitted_marks, input.mark),
    input,
    config,
    "monshin_submitted",
  );
  const shinsatsuDone = shinsatsuMeasured
    ? resolveStatus(
        shinsatsuByTag || configuredShinsatsuMarks.includes(input.mark),
        input,
        config,
        "shinsatsu_done",
      )
    : null;
  const shipped = resolveStatus(
    shippedByTag || includes(config.status_rules.shipped_marks, input.mark),
    input,
    config,
    "shipped",
  );
  const followByMark = includes(
    config.status_rules.needs_follow_marks,
    input.mark,
  );
  const followByStatus =
    paid !== null && monshinSubmitted !== null
      ? paid && !monshinSubmitted
      : null;
  const needsFollowMode = config.status_rules.needs_follow_mode ?? "marks";
  let needsFollow: boolean | null;
  if (needsFollowMode === "marks") {
    needsFollow = resolveStatus(
      followByMark,
      input,
      config,
      "needs_follow",
    );
  } else if (needsFollowMode === "paid_without_monshin") {
    needsFollow =
      followByStatus === null
        ? null
        : resolveStatus(
            followByStatus,
            input,
            config,
            "needs_follow",
          );
  } else {
    needsFollow = resolveStatus(
      followByMark || followByStatus === true,
      input,
      config,
      "needs_follow",
    );
  }

  return {
    paid,
    monshinSubmitted,
    shinsatsuDone,
    shipped,
    needsFollow,
  };
}
