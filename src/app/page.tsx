"use client";

import { useState, useCallback, useEffect } from "react";
import { CsvUploader } from "@/components/CsvUploader";
import { SummaryCards } from "@/components/SummaryCards";
import { PeriodSelector } from "@/components/PeriodSelector";
import { QueryTable } from "@/components/QueryTable";
import { ActionLists } from "@/components/ActionLists";
import { parseCsvBuffer } from "@/lib/parseCsv";
import { normalizeRows } from "@/lib/normalizeRows";
import { comparePeriods, buildDefaultPeriod } from "@/lib/comparePeriods";
import { classifyQueries } from "@/lib/classifyQueries";
import { exportToCsv } from "@/lib/exportCsv";
import type { NormalizedRow, ClassifiedQuery, PeriodConfig, SummaryStats } from "@/types/ads";

function buildPeriodFromMode(rows: NormalizedRow[], mode: PeriodConfig["mode"], custom: PeriodConfig): PeriodConfig {
  if (mode === "custom") return custom;
  const days = mode === "7d" ? 7 : mode === "14d" ? 14 : 30;
  return buildDefaultPeriod(rows, days);
}

function calcSummary(queries: ClassifiedQuery[], period: PeriodConfig): SummaryStats {
  const curr = queries.filter((q) => q.current);
  const totalCost = curr.reduce((s, q) => s + (q.current?.cost ?? 0), 0);
  const totalClicks = curr.reduce((s, q) => s + (q.current?.clicks ?? 0), 0);
  const totalConversions = curr.reduce((s, q) => s + (q.current?.conversions ?? 0), 0);
  const avgCpa = totalConversions > 0 ? totalCost / totalConversions : null;

  return {
    totalCost,
    totalClicks,
    totalConversions,
    avgCpa,
    winCount: queries.filter((q) => q.classification === "勝ちクエリ").length,
    loseCount: queries.filter((q) => q.classification === "悪化クエリ").length,
    wasteCount: queries.filter((q) => q.classification === "無駄クエリ" || q.classification === "要確認").length,
    opportunityCount: queries.filter((q) => q.classification === "機会損失クエリ").length,
    newCount: queries.filter((q) => q.classification === "新規クエリ").length,
    vanishedCount: queries.filter((q) => q.classification === "消滅クエリ").length,
    watchCount: queries.filter((q) => q.classification === "監視クエリ").length,
    cautionCount: queries.filter((q) => q.classification === "要確認").length,
  };
}

export default function Home() {
  const [rows, setRows] = useState<NormalizedRow[]>([]);
  const [period, setPeriod] = useState<PeriodConfig>({
    mode: "7d",
    currentStart: "",
    currentEnd: "",
    previousStart: "",
    previousEnd: "",
  });
  const [protectedWords, setProtectedWords] = useState("");
  const [queries, setQueries] = useState<ClassifiedQuery[]>([]);
  const [summary, setSummary] = useState<SummaryStats | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [skippedCount, setSkippedCount] = useState(0);
  const [fileName, setFileName] = useState("");

  const runAnalysis = useCallback(
    (currentRows: NormalizedRow[], currentPeriod: PeriodConfig, words: string) => {
      const protectedList = words.split(",").map((w) => w.trim()).filter(Boolean);
      const compared = comparePeriods(currentRows, currentPeriod);
      const classified = classifyQueries(compared, protectedList);
      classified.sort((a, b) => b.priorityScore - a.priorityScore);
      setQueries(classified);
      setSummary(calcSummary(classified, currentPeriod));
    },
    []
  );

  const handleFile = useCallback(
    async (buffer: ArrayBuffer, name: string) => {
      setIsLoading(true);
      setErrors([]);
      setFileName(name);
      try {
        const { rows: rawRows, missingColumns, foundColumns, skippedCount: rawSkipped, parseError } = await parseCsvBuffer(buffer);

        if (parseError) {
          setErrors([parseError]);
          setIsLoading(false);
          return;
        }

        if (missingColumns.length > 0) {
          const foundColsMsg = foundColumns.length > 0
            ? `検出された列名: ${foundColumns.slice(0, 10).join(" / ")}${foundColumns.length > 10 ? " …" : ""}`
            : "";
          setErrors([
            "必要な列が見つかりません。日付、検索語句、表示回数、クリック数、費用、コンバージョンを含むCSVをアップロードしてください。",
            `不足列: ${missingColumns.join(", ")}`,
            ...(foundColsMsg ? [foundColsMsg] : []),
          ]);
          setIsLoading(false);
          return;
        }

        const { rows: normalized, skippedCount: normSkipped } = normalizeRows(rawRows);
        const totalSkipped = rawSkipped + normSkipped;
        setSkippedCount(totalSkipped);

        if (normalized.length === 0) {
          setErrors(["指定期間に分析対象データがありません。期間設定を変更してください。"]);
          setIsLoading(false);
          return;
        }

        const defaultPeriod = buildDefaultPeriod(normalized, 7);
        setRows(normalized);
        setPeriod(defaultPeriod);
        runAnalysis(normalized, defaultPeriod, protectedWords);
      } catch {
        setErrors(["CSVの読み込みに失敗しました。文字コードまたは列形式を確認してください。"]);
      }
      setIsLoading(false);
    },
    [protectedWords, runAnalysis]
  );

  const handlePeriodChange = useCallback(
    (newPeriod: PeriodConfig) => {
      const resolved = buildPeriodFromMode(rows, newPeriod.mode, newPeriod);
      setPeriod(resolved);
      if (rows.length > 0) runAnalysis(rows, resolved, protectedWords);
    },
    [rows, protectedWords, runAnalysis]
  );

  const handleProtectedWordsChange = useCallback(
    (words: string) => {
      setProtectedWords(words);
      if (rows.length > 0) runAnalysis(rows, period, words);
    },
    [rows, period, runAnalysis]
  );

  const handleExport = useCallback(() => {
    exportToCsv(queries);
  }, [queries]);

  const hasData = rows.length > 0;

  return (
    <main className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 py-8 space-y-6">
        {/* ヘッダー */}
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            Google広告 検索語句レポート 自動診断ツール
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            CSVをアップロードすると、クエリ別に分類・優先度スコアを算出します
          </p>
        </div>

        {/* アップロード */}
        <CsvUploader onFile={handleFile} isLoading={isLoading} />

        {/* エラー表示 */}
        {errors.length > 0 && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-4 space-y-1">
            {errors.map((e, i) => (
              <p key={i} className="text-sm text-red-700">{e}</p>
            ))}
          </div>
        )}

        {/* スキップ件数 */}
        {skippedCount > 0 && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-xl px-4 py-2">
            <p className="text-sm text-yellow-700">
              一部の行は日付または数値を解釈できなかったため除外されました（{skippedCount}行）
            </p>
          </div>
        )}

        {hasData && (
          <>
            {/* ファイル名・期間 */}
            <div className="text-sm text-gray-500">
              解析ファイル: <span className="font-medium text-gray-700">{fileName}</span>
              　今期間: {period.currentStart} 〜 {period.currentEnd}
              　前期間: {period.previousStart} 〜 {period.previousEnd}
            </div>

            {/* 期間・除外禁止ワード */}
            <PeriodSelector
              period={period}
              onChange={handlePeriodChange}
              protectedWords={protectedWords}
              onProtectedWordsChange={handleProtectedWordsChange}
            />

            {/* サマリー */}
            {summary && <SummaryCards stats={summary} />}

            {/* アクションリスト */}
            {queries.length > 0 && (
              <div className="bg-white rounded-xl border border-gray-200 p-5">
                <ActionLists queries={queries} onExport={handleExport} />
              </div>
            )}

            {/* 優先度ランキング表 */}
            {queries.length > 0 && (
              <div className="bg-white rounded-xl border border-gray-200 p-5">
                <h2 className="text-base font-bold text-gray-800 mb-4">
                  優先度ランキング（全{queries.length}クエリ）
                </h2>
                <QueryTable queries={queries} />
              </div>
            )}
          </>
        )}

        {!hasData && !isLoading && errors.length === 0 && (
          <div className="text-center py-16 text-gray-400">
            <p className="text-lg">CSVをアップロードして診断を開始してください</p>
            <p className="text-sm mt-2">Google広告の検索語句レポートCSVに対応しています</p>
          </div>
        )}
      </div>
    </main>
  );
}
