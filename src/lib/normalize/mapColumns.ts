import type { AnalyzerConfig } from "@/types/lstep";

export interface ColumnMap {
  standard: Record<string, string>;
  tags: Record<string, string>;
  branchTags: Record<string, string>;
  statusTags: Record<string, string[]>;
  purchaseTags: Record<string, string>;
  allowedColumns: Set<string>;
}

export function mapColumns(config: AnalyzerConfig): ColumnMap {
  const purchaseTags =
    config.purchase_tags === "TBD" ? {} : config.purchase_tags;
  const standard = { ...config.column_mapping };
  const tags = { ...config.tags };
  const branchTags = { ...(config.branch_tags ?? {}) };
  const statusTags = Object.fromEntries(
    Object.entries(config.status_tags ?? {}).map(([key, value]) => [
      key,
      Array.isArray(value) ? value : [value],
    ]),
  );
  const allowedColumns = new Set([
    ...Object.values(standard),
    ...Object.values(tags),
    ...Object.values(branchTags),
    ...Object.values(statusTags).flat(),
    ...Object.values(purchaseTags),
  ]);

  for (const piiColumn of config.drop_pii) {
    allowedColumns.delete(piiColumn);
  }

  return {
    standard,
    tags,
    branchTags,
    statusTags,
    purchaseTags,
    allowedColumns,
  };
}
