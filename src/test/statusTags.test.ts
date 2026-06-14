import fs from "node:fs";
import path from "node:path";
import { load } from "js-yaml";
import { describe, expect, it } from "vitest";
import { mapColumns } from "@/lib/normalize/mapColumns";
import { normalizeFriends } from "@/lib/normalize/normalizeFriends";
import type { AnalyzerConfig, ProjectName } from "@/types/lstep";

function loadProjectConfig(project: ProjectName): AnalyzerConfig {
  const configPath = path.join(
    process.cwd(),
    "config",
    project,
    "config.yaml",
  );
  return load(fs.readFileSync(configPath, "utf8")) as AnalyzerConfig;
}

describe("status tags effective from 2026-06-14", () => {
  it("dayvigoの旧決済タグと新しい完了タグを併用する", () => {
    const config = loadProjectConfig("dayvigo");
    const headers = [
      "ID",
      "対応マーク",
      "友だち追加日時",
      "決済完了",
      "睡眠_決済済み",
      "睡眠_問診票提出済み",
      "睡眠_発送済み",
    ];
    const normalized = normalizeFriends(
      [
        {
          ID: "1",
          対応マーク: "",
          友だち追加日時: "2026-06-14 10:00:00",
          決済完了: "1",
          睡眠_問診票提出済み: "1",
          睡眠_発送済み: "1",
        },
        {
          ID: "2",
          対応マーク: "",
          友だち追加日時: "2026-06-15 10:00:00",
          睡眠_決済済み: "1",
        },
        {
          ID: "3",
          対応マーク: "",
          友だち追加日時: "2026-06-13 10:00:00",
        },
      ],
      headers,
      config,
      mapColumns(config),
    );

    expect(normalized.friends[0].status).toEqual({
      paid: true,
      monshinSubmitted: true,
      shinsatsuDone: null,
      shipped: true,
      needsFollow: false,
    });
    expect(normalized.friends[1].status).toEqual({
      paid: true,
      monshinSubmitted: false,
      shinsatsuDone: null,
      shipped: false,
      needsFollow: true,
    });
    expect(normalized.friends[2].status.monshinSubmitted).toBeNull();
    expect(normalized.friends[2].status.needsFollow).toBe(false);
  });

  it("STDは開始日前を未計測、開始日以降を新タグで判定する", () => {
    const config = loadProjectConfig("std");
    const headers = [
      "ID",
      "対応マーク",
      "友だち追加日時",
      "フルセット",
      "STD_決済済み",
      "STD_問診票提出済み",
      "STD_発送済み",
    ];
    const normalized = normalizeFriends(
      [
        {
          ID: "1",
          対応マーク: "",
          友だち追加日時: "2026-06-13 10:00:00",
          フルセット: "1",
        },
        {
          ID: "2",
          対応マーク: "",
          友だち追加日時: "2026-06-14 10:00:00",
          STD_決済済み: "1",
          STD_発送済み: "1",
        },
        {
          ID: "3",
          対応マーク: "",
          友だち追加日時: "2026-06-14 11:00:00",
          STD_決済済み: "1",
          STD_問診票提出済み: "1",
        },
      ],
      headers,
      config,
      mapColumns(config),
    );

    expect(normalized.friends[0].status).toEqual({
      paid: true,
      monshinSubmitted: null,
      shinsatsuDone: null,
      shipped: null,
      needsFollow: null,
    });
    expect(normalized.friends[1].status).toEqual({
      paid: true,
      monshinSubmitted: false,
      shinsatsuDone: null,
      shipped: true,
      needsFollow: true,
    });
    expect(normalized.friends[2].status).toEqual({
      paid: true,
      monshinSubmitted: true,
      shinsatsuDone: null,
      shipped: false,
      needsFollow: false,
    });
  });
});
