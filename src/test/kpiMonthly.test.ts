import { describe, expect, it } from "vitest";
import { analyzeFriends } from "@/lib/lstep/analyze";
import { buildMonthlyKpis } from "@/lib/lstep/kpiMonthly";
import { mapColumns } from "@/lib/normalize/mapColumns";
import { normalizeFriends } from "@/lib/normalize/normalizeFriends";
import { dayvigoConfig, headers } from "./lstepFixtures";

const rows = [
  {
    ID: "1",
    表示名: "非表示1",
    対応マーク: "発送済",
    友だち追加日時: "2026-05-01 10:00:00",
    デエビゴ定期: "1",
  },
  {
    ID: "2",
    表示名: "非表示2",
    対応マーク: "発送済",
    友だち追加日時: "2026-05-02 10:00:00",
    デエビゴ1ヶ月: "1",
    デエビゴ3ヶ月: "1",
  },
  {
    ID: "3",
    表示名: "非表示3",
    対応マーク: "",
    友だち追加日時: "2026-05-03 10:00:00",
  },
];

describe("buildMonthlyKpis", () => {
  it("購入タグ件数合計で決済数・CVR・定期率を集計する", () => {
    const friends = normalizeFriends(
      rows,
      headers,
      dayvigoConfig,
      mapColumns(dayvigoConfig),
    ).friends;
    const may = buildMonthlyKpis(friends, dayvigoConfig)[0];

    expect(may.registrations).toBe(3);
    expect(may.paid).toBe(3);
    expect(may.purchases.teiki).toBe(1);
    expect(may.purchases.tanpin_1m).toBe(1);
    expect(may.purchases.tanpin_3m).toBe(1);
    expect(may.cvr).toBe(1);
    expect(may.teikiRate).toBeCloseTo(1 / 3);
    expect(may.revenue).toBe(2980 + 9680 + 22396);
  });

  it("configの単価変更だけで売上結果が変わる", () => {
    const friends = normalizeFriends(
      rows,
      headers,
      dayvigoConfig,
      mapColumns(dayvigoConfig),
    ).friends;
    const changedConfig = {
      ...dayvigoConfig,
      pricing: { ...dayvigoConfig.pricing, teiki: 5000 },
    };
    const result = analyzeFriends(friends, changedConfig, {
      fileName: "test.csv",
      importedCount: 3,
      skippedCount: 0,
      discardedColumnCount: 2,
      detectedEncoding: "Shift_JIS",
    });

    expect(result.revenue.total).toBe(5000 + 9680 + 22396);
  });
});
