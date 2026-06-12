import type { AnalyzerConfig } from "@/types/lstep";

export const dayvigoConfig: AnalyzerConfig = {
  project: "dayvigo",
  display_name: "CUREA オンライン睡眠外来",
  flow: { new_flow_start: "2026-04-29" },
  ingest: { encoding: "auto", source: "lstep_friends" },
  drop_pii: ["表示名"],
  column_mapping: {
    user_id: "ID",
    mark: "対応マーク",
    added_at: "友だち追加日時",
    last_action_at: "最終アクション日",
    applied_via_step: "申込経由STEP",
  },
  tags: {
    step0a: "診察誘導_STEP0A",
    step0b: "診察誘導_STEP0B",
    step1: "診察誘導_STEP1",
    payment_click_tanpin: "RM_決済クリック（単品）",
    payment_click_teiki: "RM_決済クリック（定期）",
  },
  purchase_tags: {
    teiki: "デエビゴ定期",
    tanpin_1m: "デエビゴ1ヶ月",
    tanpin_3m: "デエビゴ3ヶ月",
    tanpin_6m: "デエビゴ6ヶ月",
  },
  pricing: {
    teiki: 2980,
    tanpin_1m: 9680,
    tanpin_3m: 22396,
    tanpin_6m: 40348,
  },
  status_rules: {
    paid_marks: ["発送済", "決済済"],
    shipped_marks: ["発送済"],
    monshin_submitted_marks: ["問診提出済み"],
    needs_follow_marks: ["決済済"],
    shinsatsu_done: "TBD",
  },
  scenarios: ["scenario-a", "scenario-b"],
  ads: { source: "google_ads", protected_words: [] },
  scoring: { scenario: {} },
};

export const headers = [
  "ID",
  "表示名",
  "電話番号",
  "対応マーク",
  "友だち追加日時",
  "最終アクション日",
  "申込経由STEP",
  "診察誘導_STEP0A",
  "診察誘導_STEP0B",
  "診察誘導_STEP1",
  "RM_決済クリック（単品）",
  "RM_決済クリック（定期）",
  "デエビゴ定期",
  "デエビゴ1ヶ月",
  "デエビゴ3ヶ月",
  "デエビゴ6ヶ月",
];
