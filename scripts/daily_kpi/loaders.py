"""管理表（日次）とLステップ（コホート）を読み、日付キーで突合できる形に整える。

このモジュールが扱う2つのデータは時間軸の意味が違う。混ぜないよう分けてある。

- 管理表: その日に発生した実績（Cost / CTs / CV(F) / 実CV / 売上 / 粗利）。**当日軸**
- Lステップ: 現在のタグ状態を「友だち追加日」に割り当てた集計。**コホート軸**
  （例: 7/21に登録した人のうち、その後いつかの時点で決済リンクを踏んだ人数）

したがって「7/21の決済クリック率」はコホート指標であり、当日の売上とは
そのまま割り算できない。突合はあくまで日付を揃えて並べることと、
管理表CV(F)とLステップ友だち追加数が一致するかの検算のために行う。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import yaml
from pypdf import PdfReader

from scripts.weekly_dashboard.core import (
    PII_PATTERNS,
    _parse_number,
    _rename_by_aliases,
    parse_management_pdf_text,
)

# 管理表から日次で持ち回る列（date以外はすべて数値）
MANAGEMENT_DAILY_COLUMNS = [
    "date",
    "gross_profit",
    "sales",
    "ad_cost",
    "impressions",
    "clicks",
    "cv_f",
    "monshin_answers",
    "purchase_cv",
    "aov",
]

# Lステップのコホート集計列
LSTEP_DAILY_COLUMNS = [
    "date",
    "registrations",
    "payment_clicks",
    "paid_tagged",
    "ng_total",
]

_LSTEP_ID_COLUMN = "ID"


def load_config(repo_root: Path, project: str) -> dict[str, Any]:
    """config/<project>/config.yaml を読み、日次KPIに必要なキーの存在まで検証する。"""
    path = repo_root / "config" / project / "config.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"configが見つかりません: {path}")
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config.get("project") != project:
        raise ValueError(f"config.projectが不一致です: {config.get('project')!r}")
    for key in ("drive", "column_mapping", "daily_kpi", "weekly_dashboard"):
        if key not in config:
            raise ValueError(f"config必須項目が不足しています: {key}")
    return config


def resolve_paths(
    repo_root: Path,
    project: str,
    run_date: Any,
    config: dict[str, Any],
    input_dir: Path | None,
    output_dir: Path | None,
) -> tuple[Path, Path]:
    values = {"project": project, "run_date": run_date.isoformat()}
    settings = config["daily_kpi"]
    resolved_input = input_dir or repo_root / settings["input_root"].format(**values)
    resolved_output = output_dir or repo_root / settings["output_root"].format(**values)
    return resolved_input, resolved_output


# --- 管理表 ---------------------------------------------------------------


def _read_management_csv(path: Path, header_row: int) -> pd.DataFrame:
    """ヘッダー行を固定指定して読む。

    ECPの管理表は1〜3行目が進捗・目標行で、4行目が実ヘッダー。
    weekly_dashboard の header_search 方式は「必須列が1つでも当たった行」を
    採用するため、上部の集計行を誤ってヘッダーに選ぶ余地がある。日次では
    列位置がずれると全指標が壊れるので行番号を固定する。
    """
    errors: list[str] = []
    for encoding in ("utf-8-sig", "cp932", "utf-8"):
        try:
            frame = pd.read_csv(
                path, encoding=encoding, skiprows=header_row - 1, low_memory=False
            )
        except (UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as error:
            errors.append(f"{encoding}: {error}")
            continue
        # 列名に改行が入る（例: "クリニック粗利\n（未入金含む）"）ので正規化
        frame.columns = [re.sub(r"\s+", "", str(column)) for column in frame.columns]
        return frame
    raise ValueError(f"管理表CSVを読み込めません: {path} ({'; '.join(errors)})")


def _normalize_aliases(aliases: dict[str, list[str]]) -> dict[str, list[str]]:
    return {
        canonical: [re.sub(r"\s+", "", candidate) for candidate in candidates]
        for canonical, candidates in aliases.items()
    }


def read_management_frames(input_dir: Path, config: dict[str, Any]) -> pd.DataFrame:
    """管理表を全ファイル読んで縦に結合する（重複日をまだ潰していない状態）。

    `source` 列にファイル名を残す。ファイルはファイル名昇順で読む。実運用の命名
    （`... - 202606.csv` / `... - 20260728.csv`）はYYYYMM・YYYYMMDDなので、
    ファイル名昇順＝エクスポートの新しい順になり、後の行が新しいスナップショットになる。
    """
    weekly = config["weekly_dashboard"]["management"]
    daily = config["daily_kpi"]["management"]
    patterns = weekly["file_patterns"]
    files = sorted({path for pattern in patterns for path in input_dir.glob(pattern)})
    if not files:
        raise FileNotFoundError(
            f"管理表が見つかりません（探索パターン: {', '.join(patterns)} / 場所: {input_dir}）"
        )

    aliases = _normalize_aliases(weekly["column_aliases"])
    frames: list[pd.DataFrame] = []
    for path in files:
        frame = _read_management_file(
            path,
            aliases,
            header_row=int(daily["header_row"]),
            pdf_layout=daily.get("pdf_layout"),
        )
        frame["source"] = path.name
        frames.append(frame)
    combined = pd.concat(frames, ignore_index=True)
    return combined.dropna(subset=["date"]).reset_index(drop=True)


def read_management_daily(input_dir: Path, config: dict[str, Any]) -> pd.DataFrame:
    """管理表を日次1行に正規化する。

    同一日が複数ファイルに現れた場合は後勝ち（新しいエクスポートを採用）。
    値が食い違う場合があるので `management_conflicts()` で別途可視化する。
    実績が入っていない未来日（Cost・CV(F)・実CV・売上がすべて0）は落とす。
    """
    return dedupe_management(read_management_frames(input_dir, config))


def dedupe_management(frames: pd.DataFrame) -> pd.DataFrame:
    combined = frames.drop_duplicates(subset=["date"], keep="last")
    activity = combined[["ad_cost", "cv_f", "purchase_cv", "sales"]].abs().sum(axis=1)
    combined = combined[activity > 0]
    return (
        combined.drop(columns=["source"], errors="ignore")
        .sort_values("date")
        .reset_index(drop=True)
    )


# 食い違いを検査する対象（比率列は端数で揺れるので実数のみ見る）
_CONFLICT_COLUMNS = ("ad_cost", "clicks", "cv_f", "purchase_cv", "sales", "gross_profit")


def management_conflicts(frames: pd.DataFrame) -> pd.DataFrame:
    """同一日が複数の管理表に載っていて、かつ値が食い違う箇所を返す。

    実データで実際に発生している（月次ファイルと最新スナップショットで7/01の
    垂直粗利・売上が違う）。採用しているのは新しいスナップショット側だが、
    黙って片方を捨てると週次の粗利率が1pt動く理由が分からなくなるため報告する。
    """
    if frames.empty or "source" not in frames.columns:
        return pd.DataFrame(columns=["date", "column", "adopted", "adopted_value", "other_value"])

    rows: list[dict[str, Any]] = []
    for date, group in frames.groupby("date"):
        if len(group) < 2:
            continue
        adopted = group.iloc[-1]
        for column in _CONFLICT_COLUMNS:
            values = group[column].round(2).unique()
            if len(values) > 1:
                others = [value for value in values if value != round(adopted[column], 2)]
                rows.append(
                    {
                        "date": date,
                        "column": column,
                        "adopted": adopted["source"],
                        "adopted_value": adopted[column],
                        "other_value": others[0] if others else None,
                    }
                )
    return pd.DataFrame(
        rows, columns=["date", "column", "adopted", "adopted_value", "other_value"]
    )


def _read_management_file(
    path: Path,
    aliases: dict[str, list[str]],
    *,
    header_row: int,
    pdf_layout: str | None,
) -> pd.DataFrame:
    if path.suffix.lower() == ".pdf":
        # parse_management_pdf_text はSTDの管理表の列順に合わせた位置決め実装
        # （values[6]=CTs, values[9]=CV(F) …）。列構成が違う診療科のPDFに当てると
        # 数字がずれたまま黙って通ってしまうため、検証済みレイアウトのみ許可する。
        if pdf_layout != "std":
            raise ValueError(
                f"この診療科の管理表PDFは未対応です（{path.name}）。"
                "PDFの読み取りはSTDの列順に合わせた実装のため、列構成が違う管理表に"
                "適用すると数値がずれます。管理表はCSV（またはXLSX）でエクスポートして"
                "ください。PDFを使う場合は config.daily_kpi.management.pdf_layout に"
                "検証済みレイアウト名を設定してください。"
            )
        reader = PdfReader(str(path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        frame = parse_management_pdf_text(text)
    elif path.suffix.lower() == ".xlsx":
        frame = pd.read_excel(path, skiprows=header_row - 1)
        frame.columns = [re.sub(r"\s+", "", str(column)) for column in frame.columns]
        frame = _rename_by_aliases(frame, aliases)
    else:
        frame = _read_management_file_csv(path, aliases, header_row=header_row)

    missing = {"date", "cv_f", "purchase_cv"} - set(frame.columns)
    if missing:
        raise ValueError(
            f"管理表に必須列がありません: {', '.join(sorted(missing))}（{path.name}）"
        )
    for column in MANAGEMENT_DAILY_COLUMNS:
        if column not in frame.columns:
            frame[column] = 0
    result = frame[MANAGEMENT_DAILY_COLUMNS].copy()
    result["date"] = pd.to_datetime(result["date"], errors="coerce").dt.normalize()
    for column in set(MANAGEMENT_DAILY_COLUMNS) - {"date"}:
        result[column] = result[column].map(lambda value: _parse_number(value) or 0)
    return result


def _read_management_file_csv(
    path: Path, aliases: dict[str, list[str]], *, header_row: int
) -> pd.DataFrame:
    frame = _read_management_csv(path, header_row)
    renamed = _rename_by_aliases(frame, aliases)
    if "date" not in renamed.columns:
        raise ValueError(
            f"管理表のヘッダー行がずれています（{path.name}の{header_row}行目に日付列が見つかりません）。"
            "config.daily_kpi.management.header_row を実ファイルに合わせてください。"
        )
    return renamed


# --- Lステップ -------------------------------------------------------------


def _read_lstep_file(path: Path, config: dict[str, Any]) -> pd.DataFrame:
    settings = config["weekly_dashboard"]["lstep"]
    errors: list[str] = []
    for encoding in settings["encodings"]:
        try:
            return pd.read_csv(
                path,
                encoding=encoding,
                skiprows=int(settings["header_row"]) - 1,
                low_memory=False,
            )
        except (UnicodeDecodeError, pd.errors.ParserError) as error:
            errors.append(f"{encoding}: {error}")
    raise ValueError(f"LステップCSVを読み込めません: {path} ({'; '.join(errors)})")


def _whitelisted_tag_columns(config: dict[str, Any]) -> dict[str, list[str]]:
    """configで定義済みのタグ名だけを役割別に返す（PII列を持ち込まないため）。"""
    return {
        "payment_click": list(config.get("click_tags", {}).values()),
        "paid": list(config.get("status_tags", {}).values()),
        "ng": list(config.get("branch_tags", {}).values()),
        "step": list(config.get("tags", {}).values()),
    }


def load_lstep_frame(input_dir: Path, config: dict[str, Any]) -> pd.DataFrame:
    """年別分割されたLステップCSVを結合し、ホワイトリスト列だけを残す。

    IDで重複排除する（年別ファイルの境界で同一人物が二重に出る場合に備える）。
    """
    patterns = config["daily_kpi"]["lstep"]["file_patterns"]
    files = sorted({path for pattern in patterns for path in input_dir.glob(pattern)})
    if not files:
        raise FileNotFoundError(
            f"LステップCSVが見つかりません（探索パターン: {', '.join(patterns)} / 場所: {input_dir}）"
        )

    added_at = config["column_mapping"]["added_at"]
    roles = _whitelisted_tag_columns(config)
    allowed = {added_at, _LSTEP_ID_COLUMN, *(name for names in roles.values() for name in names)}

    frames: list[pd.DataFrame] = []
    for path in files:
        frame = _read_lstep_file(path, config)
        if added_at not in frame.columns:
            raise ValueError(f"LステップCSVに必須列がありません: {added_at}（{path.name}）")
        selected = frame[[column for column in frame.columns if column in allowed]].copy()
        _assert_no_pii(selected.columns)
        frames.append(selected)

    combined = pd.concat(frames, ignore_index=True)
    if _LSTEP_ID_COLUMN in combined.columns:
        combined = combined.drop_duplicates(subset=[_LSTEP_ID_COLUMN], keep="last")
    combined[added_at] = pd.to_datetime(combined[added_at], errors="coerce")
    return combined.dropna(subset=[added_at])


def _assert_no_pii(columns: Iterable[Any]) -> None:
    leaked = [
        str(column)
        for column in columns
        for pattern in PII_PATTERNS
        if pattern.lower() in str(column).lower()
    ]
    if leaked:
        raise ValueError(f"PII列がホワイトリストに混入しています: {', '.join(sorted(set(leaked)))}")


def _tag_flag(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    """複数タグのいずれかが立っていれば1（ユニーク判定）。列が無ければ全0。"""
    present = [column for column in columns if column in frame.columns]
    if not present:
        return pd.Series(0, index=frame.index, dtype="int64")
    numeric = frame[present].apply(pd.to_numeric, errors="coerce").fillna(0)
    return (numeric > 0).any(axis=1).astype("int64")


def aggregate_lstep_daily(frame: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """友だち追加日ごとのコホート集計（登録数・決済クリック・処方不可・STEP到達）。"""
    added_at = config["column_mapping"]["added_at"]
    roles = _whitelisted_tag_columns(config)

    work = pd.DataFrame({"date": frame[added_at].dt.normalize()})
    work["registrations"] = 1
    work["payment_clicks"] = _tag_flag(frame, roles["payment_click"])
    work["paid_tagged"] = _tag_flag(frame, roles["paid"])
    work["ng_total"] = _tag_flag(frame, roles["ng"])

    # 商品別（延べ・重複あり）とSTEP別到達も同時に出す
    extra_columns: list[str] = []
    for key, tag in config.get("click_tags", {}).items():
        if tag in frame.columns:
            work[f"click_{key}"] = _tag_flag(frame, [tag])
            extra_columns.append(f"click_{key}")
    for key, tag in sorted(config.get("tags", {}).items()):
        if tag in frame.columns:
            work[f"reach_{key}"] = _tag_flag(frame, [tag])
            extra_columns.append(f"reach_{key}")
    for key, tag in config.get("branch_tags", {}).items():
        if tag in frame.columns:
            work[f"ng_{key}"] = _tag_flag(frame, [tag])
            extra_columns.append(f"ng_{key}")

    columns = [
        column for column in LSTEP_DAILY_COLUMNS if column != "date"
    ] + extra_columns
    grouped = work.groupby("date", as_index=False)[columns].sum()
    return grouped.sort_values("date").reset_index(drop=True)
