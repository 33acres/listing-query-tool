import { describe, expect, it } from "vitest";
import { buildFunnel } from "@/lib/lstep/funnel";
import { mapColumns } from "@/lib/normalize/mapColumns";
import { normalizeFriends } from "@/lib/normalize/normalizeFriends";
import type { AnalyzerConfig } from "@/types/lstep";
import { dayvigoConfig, headers } from "./lstepFixtures";

describe("buildFunnel", () => {
  it("dayvigoのconfigルールで新フローファネルと要フォローを集計する", () => {
    const rows = [
      {
        ID: "1",
        表示名: "非表示1",
        対応マーク: "発送済",
        友だち追加日時: "2026-05-01 10:00:00",
        診察誘導_STEP0A: "1",
        診察誘導_STEP1: "1",
        "RM_決済クリック（定期）": "1",
        デエビゴ定期: "1",
      },
      {
        ID: "2",
        表示名: "非表示2",
        対応マーク: "決済済",
        友だち追加日時: "2026-05-02 10:00:00",
        診察誘導_STEP0B: "1",
        "RM_決済クリック（単品）": "1",
        デエビゴ1ヶ月: "1",
      },
      {
        ID: "3",
        表示名: "非表示3",
        対応マーク: "",
        友だち追加日時: "2026-05-03 10:00:00",
      },
    ];
    const normalized = normalizeFriends(
      rows,
      headers,
      dayvigoConfig,
      mapColumns(dayvigoConfig),
    );
    const result = buildFunnel(normalized.friends, dayvigoConfig);
    const count = (key: string) =>
      result.steps.find((step) => step.key === key)?.count;

    expect(count("registered")).toBe(3);
    expect(count("started")).toBe(2);
    expect(count("step1")).toBe(1);
    expect(count("paymentClick")).toBe(2);
    expect(count("paid")).toBe(2);
    expect(count("shinsatsuDone")).toBeNull();
    expect(count("shipped")).toBe(1);
    expect(result.needsFollowCount).toBe(1);
  });

  it("計測不能と設定されたステータスを0件ではなく未計測にする", () => {
    const config: AnalyzerConfig = {
      ...dayvigoConfig,
      status_availability: {
        monshin_submitted: "unavailable",
        needs_follow: "unavailable",
      },
      status_notes: {
        monshin_submitted: "回答フォームにタグ付与なし",
      },
    };
    const rows = [
      {
        ID: "1",
        表示名: "破棄対象",
        対応マーク: "",
        友だち追加日時: "2026-05-01 10:00:00",
      },
    ];
    const normalized = normalizeFriends(
      rows,
      headers,
      config,
      mapColumns(config),
    );
    const result = buildFunnel(normalized.friends, config);
    const monshin = result.steps.find(
      (step) => step.key === "monshinSubmitted",
    );

    expect(monshin?.count).toBeNull();
    expect(monshin?.note).toBe("回答フォームにタグ付与なし");
    expect(result.needsFollowCount).toBeNull();
  });
});
