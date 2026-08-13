import Link from "next/link";
import { AnalyzerClient } from "@/components/AnalyzerClient";
import { loadConfig } from "@/lib/config/loadConfig";

export default function Home() {
  const config = loadConfig("dayvigo");

  return (
    <>
      <div className="border-b border-slate-200 bg-white px-4 py-2 text-right text-xs sm:px-6">
        <Link href="/search-term-cpa" className="text-emerald-700 underline underline-offset-2">
          検索語句単位 実CPAダッシュボード（プロトタイプ）を見る →
        </Link>
      </div>
      <AnalyzerClient config={config} />
    </>
  );
}
