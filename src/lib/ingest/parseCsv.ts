import Papa from "papaparse";
import { decodeCsvBuffer } from "./encoding";
import { normalizeCell } from "./numberUtils";

export type RawCsvRow = Record<string, string | undefined>;

export interface ParsedCsv {
  rows: RawCsvRow[];
  headers: string[];
  encoding: string;
  skippedCount: number;
  errors: string[];
}

function findHeaderLine(text: string, expectedColumns: string[]): number {
  const lines = text.split(/\r?\n/);
  const required = expectedColumns.filter(Boolean);

  for (let index = 0; index < Math.min(lines.length, 30); index += 1) {
    const parsed = Papa.parse<string[]>(lines[index], { skipEmptyLines: false });
    const cells = (parsed.data[0] ?? []).map(normalizeCell);
    const matches = required.filter((column) => cells.includes(column)).length;
    if (matches >= Math.min(2, required.length)) return index;
  }

  return 0;
}

export async function parseCsvBuffer(
  buffer: ArrayBuffer,
  expectedColumns: string[],
  rowTransform: (row: RawCsvRow) => RawCsvRow = (row) => row,
): Promise<ParsedCsv> {
  const decoded = decodeCsvBuffer(buffer);
  const lines = decoded.text.split(/\r?\n/);
  const headerLine = findHeaderLine(decoded.text, expectedColumns);
  const csvText = lines.slice(headerLine).join("\n");
  const parsed = Papa.parse<RawCsvRow>(csvText, {
    header: true,
    skipEmptyLines: "greedy",
    transformHeader: normalizeCell,
    transform: normalizeCell,
  });

  const rows = parsed.data
    .filter((row) =>
      Object.values(row).some((value) => normalizeCell(value) !== ""),
    )
    .map(rowTransform);

  return {
    rows,
    headers: (parsed.meta.fields ?? []).map(normalizeCell),
    encoding: decoded.encoding,
    skippedCount: headerLine + (parsed.data.length - rows.length),
    errors: parsed.errors.map(
      (error) =>
        `CSV ${error.row === undefined ? "不明" : error.row + 1}行目: ${error.message}`,
    ),
  };
}
