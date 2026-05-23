import type { RawRow, NormalizedRow, ParseResult } from "@/types/ads";

// 全角数字→半角数字
function toHalfWidth(str: string): string {
  return str.replace(/[０-９]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0xfee0));
}

export function cleanNumber(raw: string): number | null {
  if (!raw || !raw.trim()) return null;
  const cleaned = toHalfWidth(raw)
    .replace(/[¥,\s%円]/g, "")
    .trim();
  const n = parseFloat(cleaned);
  return isNaN(n) ? null : n;
}

const DATE_PATTERNS: Array<{ re: RegExp; parse: (m: RegExpMatchArray) => string }> = [
  {
    re: /^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$/,
    parse: (m) => `${m[1]}-${m[2].padStart(2, "0")}-${m[3].padStart(2, "0")}`,
  },
  {
    re: /^(\d{4})年(\d{1,2})月(\d{1,2})日$/,
    parse: (m) => `${m[1]}-${m[2].padStart(2, "0")}-${m[3].padStart(2, "0")}`,
  },
  {
    re: /^([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})$/,
    parse: (m) => {
      const months: Record<string, string> = {
        January: "01", February: "02", March: "03", April: "04",
        May: "05", June: "06", July: "07", August: "08",
        September: "09", October: "10", November: "11", December: "12",
        Jan: "01", Feb: "02", Mar: "03", Apr: "04",
        Jun: "06", Jul: "07", Aug: "08", Sep: "09",
        Oct: "10", Nov: "11", Dec: "12",
      };
      const month = months[m[1]];
      if (!month) return "";
      return `${m[3]}-${month}-${m[2].padStart(2, "0")}`;
    },
  },
];

export function parseDate(raw: string): string | null {
  if (!raw || !raw.trim()) return null;
  // 週次レポートの範囲形式に対応
  // 例: "2026年5月18日〜2026年5月24日" → 先頭日付のみ取り出す
  // 例: "2026/05/18 - 2026/05/24" → 先頭日付のみ取り出す
  // 例: "May 18, 2026 – May 24, 2026" → 先頭日付のみ取り出す
  let trimmed = raw.trim();
  const rangeSep = /[〜～\–\—]|-(?=\s*\d{4})/;
  if (rangeSep.test(trimmed)) {
    trimmed = trimmed.split(rangeSep)[0].trim();
  }

  for (const { re, parse } of DATE_PATTERNS) {
    const m = trimmed.match(re);
    if (m) {
      const result = parse(m);
      return result || null;
    }
  }
  return null;
}

export function normalizeRows(rawRows: RawRow[]): ParseResult {
  const rows: NormalizedRow[] = [];
  let skippedCount = 0;

  for (const raw of rawRows) {
    const dateStr = parseDate(raw.date ?? "");
    if (!dateStr) {
      skippedCount++;
      continue;
    }

    const clicks = cleanNumber(raw.clicks ?? "") ?? 0;
    const conversions = cleanNumber(raw.conversions ?? "") ?? 0;
    const cost = cleanNumber(raw.cost ?? "") ?? 0;

    const cvr = clicks > 0 ? conversions / clicks : null;
    const cpa = conversions > 0 ? cost / conversions : null;

    const revenueRaw = cleanNumber(raw.revenue ?? "");
    const revenue = revenueRaw;
    const roas = revenue !== null && cost > 0 ? revenue / cost : null;

    rows.push({
      date: dateStr,
      query: (raw.query ?? "").trim(),
      impressions: cleanNumber(raw.impressions ?? "") ?? 0,
      clicks,
      cost,
      conversions,
      cvr,
      cpa,
      revenue,
      roas,
      campaign: raw.campaign?.trim() || null,
      adGroup: raw.adGroup?.trim() || null,
    });
  }

  return { rows, skippedCount, errors: [] };
}
