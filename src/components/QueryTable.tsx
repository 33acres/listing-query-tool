"use client";

import { useState, useMemo } from "react";
import type { ClassifiedQuery, QueryClassification } from "@/types/ads";

const CLASS_COLORS: Record<QueryClassification, string> = {
  勝ちクエリ: "bg-green-100 text-green-800",
  悪化クエリ: "bg-red-100 text-red-800",
  無駄クエリ: "bg-orange-100 text-orange-800",
  機会損失クエリ: "bg-yellow-100 text-yellow-800",
  新規クエリ: "bg-blue-100 text-blue-800",
  消滅クエリ: "bg-purple-100 text-purple-800",
  監視クエリ: "bg-gray-100 text-gray-600",
  要確認: "bg-slate-100 text-slate-700",
};

const PAGE_SIZE = 100;

function fmt(n: number | null | undefined, prefix = ""): string {
  if (n == null) return "-";
  return prefix + Math.round(n).toLocaleString("ja-JP");
}

function fmtDiff(n: number | null): string {
  if (n == null) return "-";
  const rounded = Math.round(n);
  return (rounded >= 0 ? "+" : "") + rounded.toLocaleString("ja-JP");
}

function DiffCell({ value, inverse = false }: { value: number | null; inverse?: boolean }) {
  if (value == null) return <span className="text-gray-400">-</span>;
  const positive = inverse ? value < 0 : value > 0;
  const negative = inverse ? value > 0 : value < 0;
  return (
    <span className={positive ? "text-green-600 font-medium" : negative ? "text-red-600 font-medium" : "text-gray-500"}>
      {fmtDiff(value)}
    </span>
  );
}

interface Props {
  queries: ClassifiedQuery[];
}

const ALL_CLASSIFICATIONS: QueryClassification[] = [
  "勝ちクエリ", "悪化クエリ", "無駄クエリ", "機会損失クエリ",
  "新規クエリ", "消滅クエリ", "監視クエリ", "要確認",
];

export function QueryTable({ queries }: Props) {
  const [filterClass, setFilterClass] = useState<QueryClassification | "">("");
  const [searchText, setSearchText] = useState("");
  const [minCost, setMinCost] = useState("");
  const [minCvDiff, setMinCvDiff] = useState("");
  const [page, setPage] = useState(0);

  const filtered = useMemo(() => {
    setPage(0);
    return queries.filter((q) => {
      if (filterClass && q.classification !== filterClass) return false;
      if (searchText && !q.query.toLowerCase().includes(searchText.toLowerCase())) return false;
      if (minCost) {
        const curr = q.current?.cost ?? 0;
        if (curr < Number(minCost)) return false;
      }
      if (minCvDiff) {
        const diff = q.conversionsDiff ?? 0;
        if (diff < Number(minCvDiff)) return false;
      }
      return true;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queries, filterClass, searchText, minCost, minCvDiff]);

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const paged = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <div className="space-y-3">
      {/* フィルター */}
      <div className="flex flex-wrap gap-2 items-center">
        <select
          value={filterClass}
          onChange={(e) => setFilterClass(e.target.value as QueryClassification | "")}
          className="border border-gray-300 rounded px-2 py-1 text-sm"
        >
          <option value="">全分類</option>
          {ALL_CLASSIFICATIONS.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <input
          type="text"
          placeholder="検索語句を検索..."
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          className="border border-gray-300 rounded px-2 py-1 text-sm w-48"
        />
        <input
          type="number"
          placeholder="費用下限（円）"
          value={minCost}
          onChange={(e) => setMinCost(e.target.value)}
          className="border border-gray-300 rounded px-2 py-1 text-sm w-36"
        />
        <input
          type="number"
          placeholder="CV差分下限"
          value={minCvDiff}
          onChange={(e) => setMinCvDiff(e.target.value)}
          className="border border-gray-300 rounded px-2 py-1 text-sm w-28"
        />
        <span className="text-sm text-gray-500">{filtered.length.toLocaleString()}件</span>
      </div>

      {/* テーブル */}
      <div className="overflow-x-auto rounded-xl border border-gray-200">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50 text-gray-600 text-xs">
            <tr>
              <th className="px-3 py-3 text-left">検索語句</th>
              <th className="px-3 py-3 text-left">分類</th>
              <th className="px-3 py-3 text-right">スコア</th>
              <th className="px-3 py-3 text-right">前クリック</th>
              <th className="px-3 py-3 text-right">今クリック</th>
              <th className="px-3 py-3 text-right">前費用</th>
              <th className="px-3 py-3 text-right">今費用</th>
              <th className="px-3 py-3 text-right">前CV</th>
              <th className="px-3 py-3 text-right">今CV</th>
              <th className="px-3 py-3 text-right">前CPA</th>
              <th className="px-3 py-3 text-right">今CPA</th>
              <th className="px-3 py-3 text-right">CV差分</th>
              <th className="px-3 py-3 text-right">費用差分</th>
              <th className="px-3 py-3 text-left min-w-48">推奨アクション</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-100">
            {paged.length === 0 ? (
              <tr>
                <td colSpan={14} className="text-center py-8 text-gray-400">
                  表示できるデータがありません
                </td>
              </tr>
            ) : (
              paged.map((q, i) => (
                <tr key={i} className="hover:bg-gray-50 transition-colors">
                  <td className="px-3 py-2 font-medium text-gray-800 max-w-xs truncate">
                    {q.query}
                  </td>
                  <td className="px-3 py-2">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${CLASS_COLORS[q.classification]}`}>
                      {q.classification}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-gray-700">
                    {q.priorityScore.toLocaleString()}
                  </td>
                  <td className="px-3 py-2 text-right text-gray-500">{fmt(q.previous?.clicks)}</td>
                  <td className="px-3 py-2 text-right text-gray-700">{fmt(q.current?.clicks)}</td>
                  <td className="px-3 py-2 text-right text-gray-500">{fmt(q.previous?.cost, "¥")}</td>
                  <td className="px-3 py-2 text-right text-gray-700">{fmt(q.current?.cost, "¥")}</td>
                  <td className="px-3 py-2 text-right text-gray-500">{fmt(q.previous?.conversions)}</td>
                  <td className="px-3 py-2 text-right text-gray-700">{fmt(q.current?.conversions)}</td>
                  <td className="px-3 py-2 text-right text-gray-500">{fmt(q.previous?.cpa, "¥")}</td>
                  <td className="px-3 py-2 text-right text-gray-700">{fmt(q.current?.cpa, "¥")}</td>
                  <td className="px-3 py-2 text-right">
                    <DiffCell value={q.conversionsDiff} />
                  </td>
                  <td className="px-3 py-2 text-right">
                    <DiffCell value={q.costDiff ? -q.costDiff : null} inverse />
                  </td>
                  <td className="px-3 py-2 text-xs text-gray-500 max-w-xs">{q.recommendedAction}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* ページネーション */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-gray-500">
          <span>
            {(page * PAGE_SIZE + 1).toLocaleString()}〜{Math.min((page + 1) * PAGE_SIZE, filtered.length).toLocaleString()} 件 / 全{filtered.length.toLocaleString()}件
          </span>
          <div className="flex gap-1">
            <button
              onClick={() => setPage(0)}
              disabled={page === 0}
              className="px-2 py-1 rounded border border-gray-300 disabled:opacity-30 hover:bg-gray-50"
            >
              «
            </button>
            <button
              onClick={() => setPage((p) => p - 1)}
              disabled={page === 0}
              className="px-2 py-1 rounded border border-gray-300 disabled:opacity-30 hover:bg-gray-50"
            >
              ‹
            </button>
            <span className="px-3 py-1">{page + 1} / {totalPages}</span>
            <button
              onClick={() => setPage((p) => p + 1)}
              disabled={page >= totalPages - 1}
              className="px-2 py-1 rounded border border-gray-300 disabled:opacity-30 hover:bg-gray-50"
            >
              ›
            </button>
            <button
              onClick={() => setPage(totalPages - 1)}
              disabled={page >= totalPages - 1}
              className="px-2 py-1 rounded border border-gray-300 disabled:opacity-30 hover:bg-gray-50"
            >
              »
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
