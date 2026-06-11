import { isTruthyCell } from "@/lib/ingest/numberUtils";
import type { AnalyzerConfig, FriendStatus } from "@/types/lstep";

interface StatusInput {
  mark: string;
  purchases: Set<string>;
  raw: Record<string, string | undefined>;
}

function includes(values: string[] | undefined, target: string): boolean {
  return (values ?? []).includes(target);
}

export function deriveStatus(
  input: StatusInput,
  config: AnalyzerConfig,
): FriendStatus {
  const paidByTag = config.status_tags?.paid
    ? isTruthyCell(input.raw[config.status_tags.paid])
    : false;
  const monshinByTag = config.status_tags?.monshin_submitted
    ? isTruthyCell(input.raw[config.status_tags.monshin_submitted])
    : false;
  const shinsatsuByTag = config.status_tags?.shinsatsu_done
    ? isTruthyCell(input.raw[config.status_tags.shinsatsu_done])
    : false;
  const configuredShinsatsuMarks = Array.isArray(config.status_rules.shinsatsu_done)
    ? config.status_rules.shinsatsu_done
    : [];
  const shinsatsuMeasured =
    Boolean(config.status_tags?.shinsatsu_done) || configuredShinsatsuMarks.length > 0;

  const paid =
    paidByTag ||
    input.purchases.size > 0 ||
    includes(config.status_rules.paid_marks, input.mark);
  const monshinSubmitted =
    monshinByTag ||
    includes(config.status_rules.monshin_submitted_marks, input.mark);
  const shinsatsuDone = shinsatsuMeasured
    ? shinsatsuByTag || configuredShinsatsuMarks.includes(input.mark)
    : null;
  const shipped = includes(config.status_rules.shipped_marks, input.mark);
  const needsFollow =
    config.project === "std"
      ? paid && !monshinSubmitted
      : includes(config.status_rules.needs_follow_marks, input.mark);

  return {
    paid,
    monshinSubmitted,
    shinsatsuDone,
    shipped,
    needsFollow,
  };
}
