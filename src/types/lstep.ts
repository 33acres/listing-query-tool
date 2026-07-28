export type ProjectName = "dayvigo" | "std";

export type PurchaseKey = string;

export type StatusKey =
  | "paid"
  | "monshin_submitted"
  | "shinsatsu_done"
  | "shipped"
  | "needs_follow";

export interface StatusRules {
  paid_marks?: string[];
  shipped_marks?: string[];
  monshin_submitted_marks?: string[];
  needs_follow_marks?: string[];
  needs_follow_mode?:
    | "marks"
    | "paid_without_monshin"
    | "paid_without_monshin_or_marks";
  shinsatsu_done?: string | string[];
}

export type MeasurementAvailability = "derived" | "unavailable";

export interface AnalyzerConfig {
  project: ProjectName;
  display_name: string;
  flow: {
    new_flow_start: string;
  };
  kpi_periods?: Array<{
    key: string;
    label: string;
    flow: "old" | "new";
    start: string;
    end?: string;
  }>;
  ingest: {
    encoding: string;
    source: string;
  };
  drop_pii: string[];
  column_mapping: Record<string, string>;
  tags: Record<string, string>;
  branch_tags?: Record<string, string>;
  status_tags?: Partial<Record<StatusKey, string | string[]>>;
  purchase_tags: Record<PurchaseKey, string> | "TBD";
  pricing: Record<PurchaseKey, number>;
  status_rules: StatusRules;
  status_availability?: Partial<
    Record<StatusKey, MeasurementAvailability>
  >;
  status_available_from?: Partial<Record<StatusKey, string>>;
  status_notes?: Partial<Record<StatusKey, string>>;
  scenarios: string[];
  ads: {
    source: string;
    protected_words: string[];
  };
  scoring: {
    scenario: Record<string, number>;
  };
}

export interface FriendStatus {
  paid: boolean | null;
  monshinSubmitted: boolean | null;
  shinsatsuDone: boolean | null;
  shipped: boolean | null;
  needsFollow: boolean | null;
}

export interface LstepFriend {
  userId: string;
  mark: string;
  addedAt: Date;
  lastActionAt: Date | null;
  appliedViaStep: string | null;
  steps: Set<string>;
  paymentClicks: {
    tanpin: boolean;
    teiki: boolean;
  };
  purchases: Set<PurchaseKey>;
  status: FriendStatus;
  step0Branch: string | null;
}

export interface FunnelStep {
  key:
    | "registered"
    | "started"
    | "step1"
    | "paymentClick"
    | "paid"
    | "monshinSubmitted"
    | "shinsatsuDone"
    | "shipped";
  label: string;
  count: number | null;
  conversionFromPrevious: number | null;
  conversionFromRegistered: number | null;
  note?: string;
}

export interface FunnelResult {
  steps: FunnelStep[];
  needsFollowCount: number | null;
}

export interface KpiPeriod {
  key: string;
  label: string;
  flow: "旧フロー" | "新フロー";
  registrations: number;
  paid: number;
  purchases: Record<PurchaseKey, number>;
  cvr: number | null;
  teikiRate: number | null;
  revenue: number;
}

export interface TeikiRateResult {
  teiki: number;
  tanpin: number;
  total: number;
  rate: number | null;
  breakdown: Record<PurchaseKey, number>;
}

export interface WeeklyLogEntry {
  weekStart: string;
  registrations: number;
  paid: number;
  teikiRate: number | null;
  needsFollow: number | null;
}

export interface AnalysisResult {
  fileName: string;
  importedCount: number;
  skippedCount: number;
  discardedColumnCount: number;
  detectedEncoding: string;
  dateRange: {
    start: string;
    end: string;
  };
  funnel: FunnelResult;
  monthly: KpiPeriod[];
  teikiRate: TeikiRateResult;
  weekly: WeeklyLogEntry[];
  revenue: {
    total: number;
    byProduct: Record<PurchaseKey, { count: number; unitPrice: number; revenue: number }>;
  };
}
