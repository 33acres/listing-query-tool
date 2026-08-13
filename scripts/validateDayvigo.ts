import fs from "node:fs";
import path from "node:path";
import { load } from "js-yaml";
import { parseCsvBuffer } from "@/lib/ingest/parseCsv";
import { analyzeFriends } from "@/lib/lstep/analyze";
import { mapColumns } from "@/lib/normalize/mapColumns";
import { normalizeFriends } from "@/lib/normalize/normalizeFriends";
import { privacyFilter } from "@/lib/normalize/privacyFilter";
import type { AnalyzerConfig } from "@/types/lstep";

async function main() {
  const csvPath = process.argv[2];
  if (!csvPath) {
    throw new Error(
      "Usage: npm run validate:dayvigo -- /absolute/path/to/friends.csv",
    );
  }

  const config = load(
    fs.readFileSync(
      path.join(process.cwd(), "config", "dayvigo", "config.yaml"),
      "utf8",
    ),
  ) as AnalyzerConfig;
  const file = fs.readFileSync(csvPath);
  const buffer = file.buffer.slice(
    file.byteOffset,
    file.byteOffset + file.byteLength,
  ) as ArrayBuffer;
  const columns = mapColumns(config);
  const parsed = await parseCsvBuffer(
    buffer,
    Object.values(config.column_mapping),
    (row) => privacyFilter(row, columns.allowedColumns, config.drop_pii),
  );
  const normalized = normalizeFriends(
    parsed.rows,
    parsed.headers,
    config,
    columns,
  );
  const result = analyzeFriends(normalized.friends, config, {
    fileName: path.basename(csvPath),
    importedCount: normalized.friends.length,
    skippedCount: parsed.skippedCount + normalized.skippedCount,
    discardedColumnCount: normalized.discardedColumnCount,
    detectedEncoding: parsed.encoding,
  });

  const output = {
    importedCount: result.importedCount,
    detectedEncoding: result.detectedEncoding,
    discardedColumnCount: result.discardedColumnCount,
    dateRange: result.dateRange,
    funnel: Object.fromEntries(
      result.funnel.steps.map((step) => [step.key, step.count]),
    ),
    needsFollowCount: result.funnel.needsFollowCount,
    teikiRate: result.teikiRate,
    revenue: result.revenue,
    monthly: result.monthly,
    weekly: result.weekly,
  };
  const serialized = JSON.stringify(output, null, 2);

  if (serialized.includes("PII_TEST_NAME")) {
    throw new Error("PIIが検証出力に含まれています。");
  }

  process.stdout.write(`${serialized}\n`);
}

void main();
