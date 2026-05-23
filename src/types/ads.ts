export type QueryClassification =
  | "勝ちクエリ"
  | "悪化クエリ"
  | "無駄クエリ"
  | "機会損失クエリ"
  | "新規クエリ"
  | "消滅クエリ"
  | "監視クエリ"
  | "要確認";

export interface RawRow {
  [key: string]: string;
}

export interface NormalizedRow {
  date: string;
  query: string;
  impressions: number;
  clicks: number;
  cost: number;
  conversions: number;
  cvr: number | null;
  cpa: number | null;
  revenue: number | null;
  roas: number | null;
  campaign: string | null;
  adGroup: string | null;
}

export interface AggregatedQuery {
  query: string;
  impressions: number;
  clicks: number;
  cost: number;
  conversions: number;
  cvr: number | null;
  cpa: number | null;
  revenue: number | null;
  roas: number | null;
}

export interface ComparedQuery {
  query: string;
  previous: AggregatedQuery | null;
  current: AggregatedQuery | null;
  impressionsDiff: number | null;
  clicksDiff: number | null;
  costDiff: number | null;
  conversionsDiff: number | null;
  cvrDiff: number | null;
  cpaDiff: number | null;
  roasDiff: number | null;
}

export interface ClassifiedQuery extends ComparedQuery {
  classification: QueryClassification;
  cautionFlag: boolean;
  priorityScore: number;
  recommendedAction: string;
}

export interface ParseResult {
  rows: NormalizedRow[];
  skippedCount: number;
  errors: string[];
}

export interface PeriodConfig {
  mode: "7d" | "14d" | "30d" | "custom";
  currentStart: string;
  currentEnd: string;
  previousStart: string;
  previousEnd: string;
}

export interface SummaryStats {
  totalCost: number;
  totalClicks: number;
  totalConversions: number;
  avgCpa: number | null;
  winCount: number;
  loseCount: number;
  wasteCount: number;
  opportunityCount: number;
  newCount: number;
  vanishedCount: number;
  watchCount: number;
  cautionCount: number;
}
