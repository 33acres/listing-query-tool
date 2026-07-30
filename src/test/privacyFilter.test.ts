import { describe, expect, it } from "vitest";
import { mapColumns } from "@/lib/normalize/mapColumns";
import { privacyFilter } from "@/lib/normalize/privacyFilter";
import { dayvigoConfig } from "./lstepFixtures";

describe("privacyFilter", () => {
  it("configのホワイトリスト外とPII列を読み込み時点で破棄する", () => {
    const columns = mapColumns(dayvigoConfig);
    const result = privacyFilter(
      {
        ID: "123",
        表示名: "山田太郎",
        電話番号: "090-0000-0000",
        住所: "東京都",
        対応マーク: "発送済",
        友だち追加日時: "2026-05-01 10:00:00",
        デエビゴ定期: "1",
      },
      columns.allowedColumns,
      dayvigoConfig.drop_pii,
    );

    expect(result.ID).toBe("123");
    expect(result.対応マーク).toBe("発送済");
    expect(result.デエビゴ定期).toBe("1");
    expect(result).not.toHaveProperty("表示名");
    expect(result).not.toHaveProperty("電話番号");
    expect(result).not.toHaveProperty("住所");
    expect(JSON.stringify(result)).not.toContain("山田太郎");
  });
});
