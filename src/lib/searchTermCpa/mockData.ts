import type {
  SearchTermCpaDailyPoint,
  SearchTermCpaDataset,
  SearchTermCpaProject,
  SearchTermCpaRow,
} from "@/types/searchTermCpa";

/**
 * ダミーデータ生成器（プロトタイプ用）。
 * 実データ（gclid/ValueTrack突合）が整備されるまでの画面検証用であり、
 * ここで生成される数値は実在の広告実績・売上とは一切関係ない。
 * mulberry32で決定的に生成し、同一seedなら常に同じ結果を返す（テスト容易性のため）。
 */
function mulberry32(seed: number) {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hashSeed(text: string): number {
  let hash = 0;
  for (let i = 0; i < text.length; i += 1) {
    hash = (hash * 31 + text.charCodeAt(i)) | 0;
  }
  return hash;
}

interface KeywordSeed {
  keyword: string;
  campaign: string;
  adGroup: string;
  /** クリック率レンジ、コンバージョン率レンジ、乖離係数レンジの中心。intent が高いほど実CVが伸びやすい */
  intent: "brand" | "commercial" | "informational" | "geo";
}

const KEYWORD_SEEDS: Record<SearchTermCpaProject, KeywordSeed[]> = {
  ecp: [
    { keyword: "あしたのクリニック アフターピル", campaign: "ECP_検索_指名", adGroup: "指名", intent: "brand" },
    { keyword: "あしたのクリニック ecp オンライン", campaign: "ECP_検索_指名", adGroup: "指名", intent: "brand" },
    { keyword: "アフターピル オンライン 即日", campaign: "ECP_検索_一般", adGroup: "一般ワード", intent: "commercial" },
    { keyword: "緊急避妊薬 通販 オンライン診療", campaign: "ECP_検索_一般", adGroup: "一般ワード", intent: "commercial" },
    { keyword: "アフターピル 安い オンライン", campaign: "ECP_検索_一般", adGroup: "一般ワード", intent: "commercial" },
    { keyword: "モーニングアフターピル 通販", campaign: "ECP_検索_一般", adGroup: "一般ワード", intent: "commercial" },
    { keyword: "避妊 失敗 薬 オンライン", campaign: "ECP_検索_情報", adGroup: "情報ワード", intent: "informational" },
    { keyword: "アフターピル 副作用 通販", campaign: "ECP_検索_情報", adGroup: "情報ワード", intent: "informational" },
    { keyword: "アフターピル 東京 オンライン", campaign: "ECP_検索_地域", adGroup: "地域ワード", intent: "geo" },
    { keyword: "アフターピル 大阪 オンライン", campaign: "ECP_検索_地域", adGroup: "地域ワード", intent: "geo" },
  ],
  std: [
    { keyword: "あしたのクリニック 性病", campaign: "STD_検索_指名", adGroup: "指名", intent: "brand" },
    { keyword: "あしたのクリニック std オンライン", campaign: "STD_検索_指名", adGroup: "指名", intent: "brand" },
    { keyword: "性病 オンライン診療 治療薬", campaign: "STD_検索_症状", adGroup: "症状ワード", intent: "commercial" },
    { keyword: "クラミジア 症状 オンライン", campaign: "STD_検索_症状", adGroup: "症状ワード", intent: "commercial" },
    { keyword: "梅毒 治療 オンライン診療", campaign: "STD_検索_症状", adGroup: "症状ワード", intent: "commercial" },
    { keyword: "性病検査キット オンライン", campaign: "STD_検索_検査", adGroup: "検査ワード", intent: "commercial" },
    { keyword: "std 検査 自宅 郵送", campaign: "STD_検索_検査", adGroup: "検査ワード", intent: "commercial" },
    { keyword: "性病とは 症状", campaign: "STD_検索_情報", adGroup: "情報ワード", intent: "informational" },
    { keyword: "性病 オンライン診療 東京", campaign: "STD_検索_地域", adGroup: "地域ワード", intent: "geo" },
    { keyword: "性病 オンライン診療 大阪", campaign: "STD_検索_地域", adGroup: "地域ワード", intent: "geo" },
  ],
};

const INTENT_RANGES: Record<
  KeywordSeed["intent"],
  { ctr: [number, number]; cvr: [number, number]; realityFactor: [number, number]; cpc: [number, number] }
> = {
  brand: { ctr: [0.08, 0.14], cvr: [0.06, 0.11], realityFactor: [0.9, 1.1], cpc: [60, 140] },
  commercial: { ctr: [0.04, 0.08], cvr: [0.02, 0.05], realityFactor: [0.6, 1.05], cpc: [150, 420] },
  informational: { ctr: [0.02, 0.045], cvr: [0.004, 0.015], realityFactor: [0.3, 0.7], cpc: [80, 220] },
  geo: { ctr: [0.03, 0.06], cvr: [0.015, 0.035], realityFactor: [0.5, 0.9], cpc: [120, 300] },
};

const AOV_BY_PROJECT: Record<SearchTermCpaProject, number> = {
  ecp: 15200,
  std: 16800,
};

function pick(rng: () => number, [min, max]: [number, number]): number {
  return min + rng() * (max - min);
}

function buildRow(seed: KeywordSeed, project: SearchTermCpaProject): SearchTermCpaRow {
  const rng = mulberry32(hashSeed(`${project}:${seed.keyword}`));
  const ranges = INTENT_RANGES[seed.intent];
  const impressions = Math.round(pick(rng, [800, 9000]));
  const ctr = pick(rng, ranges.ctr);
  const clicks = Math.round(impressions * ctr);
  const cpc = pick(rng, ranges.cpc);
  const cost = Math.round(clicks * cpc);
  const cvr = pick(rng, ranges.cvr);
  const platformConversions = Math.round(clicks * cvr);
  const realityFactor = pick(rng, ranges.realityFactor);
  const realConversions = Math.max(0, Math.round(platformConversions * realityFactor));
  const revenue = realConversions * AOV_BY_PROJECT[project];

  return {
    keyword: seed.keyword,
    campaign: seed.campaign,
    adGroup: seed.adGroup,
    impressions,
    clicks,
    cost,
    platformConversions,
    realConversions,
    revenue,
  };
}

function buildDailyTrend(project: SearchTermCpaProject, rows: SearchTermCpaRow[]): SearchTermCpaDailyPoint[] {
  const rng = mulberry32(hashSeed(`${project}:daily-trend`));
  const totalCost = rows.reduce((sum, row) => sum + row.cost, 0);
  const totalRealConversions = rows.reduce((sum, row) => sum + row.realConversions, 0);
  const baseDailyCost = totalCost / 28;
  const baseCpa = totalRealConversions > 0 ? totalCost / totalRealConversions : null;

  const points: SearchTermCpaDailyPoint[] = [];
  const today = new Date("2026-08-13T00:00:00+09:00");
  for (let i = 27; i >= 0; i -= 1) {
    const date = new Date(today);
    date.setDate(date.getDate() - i);
    const noise = 0.75 + rng() * 0.5;
    const cost = Math.round(baseDailyCost * noise);
    const cpaNoise = 0.8 + rng() * 0.55;
    const realCpa = baseCpa === null ? null : Math.round(baseCpa * cpaNoise);
    points.push({
      date: date.toISOString().slice(0, 10),
      cost,
      realCpa,
    });
  }
  return points;
}

export function buildSearchTermCpaDataset(project: SearchTermCpaProject): SearchTermCpaDataset {
  const rows = KEYWORD_SEEDS[project].map((seed) => buildRow(seed, project));
  return {
    project,
    generatedAt: "2026-08-13",
    rows,
    dailyTrend: buildDailyTrend(project, rows),
  };
}
