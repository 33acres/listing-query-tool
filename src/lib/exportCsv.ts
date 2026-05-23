import type { ClassifiedQuery } from "@/types/ads";

function fmt(v: number | null | undefined, decimals = 0): string {
  if (v == null) return "";
  return v.toFixed(decimals);
}

export function exportToCsv(queries: ClassifiedQuery[]): void {
  const BOM = "﻿";
  const headers = [
    "検索語句",
    "分類",
    "優先度スコア",
    "前期間クリック",
    "今期間クリック",
    "前期間費用",
    "今期間費用",
    "前期間CV",
    "今期間CV",
    "前期間CPA",
    "今期間CPA",
    "CV差分",
    "費用差分",
    "推奨アクション",
    "要確認フラグ",
  ];

  const rows = queries.map((q) => [
    q.query,
    q.classification,
    String(q.priorityScore),
    fmt(q.previous?.clicks),
    fmt(q.current?.clicks),
    fmt(q.previous?.cost),
    fmt(q.current?.cost),
    fmt(q.previous?.conversions),
    fmt(q.current?.conversions),
    fmt(q.previous?.cpa, 0),
    fmt(q.current?.cpa, 0),
    fmt(q.conversionsDiff),
    fmt(q.costDiff),
    q.recommendedAction,
    q.cautionFlag ? "要確認" : "",
  ]);

  const csvContent =
    BOM +
    [headers, ...rows]
      .map((row) =>
        row
          .map((cell) => `"${String(cell).replace(/"/g, '""')}"`)
          .join(",")
      )
      .join("\r\n");

  const date = new Date().toISOString().slice(0, 10).replace(/-/g, "");
  const fileName = `google_ads_query_diagnosis_${date}.csv`;

  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  a.click();
  URL.revokeObjectURL(url);
}
