from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import yaml
from pypdf import PdfReader


HISTORY_COLUMNS = [
    "project",
    "week_start",
    "week_end",
    "ad_clicks",
    "line_registrations",
    "cv_f",
    "monshin_answers",
    "purchase_cv",
    "line_registration_rate",
    "cv_f_rate",
    "monshin_answer_rate",
    "purchase_rate",
]

MANAGEMENT_COLUMNS = [
    "date",
    "gross_profit",
    "sales",
    "ad_cost",
    "impressions",
    "clicks",
    "cv_f",
    "monshin_answers",
    "treat_drug_cv",
    "test_light_cv",
    "test_basic_cv",
    "test_standard_cv",
    "test_full_cv",
    "purchase_cv",
]

AD_COLUMNS = [
    "date",
    "search_term",
    "cost",
    "clicks",
    "impressions",
    "conversions",
]

PII_PATTERNS = (
    "表示名",
    "氏名",
    "名前",
    "電話",
    "メール",
    "email",
    "住所",
    "自由記述",
)

NUMBER_RE = re.compile(
    r"#DIV/0!|-?\d{1,3}(?:,\d{3})+(?:\.\d+)?%?|-?\d+(?:\.\d+)?%?"
)
PDF_ROW_RE = re.compile(r"(\d{4}/\d{2}/\d{2})([月火水木金土日])")


@dataclass(frozen=True)
class Week:
    start: date
    end: date


def load_config(repo_root: Path, project: str) -> dict[str, Any]:
    path = repo_root / "config" / project / "config.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"configが見つかりません: {path}")
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config.get("project") != project:
        raise ValueError(f"config.projectが不一致です: {config.get('project')!r}")
    required = ("drive", "column_mapping", "weekly_dashboard")
    missing = [key for key in required if key not in config]
    if missing:
        raise ValueError(f"config必須項目が不足しています: {', '.join(missing)}")
    return config


def target_week(run_date: date) -> Week:
    monday = run_date - timedelta(days=run_date.weekday() + 7)
    return Week(start=monday, end=monday + timedelta(days=6))


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == "#DIV/0!":
        return None
    percent = text.endswith("%")
    text = text.rstrip("%").replace(",", "").replace(")", "")
    try:
        number = float(text)
    except ValueError:
        return None
    return number / 100 if percent else number


def _safe_div(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def _read_csv_with_encodings(
    path: Path, encodings: Iterable[str], *, skiprows: int = 0
) -> pd.DataFrame:
    errors: list[str] = []
    for encoding in encodings:
        try:
            return pd.read_csv(path, encoding=encoding, skiprows=skiprows, low_memory=False)
        except (UnicodeDecodeError, pd.errors.ParserError) as error:
            errors.append(f"{encoding}: {error}")
    raise ValueError(f"CSVを読み込めません: {path} ({'; '.join(errors)})")


def _read_table_with_header_search(
    path: Path,
    encodings: Iterable[str],
    *,
    separators: Iterable[str] = (",",),
    header_search_rows: int = 1,
    required_aliases: set[str],
) -> pd.DataFrame:
    errors: list[str] = []
    for encoding in encodings:
        for separator in separators:
            for skiprows in range(header_search_rows):
                try:
                    candidate = pd.read_csv(
                        path,
                        encoding=encoding,
                        sep=separator,
                        skiprows=skiprows,
                        low_memory=False,
                    )
                except (UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as error:
                    errors.append(f"{encoding}/{separator!r}/{skiprows}: {error}")
                    continue
                if required_aliases.intersection(candidate.columns):
                    return candidate
    raise ValueError(f"CSVのヘッダーを検出できません: {path} ({'; '.join(errors[-3:])})")


def _rename_by_aliases(frame: pd.DataFrame, aliases: dict[str, list[str]]) -> pd.DataFrame:
    rename: dict[str, str] = {}
    for canonical, candidates in aliases.items():
        match = next((candidate for candidate in candidates if candidate in frame.columns), None)
        if match:
            rename[match] = canonical
    return frame.rename(columns=rename)


def read_lstep(
    path: Path, config: dict[str, Any], week: Week
) -> tuple[int, dict[str, int]]:
    settings = config["weekly_dashboard"]["lstep"]
    frame = _read_csv_with_encodings(
        path,
        settings["encodings"],
        skiprows=int(settings["header_row"]) - 1,
    )
    added_at = config["column_mapping"]["added_at"]
    if added_at not in frame.columns:
        raise ValueError(f"LステップCSVに必須列がありません: {added_at}")

    allowed = {
        added_at,
        *config.get("status_tags", {}).values(),
        *config.get("purchase_tags", {}).values(),
        *config.get("tags", {}).values(),
        *config.get("branch_tags", {}).values(),
    }
    selected = frame[[column for column in frame.columns if column in allowed]].copy()
    if any(
        pattern.lower() in str(column).lower()
        for column in selected.columns
        for pattern in PII_PATTERNS
    ):
        raise ValueError("PII列がホワイトリストに混入しています")

    selected[added_at] = pd.to_datetime(selected[added_at], errors="coerce")
    start = pd.Timestamp(week.start)
    end_exclusive = pd.Timestamp(week.end + timedelta(days=1))

    min_added_at = selected[added_at].min()
    if pd.isna(min_added_at) or pd.Timestamp(min_added_at).normalize() > start.normalize():
        raise ValueError(
            "LステップCSVが「全量」エクスポートになっていない可能性があります"
            f"（データ中の最も古い友だち追加日時が {min_added_at} で、"
            f"対象週の開始日 {week.start} より後です）。"
            "期間指定・絞り込みをせず、全量で出力し直してください。"
        )

    weekly = selected[
        (selected[added_at] >= start) & (selected[added_at] < end_exclusive)
    ].copy()

    totals: dict[str, int] = {}
    for column in selected.columns:
        if column == added_at:
            continue
        totals[column] = int(pd.to_numeric(selected[column], errors="coerce").fillna(0).sum())
    return int(weekly[added_at].notna().sum()), totals


def read_ads_detail(path: Path, config: dict[str, Any]) -> pd.DataFrame:
    settings = config["weekly_dashboard"]["ads"]
    aliases = settings["column_aliases"]
    required_aliases = {candidate for values in aliases.values() for candidate in values}
    frame = _read_table_with_header_search(
        path,
        settings["encodings"],
        separators=settings["separators"],
        header_search_rows=int(settings["header_search_rows"]),
        required_aliases=required_aliases,
    )
    frame = _rename_by_aliases(frame, aliases)
    missing = {"date", "clicks"} - set(frame.columns)
    if missing:
        if "date" in missing and "週" in frame.columns:
            raise ValueError(
                "広告CSVが「週」単位（週別）でエクスポートされています。"
                "2026年7月以降の運用ルールでは「日」単位（日別）での出力が必要です。"
                "Google広告の検索語句レポートで期間の粒度を「日」に変更して出力し直してください。"
            )
        raise ValueError(f"広告CSVに必須列がありません: {', '.join(sorted(missing))}")
    for column in AD_COLUMNS:
        if column not in frame.columns:
            frame[column] = None
    result = frame[AD_COLUMNS].copy()
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    for column in ("cost", "clicks", "impressions", "conversions"):
        result[column] = result[column].map(lambda value: _parse_number(value) or 0)
    return result.dropna(subset=["date"])


def read_ads(path: Path, config: dict[str, Any], week: Week) -> int:
    settings = config["weekly_dashboard"]["ads"]
    frame = read_ads_detail(path, config)
    if "search_term" in frame.columns:
        account_totals = frame[
            frame["search_term"].astype(str).isin(settings.get("account_total_labels", []))
        ]
        if not account_totals.empty:
            frame = account_totals.copy()
    mask = (frame["date"].dt.date >= week.start) & (frame["date"].dt.date <= week.end)
    weekly = frame[mask]
    return int(round(float(weekly["clicks"].sum())))


def parse_management_pdf_text(text: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    matches = list(PDF_ROW_RE.finditer(text))
    for index, match in enumerate(matches):
        segment_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        tokens = NUMBER_RE.findall(text[match.end() : segment_end])

        if len(tokens) > 6 and re.fullmatch(r"-?\d{6,}", tokens[5]) and tokens[6].endswith("%"):
            merged = tokens[5]
            tokens = [*tokens[:5], merged[:-3], merged[-3:], *tokens[6:]]
        if len(tokens) > 5 and re.fullmatch(r"\d{8,}\.\d+%", tokens[5]):
            merged = tokens[5]
            prefix, decimals = merged[:-1].split(".", 1)
            ctr = f"{prefix[-1]}.{decimals}%"
            impressions_clicks = prefix[:-1]
            split = 4 if len(impressions_clicks) >= 8 else 3
            tokens = [
                *tokens[:5],
                impressions_clicks[:-split],
                impressions_clicks[-split:],
                ctr,
                *tokens[6:],
            ]
        if (
            len(tokens) > 6
            and re.fullmatch(r"\d{5,}\.\d+%", tokens[6])
            and tokens[5].replace(",", "").isdigit()
        ):
            merged = tokens[6]
            prefix, decimals = merged[:-1].split(".", 1)
            tokens = [*tokens[:6], prefix[:-1], f"{prefix[-1]}.{decimals}%", *tokens[7:]]

        values = [_parse_number(token) for token in tokens]
        if len(values) < 19:
            continue
        rows.append(
            {
                "date": pd.Timestamp(datetime.strptime(match.group(1), "%Y/%m/%d").date()),
                "clicks": values[6] or 0,
                "cv_f": values[9] or 0,
                "monshin_answers": values[12] or 0,
                "purchase_cv": sum(value or 0 for value in values[14:19]),
            }
        )
    return pd.DataFrame(rows, columns=MANAGEMENT_COLUMNS)


def _read_management_file(path: Path, config: dict[str, Any]) -> pd.DataFrame:
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(str(path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return parse_management_pdf_text(text)
    if path.suffix.lower() == ".xlsx":
        frame = pd.read_excel(path)
    else:
        settings = config["weekly_dashboard"]["management"]
        aliases = settings["column_aliases"]
        required_aliases = {candidate for values in aliases.values() for candidate in values}
        frame = _read_table_with_header_search(
            path,
            ("utf-8-sig", "cp932", "utf-8"),
            header_search_rows=int(settings.get("header_search_rows", 1)),
            required_aliases=required_aliases,
        )

    settings = config["weekly_dashboard"]["management"]
    aliases = settings["column_aliases"]
    frame = _rename_by_aliases(frame, aliases)
    if "purchase_cv" not in frame.columns:
        component_columns = [
            column
            for column in (
                "treat_drug_cv",
                "test_light_cv",
                "test_basic_cv",
                "test_standard_cv",
                "test_full_cv",
                *settings.get("purchase_cv_component_aliases", []),
            )
            if column in frame.columns
        ]
        if component_columns:
            frame["purchase_cv"] = pd.DataFrame(
                {
                    column: frame[column].map(lambda value: _parse_number(value) or 0)
                    for column in component_columns
                }
            ).sum(axis=1)

    required = {"date", "cv_f", "monshin_answers", "purchase_cv"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"管理表に必須列がありません: {', '.join(sorted(missing))}")
    for column in MANAGEMENT_COLUMNS:
        if column not in frame.columns:
            frame[column] = 0
    result = frame[MANAGEMENT_COLUMNS].copy()
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    for column in set(MANAGEMENT_COLUMNS) - {"date"}:
        result[column] = result[column].map(lambda value: _parse_number(value) or 0)
    return result


def read_management_detail(input_dir: Path, config: dict[str, Any]) -> pd.DataFrame:
    patterns = config["weekly_dashboard"]["management"]["file_patterns"]
    files = sorted({path for pattern in patterns for path in input_dir.glob(pattern)})
    if not files:
        raise FileNotFoundError("management.* が見つかりません")
    frames = [_read_management_file(path, config) for path in files]
    combined = pd.concat(frames, ignore_index=True)
    return combined.dropna(subset=["date"]).drop_duplicates(subset=["date"], keep="last")


def read_management(
    input_dir: Path, config: dict[str, Any], week: Week
) -> dict[str, int]:
    combined = read_management_detail(input_dir, config)
    mask = (combined["date"].dt.date >= week.start) & (combined["date"].dt.date <= week.end)
    weekly = combined[mask]
    return {
        column: int(round(float(weekly[column].sum())))
        for column in ("clicks", "cv_f", "monshin_answers", "purchase_cv")
    }


def build_history_row(
    project: str,
    week: Week,
    management: dict[str, int],
    line_registrations: int,
) -> dict[str, Any]:
    clicks = management["clicks"]
    cv_f = management["cv_f"]
    monshin = management["monshin_answers"]
    purchase = management["purchase_cv"]
    return {
        "project": project,
        "week_start": week.start.isoformat(),
        "week_end": week.end.isoformat(),
        "ad_clicks": clicks,
        "line_registrations": line_registrations,
        "cv_f": cv_f,
        "monshin_answers": monshin,
        "purchase_cv": purchase,
        "line_registration_rate": _safe_div(line_registrations, clicks),
        "cv_f_rate": _safe_div(cv_f, clicks),
        "monshin_answer_rate": _safe_div(monshin, clicks),
        "purchase_rate": _safe_div(purchase, clicks),
    }


def update_history(path: Path, row: dict[str, Any]) -> pd.DataFrame:
    if path.exists():
        history = pd.read_csv(path)
    else:
        history = pd.DataFrame(columns=HISTORY_COLUMNS)
    for column in HISTORY_COLUMNS:
        if column not in history.columns:
            history[column] = None
    key = (history["project"] == row["project"]) & (
        history["week_start"].astype(str) == row["week_start"]
    )
    history = history.loc[~key, HISTORY_COLUMNS]
    history = pd.concat([history, pd.DataFrame([row])], ignore_index=True)
    history = history.sort_values(["project", "week_start"]).reset_index(drop=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    history.to_csv(path, index=False, encoding="utf-8-sig", float_format="%.10g")
    return history


def monthly_management(management_detail: pd.DataFrame) -> pd.DataFrame:
    frame = management_detail.copy()
    if frame.empty:
        return pd.DataFrame()
    frame["month"] = frame["date"].dt.strftime("%Y-%m")
    grouped = frame.groupby("month", as_index=False)[
        [
            "gross_profit",
            "sales",
            "ad_cost",
            "impressions",
            "clicks",
            "cv_f",
            "monshin_answers",
            "treat_drug_cv",
            "test_light_cv",
            "test_basic_cv",
            "test_standard_cv",
            "test_full_cv",
            "purchase_cv",
        ]
    ].sum()
    grouped["days"] = frame.groupby("month")["date"].nunique().values
    grouped["vertical_roas"] = grouped.apply(lambda r: _safe_div(r["sales"], r["ad_cost"]), axis=1)
    grouped["gross_margin"] = grouped.apply(lambda r: _safe_div(r["gross_profit"], r["sales"]), axis=1)
    grouped["ctr"] = grouped.apply(lambda r: _safe_div(r["clicks"], r["impressions"]), axis=1)
    grouped["cvr"] = grouped.apply(lambda r: _safe_div(r["cv_f"], r["clicks"]), axis=1)
    grouped["cpa"] = grouped.apply(lambda r: _safe_div(r["ad_cost"], r["cv_f"]), axis=1)
    grouped["click_to_purchase"] = grouped.apply(
        lambda r: _safe_div(r["purchase_cv"], r["clicks"]), axis=1
    )
    return grouped


def _build_bottlenecks_row(row: dict[str, Any], bottleneck_row: dict[str, Any] | None) -> pd.DataFrame:
    """当該週のボトルネック判定を bottlenecks.csv 用の要約1行に変換する。

    bottleneck_row は `bottleneck.compute_bottleneck_frame()` が返す全カラムを持つ
    当該週の1行分の辞書（未算出/履歴不足の場合は None）。
    """
    stage_key = bottleneck_row.get("bottleneck_stage") if bottleneck_row else None
    stage_label = bottleneck_row.get("bottleneck_stage_label") if bottleneck_row else None
    severity = bottleneck_row.get("bottleneck_severity_pt") if bottleneck_row else None
    confidence = bottleneck_row.get("bottleneck_confidence") if bottleneck_row else None
    reason = (
        f"{stage_label}のCVRが前週比{severity:+.1f}pt（{confidence}）"
        if stage_label and severity is not None and confidence
        else "比較可能な前週データがないため未判定"
    )
    return pd.DataFrame(
        [
            {
                "week_start": row["week_start"],
                "stage": stage_label,
                "severity_pt": severity,
                "wow_delta_pt": bottleneck_row.get(f"{stage_key}_delta_wow_pt") if stage_key else None,
                "avg4_delta_pt": bottleneck_row.get(f"{stage_key}_delta_avg4_pt") if stage_key else None,
                "confidence": confidence,
                "reason": reason,
            }
        ]
    )


def write_outputs(
    output_dir: Path,
    config: dict[str, Any],
    row: dict[str, Any],
    history: pd.DataFrame,
    source_files: list[Path],
    *,
    bottleneck_row: dict[str, Any] | None = None,
) -> None:
    names = config["drive"]["output_files"]
    output_dir.mkdir(parents=True, exist_ok=True)

    pd.DataFrame([row]).to_csv(
        output_dir / names["kpi"], index=False, encoding="utf-8-sig", float_format="%.10g"
    )
    _build_bottlenecks_row(row, bottleneck_row).to_csv(
        output_dir / names["bottlenecks"], index=False, encoding="utf-8-sig", float_format="%.10g"
    )
    history.to_csv(
        output_dir / names["history"],
        index=False,
        encoding="utf-8-sig",
        float_format="%.10g",
    )

    source_hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(source_files)
    }
    meta = {
        "project": config["project"],
        "week_start": row["week_start"],
        "week_end": row["week_end"],
        "drive_folder_id": config["drive"]["folder_id"],
        "sources": source_hashes,
        "privacy": "Only config-whitelisted aggregate columns are processed; no person-level rows are exported.",
    }
    (output_dir / names["audit"]).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def resolve_paths(
    repo_root: Path,
    project: str,
    run_date: date,
    config: dict[str, Any],
    input_dir: Path | None,
    output_dir: Path | None,
) -> tuple[Path, Path]:
    values = {"project": project, "run_date": run_date.isoformat()}
    settings = config["weekly_dashboard"]
    resolved_input = input_dir or repo_root / settings["input_root"].format(**values)
    resolved_output = output_dir or repo_root / settings["output_root"].format(**values)
    return resolved_input, resolved_output
