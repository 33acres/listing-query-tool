"use client";

import type { ClassifiedQuery } from "@/types/ads";

interface Props {
  queries: ClassifiedQuery[];
  onExport: () => void;
}

function QueryBadge({ query, score, action }: { query: string; score: number; action: string }) {
  return (
    <div className="border border-gray-100 rounded-lg p-3 space-y-1">
      <div className="flex items-start justify-between gap-2">
        <p className="font-medium text-gray-800 text-sm">{query}</p>
        <span className="text-xs text-gray-400 whitespace-nowrap">スコア: {score.toLocaleString()}</span>
      </div>
      <p className="text-xs text-gray-500">{action}</p>
    </div>
  );
}

function Section({
  title,
  color,
  items,
}: {
  title: string;
  color: string;
  items: ClassifiedQuery[];
}) {
  if (items.length === 0) return null;
  return (
    <div>
      <h3 className={`font-semibold text-sm mb-2 ${color}`}>{title}（{items.length}件）</h3>
      <div className="space-y-2">
        {items.slice(0, 10).map((q, i) => (
          <QueryBadge key={i} query={q.query} score={q.priorityScore} action={q.recommendedAction} />
        ))}
        {items.length > 10 && (
          <p className="text-xs text-gray-400">...他{items.length - 10}件</p>
        )}
      </div>
    </div>
  );
}

export function ActionLists({ queries, onExport }: Props) {
  const waste = queries.filter((q) => q.classification === "無駄クエリ");
  const win = queries.filter((q) => q.classification === "勝ちクエリ");
  const opportunity = queries.filter((q) => q.classification === "機会損失クエリ");
  const caution = queries.filter((q) => q.classification === "要確認");
  const vanished = queries.filter(
    (q) => q.classification === "消滅クエリ" && (q.previous?.conversions ?? 0) > 0
  );

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-base font-bold text-gray-800">アクションリスト</h2>
        <button
          onClick={onExport}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 transition-colors"
        >
          分析結果CSVダウンロード
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Section title="除外候補（無駄クエリ）" color="text-orange-600" items={waste} />
        <Section title="強化すべきクエリ（勝ちクエリ）" color="text-green-600" items={win} />
        <Section title="機会損失クエリ（LP・訴求を要確認）" color="text-yellow-600" items={opportunity} />
        <Section title="要確認（ブランド名含む可能性）" color="text-slate-600" items={caution} />
        {vanished.length > 0 && (
          <Section title="消滅した勝ちクエリ（要アラート）" color="text-purple-600" items={vanished} />
        )}
      </div>
    </div>
  );
}
