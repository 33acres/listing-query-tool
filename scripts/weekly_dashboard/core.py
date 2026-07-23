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
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
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
                except (UnicodeDecodeError, pd.errors.ParserError) as error:
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


def _style_sheet(sheet: Any) -> None:
    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(color="FFFFFF", bold=True)
    thin = Side(style="thin", color="D9E2F3")
    for row in sheet.iter_rows():
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = Border(bottom=thin)
            if cell.row == 1:
                cell.fill = header_fill
                cell.font = header_font
    for column_cells in sheet.columns:
        width = max(len(str(cell.value or "")) for cell in column_cells[:50])
        sheet.column_dimensions[get_column_letter(column_cells[0].column)].width = min(
            max(width + 2, 10), 28
        )
    sheet.freeze_panes = "A2"


def _append_table(sheet: Any, rows: list[list[Any]], *, start_row: int = 1, start_col: int = 1) -> None:
    for row_index, row_values in enumerate(rows, start_row):
        for col_index, value in enumerate(row_values, start_col):
            sheet.cell(row=row_index, column=col_index, value=value)


def _week_label(value: Any) -> str:
    return pd.Timestamp(value).date().isoformat()


def _monthly_management(management_detail: pd.DataFrame) -> pd.DataFrame:
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


def _weekly_management(management_detail: pd.DataFrame) -> pd.DataFrame:
    frame = management_detail.copy()
    if frame.empty:
        return pd.DataFrame()
    frame["week"] = frame["date"].dt.to_period("W-SUN").apply(lambda p: p.start_time.date())
    grouped = frame.groupby("week", as_index=False)[
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
    grouped["vertical_roas"] = grouped.apply(lambda r: _safe_div(r["sales"], r["ad_cost"]), axis=1)
    grouped["gross_margin"] = grouped.apply(lambda r: _safe_div(r["gross_profit"], r["sales"]), axis=1)
    grouped["ctr"] = grouped.apply(lambda r: _safe_div(r["clicks"], r["impressions"]), axis=1)
    grouped["cvr"] = grouped.apply(lambda r: _safe_div(r["cv_f"], r["clicks"]), axis=1)
    grouped["cpa"] = grouped.apply(lambda r: _safe_div(r["ad_cost"], r["cv_f"]), axis=1)
    grouped["click_to_purchase"] = grouped.apply(
        lambda r: _safe_div(r["purchase_cv"], r["clicks"]), axis=1
    )
    return grouped


def _scenario_rows(config: dict[str, Any], lstep_totals: dict[str, int]) -> list[list[Any]]:
    added_total = max(lstep_totals.values(), default=0)
    sequence = [
        ("分岐", config.get("branch_tags", {}).get("treat")),
        ("分岐", config.get("branch_tags", {}).get("test")),
        ("診察誘導", config.get("tags", {}).get("step0a")),
        ("診察誘導", config.get("tags", {}).get("step1")),
        ("診察誘導", config.get("tags", {}).get("step2")),
        ("診察誘導", config.get("tags", {}).get("step3")),
        ("診察誘導", config.get("tags", {}).get("step4")),
        ("診察誘導", config.get("tags", {}).get("step5")),
        ("診察誘導", config.get("tags", {}).get("step6")),
        ("FAQ", config.get("tags", {}).get("faq1")),
        ("FAQ", config.get("tags", {}).get("faq2")),
    ]
    rows: list[list[Any]] = []
    previous_label = "友だち追加"
    previous_count = added_total
    for category, tag in sequence:
        if not tag:
            continue
        count = int(lstep_totals.get(tag, 0))
        retention = _safe_div(count, previous_count)
        rows.append(
            [
                category,
                tag,
                count,
                _safe_div(count, added_total),
                previous_label,
                previous_count,
                retention,
                max(previous_count - count, 0),
                None if retention is None else max(1 - retention, 0),
                "現在値タグから推定。厳密な発火日時別遷移ではない。",
            ]
        )
        if category == "診察誘導":
            previous_label = tag
            previous_count = count
    return rows


def _ads_top_cost(ads_detail: pd.DataFrame, week: Week) -> pd.DataFrame:
    if ads_detail.empty or "search_term" not in ads_detail.columns:
        return pd.DataFrame()
    mask = (ads_detail["date"].dt.date >= week.start) & (ads_detail["date"].dt.date <= week.end)
    weekly = ads_detail[mask].copy()
    weekly = weekly[weekly["search_term"].notna()]
    weekly = weekly[~weekly["search_term"].astype(str).str.startswith("合計:")]
    if weekly.empty:
        return pd.DataFrame()
    grouped = weekly.groupby("search_term", as_index=False)[
        ["cost", "clicks", "impressions", "conversions"]
    ].sum()
    grouped = grouped.sort_values("cost", ascending=False).head(20).reset_index(drop=True)
    grouped.insert(0, "費用順位", grouped.index + 1)
    grouped.insert(2, "週", week.start.isoformat())
    grouped["CTR"] = grouped.apply(lambda r: _safe_div(r["clicks"], r["impressions"]), axis=1)
    grouped["CVR"] = grouped.apply(lambda r: _safe_div(r["conversions"], r["clicks"]), axis=1)
    grouped["CPA"] = grouped.apply(lambda r: _safe_div(r["cost"], r["conversions"]), axis=1)
    return grouped.rename(
        columns={
            "search_term": "検索クエリ",
            "cost": "週次費用",
            "clicks": "週次クリック",
            "impressions": "週次表示回数",
            "conversions": "週次CV",
        }
    )


def _write_rich_dashboard(
    path: Path,
    config: dict[str, Any],
    row: dict[str, Any],
    history: pd.DataFrame,
    lstep_totals: dict[str, int],
    management_detail: pd.DataFrame,
    ads_detail: pd.DataFrame,
    source_files: list[Path],
) -> None:
    wb = Workbook()
    wb.remove(wb.active)
    dashboard = wb.create_sheet("Dashboard")
    kpi = wb.create_sheet("KPI")
    weekly_sheet = wb.create_sheet("Weekly")
    bottlenecks = wb.create_sheet("Bottlenecks")
    product = wb.create_sheet("Product")
    coupon = wb.create_sheet("Coupon")
    ad_funnel = wb.create_sheet("Ad_Funnel")
    lstep_summary = wb.create_sheet("LSTEP_Summary")
    lstep_scenario = wb.create_sheet("LSTEP_Scenario")
    ads_top = wb.create_sheet("Ads_TopCost")
    meta = wb.create_sheet("Meta")

    monthly = _monthly_management(management_detail)
    weekly_management = _weekly_management(management_detail)
    current_month = monthly.iloc[-1].to_dict() if not monthly.empty else {}
    scenario = _scenario_rows(config, lstep_totals)
    ads_top_cost = _ads_top_cost(ads_detail, Week(date.fromisoformat(row["week_start"]), date.fromisoformat(row["week_end"])))

    dashboard["B1"] = "STD 売上分析ダッシュボード"
    dashboard["B1"].font = Font(size=18, bold=True, color="1F4E78")
    dashboard.merge_cells("B1:L2")
    dashboard["B4"] = f"対象期間: {row['week_start']} - {row['week_end']} / 最終更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    dashboard.merge_cells("B4:L4")
    cards = [
        ("売上金額", current_month.get("sales", 0), "円"),
        ("垂直粗利", current_month.get("gross_profit", 0), "円"),
        ("垂直ROAS", current_month.get("vertical_roas", 0), ""),
        ("購入CV", row["purchase_cv"], ""),
    ]
    for index, (label, value, suffix) in enumerate(cards):
        col = 2 + index * 3
        cell = dashboard.cell(6, col, label)
        val = dashboard.cell(7, col, value)
        dashboard.merge_cells(start_row=6, start_column=col, end_row=6, end_column=col + 1)
        dashboard.merge_cells(start_row=7, start_column=col, end_row=8, end_column=col + 1)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="5B9BD5")
        val.font = Font(size=16, bold=True)
        val.number_format = "0.0%" if label == "垂直ROAS" else '#,##0'
        if suffix == "円":
            val.number_format = '#,##0"円"'

    dashboard["B10"] = "月次KPI"
    kpi_rows = [
        ["月", "売上", "垂直粗利", "粗利率", "広告費", "垂直ROAS", "クリック", "CV(F)", "問診回答", "購入CV", "実CPA"],
    ]
    for record in monthly.to_dict("records"):
        kpi_rows.append(
            [
                record["month"],
                record["sales"],
                record["gross_profit"],
                record["gross_margin"],
                record["ad_cost"],
                record["vertical_roas"],
                record["clicks"],
                record["cv_f"],
                record["monshin_answers"],
                record["purchase_cv"],
                record["cpa"],
            ]
        )
    _append_table(dashboard, kpi_rows, start_row=11, start_col=2)

    dashboard["B17"] = "最新週ファネル"
    funnel_rows = [
        ["段階", "件数", "前段階比"],
        ["広告クリック", row["ad_clicks"], 1],
        ["LINE登録", row["line_registrations"], row["line_registration_rate"]],
        ["CV(F)", row["cv_f"], row["cv_f_rate"]],
        ["問診回答", row["monshin_answers"], row["monshin_answer_rate"]],
        ["購入CV", row["purchase_cv"], row["purchase_rate"]],
    ]
    _append_table(dashboard, funnel_rows, start_row=18, start_col=2)

    dashboard["G17"] = "確認事項"
    note = (
        "問診回答が0だが購入CVは発生。管理表上の問診計測定義またはタグ連携を確認。"
        if row["monshin_answers"] == 0 and row["purchase_cv"] > 0
        else "大きな計測欠損候補なし。"
    )
    dashboard["G18"] = note
    dashboard.merge_cells("G18:L20")

    dashboard["B25"] = "商品別CV"
    product_rows = [
        ["商品", "CV", "単価ベース売上"],
        ["性感染症治療薬", current_month.get("treat_drug_cv", 0), current_month.get("treat_drug_cv", 0) * config["pricing"]["treat_drug"]],
        ["ライトセット", current_month.get("test_light_cv", 0), current_month.get("test_light_cv", 0) * config["pricing"]["test_light"]],
        ["ベーシックセット", current_month.get("test_basic_cv", 0), current_month.get("test_basic_cv", 0) * config["pricing"]["test_basic"]],
        ["スタンダードセット", current_month.get("test_standard_cv", 0), current_month.get("test_standard_cv", 0) * config["pricing"]["test_standard"]],
        ["フルセット", current_month.get("test_full_cv", 0), current_month.get("test_full_cv", 0) * config["pricing"]["test_full"]],
    ]
    _append_table(dashboard, product_rows, start_row=26, start_col=2)

    dashboard["B34"] = "シナリオタグファネル（Lステップ現在値）"
    _append_table(
        dashboard,
        [["区分", "タグ", "人数", "友だち比", "前段階", "前段階人数", "前段階比", "減少数", "減少率"]]
        + [r[:9] for r in scenario],
        start_row=35,
        start_col=2,
    )

    dashboard["B50"] = "広告ファネル歩留り"
    ad_rows = [
        ["項目", "件数", "広告クリック比"],
        ["広告クリック", row["ad_clicks"], 1],
        ["LINE登録", row["line_registrations"], row["line_registration_rate"]],
        ["CV(F)", row["cv_f"], row["cv_f_rate"]],
        ["問診回答", row["monshin_answers"], row["monshin_answer_rate"]],
        ["購入CV", row["purchase_cv"], row["purchase_rate"]],
    ]
    _append_table(dashboard, ad_rows, start_row=51, start_col=2)

    for cell_range in ("B11:L13", "B18:D23", "B26:D31", "B35:J46", "B51:D56"):
        for row_cells in dashboard[cell_range]:
            for cell in row_cells:
                if cell.row in (11, 18, 26, 35, 51):
                    cell.fill = PatternFill("solid", fgColor="1F4E78")
                    cell.font = Font(color="FFFFFF", bold=True)
    dashboard.freeze_panes = "A12"
    for col in range(1, 13):
        dashboard.column_dimensions[get_column_letter(col)].width = 16

    if len(kpi_rows) > 1:
        chart = LineChart()
        chart.title = "月次 売上/粗利"
        chart.add_data(Reference(dashboard, min_col=3, max_col=4, min_row=11, max_row=10 + len(kpi_rows)), titles_from_data=True)
        chart.set_categories(Reference(dashboard, min_col=2, min_row=12, max_row=10 + len(kpi_rows)))
        chart.height = 6
        chart.width = 12
        dashboard.add_chart(chart, "G24")
    chart2 = BarChart()
    chart2.title = "最新週ファネル"
    chart2.add_data(Reference(dashboard, min_col=3, min_row=18, max_row=23), titles_from_data=True)
    chart2.set_categories(Reference(dashboard, min_col=2, min_row=19, max_row=23))
    chart2.height = 6
    chart2.width = 10
    dashboard.add_chart(chart2, "G33")
    chart3 = BarChart()
    chart3.title = "商品別CV"
    chart3.add_data(Reference(dashboard, min_col=3, min_row=26, max_row=31), titles_from_data=True)
    chart3.set_categories(Reference(dashboard, min_col=2, min_row=27, max_row=31))
    chart3.height = 6
    chart3.width = 10
    dashboard.add_chart(chart3, "G47")

    kpi_data = monthly.to_dict("records")
    _append_table(kpi, [list(monthly.columns)] + [[record.get(c) for c in monthly.columns] for record in kpi_data])
    _append_table(weekly_sheet, [list(weekly_management.columns)] + [[record.get(c) for c in weekly_management.columns] for record in weekly_management.to_dict("records")])
    _append_table(
        bottlenecks,
        [["week_start", "bottleneck", "rate", "definition", "note"],
         [row["week_start"], "CV(F)→問診回答", row["monshin_answer_rate"] or 0, "問診回答 / CV(F)", note]],
    )
    _append_table(product, product_rows)
    _append_table(coupon, [["配信日", "配信数", "開封数", "開封率", "検査キット購入クリック", "治療薬購入クリック", "合計クリック", "クリック率(対開封)"], ["未取得", None, None, None, None, None, None, None]])
    _append_table(ad_funnel, ad_rows)
    lstep_columns = ["friends", *list(config.get("status_tags", {}).values()), *list(config.get("purchase_tags", {}).values()), *list(config.get("branch_tags", {}).values()), *list(config.get("tags", {}).values())]
    _append_table(lstep_summary, [lstep_columns, [row["line_registrations"], *[lstep_totals.get(c, 0) for c in lstep_columns[1:]]]])
    _append_table(lstep_scenario, [["category", "tag", "count", "share_of_friends", "previous_stage", "previous_count", "retention_from_previous", "drop_from_previous", "drop_rate_from_previous", "note"], *scenario])
    if not ads_top_cost.empty:
        _append_table(ads_top, [list(ads_top_cost.columns)] + [[record.get(c) for c in ads_top_cost.columns] for record in ads_top_cost.to_dict("records")])
    else:
        _append_table(ads_top, [["費用順位", "検索クエリ", "週", "週次費用", "週次クリック", "週次表示回数", "CTR", "週次CV", "CVR", "CPA"]])
    source_names = {
        "ads": "ads.csv",
        "lstep": "lstep.csv",
        "management": [p.name for p in source_files if p.name not in {"ads.csv", "lstep.csv"}],
    }
    _append_table(
        meta,
        [
            ["key", "value"],
            ["project", config["project"]],
            ["period_start", row["week_start"]],
            ["period_end", row["week_end"]],
            ["generated_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            ["sources", json.dumps(source_names, ensure_ascii=False)],
            ["privacy", "No per-person rows are exported. LSTEP display names are ignored."],
            ["notes", "Phase A canonical pipeline with dashboard-format workbook."],
        ],
    )

    for sheet in wb.worksheets:
        if sheet.title != "Dashboard":
            _style_sheet(sheet)
        for row_cells in sheet.iter_rows():
            for cell in row_cells:
                if isinstance(cell.value, float) and 0 <= cell.value <= 1:
                    cell.number_format = "0.0%"
                elif isinstance(cell.value, (int, float)):
                    cell.number_format = "#,##0"
    wb.save(path)


def write_outputs(
    output_dir: Path,
    config: dict[str, Any],
    row: dict[str, Any],
    history: pd.DataFrame,
    source_files: list[Path],
    lstep_totals: dict[str, int] | None = None,
    management_detail: pd.DataFrame | None = None,
    ads_detail: pd.DataFrame | None = None,
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

    _write_rich_dashboard(
        output_dir / names["dashboard"],
        config,
        row,
        history,
        lstep_totals or {},
        management_detail if management_detail is not None else pd.DataFrame(columns=MANAGEMENT_COLUMNS),
        ads_detail if ads_detail is not None else pd.DataFrame(columns=AD_COLUMNS),
        source_files,
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
