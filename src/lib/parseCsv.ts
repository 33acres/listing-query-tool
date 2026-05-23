import Papa from "papaparse";
import type { RawRow } from "@/types/ads";

const COLUMN_MAP: Record<string, string> = {
  // date — 日次・週次・月次レポートすべてに対応
  日: "date", 日付: "date", 年月日: "date", Date: "date", Day: "date",
  週: "date", Week: "date",   // 週次集計レポート
  月: "date", Month: "date",  // 月次集計レポート
  四半期: "date", Quarter: "date",
  // query
  検索語句: "query", 検索キーワード: "query", 検索語句テキスト: "query",
  "Search term": "query", "Search keyword": "query", "Search Keyword": "query",
  "Search Term": "query",
  // impressions
  表示回数: "impressions", インプレッション: "impressions", インプレッション数: "impressions",
  Impressions: "impressions", Impr: "impressions",
  // clicks
  クリック数: "clicks", クリック: "clicks", Clicks: "clicks",
  // cost
  費用: "cost", コスト: "cost",
  Cost: "cost", "Cost JPY": "cost",
  // conversions — Google広告は "コンバージョン" 単独 or "コンバージョン: [名前]" になる
  // normalizeHeader で "コンバージョン: [名前]" → "コンバージョン" になりここに一致
  コンバージョン: "conversions", コンバージョン数: "conversions",
  CV: "conversions", Conversions: "conversions", "Conv.": "conversions",
  // cvr
  コンバージョン率: "cvr", CVR: "cvr",
  "Conv. rate": "cvr", "Conversion rate": "cvr",
  // cpa
  コンバージョン単価: "cpa", CPA: "cpa",
  "Cost / conv.": "cpa", "Cost per conversion": "cpa",
  // revenue
  売上: "revenue", コンバージョン値: "revenue",
  "Conv. value": "revenue", "Conversion value": "revenue", Revenue: "revenue",
  // campaign
  キャンペーン: "campaign", Campaign: "campaign",
  // adGroup
  広告グループ: "adGroup", "Ad group": "adGroup", "Ad Group": "adGroup",
};

const REQUIRED_KEYS = ["date", "query", "impressions", "clicks", "cost", "conversions"];

// Google広告が出力する括弧付き・コロン付き列名のための正規化
// 例: "クリック数（クリック）" → "クリック数"
//     "コンバージョン: cv_name" → "コンバージョン"
//     "費用 (JPY)" → "費用"
function normalizeHeader(h: string): string {
  return h
    .trim()
    // 全角・半角括弧内の内容を除去
    .replace(/[（(][^）)]*[）)]/g, "")
    // コロン（全角・半角）以降を除去
    .replace(/\s*[:：].*$/, "")
    .trim();
}

const SKIP_PATTERNS = [
  /^合計/,
  /^合計:/,
  /^総計/,
  /^Total/i,
  /^\s*$/,
];

// 実際の列ヘッダー行を示すキーワード（いずれかが含まれていれば列ヘッダー行と判定）
const HEADER_INDICATOR_KEYS = [
  "日", "日付", "検索語句", "Search term", "Date", "Impressions", "表示回数",
];

function detectEncoding(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  // BOM検出
  if (bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) return "utf-8-bom";
  if (bytes[0] === 0xff && bytes[1] === 0xfe) return "utf-16le";
  return "utf-8";
}

function decodeBuffer(buffer: ArrayBuffer): string {
  const enc = detectEncoding(buffer);
  if (enc === "utf-16le") {
    return new TextDecoder("utf-16le").decode(buffer);
  }
  if (enc === "utf-8-bom") {
    return new TextDecoder("utf-8").decode(buffer.slice(3));
  }
  try {
    const text = new TextDecoder("utf-8").decode(buffer);
    // Shift-JIS判定: 置換文字が多い場合は再デコード
    if ((text.match(/�/g) || []).length > 5) {
      return new TextDecoder("shift-jis").decode(buffer);
    }
    return text;
  } catch {
    return new TextDecoder("shift-jis").decode(buffer);
  }
}

function mapColumns(headers: string[]): Record<string, string> {
  const mapping: Record<string, string> = {};
  for (const h of headers) {
    const trimmed = h.trim();
    // 1. 完全一致を優先
    if (COLUMN_MAP[trimmed]) {
      mapping[trimmed] = COLUMN_MAP[trimmed];
      continue;
    }
    // 2. 括弧・コロン除去後の正規化一致
    //    例: "クリック数（クリック）" → "クリック数" → clicks
    //    例: "コンバージョン: cv_name" → "コンバージョン" → conversions
    //    例: "費用 (JPY)" → "費用" → cost
    const normalized = normalizeHeader(trimmed);
    if (normalized !== trimmed && COLUMN_MAP[normalized]) {
      mapping[trimmed] = COLUMN_MAP[normalized];
      continue;
    }
    // 3. COLUMN_MAPのキーが列名の先頭に含まれるか確認（前方一致）
    //    例: "インプレッション" が "表示回数" 系列の別名として出るケース対応
    for (const [mapKey, stdKey] of Object.entries(COLUMN_MAP)) {
      if (trimmed.startsWith(mapKey) || normalizeHeader(trimmed) === mapKey) {
        mapping[trimmed] = stdKey;
        break;
      }
    }
  }
  return mapping;
}

function isSkipRow(row: RawRow, firstValue: string): boolean {
  for (const p of SKIP_PATTERNS) {
    if (p.test(firstValue)) return true;
  }
  // 全列が空
  if (Object.values(row).every((v) => !v || !v.trim())) return true;
  // 全セルのいずれかが合計系ワードを含む（例: "合計: 検索" が検索語句列に入るケース）
  const allValues = Object.values(row);
  if (allValues.some((v) => /^合計/.test((v ?? "").trim()))) return true;
  return false;
}

export interface CsvParseRawResult {
  rows: RawRow[];
  missingColumns: string[];
  foundColumns: string[];  // デバッグ用：CSVに実際にあった列名
  skippedCount: number;
  parseError: string | null;
}

function skipLeadingMetaRows(text: string): string {
  const lines = text.split(/\r?\n/);
  // Google広告はアカウント名・期間・フィルタ等のメタ行が複数続くことがある
  // 最大20行スキャンしてヘッダー行を探す
  for (let i = 0; i < Math.min(lines.length, 20); i++) {
    const cols = lines[i].split(",").map((c) => c.replace(/^"|"$/g, "").trim());
    // 正規化ヘッダーでもマッチングを試みる
    const isHeaderRow = HEADER_INDICATOR_KEYS.some(
      (k) => cols.includes(k) || cols.some((c) => normalizeHeader(c) === k)
    );
    if (isHeaderRow) {
      return lines.slice(i).join("\n");
    }
  }
  return text;
}

export async function parseCsvBuffer(buffer: ArrayBuffer): Promise<CsvParseRawResult> {
  let text: string;
  try {
    text = decodeBuffer(buffer);
  } catch {
    return { rows: [], missingColumns: [], foundColumns: [], skippedCount: 0, parseError: "CSVの読み込みに失敗しました。文字コードまたは列形式を確認してください。" };
  }

  // タイトル行・期間行などのメタ行を読み飛ばす
  text = skipLeadingMetaRows(text);

  const result = Papa.parse<RawRow>(text, {
    header: true,
    skipEmptyLines: true,
    transformHeader: (h) => h.trim(),
  });

  if (result.errors.length > 0 && result.data.length === 0) {
    return { rows: [], missingColumns: [], foundColumns: [], skippedCount: 0, parseError: "CSVの読み込みに失敗しました。文字コードまたは列形式を確認してください。" };
  }

  const headers = result.meta.fields ?? [];
  const colMap = mapColumns(headers);

  // 必須列チェック
  const foundKeys = new Set(Object.values(colMap));
  const missingColumns = REQUIRED_KEYS.filter((k) => !foundKeys.has(k));
  // デバッグ用：実際に見つかった列名リスト
  const foundColumns = headers;

  const rows: RawRow[] = [];
  let skippedCount = 0;

  for (const raw of result.data) {
    const firstKey = headers[0];
    const firstValue = raw[firstKey] ?? "";

    if (isSkipRow(raw, firstValue)) {
      skippedCount++;
      continue;
    }

    // 列名を標準キーに変換
    const normalized: RawRow = {};
    for (const [origKey, stdKey] of Object.entries(colMap)) {
      normalized[stdKey] = raw[origKey] ?? "";
    }
    rows.push(normalized);
  }

  return { rows, missingColumns, foundColumns, skippedCount, parseError: null };
}
