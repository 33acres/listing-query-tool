"use client";

import { useMemo, useState } from "react";
import { FlaskConical, TrendingDown, TrendingUp } from "lucide-react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { buildSearchTermCpaDataset } from "@/lib/searchTermCpa/mockData";
import type { SearchTermCpaProject, SearchTermCpaRow } from "@/types/searchTermCpa";

const PROJECT_LABEL: Record<SearchTermCpaProject, string> = {
  ecp: "ECP（緊急避妊薬）",
  std: "STD（性病外来）",
};

const CHART_COLORS = {
  cost: "#0f2740",
  cpa: "#1f6f54",
};

function yen(value: number): string {
  return `¥${Math.round(value).toLocaleString("ja-JP")}`;
}

function realCpa(row: SearchTermCpaRow): number | null {
  return row.realConversions > 0 ? row.cost / row.realConversions : null;
}

function platformCpa(row: SearchTermCpaRow): number | null {
  return row.platformConversions > 0 ? row.cost / row.platformConversions : null;
}

type SortKey = "realCpa" | "realConversions" | "cost" | "revenue";

export function SearchTermCpaDashboard() {
  const [project, setProject] = useState<SearchTermCpaProject>("ecp");
  const [campaignFilter, setCampaignFilter] = useState<string>("all");
  const [sortKey, setSortKey] = useState<SortKey>("realCpa");

  const dataset = useMemo(() => buildSearchTermCpaDataset(project), [project]);

  const campaigns = useMemo(
    () => Array.from(new Set(dataset.rows.map((row) => row.campaign))),
    [dataset]
  );

  const filteredRows = useMemo(() => {
    const rows =
      campaignFilter === "all"
        ? dataset.rows
        : dataset.rows.filter((row) => row.campaign === campaignFilter);

    return [...rows].sort((a, b) => {
      if (sortKey === "realCpa") {
        const aCpa = realCpa(a) ?? Number.POSITIVE_INFINITY;
        const bCpa = realCpa(b) ?? Number.POSITIVE_INFINITY;
        return aCpa - bCpa;
      }
      return b[sortKey] - a[sortKey];
    });
  }, [dataset, campaignFilter, sortKey]);

  const summary = useMemo(() => {
    const totalCost = filteredRows.reduce((sum, row) => sum + row.cost, 0);
    const totalRealConversions = filteredRows.reduce((sum, row) => sum + row.realConversions, 0);
    const totalRevenue = filteredRows.reduce((sum, row) => sum + row.revenue, 0);
    return {
      totalCost,
      totalRealConversions,
      totalRevenue,
      averageRealCpa: totalRealConversions > 0 ? totalCost / totalRealConversions : null,
    };
  }, [filteredRows]);

  const cpaValues = filteredRows
    .map((row) => realCpa(row))
    .filter((value): value is number => value !== null);
  const medianCpa =
    cpaValues.length > 0
      ? [...cpaValues].sort((a, b) => a - b)[Math.floor(cpaValues.length / 2)]
      : null;

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
      <div className="mb-6 flex items-start gap-3 rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
        <FlaskConical className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
        <div>
          <p className="font-semibold">プロトタイプ（ダミーデータ）</p>
          <p className="mt-1 leading-6">
            表示中の数値はすべて画面検証用のダミーデータです。実データ（gclid/ValueTrack突合）が整うまでは実際の広告実績・売上を反映していません。詳細は
            {" "}
            <code className="rounded bg-amber-100 px-1 py-0.5">
              spec/検索語句単位実CPA分析_要件v1.md
            </code>{" "}
            を参照してください。
          </p>
        </div>
      </div>

      <header className="mb-8">
        <p className="text-sm font-semibold text-emerald-700">検索語句単位 実CPA分析</p>
        <h1 className="mt-1 text-2xl font-bold text-slate-950 sm:text-3xl">
          キーワード別 実CPAダッシュボード
        </h1>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          媒体（Google Ads）計測のコンバージョンではなく、実際の成約・売上（実CV）ベースでキーワードの勝ち負けを判断するための画面。
        </p>
      </header>

      <div className="mb-6 flex flex-wrap items-center gap-3">
        <div className="flex rounded-lg border border-slate-200 bg-white p-1 shadow-sm">
          {(Object.keys(PROJECT_LABEL) as SearchTermCpaProject[]).map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => {
                setProject(key);
                setCampaignFilter("all");
              }}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
                project === key
                  ? "bg-slate-950 text-white"
                  : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              {PROJECT_LABEL[key]}
            </button>
          ))}
        </div>

        <select
          value={campaignFilter}
          onChange={(event) => setCampaignFilter(event.target.value)}
          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 shadow-sm"
        >
          <option value="all">全キャンペーン</option>
          {campaigns.map((campaign) => (
            <option key={campaign} value={campaign}>
              {campaign}
            </option>
          ))}
        </select>

        <select
          value={sortKey}
          onChange={(event) => setSortKey(event.target.value as SortKey)}
          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 shadow-sm"
        >
          <option value="realCpa">実CPAが低い順</option>
          <option value="realConversions">実CV数が多い順</option>
          <option value="revenue">実売上が高い順</option>
          <option value="cost">費用が高い順</option>
        </select>
      </div>

      <section className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <SummaryCard label="費用合計" value={yen(summary.totalCost)} />
        <SummaryCard label="実CV合計" value={`${summary.totalRealConversions.toLocaleString("ja-JP")}件`} />
        <SummaryCard
          label="平均実CPA"
          value={summary.averageRealCpa === null ? "—" : yen(summary.averageRealCpa)}
        />
        <SummaryCard label="実売上合計" value={yen(summary.totalRevenue)} />
      </section>

      <section className="mb-8 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <p className="text-sm font-semibold text-emerald-700">日別推移</p>
        <h2 className="mt-1 text-xl font-bold text-slate-950">費用・実CPAの日次推移</h2>
        <div className="mt-4 h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart
              data={dataset.dailyTrend.map((point) => ({
                date: point.date.slice(5),
                費用: point.cost,
                実CPA: point.realCpa,
              }))}
              margin={{ top: 8, right: 8, left: -16, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#eef2f6" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis yAxisId="cost" tick={{ fontSize: 11 }} allowDecimals={false} />
              <YAxis yAxisId="cpa" orientation="right" tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip
                formatter={(value: number, name: string) => [yen(value), name]}
              />
              <Bar yAxisId="cost" dataKey="費用" fill={CHART_COLORS.cost} radius={[4, 4, 0, 0]} />
              <Line
                yAxisId="cpa"
                dataKey="実CPA"
                stroke={CHART_COLORS.cpa}
                strokeWidth={2}
                dot={false}
                connectNulls
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <p className="text-sm font-semibold text-emerald-700">キーワード別</p>
        <h2 className="mt-1 text-xl font-bold text-slate-950">実CPAテーブル</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                <th className="py-2 pr-3">判定</th>
                <th className="py-2 pr-3">検索語句/キーワード</th>
                <th className="py-2 pr-3">キャンペーン</th>
                <th className="py-2 pr-3 text-right">費用</th>
                <th className="py-2 pr-3 text-right">媒体CV</th>
                <th className="py-2 pr-3 text-right">実CV</th>
                <th className="py-2 pr-3 text-right">実CPA</th>
                <th className="py-2 pr-3 text-right">媒体CPA</th>
                <th className="py-2 pr-3 text-right">実売上</th>
              </tr>
            </thead>
            <tbody>
              {filteredRows.map((row) => {
                const rCpa = realCpa(row);
                const pCpa = platformCpa(row);
                const isWinner = medianCpa !== null && rCpa !== null && rCpa <= medianCpa;
                return (
                  <tr key={row.keyword} className="border-b border-slate-100 last:border-0">
                    <td className="py-2 pr-3">
                      {rCpa === null ? (
                        <span className="text-slate-400">—</span>
                      ) : isWinner ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">
                          <TrendingUp className="h-3.5 w-3.5" aria-hidden="true" />
                          勝ち
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded-full bg-rose-50 px-2 py-0.5 text-xs font-medium text-rose-700">
                          <TrendingDown className="h-3.5 w-3.5" aria-hidden="true" />
                          負け
                        </span>
                      )}
                    </td>
                    <td className="py-2 pr-3 font-medium text-slate-900">{row.keyword}</td>
                    <td className="py-2 pr-3 text-slate-600">{row.campaign}</td>
                    <td className="py-2 pr-3 text-right tabular-nums text-slate-700">{yen(row.cost)}</td>
                    <td className="py-2 pr-3 text-right tabular-nums text-slate-500">
                      {row.platformConversions.toLocaleString("ja-JP")}
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums font-semibold text-slate-900">
                      {row.realConversions.toLocaleString("ja-JP")}
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums font-semibold text-slate-900">
                      {rCpa === null ? "—" : yen(rCpa)}
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums text-slate-400">
                      {pCpa === null ? "—" : yen(pCpa)}
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums text-slate-700">{yen(row.revenue)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs leading-5 text-slate-500">
          「判定」は表示中キーワードの実CPA中央値との比較による簡易ラベル（プロトタイプ用の暫定ロジック）。媒体CPAとの差が大きいキーワードほど、媒体計測CVと実CVの乖離が大きい＝要調査。
        </p>
      </section>
    </div>
  );
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium text-slate-500">{label}</p>
      <p className="mt-1 text-xl font-bold text-slate-950">{value}</p>
    </div>
  );
}
