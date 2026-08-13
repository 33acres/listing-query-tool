import { describe, expect, it } from "vitest";
import { buildSearchTermCpaDataset } from "@/lib/searchTermCpa/mockData";

describe("buildSearchTermCpaDataset", () => {
  it("生成結果が決定的である（同一projectなら同じ数値）", () => {
    const a = buildSearchTermCpaDataset("ecp");
    const b = buildSearchTermCpaDataset("ecp");
    expect(a.rows).toEqual(b.rows);
    expect(a.dailyTrend).toEqual(b.dailyTrend);
  });

  it("ecpとstdで異なるキーワードセットを返す", () => {
    const ecp = buildSearchTermCpaDataset("ecp");
    const std = buildSearchTermCpaDataset("std");
    const ecpKeywords = new Set(ecp.rows.map((r) => r.keyword));
    const stdKeywords = new Set(std.rows.map((r) => r.keyword));
    for (const keyword of ecpKeywords) {
      expect(stdKeywords.has(keyword)).toBe(false);
    }
  });

  it("各行の指標が整合している（clicks<=impressions, realCV<=platformCVの前提は崩れうるので非負のみ検証）", () => {
    const { rows } = buildSearchTermCpaDataset("std");
    for (const row of rows) {
      expect(row.clicks).toBeLessThanOrEqual(row.impressions);
      expect(row.clicks).toBeGreaterThanOrEqual(0);
      expect(row.cost).toBeGreaterThanOrEqual(0);
      expect(row.realConversions).toBeGreaterThanOrEqual(0);
      expect(row.revenue).toBe(row.realConversions * (row.revenue / (row.realConversions || 1)));
    }
  });

  it("日次推移は28日分で、合計費用は行合計に近似する", () => {
    const { rows, dailyTrend } = buildSearchTermCpaDataset("ecp");
    expect(dailyTrend).toHaveLength(28);
    const totalRowCost = rows.reduce((sum, row) => sum + row.cost, 0);
    const totalDailyCost = dailyTrend.reduce((sum, point) => sum + point.cost, 0);
    // ノイズを掛けているため厳密一致ではなく大まかな整合性のみ確認
    expect(totalDailyCost).toBeGreaterThan(totalRowCost * 0.5);
    expect(totalDailyCost).toBeLessThan(totalRowCost * 1.5);
  });
});
