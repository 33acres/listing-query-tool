"""日次KPI表・ボトルネック判定をGoogle Sheetsの専用タブへ同期する。

週次側（scripts/weekly_dashboard/sheets_sync.py）と同じ「毎回全件洗い替え」方式。
再実行で同一日が重複しないことが実装レベルで保証される。
gspreadへの依存は sheets_gateway.SheetsGateway Protocol 越しに閉じてあるので、
このモジュールはネットワークなしでテストできる。
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from scripts.daily_kpi.bottleneck import OUTPUT_COLUMNS as BOTTLENECK_COLUMNS
from scripts.weekly_dashboard.sheets_gateway import (
    FormatSpec,
    SheetRange,
    SheetsGateway,
)

_ROW_CAPACITY = 1200  # 約3年分の日次行
_DELTA_SUFFIX = "_delta_pt"


def _column_letter(index_1_based: int) -> str:
    letters = ""
    value = index_1_based
    while value > 0:
        value, remainder = divmod(value - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def _rows(frame: pd.DataFrame, columns: list[str]) -> list[list[Any]]:
    if frame.empty:
        return [columns]
    normalized = frame.copy()
    if "date" in normalized.columns:
        normalized["date"] = pd.to_datetime(normalized["date"]).dt.strftime("%Y-%m-%d")
    records = normalized[columns].to_dict("records")
    return [columns] + [[record.get(column) for column in columns] for record in records]


def sync_daily(
    gateway: SheetsGateway,
    config: dict[str, Any],
    *,
    kpi: pd.DataFrame,
    bottleneck: pd.DataFrame,
) -> None:
    worksheets = config["google_sheets"]["worksheets"]

    kpi_columns = list(kpi.columns)
    kpi_handle = gateway.get_or_create_worksheet(
        worksheets["daily_kpi"], rows=_ROW_CAPACITY, cols=len(kpi_columns)
    )
    gateway.replace_all(kpi_handle, _rows(kpi, kpi_columns))

    bottleneck_handle = gateway.get_or_create_worksheet(
        worksheets["daily_bottleneck"], rows=_ROW_CAPACITY, cols=len(BOTTLENECK_COLUMNS)
    )
    gateway.replace_all(bottleneck_handle, _rows(bottleneck, BOTTLENECK_COLUMNS))

    # 悪化幅の列にカラースケールを当てて、表を開いた瞬間に詰まりが見えるようにする
    for position, column in enumerate(BOTTLENECK_COLUMNS, start=1):
        if not column.endswith(_DELTA_SUFFIX):
            continue
        letter = _column_letter(position)
        gateway.ensure_conditional_format(
            bottleneck_handle,
            FormatSpec(
                description=f"daily_bottleneck_{column}_color_scale",
                range_=SheetRange(
                    sheet_id=bottleneck_handle.id,
                    a1_range=f"{letter}2:{letter}{_ROW_CAPACITY}",
                ),
            ),
        )
