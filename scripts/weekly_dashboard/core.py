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
from openpyxl import Workbook
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
    weekly = selected[
        (selected[added_at] >= start) & (selected[added_at] < end_exclusive)
    ].copy()

    totals: dict[str, int] = {}
    for column in selected.columns:
        if column == added_at:
            continue
        totals[column] = int(pd.to_numeric(selected[column], errors="coerce").fillna(0).sum())
    return int(weekly[added_at].notna().sum()), totals


def read_ads(path: Path, config: dict[str, Any], week: Week) -> int:
    settings = config["weekly_dashboard"]["ads"]
    frame: pd.DataFrame | None = None
    aliases = settings["column_aliases"]
    required_aliases = {candidate for values in aliases.values() for candidate in values}
    errors: list[str] = []
    for encoding in settings["encodings"]:
        for separator in settings["separators"]:
            for skiprows in range(int(settings["header_search_rows"])):
                try:
                    candidate = pd.read_csv(
                        path,
                        encoding=encoding,
                        sep=separator,
                        skiprows=skiprows,
                        low_memory=False,
                    )
                except (UnicodeDecodeError, pd.errors.ParserError) as error:
                    errors.append(f"{encoding}/{separator!r}/{skiprows}: {error}")
                    continue
                if required_aliases.intersection(candidate.columns):
                    frame = candidate
                    break
            if frame is not None:
                break
        if frame is not None:
            break
    if frame is None:
        raise ValueError(f"広告CSVのヘッダーを検出できません: {path} ({'; '.join(errors[-3:])})")

    rename: dict[str, str] = {}
    for canonical, candidates in aliases.items():
        match = next((candidate for candidate in candidates if candidate in frame.columns), None)
        if match:
            rename[match] = canonical
    frame = frame.rename(columns=rename)
    missing = {"date", "clicks"} - set(frame.columns)
    if missing:
        raise ValueError(f"広告CSVに必須列がありません: {', '.join(sorted(missing))}")
    if "search_term" in frame.columns:
        account_totals = frame[
            frame["search_term"].astype(str).isin(settings["account_total_labels"])
        ]
        if not account_totals.empty:
            frame = account_totals.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["clicks"] = pd.to_numeric(
        frame["clicks"].astype(str).str.replace(",", "", regex=False),
        errors="coerce",
    ).fillna(0)
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
    return pd.DataFrame(rows, columns=["date", "clicks", "cv_f", "monshin_answers", "purchase_cv"])


def _read_management_file(path: Path, config: dict[str, Any]) -> pd.DataFrame:
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(str(path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return parse_management_pdf_text(text)
    settings = config["weekly_dashboard"]["management"]
    if path.suffix.lower() == ".xlsx":
        frame = pd.read_excel(path)
    else:
        frame = None
        errors: list[str] = []
        aliases = settings["column_aliases"]
        required_aliases = {candidate for values in aliases.values() for candidate in values}
        for skiprows in range(int(settings.get("header_search_rows", 1))):
            try:
                candidate = _read_csv_with_encodings(
                    path, ("utf-8-sig", "cp932", "utf-8"), skiprows=skiprows
                )
            except ValueError as error:
                errors.append(f"{skiprows}: {error}")
                continue
            if required_aliases.intersection(candidate.columns):
                frame = candidate
                break
        if frame is None:
            raise ValueError(
                f"管理表のヘッダーを検出できません: {path} ({'; '.join(errors[-3:])})"
            )

    aliases = settings["column_aliases"]
    rename: dict[str, str] = {}
    for canonical, candidates in aliases.items():
        match = next((candidate for candidate in candidates if candidate in frame.columns), None)
        if match:
            rename[match] = canonical
    frame = frame.rename(columns=rename)
    if "purchase_cv" not in frame.columns:
        component_columns = [
            column
            for column in config["weekly_dashboard"]["management"].get(
                "purchase_cv_component_aliases", []
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
    result = frame[["date", "cv_f", "monshin_answers", "purchase_cv"]].copy()
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    for column in required - {"date"}:
        result[column] = result[column].map(lambda value: _parse_number(value) or 0)
    return result


def read_management(
    input_dir: Path, config: dict[str, Any], week: Week
) -> dict[str, int]:
    patterns = config["weekly_dashboard"]["management"]["file_patterns"]
    files = sorted({path for pattern in patterns for path in input_dir.glob(pattern)})
    if not files:
        raise FileNotFoundError("management.* が見つかりません")
    frames = [_read_management_file(path, config) for path in files]
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.dropna(subset=["date"]).drop_duplicates(subset=["date"], keep="last")
    mask = (combined["date"].dt.date >= week.start) & (combined["date"].dt.date <= week.end)
    weekly = combined[mask]
    return {
        column: int(round(float(weekly[column].sum())))
        for column in ("cv_f", "monshin_answers", "purchase_cv")
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


def write_outputs(
    output_dir: Path,
    config: dict[str, Any],
    row: dict[str, Any],
    history: pd.DataFrame,
    source_files: list[Path],
) -> None:
    names = config["drive"]["output_files"]
    output_dir.mkdir(parents=True, exist_ok=True)

    pd.DataFrame([row]).to_csv(
        output_dir / names["kpi"], index=False, encoding="utf-8-sig", float_format="%.10g"
    )
    pd.DataFrame(
        columns=["week_start", "stage", "severity", "reason"]
    ).to_csv(output_dir / names["bottlenecks"], index=False, encoding="utf-8-sig")
    history.to_csv(
        output_dir / names["history"],
        index=False,
        encoding="utf-8-sig",
        float_format="%.10g",
    )

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Weekly"
    sheet.append(HISTORY_COLUMNS)
    for record in history[HISTORY_COLUMNS].itertuples(index=False, name=None):
        sheet.append(list(record))
    workbook.save(output_dir / names["dashboard"])

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
