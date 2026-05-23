import type { NormalizedRow } from "@/types/ads";

// 今期間: 2026-05-08〜2026-05-14, 前期間: 2026-05-01〜2026-05-07
const BASE_CURRENT = "2026-05-10";
const BASE_PREV = "2026-05-03";

function row(
  date: string,
  query: string,
  impressions: number,
  clicks: number,
  cost: number,
  conversions: number,
  campaign = "テストキャンペーン",
  adGroup = "テスト広告グループ"
): NormalizedRow {
  const cvr = clicks > 0 ? conversions / clicks : null;
  const cpa = conversions > 0 ? cost / conversions : null;
  return {
    date,
    query,
    impressions,
    clicks,
    cost,
    conversions,
    cvr,
    cpa,
    revenue: null,
    roas: null,
    campaign,
    adGroup,
  };
}

export const sampleRows: NormalizedRow[] = [
  // 勝ちクエリ: 今期CV増加、CPA改善
  row(BASE_PREV, "転職エージェント おすすめ", 500, 30, 15000, 2),
  row(BASE_CURRENT, "転職エージェント おすすめ", 600, 40, 18000, 5),

  // 悪化クエリ: 前期CV有り、今期CV減少・CPA悪化
  row(BASE_PREV, "IT転職 未経験", 300, 20, 12000, 3),
  row(BASE_CURRENT, "IT転職 未経験", 350, 22, 14000, 1),

  // 無駄クエリ: 今期費用>=10000、クリック>=20、CV=0
  row(BASE_PREV, "転職サイト 比較", 200, 15, 8000, 0),
  row(BASE_CURRENT, "転職サイト 比較", 400, 25, 15000, 0),

  // 機会損失クエリ: クリック・費用増、CV減少、CVR悪化
  row(BASE_PREV, "転職 30代", 250, 20, 10000, 2),
  row(BASE_CURRENT, "転職 30代", 500, 45, 22000, 2),

  // 新規クエリ (今期のみ)
  row(BASE_CURRENT, "キャリアアップ 方法", 150, 12, 5000, 0),

  // 消滅クエリ (前期のみ、前期CV有り)
  row(BASE_PREV, "転職活動 進め方", 200, 18, 9000, 2),

  // 母数不足 → 監視クエリ
  row(BASE_CURRENT, "転職 40代 女性", 50, 5, 2000, 0),
  row(BASE_PREV, "転職 40代 女性", 40, 4, 1500, 0),

  // ブランド名含む → 要確認
  row(BASE_PREV, "リクナビ 登録", 300, 50, 20000, 0),
  row(BASE_CURRENT, "リクナビ 登録", 400, 60, 28000, 0),

  // 費用に円記号がある行のテスト用（正規化後なので数値として格納済み）
  row(BASE_PREV, "転職 志望動機 書き方", 180, 14, 7000, 1),
  row(BASE_CURRENT, "転職 志望動機 書き方", 190, 15, 7500, 1),
];

// 列名マッピングテスト用の生CSVデータ（文字列形式）
export const sampleCsvJapanese = `日付,検索語句,表示回数,クリック数,費用,コンバージョン
2026-05-03,転職エージェント おすすめ,500,30,"¥15,000",2
2026-05-10,転職エージェント おすすめ,600,40,"¥18,000",5

合計行,,,,,
`;

export const sampleCsvEnglish = `Date,Search term,Impressions,Clicks,Cost,Conversions
2026-05-03,転職エージェント おすすめ,500,30,"15,000",2
2026-05-10,転職エージェント おすすめ,600,40,"18,000",5
`;

export const sampleCsvWithErrors = `日付,検索語句,表示回数,クリック数,費用,コンバージョン
invalid-date,無効な行,100,10,5000,0
2026-05-03,有効な行,200,20,10000,1
,空の日付行,50,5,2000,0
`;

// CVRにパーセント付き（パース前の生データ想定）
export const sampleCsvWithPercent = `Date,Search term,Impressions,Clicks,Cost,Conversions,Conv. rate
2026-05-03,test query,1000,100,"10,000",5,5.00%
`;
