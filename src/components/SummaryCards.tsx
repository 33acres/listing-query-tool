"use client";

import type { SummaryStats } from "@/types/ads";

interface Props {
  stats: SummaryStats;
}

function Card({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className="text-2xl font-bold text-gray-800">{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  );
}

function fmt(n: number) {
  return n.toLocaleString("ja-JP");
}

export function SummaryCards({ stats }: Props) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      <Card label="総費用" value={`¥${fmt(Math.round(stats.totalCost))}`} />
      <Card label="総クリック" value={fmt(stats.totalClicks)} />
      <Card label="総CV" value={fmt(stats.totalConversions)} />
      <Card
        label="平均CPA"
        value={stats.avgCpa != null ? `¥${fmt(Math.round(stats.avgCpa))}` : "-"}
      />
      <Card label="CV増加クエリ" value={stats.winCount} sub="勝ちクエリ" />
      <Card label="CV減少クエリ" value={stats.loseCount} sub="悪化クエリ" />
      <Card label="無駄クエリ候補" value={stats.wasteCount} sub="要確認含む" />
      <Card label="機会損失クエリ" value={stats.opportunityCount} />
    </div>
  );
}
