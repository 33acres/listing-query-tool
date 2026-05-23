import { describe, it, expect } from "vitest";
import { classifyQueries } from "@/lib/classifyQueries";
import type { ComparedQuery } from "@/types/ads";

function makeAgg(clicks: number, cost: number, conversions: number, impressions = 500) {
  const cvr = clicks > 0 ? conversions / clicks : null;
  const cpa = conversions > 0 ? cost / conversions : null;
  return { query: "test", impressions, clicks, cost, conversions, cvr, cpa, revenue: null, roas: null };
}

function makeCompared(
  query: string,
  prev: ReturnType<typeof makeAgg> | null,
  curr: ReturnType<typeof makeAgg> | null
): ComparedQuery {
  return {
    query,
    previous: prev ? { ...prev, query } : null,
    current: curr ? { ...curr, query } : null,
    impressionsDiff: curr && prev ? curr.impressions - prev.impressions : null,
    clicksDiff: curr && prev ? curr.clicks - prev.clicks : null,
    costDiff: curr && prev ? curr.cost - prev.cost : null,
    conversionsDiff: curr && prev ? curr.conversions - prev.conversions : null,
    cvrDiff: curr && prev && curr.cvr !== null && prev.cvr !== null ? curr.cvr - prev.cvr : null,
    cpaDiff: curr && prev && curr.cpa !== null && prev.cpa !== null ? curr.cpa - prev.cpa : null,
    roasDiff: null,
  };
}

describe("classifyQueries", () => {
  it("勝ちクエリを正しく分類する", () => {
    const compared = makeCompared(
      "勝ちクエリtest",
      makeAgg(30, 15000, 2),
      makeAgg(40, 18000, 5)
    );
    const result = classifyQueries([compared]);
    expect(result[0].classification).toBe("勝ちクエリ");
  });

  it("悪化クエリを正しく分類する", () => {
    const compared = makeCompared(
      "悪化クエリtest",
      makeAgg(20, 12000, 3),
      makeAgg(22, 14000, 1)
    );
    const result = classifyQueries([compared]);
    expect(result[0].classification).toBe("悪化クエリ");
  });

  it("無駄クエリを正しく分類する（費用>=10000、クリック>=20、CV=0）", () => {
    const compared = makeCompared(
      "無駄クエリtest",
      makeAgg(15, 8000, 0),
      makeAgg(25, 15000, 0)
    );
    const result = classifyQueries([compared]);
    expect(result[0].classification).toBe("無駄クエリ");
  });

  it("機会損失クエリを正しく分類する", () => {
    const compared = makeCompared(
      "機会損失test",
      makeAgg(20, 10000, 2),
      makeAgg(45, 22000, 2)
    );
    const result = classifyQueries([compared]);
    expect(result[0].classification).toBe("機会損失クエリ");
  });

  it("新規クエリを正しく分類する", () => {
    const compared = makeCompared(
      "新規クエリtest",
      null,
      makeAgg(12, 5000, 0)
    );
    const result = classifyQueries([compared]);
    expect(result[0].classification).toBe("新規クエリ");
  });

  it("消滅クエリを正しく分類する", () => {
    const compared = makeCompared(
      "消滅クエリtest",
      makeAgg(18, 9000, 2),
      null
    );
    const result = classifyQueries([compared]);
    expect(result[0].classification).toBe("消滅クエリ");
  });

  it("母数不足の場合は監視クエリになる", () => {
    const compared = makeCompared(
      "母数不足test",
      makeAgg(4, 1500, 0, 40),
      makeAgg(5, 2000, 0, 50)
    );
    const result = classifyQueries([compared]);
    expect(result[0].classification).toBe("監視クエリ");
  });

  it("保護ワードを含む無駄クエリは要確認になる", () => {
    const compared = makeCompared(
      "リクナビ 登録",
      makeAgg(50, 20000, 0),
      makeAgg(60, 28000, 0)
    );
    const result = classifyQueries([compared], ["リクナビ"]);
    expect(result[0].classification).toBe("要確認");
    expect(result[0].cautionFlag).toBe(true);
  });

  it("priorityScoreが正しく計算される", () => {
    // 前期CV=3、今期CV=0 → CV減少インパクト=30000
    const compared = makeCompared(
      "スコアtest",
      makeAgg(30, 15000, 3),
      makeAgg(30, 20000, 0)
    );
    const result = classifyQueries([compared]);
    // CV減少: (3-0)*10000=30000, 費用悪化: 5000
    expect(result[0].priorityScore).toBeGreaterThanOrEqual(35000);
  });
});
