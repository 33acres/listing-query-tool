import { parseDateValue } from "@/lib/ingest/dateUtils";
import { isTruthyCell, normalizeCell } from "@/lib/ingest/numberUtils";
import type { RawCsvRow } from "@/lib/ingest/parseCsv";
import { deriveStatus } from "@/lib/lstep/statusDerive";
import type { AnalyzerConfig, LstepFriend } from "@/types/lstep";
import type { ColumnMap } from "./mapColumns";
import { privacyFilter } from "./privacyFilter";

export interface NormalizeFriendsResult {
  friends: LstepFriend[];
  skippedCount: number;
  discardedColumnCount: number;
}

function readStandard(
  raw: RawCsvRow,
  columns: ColumnMap,
  key: string,
): string {
  const column = columns.standard[key];
  return normalizeCell(column ? raw[column] : "");
}

export function normalizeFriends(
  rawRows: RawCsvRow[],
  headers: string[],
  config: AnalyzerConfig,
  columns: ColumnMap,
): NormalizeFriendsResult {
  const friends: LstepFriend[] = [];
  let skippedCount = 0;

  for (let index = 0; index < rawRows.length; index += 1) {
    const filtered = privacyFilter(rawRows[index], columns.allowedColumns, config.drop_pii);
    const addedAt = parseDateValue(readStandard(filtered, columns, "added_at"));
    if (!addedAt) {
      skippedCount += 1;
      continue;
    }

    const steps = new Set(
      Object.entries(columns.tags)
        .filter(([key, column]) => key.startsWith("step") && isTruthyCell(filtered[column]))
        .map(([key]) => key.toUpperCase()),
    );
    const purchases = new Set(
      Object.entries(columns.purchaseTags)
        .filter(([, column]) => isTruthyCell(filtered[column]))
        .map(([key]) => key),
    );
    const mark = readStandard(filtered, columns, "mark");
    const rawUserId = readStandard(filtered, columns, "user_id");
    const status = deriveStatus(
      { mark, purchases, raw: filtered, addedAt },
      config,
    );
    const step0Branch =
      Object.entries(columns.branchTags).find(([, column]) =>
        isTruthyCell(filtered[column]),
      )?.[0] ?? null;

    friends.push({
      userId: rawUserId || `row-${index + 1}`,
      mark,
      addedAt,
      lastActionAt: parseDateValue(
        readStandard(filtered, columns, "last_action_at"),
      ),
      appliedViaStep: readStandard(filtered, columns, "applied_via_step") || null,
      steps,
      paymentClicks: {
        tanpin: isTruthyCell(filtered[columns.tags.payment_click_tanpin]),
        teiki: isTruthyCell(filtered[columns.tags.payment_click_teiki]),
      },
      purchases,
      status,
      step0Branch,
    });
  }

  return {
    friends,
    skippedCount,
    discardedColumnCount: headers.filter(
      (header) => !columns.allowedColumns.has(header),
    ).length,
  };
}
