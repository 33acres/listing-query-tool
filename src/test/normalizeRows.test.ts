import { describe, it, expect } from "vitest";
import { cleanNumber, parseDate, normalizeRows } from "@/lib/normalizeRows";

describe("cleanNumber", () => {
  it("円記号とカンマを除去する", () => {
    expect(cleanNumber("¥12,345")).toBe(12345);
  });
  it("パーセントを除去して数値化する", () => {
    expect(cleanNumber("12.3%")).toBe(12.3);
  });
  it("カンマのみ除去する", () => {
    expect(cleanNumber("1,000")).toBe(1000);
  });
  it("空文字はnullを返す", () => {
    expect(cleanNumber("")).toBeNull();
  });
  it("全角数字を半角に変換する", () => {
    expect(cleanNumber("１２３")).toBe(123);
  });
});

describe("parseDate", () => {
  it("YYYY-MM-DD形式をそのまま返す", () => {
    expect(parseDate("2026-05-01")).toBe("2026-05-01");
  });
  it("YYYY/MM/DD形式を変換する", () => {
    expect(parseDate("2026/05/01")).toBe("2026-05-01");
  });
  it("YYYY年M月D日形式を変換する", () => {
    expect(parseDate("2026年5月1日")).toBe("2026-05-01");
  });
  it("May 1, 2026形式を変換する", () => {
    expect(parseDate("May 1, 2026")).toBe("2026-05-01");
  });
  it("無効な日付はnullを返す", () => {
    expect(parseDate("invalid")).toBeNull();
  });
  it("空文字はnullを返す", () => {
    expect(parseDate("")).toBeNull();
  });
});

describe("normalizeRows", () => {
  it("日付が不正な行をスキップしてカウントする", () => {
    const result = normalizeRows([
      { date: "invalid", query: "test", impressions: "100", clicks: "10", cost: "5000", conversions: "0" },
      { date: "2026-05-01", query: "valid", impressions: "200", clicks: "20", cost: "10000", conversions: "1" },
    ]);
    expect(result.skippedCount).toBe(1);
    expect(result.rows).toHaveLength(1);
  });

  it("CVが0のときCPAはnullになる", () => {
    const result = normalizeRows([
      { date: "2026-05-01", query: "test", impressions: "100", clicks: "10", cost: "5000", conversions: "0" },
    ]);
    expect(result.rows[0].cpa).toBeNull();
  });

  it("数値にカンマがある行を正規化する", () => {
    const result = normalizeRows([
      { date: "2026-05-01", query: "test", impressions: "1,000", clicks: "100", cost: "10,000", conversions: "5" },
    ]);
    expect(result.rows[0].impressions).toBe(1000);
    expect(result.rows[0].cost).toBe(10000);
  });

  it("CVR・CPAを内部で再計算する", () => {
    const result = normalizeRows([
      { date: "2026-05-01", query: "test", impressions: "100", clicks: "20", cost: "10000", conversions: "4" },
    ]);
    expect(result.rows[0].cvr).toBeCloseTo(0.2);
    expect(result.rows[0].cpa).toBe(2500);
  });
});
