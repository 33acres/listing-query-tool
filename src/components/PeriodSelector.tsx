"use client";

import type { PeriodConfig } from "@/types/ads";

interface Props {
  period: PeriodConfig;
  onChange: (period: PeriodConfig) => void;
  protectedWords: string;
  onProtectedWordsChange: (words: string) => void;
}

const MODES = [
  { value: "7d", label: "直近7日 vs 前7日" },
  { value: "14d", label: "直近14日 vs 前14日" },
  { value: "30d", label: "直近30日 vs 前30日" },
  { value: "custom", label: "カスタム" },
] as const;

export function PeriodSelector({ period, onChange, protectedWords, onProtectedWordsChange }: Props) {
  const handleMode = (mode: PeriodConfig["mode"]) => {
    onChange({ ...period, mode });
  };

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4 space-y-4">
      <div>
        <p className="text-sm font-medium text-gray-700 mb-2">比較期間</p>
        <div className="flex flex-wrap gap-2">
          {MODES.map((m) => (
            <button
              key={m.value}
              onClick={() => handleMode(m.value)}
              className={`px-3 py-1 text-sm rounded-full border transition-colors ${
                period.mode === m.value
                  ? "bg-blue-600 text-white border-blue-600"
                  : "text-gray-600 border-gray-300 hover:border-blue-400"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      {period.mode === "custom" && (
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-gray-500 mb-1">今期間</p>
            <div className="flex gap-2 items-center">
              <input
                type="date"
                value={period.currentStart}
                onChange={(e) => onChange({ ...period, currentStart: e.target.value })}
                className="border border-gray-300 rounded px-2 py-1"
              />
              <span className="text-gray-400">〜</span>
              <input
                type="date"
                value={period.currentEnd}
                onChange={(e) => onChange({ ...period, currentEnd: e.target.value })}
                className="border border-gray-300 rounded px-2 py-1"
              />
            </div>
          </div>
          <div>
            <p className="text-gray-500 mb-1">前期間</p>
            <div className="flex gap-2 items-center">
              <input
                type="date"
                value={period.previousStart}
                onChange={(e) => onChange({ ...period, previousStart: e.target.value })}
                className="border border-gray-300 rounded px-2 py-1"
              />
              <span className="text-gray-400">〜</span>
              <input
                type="date"
                value={period.previousEnd}
                onChange={(e) => onChange({ ...period, previousEnd: e.target.value })}
                className="border border-gray-300 rounded px-2 py-1"
              />
            </div>
          </div>
        </div>
      )}

      <div>
        <p className="text-sm font-medium text-gray-700 mb-1">
          除外禁止ワード（カンマ区切り）
        </p>
        <input
          type="text"
          value={protectedWords}
          onChange={(e) => onProtectedWordsChange(e.target.value)}
          placeholder="例: ブランド名, 商品名, リクナビ"
          className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
        />
        <p className="text-xs text-gray-400 mt-1">
          このワードを含むクエリは無駄クエリ・悪化クエリではなく「要確認」として扱います
        </p>
      </div>
    </div>
  );
}
