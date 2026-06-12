import "server-only";

import fs from "node:fs";
import path from "node:path";
import { load } from "js-yaml";
import type { AnalyzerConfig, ProjectName } from "@/types/lstep";

function assertConfig(value: unknown, project: ProjectName): asserts value is AnalyzerConfig {
  if (!value || typeof value !== "object") {
    throw new Error(`${project} config.yaml を読み込めませんでした。`);
  }

  const config = value as Partial<AnalyzerConfig>;
  if (
    config.project !== project ||
    !config.column_mapping ||
    !config.tags ||
    !config.pricing ||
    !config.status_rules
  ) {
    throw new Error(`${project} config.yaml の必須項目が不足しています。`);
  }
}

export function loadConfig(project: ProjectName): AnalyzerConfig {
  const configPath = path.join(process.cwd(), "config", project, "config.yaml");
  const parsed = load(fs.readFileSync(configPath, "utf8"));
  assertConfig(parsed, project);
  return parsed;
}
