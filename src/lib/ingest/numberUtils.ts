export function toHalfWidth(value: string): string {
  return value.replace(/[０-９]/g, (char) =>
    String.fromCharCode(char.charCodeAt(0) - 0xfee0),
  );
}

export function normalizeCell(value: unknown): string {
  return String(value ?? "")
    .replace(/\u3000/g, " ")
    .trim();
}

export function parseNumber(value: unknown): number | null {
  const normalized = toHalfWidth(normalizeCell(value)).replace(/[,\s¥￥円]/g, "");
  if (!normalized) return null;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

export function isTruthyCell(value: unknown): boolean {
  const normalized = normalizeCell(value).toLowerCase();
  return !["", "0", "false", "no", "null", "undefined"].includes(normalized);
}
