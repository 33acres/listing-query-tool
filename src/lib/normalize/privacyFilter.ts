import type { RawCsvRow } from "@/lib/ingest/parseCsv";

const PII_NAME_PATTERNS = [
  /表示名/,
  /氏名/,
  /名前/,
  /電話/,
  /tel/i,
  /mail/i,
  /メール/,
  /住所/,
  /address/i,
];

export function privacyFilter(
  row: RawCsvRow,
  allowedColumns: Set<string>,
  dropPii: string[],
): RawCsvRow {
  const blocked = new Set(dropPii);
  const filtered: RawCsvRow = {};

  for (const column of allowedColumns) {
    if (blocked.has(column) || PII_NAME_PATTERNS.some((pattern) => pattern.test(column))) {
      continue;
    }
    filtered[column] = row[column] ?? "";
  }

  return filtered;
}
