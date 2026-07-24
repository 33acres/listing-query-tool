from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.weekly_dashboard.bottleneck import compute_bottleneck_frame  # noqa: E402
from scripts.weekly_dashboard.core import (  # noqa: E402
    build_history_row,
    load_config,
    read_ads,
    read_lstep,
    read_management,
    read_management_detail,
    resolve_paths,
    target_week,
    update_history,
    write_outputs,
)
from scripts.weekly_dashboard.sheets_gateway import GspreadSheetsGateway  # noqa: E402
from scripts.weekly_dashboard.sheets_sync import sync_all  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the canonical weekly dashboard")
    parser.add_argument("--project", required=True)
    parser.add_argument("--run-date", required=True, type=date.fromisoformat)
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--history-file", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    config = load_config(repo_root, args.project)
    week = target_week(args.run_date)
    input_dir, output_dir = resolve_paths(
        repo_root, args.project, args.run_date, config, args.input_dir, args.output_dir
    )
    lstep_path = input_dir / config["drive"]["required_files"]["lstep"]
    if not lstep_path.is_file():
        raise FileNotFoundError(f"lstep.csvが見つかりません: {lstep_path}")

    line_registrations, _ = read_lstep(lstep_path, config, week)
    ads_path = input_dir / config["drive"]["required_files"]["ads"]
    if not ads_path.is_file():
        raise FileNotFoundError(f"ads.csvが見つかりません: {ads_path}")
    ad_clicks = read_ads(ads_path, config, week)
    management = read_management(input_dir, config, week)
    management_detail = read_management_detail(input_dir, config)
    management["clicks"] = ad_clicks
    row = build_history_row(args.project, week, management, line_registrations)

    history_path = args.history_file or (
        repo_root / config["weekly_dashboard"]["history_root"].format(project=args.project)
    )
    history = update_history(history_path, row)

    bottleneck_config = config.get("google_sheets", {}).get("bottleneck", {})
    bottleneck_frame = compute_bottleneck_frame(
        history,
        trailing_weeks=int(bottleneck_config.get("trailing_weeks", 4)),
        threshold_pt=float(bottleneck_config.get("threshold_pt", 2.0)),
    )
    current_bottleneck = bottleneck_frame[
        (bottleneck_frame["project"] == args.project)
        & (bottleneck_frame["week_start"] == row["week_start"])
    ]
    bottleneck_row = current_bottleneck.iloc[0].to_dict() if not current_bottleneck.empty else None

    management_patterns = config["weekly_dashboard"]["management"]["file_patterns"]
    management_files = sorted(
        {path for pattern in management_patterns for path in input_dir.glob(pattern)}
    )
    source_files = [ads_path, lstep_path, *management_files]

    # ローカル成果物を先に書く（Google Sheets同期が失敗してもデータは失われない）。
    write_outputs(
        output_dir,
        config,
        row,
        history,
        source_files,
        bottleneck_row=bottleneck_row,
    )

    if config.get("google_sheets", {}).get("enabled"):
        try:
            gateway = GspreadSheetsGateway(
                credentials_path=repo_root / config["google_sheets"]["credentials_path"],
                spreadsheet_id=config["google_sheets"]["spreadsheet_id"],
            )
            sync_all(
                gateway,
                config,
                current_row=row,
                history=history,
                bottleneck=bottleneck_frame,
                management_detail=management_detail,
            )
        except Exception as error:  # noqa: BLE001 - 失敗工程を明示して報告するため意図的に広く捕捉
            raise RuntimeError(f"Google Sheets同期に失敗しました: {error}") from error

    print(json.dumps(row, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
