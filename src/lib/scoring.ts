import type { ComparedQuery } from "@/types/ads";

export function calcPriorityScore(compared: ComparedQuery): number {
  const curr = compared.current;
  const prev = compared.previous;

  const prevCV = prev?.conversions ?? 0;
  const currCV = curr?.conversions ?? 0;
  const prevCost = prev?.cost ?? 0;
  const currCost = curr?.cost ?? 0;
  const prevCPA = prev?.cpa ?? null;
  const currCPA = curr?.cpa ?? null;
  const prevClicks = prev?.clicks ?? 0;
  const currClicks = curr?.clicks ?? 0;
  const prevCVR = prev?.cvr ?? null;
  const currCVR = curr?.cvr ?? null;

  // CV減少インパクト
  const cvDeclineImpact = Math.max(0, prevCV - currCV) * 10000;

  // 費用悪化インパクト
  const costImpact = Math.max(0, currCost - prevCost);

  // CPA悪化インパクト
  let cpaImpact = 0;
  if (currCPA !== null && prevCPA !== null) {
    cpaImpact = Math.max(0, currCPA - prevCPA);
  }

  // 機会損失インパクト
  let opportunityImpact = 0;
  const clicksIncreased = currClicks > prevClicks;
  const cvNotIncreased = currCV <= prevCV;
  if (clicksIncreased && cvNotIncreased) {
    const costIncrease = Math.max(0, currCost - prevCost);
    const cvrDecline =
      prevCVR !== null && currCVR !== null
        ? Math.max(0, prevCVR - currCVR) * 10000
        : 0;
    opportunityImpact = costIncrease + cvrDecline;
  }

  return Math.round(cvDeclineImpact + costImpact + cpaImpact + opportunityImpact);
}
