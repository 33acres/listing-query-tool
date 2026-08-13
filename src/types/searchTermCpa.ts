export type SearchTermCpaProject = "ecp" | "std";

export interface SearchTermCpaRow {
  keyword: string;
  campaign: string;
  adGroup: string;
  impressions: number;
  clicks: number;
  cost: number;
  /** 媒体（Google Ads）が自己計測したコンバージョン数 */
  platformConversions: number;
  /** 実CV（gclid/ValueTrack突合による実際の成約数）。ダミーデータでは媒体計測CVに乖離係数を掛けて生成 */
  realConversions: number;
  /** 実売上（実CV × 商品単価） */
  revenue: number;
}

export interface SearchTermCpaDailyPoint {
  date: string;
  cost: number;
  realCpa: number | null;
}

export interface SearchTermCpaDataset {
  project: SearchTermCpaProject;
  generatedAt: string;
  rows: SearchTermCpaRow[];
  dailyTrend: SearchTermCpaDailyPoint[];
}
