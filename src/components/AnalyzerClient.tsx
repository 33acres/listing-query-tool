"use client";

import { useCallback, useRef, useState } from "react";
import {
  AlertTriangle,
  CalendarDays,
  CircleDollarSign,
  FileUp,
  LockKeyhole,
  TrendingUp,
  Users,
} from "lucide-react";
import { parseCsvBuffer } from "@/lib/ingest/parseCsv";
import { analyzeFriends } from "@/lib/lstep/analyze";
import { mapColumns } from "@/lib/normalize/mapColumns";
import { normalizeFriends } from "@/lib/normalize/normalizeFriends";
import { privacyFilter } from "@/lib/normalize/privacyFilter";
import type {
  AnalysisResult,
  AnalyzerConfig,
  FunnelStep,
} from "@/types/lstep";

interface Props {
  config: AnalyzerConfig;
}

function formatRate(value: number | null): string {
  return value === null ? "未計測" : `${(value * 100).toFixed(1)}%`;
}

function formatNumber(value: number | null): string {
  return value === null ? "未計測" : value.toLocaleString("ja-JP");
}

function KpiCard({
  label,
  value,
  note,
  icon,
}: {
  label: string;
  value: string;
  note: string;
  icon: React.ReactNode;
}) {
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-semibold text-slate-600">{label}</p>
        <span className="rounded-xl bg-blue-50 p-2 text-blue-700">{icon}</span>
      </div>
      <p className="mt-4 text-3xl font-bold tracking-tight text-slate-950">{value}</p>
      <p className="mt-2 text-sm text-slate-500">{note}</p>
    </article>
  );
}

function FunnelRow({ step, index }: { step: FunnelStep; index: number }) {
  return (
    <div className="grid grid-cols-[2rem_minmax(0,1fr)_auto] items-center gap-3 border-b border-slate-100 py-4 last:border-0">
      <span className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-100 text-sm font-bold text-blue-800">
        {index + 1}
      </span>
      <div>
        <p className="font-semibold text-slate-900">{step.label}</p>
        <p className="mt-1 text-xs text-slate-500">
          前段比 {formatRate(step.conversionFromPrevious)} / 登録比{" "}
          {formatRate(step.conversionFromRegistered)}
        </p>
        {step.note && <p className="mt-1 text-xs text-amber-700">{step.note}</p>}
      </div>
      <p className="text-xl font-bold tabular-nums text-slate-950">
        {formatNumber(step.count)}
        {step.count !== null && <span className="ml-1 text-xs font-medium">人</span>}
      </p>
    </div>
  );
}

export function AnalyzerClient({ config }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  const handleFile = useCallback(
    async (file: File) => {
      setIsLoading(true);
      setErrors([]);
      setResult(null);

      try {
        const columns = mapColumns(config);
        const parsed = await parseCsvBuffer(
          await file.arrayBuffer(),
          Object.values(config.column_mapping),
          (row) =>
            privacyFilter(row, columns.allowedColumns, config.drop_pii),
        );
        const normalized = normalizeFriends(
          parsed.rows,
          parsed.headers,
          config,
          columns,
        );

        if (normalized.friends.length === 0) {
          throw new Error(
            "分析できる友だちデータがありません。configの列名とCSVを確認してください。",
          );
        }

        setResult(
          analyzeFriends(normalized.friends, config, {
            fileName: file.name,
            importedCount: normalized.friends.length,
            skippedCount: parsed.skippedCount + normalized.skippedCount,
            discardedColumnCount: normalized.discardedColumnCount,
            detectedEncoding: parsed.encoding,
          }),
        );
        if (parsed.errors.length > 0) setErrors(parsed.errors.slice(0, 5));
      } catch (error) {
        setErrors([
          error instanceof Error
            ? error.message
            : "CSVの読み込みに失敗しました。",
        ]);
      } finally {
        setIsLoading(false);
      }
    },
    [config],
  );

  const newFlowMonthly = result?.monthly.filter((item) => item.flow === "新フロー");
  const latestMonthly = newFlowMonthly?.at(-1);

  return (
    <main className="min-h-screen">
      <header className="border-b border-blue-950/10 bg-blue-950 text-white">
        <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
          <div className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.18em] text-blue-200">
                CUREA Analytics
              </p>
              <h1 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">
                Scenario Revenue Analyzer
              </h1>
              <p className="mt-3 max-w-2xl text-base leading-7 text-blue-100">
                Lステップ友だちCSVをブラウザ内だけで集計し、ファネル・KPI・定期率・売上を確認します。
              </p>
            </div>
            <div className="flex items-center gap-2 rounded-xl bg-white/10 px-4 py-3 text-sm text-blue-50">
              <LockKeyhole className="h-5 w-5" aria-hidden="true" />
              PII非保持・サーバ送信なし
            </div>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm font-semibold text-blue-700">分析案件</p>
              <h2 className="mt-1 text-xl font-bold text-slate-950">
                {config.display_name}
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                新フロー起点: {config.flow.new_flow_start}
              </p>
            </div>
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              disabled={isLoading}
              className="inline-flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-xl bg-amber-500 px-5 py-3 font-bold text-slate-950 transition-colors hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <FileUp className="h-5 w-5" aria-hidden="true" />
              {isLoading ? "分析中..." : "CSVを選択"}
            </button>
          </div>

          <div
            className={`mt-5 cursor-pointer rounded-2xl border-2 border-dashed px-5 py-10 text-center transition-colors ${
              isDragging
                ? "border-blue-500 bg-blue-50"
                : "border-slate-300 bg-slate-50 hover:border-blue-400"
            }`}
            onClick={() => inputRef.current?.click()}
            onDragOver={(event) => {
              event.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setIsDragging(false);
              const file = event.dataTransfer.files[0];
              if (file) void handleFile(file);
            }}
          >
            <input
              ref={inputRef}
              type="file"
              accept=".csv,text/csv"
              className="sr-only"
              aria-label="Lステップ友だちCSV"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void handleFile(file);
                event.target.value = "";
              }}
            />
            <FileUp className="mx-auto h-9 w-9 text-blue-700" aria-hidden="true" />
            <p className="mt-3 font-bold text-slate-900">
              Lステップ友だちCSVをドロップ
            </p>
            <p className="mt-1 text-sm text-slate-500">
              Shift_JIS / UTF-8対応。表示名・未許可列は読み込み時に破棄します。
            </p>
          </div>
        </section>

        {errors.length > 0 && (
          <section
            className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"
            role="alert"
          >
            {errors.map((error) => (
              <p key={error}>{error}</p>
            ))}
          </section>
        )}

        {result && (
          <>
            <section className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">
              <p className="font-bold">取込完了: {result.fileName}</p>
              <p className="mt-1">
                {result.importedCount.toLocaleString("ja-JP")}件 /{" "}
                {result.detectedEncoding} / 破棄列 {result.discardedColumnCount}列 /
                除外行 {result.skippedCount}行
              </p>
              <p className="mt-1">
                新フロー分析期間: {result.dateRange.start}〜{result.dateRange.end}
              </p>
            </section>

            <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <KpiCard
                label="新フロー登録"
                value={`${result.funnel.steps[0].count?.toLocaleString("ja-JP")}人`}
                note="configの新フロー開始日以降"
                icon={<Users className="h-5 w-5" aria-hidden="true" />}
              />
              <KpiCard
                label="決済完了"
                value={`${result.teikiRate.total.toLocaleString("ja-JP")}件`}
                note={`CVR ${latestMonthly ? formatRate(latestMonthly.cvr) : "-"}`}
                icon={<TrendingUp className="h-5 w-5" aria-hidden="true" />}
              />
              <KpiCard
                label="定期率"
                value={formatRate(result.teikiRate.rate)}
                note={`定期 ${result.teikiRate.teiki}件 / 単品 ${result.teikiRate.tanpin}件`}
                icon={<CalendarDays className="h-5 w-5" aria-hidden="true" />}
              />
              <KpiCard
                label="推定売上"
                value={`¥${result.revenue.total.toLocaleString("ja-JP")}`}
                note="購入タグ件数 × config単価"
                icon={<CircleDollarSign className="h-5 w-5" aria-hidden="true" />}
              />
            </section>

            <section className="grid gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(20rem,0.85fr)]">
              <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-sm font-semibold text-blue-700">新フロー</p>
                    <h2 className="mt-1 text-xl font-bold text-slate-950">
                      売上ファネル
                    </h2>
                  </div>
                  <div className="rounded-xl bg-amber-50 px-3 py-2 text-right">
                    <p className="text-xs font-semibold text-amber-800">要フォロー</p>
                    <p className="text-xl font-bold text-amber-950">
                      {result.funnel.needsFollowCount === null
                        ? "未計測"
                        : `${result.funnel.needsFollowCount}人`}
                    </p>
                  </div>
                </div>
                <div className="mt-5">
                  {result.funnel.steps.map((step, index) => (
                    <FunnelRow key={step.key} step={step} index={index} />
                  ))}
                </div>
              </article>

              <div className="space-y-6">
                <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
                  <p className="text-sm font-semibold text-blue-700">購入内訳</p>
                  <h2 className="mt-1 text-xl font-bold text-slate-950">
                    売上推定
                  </h2>
                  <div className="mt-4 space-y-3">
                    {Object.entries(result.revenue.byProduct).map(([key, item]) => (
                      <div
                        key={key}
                        className="flex items-center justify-between gap-3 rounded-xl bg-slate-50 px-4 py-3"
                      >
                        <div>
                          <p className="font-semibold text-slate-900">
                            {config.purchase_tags === "TBD"
                              ? key
                              : config.purchase_tags[key] ?? key}
                          </p>
                          <p className="text-xs text-slate-500">
                            {item.count}件 × ¥{item.unitPrice.toLocaleString("ja-JP")}
                          </p>
                        </div>
                        <p className="font-bold tabular-nums text-slate-950">
                          ¥{item.revenue.toLocaleString("ja-JP")}
                        </p>
                      </div>
                    ))}
                  </div>
                </article>

                <article className="rounded-2xl border border-amber-200 bg-amber-50 p-5 sm:p-6">
                  <div className="flex gap-3">
                    <AlertTriangle
                      className="mt-0.5 h-5 w-5 shrink-0 text-amber-700"
                      aria-hidden="true"
                    />
                    <div>
                      <h2 className="font-bold text-amber-950">計測状況</h2>
                      <p className="mt-2 text-sm leading-6 text-amber-900">
                        取得できない指標は0件ではなく「未計測」と表示します。判定方法は
                        configのstatus_availability / status_rulesで切り替えられます。
                      </p>
                    </div>
                  </div>
                </article>
              </div>
            </section>

            <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
              <p className="text-sm font-semibold text-blue-700">月別推移</p>
              <h2 className="mt-1 text-xl font-bold text-slate-950">月別KPI</h2>
              <div className="mt-5 overflow-x-auto">
                <table className="min-w-[760px] w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-slate-500">
                      <th className="px-3 py-3 font-semibold">月</th>
                      <th className="px-3 py-3 font-semibold">フロー</th>
                      <th className="px-3 py-3 text-right font-semibold">登録</th>
                      <th className="px-3 py-3 text-right font-semibold">決済</th>
                      <th className="px-3 py-3 text-right font-semibold">CVR</th>
                      <th className="px-3 py-3 text-right font-semibold">定期率</th>
                      <th className="px-3 py-3 text-right font-semibold">推定売上</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.monthly.map((month) => (
                      <tr key={month.key} className="border-b border-slate-100">
                        <td className="px-3 py-3 font-semibold text-slate-900">
                          {month.label}
                        </td>
                        <td className="px-3 py-3 text-slate-600">{month.flow}</td>
                        <td className="px-3 py-3 text-right tabular-nums">
                          {month.registrations.toLocaleString("ja-JP")}
                        </td>
                        <td className="px-3 py-3 text-right tabular-nums">
                          {month.paid.toLocaleString("ja-JP")}
                        </td>
                        <td className="px-3 py-3 text-right tabular-nums">
                          {formatRate(month.cvr)}
                        </td>
                        <td className="px-3 py-3 text-right tabular-nums">
                          {formatRate(month.teikiRate)}
                        </td>
                        <td className="px-3 py-3 text-right font-semibold tabular-nums">
                          ¥{month.revenue.toLocaleString("ja-JP")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
              <p className="text-sm font-semibold text-blue-700">月曜起点</p>
              <h2 className="mt-1 text-xl font-bold text-slate-950">週次ログ</h2>
              <div className="mt-5 overflow-x-auto">
                <table className="min-w-[640px] w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-slate-500">
                      <th className="px-3 py-3 font-semibold">週開始</th>
                      <th className="px-3 py-3 text-right font-semibold">登録</th>
                      <th className="px-3 py-3 text-right font-semibold">決済</th>
                      <th className="px-3 py-3 text-right font-semibold">定期率</th>
                      <th className="px-3 py-3 text-right font-semibold">要フォロー</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.weekly.map((week) => (
                      <tr key={week.weekStart} className="border-b border-slate-100">
                        <td className="px-3 py-3 font-semibold text-slate-900">
                          {week.weekStart}
                        </td>
                        <td className="px-3 py-3 text-right tabular-nums">
                          {week.registrations}
                        </td>
                        <td className="px-3 py-3 text-right tabular-nums">
                          {week.paid}
                        </td>
                        <td className="px-3 py-3 text-right tabular-nums">
                          {formatRate(week.teikiRate)}
                        </td>
                        <td className="px-3 py-3 text-right tabular-nums">
                          {week.needsFollow === null
                            ? "未計測"
                            : week.needsFollow}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
      </div>
    </main>
  );
}
