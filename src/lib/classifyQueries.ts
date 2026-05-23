import type { ComparedQuery, ClassifiedQuery, QueryClassification } from "@/types/ads";
import { calcPriorityScore } from "./scoring";

const LOW_DATA_THRESHOLDS = {
  clicks: 10,
  cost: 3000,
  impressions: 100,
  totalClicks: 20,
};

function isLowData(compared: ComparedQuery): boolean {
  const curr = compared.current;
  const prev = compared.previous;
  if (!curr) return true;
  if (curr.clicks < LOW_DATA_THRESHOLDS.clicks) return true;
  if (curr.cost < LOW_DATA_THRESHOLDS.cost) return true;
  if (curr.impressions < LOW_DATA_THRESHOLDS.impressions) return true;
  const totalClicks = (curr.clicks ?? 0) + (prev?.clicks ?? 0);
  if (totalClicks < LOW_DATA_THRESHOLDS.totalClicks) return true;
  return false;
}

function isCautionQuery(query: string, protectedWords: string[]): boolean {
  const q = query.toLowerCase();
  for (const word of protectedWords) {
    if (word.trim() && q.includes(word.trim().toLowerCase())) return true;
  }
  return false;
}

function classify(compared: ComparedQuery): QueryClassification {
  const { current: curr, previous: prev } = compared;

  // 消滅クエリ
  if (prev && !curr) return "消滅クエリ";

  // 新規クエリ
  if (!prev && curr) return "新規クエリ";

  if (!curr) return "監視クエリ";

  // 母数不足 → 監視（例外: 費用>=10000かつCV=0 → 無駄クエリへ）
  const lowData = isLowData(compared);
  if (lowData) {
    if (curr.cost >= 10000 && curr.conversions === 0) {
      // 無駄クエリとして扱う（後続で判定）
    } else {
      return "監視クエリ";
    }
  }

  const prevCV = prev?.conversions ?? 0;
  const currCV = curr.conversions ?? 0;
  const prevCPA = prev?.cpa ?? null;
  const currCPA = curr.cpa ?? null;
  const prevCost = prev?.cost ?? 0;
  const currCost = curr.cost ?? 0;
  const prevClicks = prev?.clicks ?? 0;
  const currClicks = curr.clicks ?? 0;
  const prevCVR = prev?.cvr ?? null;
  const currCVR = curr.cvr ?? null;

  // 無駄クエリ（パターン1）
  if (currCV === 0 && curr.cost >= 10000 && currClicks >= 20) {
    return "無駄クエリ";
  }

  // 無駄クエリ（パターン2）
  if (
    currCost > prevCost &&
    currCV === 0 &&
    prevCV === 0 &&
    currCost + prevCost >= 15000
  ) {
    return "無駄クエリ";
  }

  // 悪化クエリ
  if (
    prevCV >= 1 &&
    currCV < prevCV &&
    !lowData &&
    (currCPA === null || (prevCPA !== null && currCPA > prevCPA) || currCV === 0)
  ) {
    return "悪化クエリ";
  }

  // 勝ちクエリ
  const cpaNotWorse = currCPA === null || prevCPA === null || currCPA <= prevCPA;
  if (currCV > prevCV && cpaNotWorse) return "勝ちクエリ";
  if (currCV >= 2 && prevCPA !== null && currCPA !== null && currCPA < prevCPA) return "勝ちクエリ";
  if (
    currCV > prevCV &&
    prevCV > 0 &&
    (currCV / prevCV) > (currCost / (prevCost || 1))
  ) {
    return "勝ちクエリ";
  }

  // 機会損失クエリ
  if (
    currClicks > prevClicks &&
    currCost > prevCost &&
    currCV <= prevCV &&
    prevCVR !== null &&
    currCVR !== null &&
    currCVR < prevCVR
  ) {
    return "機会損失クエリ";
  }

  return "監視クエリ";
}

function buildAction(classification: QueryClassification, cautionFlag: boolean): string {
  if (cautionFlag && (classification === "無駄クエリ" || classification === "悪化クエリ")) {
    return "ブランド名・高意図ワードを含む可能性があります。除外前に必ず確認してください。";
  }
  switch (classification) {
    case "勝ちクエリ":
      return "CVが増加しており、CPAも悪化していません。予算・入札強化、広告文への反映を検討してください。";
    case "悪化クエリ":
      return "前期間よりCVが減少し、CPAも悪化しています。検索意図、広告文、LP訴求のズレを確認してください。";
    case "無駄クエリ":
      return "一定以上の費用を使用していますが、CVが発生していません。除外候補として確認してください。";
    case "機会損失クエリ":
      return "クリックと費用は増えていますが、CVが伸びていません。流入意図とLPの一致度を確認してください。";
    case "新規クエリ":
      return "今期間から新しく発生したクエリです。費用とCVの推移を数日監視してください。";
    case "消滅クエリ":
      return "前期間には配信実績がありましたが、今期間は出現していません。配信量低下や需要変化を確認してください。";
    case "監視クエリ":
      return "母数が少ないか変化が小さいため、引き続き監視してください。";
    case "要確認":
      return "ブランド名・高意図ワードを含む可能性があります。除外前に必ず確認してください。";
  }
}

export function classifyQueries(
  comparedList: ComparedQuery[],
  protectedWords: string[] = []
): ClassifiedQuery[] {
  return comparedList.map((compared) => {
    let classification = classify(compared);
    const cautionFlag =
      isCautionQuery(compared.query, protectedWords) &&
      (classification === "無駄クエリ" || classification === "悪化クエリ");

    if (cautionFlag) classification = "要確認";

    const priorityScore = calcPriorityScore(compared);
    const recommendedAction = buildAction(classification, false);

    return {
      ...compared,
      classification,
      cautionFlag,
      priorityScore,
      recommendedAction,
    };
  });
}
