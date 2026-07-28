import fs from "node:fs";
import path from "node:path";
import { load } from "js-yaml";
import { describe, expect, it } from "vitest";
import { buildFunnel } from "@/lib/lstep/funnel";
import { estimateRevenue } from "@/lib/lstep/revenue";
import { mapColumns } from "@/lib/normalize/mapColumns";
import { normalizeFriends } from "@/lib/normalize/normalizeFriends";
import type { AnalyzerConfig } from "@/types/lstep";

function loadStdConfig(): AnalyzerConfig {
  const configPath = path.join(
    process.cwd(),
    "config",
    "std",
    "config.yaml",
  );
  return load(fs.readFileSync(configPath, "utf8")) as AnalyzerConfig;
}

describe("STD purchase tags", () => {
  it("購入後の商品タグから商品別売上と決済完了を集計する", () => {
    const config = loadStdConfig();
    const headers = [
      "ID",
      "表示名",
      "電話番号",
      "対応マーク",
      "友だち追加日時",
      "性感染症治療薬",
      "フルセット",
      "スタンダードセット",
      "ベーシックセット",
      "ライトセット",
    ];
    const productColumns = [
      "性感染症治療薬",
      "フルセット",
      "スタンダードセット",
      "ベーシックセット",
      "ライトセット",
    ];
    const rows = productColumns.map((column, index) => ({
      ID: String(index + 1),
      表示名: `破棄対象${index + 1}`,
      電話番号: `090-0000-000${index}`,
      対応マーク: "",
      友だち追加日時: `2026-06-${String(index + 1).padStart(2, "0")} 10:00:00`,
      [column]: "1",
    }));
    const normalized = normalizeFriends(
      rows,
      headers,
      config,
      mapColumns(config),
    );
    const revenue = estimateRevenue(normalized.friends, config);
    const funnel = buildFunnel(normalized.friends, config);
    const count = (key: string) =>
      funnel.steps.find((step) => step.key === key)?.count;

    expect(revenue.byProduct.treat_drug.count).toBe(1);
    expect(revenue.byProduct.test_full.count).toBe(1);
    expect(revenue.byProduct.test_standard.count).toBe(1);
    expect(revenue.byProduct.test_basic.count).toBe(1);
    expect(revenue.byProduct.test_light.count).toBe(1);
    expect(revenue.total).toBe(8140 + 28000 + 19000 + 15000 + 9900);
    expect(count("paid")).toBe(5);
    expect(count("monshinSubmitted")).toBeNull();
    expect(funnel.needsFollowCount).toBeNull();
    expect(normalized.discardedColumnCount).toBe(2);
    expect(JSON.stringify(normalized.friends)).not.toContain("破棄対象");
    expect(JSON.stringify(normalized.friends)).not.toContain("090-");
  });
});
