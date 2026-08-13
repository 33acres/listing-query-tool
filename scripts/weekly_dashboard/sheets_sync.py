"""週次ファネル履歴・ボトルネック分析結果をGoogle Sheetsへ同期する。

同期は「毎回全件洗い替え」方式（History/Bottleneckタブのデータ行を毎回クリアして
最新の全期間DataFrameで上書き）。行単位upsertより実装がシンプルで、同一週の
再実行でも重複が原理的に発生しない。gspreadに依存するのは sheets_gateway.py のみ。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from scripts.weekly_dashboard import bottleneck as bottleneck_module
from scripts.weekly_dashboard.core import HISTORY_COLUMNS, monthly_management
from scripts.weekly_dashboard.sheets_gateway import (
    ChartSpec,
    FormatSpec,
    SheetRange,
    SheetsGateway,
)

_TREND_ROW_CAPACITY = 2000  # チャート/条件付き書式に使うopen-ended範囲の想定最大行数
_DELTA_SUFFIXES = ("_delta_wow_pt", "_delta_avg4_pt", "_delta_wow_pct", "_delta_avg4_pct")


def _column_letter(index_1_based: int) -> str:
    letters = ""
    value = index_1_based
    while value > 0:
        value, remainder = divmod(value - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def _dataframe_rows(frame: pd.DataFrame, columns: list[str]) -> list[list[Any]]:
    if frame.empty:
        return [columns]
    records = frame[columns].to_dict("records")
    return [columns] + [[record.get(column) for column in columns] for record in records]


def sync_history(gateway: SheetsGateway, config: dict[str, Any], history: pd.DataFrame) -> Any:
    title = config["google_sheets"]["worksheets"]["history"]
    handle = gateway.get_or_create_worksheet(
        title, rows=_TREND_ROW_CAPACITY, cols=len(HISTORY_COLUMNS)
    )
    gateway.replace_all(handle, _dataframe_rows(history, HISTORY_COLUMNS))
    return handle


def sync_bottleneck(
    gateway: SheetsGateway, config: dict[str, Any], bottleneck: pd.DataFrame
) -> Any:
    title = config["google_sheets"]["worksheets"]["bottleneck"]
    columns = bottleneck_module.OUTPUT_COLUMNS
    handle = gateway.get_or_create_worksheet(title, rows=_TREND_ROW_CAPACITY, cols=len(columns))
    gateway.replace_all(handle, _dataframe_rows(bottleneck, columns))

    for position, column in enumerate(columns, start=1):
        if not column.endswith(_DELTA_SUFFIXES):
            continue
        letter = _column_letter(position)
        gateway.ensure_conditional_format(
            handle,
            FormatSpec(
                description=f"bottleneck_{column}_color_scale",
                range_=SheetRange(
                    sheet_id=handle.id,
                    a1_range=f"{letter}2:{letter}{_TREND_ROW_CAPACITY}",
                ),
            ),
        )
    return handle


def _current_bottleneck_row(
    bottleneck: pd.DataFrame, project: str, week_start: str
) -> dict[str, Any]:
    if bottleneck.empty:
        return {}
    match = bottleneck[
        (bottleneck["project"] == project) & (bottleneck["week_start"] == week_start)
    ]
    if match.empty:
        return {}
    return match.iloc[0].to_dict()


def sync_dashboard(
    gateway: SheetsGateway,
    config: dict[str, Any],
    *,
    current_row: dict[str, Any],
    bottleneck: pd.DataFrame,
    management_detail: pd.DataFrame,
    history_handle: Any,
) -> None:
    worksheets = config["google_sheets"]["worksheets"]
    handle = gateway.get_or_create_worksheet(worksheets["dashboard"], rows=60, cols=12)
    gateway.replace_all(handle, [])  # 前回実行分の残存セルを一掃してから書き直す

    monthly = monthly_management(management_detail)
    current_month = monthly.iloc[-1].to_dict() if not monthly.empty else {}
    current_bottleneck = _current_bottleneck_row(
        bottleneck, current_row["project"], current_row["week_start"]
    )

    updates: dict[str, Any] = {
        "B2": f"{config.get('display_name', config['project'])} 週次ダッシュボード",
        "B3": (
            f"対象期間: {current_row['week_start']} - {current_row['week_end']} "
            f"/ 最終更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        ),
        "B5": "売上",
        "C5": current_month.get("sales"),
        "E5": "垂直粗利",
        "F5": current_month.get("gross_profit"),
        "H5": "垂直ROAS",
        "I5": current_month.get("vertical_roas"),
        "K5": "購入CV",
        "L5": current_row.get("purchase_cv"),
        "B8": "ボトルネック（今週）",
        "B9": "段階",
        "C9": current_bottleneck.get("bottleneck_stage_label") or "―",
        "B10": "前週比(pt)",
        "C10": current_bottleneck.get("bottleneck_severity_pt"),
        "B11": "確度",
        "C11": current_bottleneck.get("bottleneck_confidence") or "―",
        "B13": "今週のファネル（チャート用データ）",
        "B14": "段階",
        "C14": "件数",
        "B15": "広告クリック",
        "C15": current_row.get("ad_clicks", 0),
        "B16": "LINE登録",
        "C16": current_row.get("line_registrations", 0),
        "B17": "CV(F)",
        "C17": current_row.get("cv_f", 0),
        "B18": "問診回答",
        "C18": current_row.get("monshin_answers", 0),
        "B19": "購入CV",
        "C19": current_row.get("purchase_cv", 0),
    }
    gateway.write_cells(handle, updates)

    # チャートA（主目的）: 全期間×4段CVR（対クリック比）の推移。
    # Historyタブの行が増えるほど自動的に反映される（open-endedな範囲を指定して
    # いるため、週次実行のたびにチャートを再作成/再指定する必要はない）。
    rate_columns_1_based = [
        HISTORY_COLUMNS.index("line_registration_rate") + 1,
        HISTORY_COLUMNS.index("cv_f_rate") + 1,
        HISTORY_COLUMNS.index("monshin_answer_rate") + 1,
        HISTORY_COLUMNS.index("purchase_rate") + 1,
    ]
    week_start_col = _column_letter(HISTORY_COLUMNS.index("week_start") + 1)
    gateway.ensure_chart(
        handle,
        ChartSpec(
            description="STD_全期間CVR推移",
            chart_type="LINE",
            domain=SheetRange(
                sheet_id=history_handle.id,
                a1_range=f"{week_start_col}2:{week_start_col}{_TREND_ROW_CAPACITY}",
            ),
            series=[
                SheetRange(
                    sheet_id=history_handle.id,
                    a1_range=f"{_column_letter(col)}2:{_column_letter(col)}{_TREND_ROW_CAPACITY}",
                )
                for col in rate_columns_1_based
            ],
            anchor_sheet_id=handle.id,
            anchor_cell_a1="E14",
        ),
    )

    # チャートB: 今週の5段ファネル（件数）。B15:C19の即席テーブルを参照。
    gateway.ensure_chart(
        handle,
        ChartSpec(
            description="STD_今週ファネル",
            chart_type="COLUMN",
            domain=SheetRange(sheet_id=handle.id, a1_range="B15:B19"),
            series=[SheetRange(sheet_id=handle.id, a1_range="C15:C19")],
            anchor_sheet_id=handle.id,
            anchor_cell_a1="E32",
        ),
    )


def sync_all(
    gateway: SheetsGateway,
    config: dict[str, Any],
    *,
    current_row: dict[str, Any],
    history: pd.DataFrame,
    bottleneck: pd.DataFrame,
    management_detail: pd.DataFrame,
) -> None:
    """History/Bottleneck/Dashboardの3タブをまとめて最新状態に同期する。"""
    history_handle = sync_history(gateway, config, history)
    sync_bottleneck(gateway, config, bottleneck)
    sync_dashboard(
        gateway,
        config,
        current_row=current_row,
        bottleneck=bottleneck,
        management_detail=management_detail,
        history_handle=history_handle,
    )
