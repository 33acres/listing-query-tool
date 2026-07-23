from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.weekly_dashboard.core import (  # noqa: E402
    build_history_row,
    load_config,
    read_ads,
    read_lstep,
    read_management,
    resolve_paths,
    target_week,
    update_history,
    write_outputs,
)


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

    line_registrations, _snapshot_totals = read_lstep(lstep_path, config, week)
    ads_path = input_dir / config["drive"]["required_files"]["ads"]
    if not ads_path.is_file():
        raise FileNotFoundError(f"ads.csvが見つかりません: {ads_path}")
    ad_clicks = read_ads(ads_path, config, week)
    management = read_management(input_dir, config, week)
    management["clicks"] = ad_clicks
    row = build_history_row(args.project, week, management, line_registrations)

    history_path = args.history_file or (
        repo_root
        / config["weekly_dashboard"]["history_root"].format(project=args.project)
    )
    history = update_history(history_path, row)
    management_patterns = config["weekly_dashboard"]["management"]["file_patterns"]
    management_files = sorted(
        {path for pattern in management_patterns for path in input_dir.glob(pattern)}
    )
    source_files = [ads_path, lstep_path, *management_files]
    write_outputs(output_dir, config, row, history, source_files)
    print(json.dumps(row, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
