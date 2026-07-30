"""日次KPI表を生成するCLI。

    .venv/bin/python -m scripts.daily_kpi.main --project ecp --run-date 2026-07-28

入力（--input-dir 既定は output/<project>/<run_date>/raw）:
  - 管理表 CSV/XLSX/PDF（config.weekly_dashboard.management.file_patterns）
  - Lステップ CSV（config.daily_kpi.lstep.file_patterns・年別分割OK）

出力（--output-dir 既定は output/<project>/<run_date>）:
  - daily_kpi.csv               日次KPI表（管理表×Lステップ突合済み）
  - daily_bottleneck.csv        区間別悪化幅・ボトルネック判定・アラート
  - daily_bottleneck_report.md  そのまま読める日本語サマリー
  - daily_kpi_meta.json         入力ファイルのSHA256（再現性の監査用）
  - daily_kpi_history.csv       全期間の追記履歴（output/<project>/直下）

Google Sheetsへの同期は --sync-sheets を付けたときだけ実行する（外部書き込みを
既定で走らせない）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.daily_kpi.bottleneck import (  # noqa: E402
    compute_daily_bottleneck,
    stage_validity,
)
from scripts.daily_kpi.kpi import build_daily_kpi  # noqa: E402
from scripts.daily_kpi.loaders import (  # noqa: E402
    aggregate_lstep_daily,
    dedupe_management,
    load_config,
    load_lstep_frame,
    management_conflicts,
    read_management_frames,
    resolve_paths,
)
from scripts.daily_kpi.report import build_report  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="日次KPI・ボトルネック表を生成する")
    parser.add_argument("--project", required=True)
    parser.add_argument(
        "--run-date",
        required=True,
        type=date.fromisoformat,
        help="実行日（コホート成熟度の基準日。入力スナップショットの取得日を指定する）",
    )
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--history-file", type=Path)
    parser.add_argument(
        "--sync-sheets",
        action="store_true",
        help="config.google_sheets の設定先へDailyKPI/DailyBottleneckタブを洗い替えする",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    config = load_config(repo_root, args.project)
    input_dir, output_dir = resolve_paths(
        repo_root, args.project, args.run_date, config, args.input_dir, args.output_dir
    )
    if not input_dir.is_dir():
        raise FileNotFoundError(f"入力ディレクトリがありません: {input_dir}")

    management_frames = read_management_frames(input_dir, config)
    conflicts = management_conflicts(management_frames)
    management = dedupe_management(management_frames)
    lstep = load_lstep_frame(input_dir, config)
    lstep_daily = aggregate_lstep_daily(lstep, config)
    kpi = build_daily_kpi(
        management, lstep_daily, config, as_of=pd.Timestamp(args.run_date)
    )
    bottleneck = compute_daily_bottleneck(kpi, config)
    validity = stage_validity(kpi, config)

    names = config["daily_kpi"]["output_files"]
    output_dir.mkdir(parents=True, exist_ok=True)
    kpi.to_csv(
        output_dir / names["kpi"], index=False, encoding="utf-8-sig", float_format="%.10g"
    )
    bottleneck.to_csv(
        output_dir / names["bottleneck"],
        index=False,
        encoding="utf-8-sig",
        float_format="%.10g",
    )

    source_files = sorted(
        {
            path
            for pattern in (
                *config["weekly_dashboard"]["management"]["file_patterns"],
                *config["daily_kpi"]["lstep"]["file_patterns"],
            )
            for path in input_dir.glob(pattern)
        }
    )
    report = build_report(
        kpi,
        bottleneck,
        config,
        source_files=[path.name for path in source_files],
        validity=validity,
        conflicts=conflicts,
    )
    (output_dir / names["report"]).write_text(report, encoding="utf-8")

    history_path = args.history_file or (
        repo_root / config["daily_kpi"]["history_root"].format(project=args.project)
    )
    history = update_history(history_path, args.project, kpi, bottleneck)

    meta = {
        "project": args.project,
        "run_date": args.run_date.isoformat(),
        "date_range": [
            pd.Timestamp(kpi["date"].min()).strftime("%Y-%m-%d"),
            pd.Timestamp(kpi["date"].max()).strftime("%Y-%m-%d"),
        ],
        "days": int(len(kpi)),
        "drive_folder_id": config["drive"]["folder_id"],
        "stage_validity": validity,
        "management_conflicts": [
            {
                "date": pd.Timestamp(row["date"]).strftime("%Y-%m-%d"),
                "column": row["column"],
                "adopted": row["adopted"],
                "adopted_value": row["adopted_value"],
                "other_value": row["other_value"],
            }
            for _, row in conflicts.iterrows()
        ],
        "sources": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in source_files
        },
        "privacy": "Only config-whitelisted tag columns are aggregated; no person-level rows are exported.",
    }
    (output_dir / names["audit"]).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if args.sync_sheets:
        from scripts.daily_kpi.sheets import sync_daily  # 遅延importでgspread依存を任意に
        from scripts.weekly_dashboard.sheets_gateway import GspreadSheetsGateway

        gateway = GspreadSheetsGateway(
            credentials_path=repo_root / config["google_sheets"]["credentials_path"],
            spreadsheet_id=config["google_sheets"]["spreadsheet_id"],
        )
        sync_daily(gateway, config, kpi=kpi, bottleneck=bottleneck)

    latest = bottleneck.iloc[-1]
    print(
        json.dumps(
            {
                "project": args.project,
                "date": pd.Timestamp(latest["date"]).strftime("%Y-%m-%d"),
                "bottleneck_stage": latest.get("bottleneck_stage_label"),
                "severity_pt": (
                    None
                    if pd.isna(latest.get("bottleneck_severity_pt"))
                    else round(float(latest["bottleneck_severity_pt"]), 2)
                ),
                "confidence": latest.get("bottleneck_confidence"),
                "alert_level": latest.get("alert_level"),
                "alerts": latest.get("alerts"),
                "days": int(len(kpi)),
                "history_rows": int(len(history)),
            },
            ensure_ascii=False,
        )
    )
    return 0


def update_history(
    path: Path, project: str, kpi: pd.DataFrame, bottleneck: pd.DataFrame
) -> pd.DataFrame:
    """全期間の日次KPI＋判定を1ファイルに保持する（同一日は今回の値で置き換え）。"""
    judgement_columns = [
        "date",
        "bottleneck_stage_label",
        "bottleneck_severity_pt",
        "bottleneck_confidence",
        "alert_level",
        "alerts",
    ]
    merged = kpi.merge(bottleneck[judgement_columns], on="date", how="left")
    merged.insert(0, "project", project)
    merged["date"] = pd.to_datetime(merged["date"]).dt.strftime("%Y-%m-%d")

    if path.exists():
        previous = pd.read_csv(path)
        previous["date"] = previous["date"].astype(str)
        keep = ~(
            (previous["project"] == project) & (previous["date"].isin(set(merged["date"])))
        )
        combined = pd.concat([previous.loc[keep], merged], ignore_index=True)
    else:
        combined = merged
    combined = combined.sort_values(["project", "date"]).reset_index(drop=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(path, index=False, encoding="utf-8-sig", float_format="%.10g")
    return combined


if __name__ == "__main__":
    raise SystemExit(main())
