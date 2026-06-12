import Encoding from "encoding-japanese";
import { describe, expect, it } from "vitest";
import { parseCsvBuffer } from "@/lib/ingest/parseCsv";
import { mapColumns } from "@/lib/normalize/mapColumns";
import { privacyFilter } from "@/lib/normalize/privacyFilter";
import { dayvigoConfig } from "./lstepFixtures";

describe("parseCsvBuffer", () => {
  it("Shift_JISとLステップの先頭メタ行を自動判定する", async () => {
    const csv = [
      "登録ID,,,,タグ_1",
      "ID,表示名,対応マーク,友だち追加日時,デエビゴ定期",
      "1,山田太郎,発送済,2026-05-01 10:00:00,1",
    ].join("\r\n");
    const encoded = Encoding.convert(csv, {
      to: "SJIS",
      from: "UNICODE",
      type: "array",
    });
    const buffer = Uint8Array.from(encoded).buffer;
    const columns = mapColumns(dayvigoConfig);
    const result = await parseCsvBuffer(
      buffer,
      ["ID", "対応マーク", "友だち追加日時"],
      (row) =>
        privacyFilter(row, columns.allowedColumns, dayvigoConfig.drop_pii),
    );

    expect(result.encoding).toBe("Shift_JIS");
    expect(result.headers).toContain("表示名");
    expect(result.rows).toHaveLength(1);
    expect(result.rows[0]).not.toHaveProperty("表示名");
    expect(JSON.stringify(result.rows)).not.toContain("山田太郎");
    expect(result.skippedCount).toBe(1);
  });
});
