"""テスト用インメモリ SheetsGateway 実装。gspread・ネットワークに一切依存しない。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from scripts.weekly_dashboard.sheets_gateway import ChartSpec, FormatSpec
from scripts.weekly_dashboard.sheets_gateway import _stringify as _clean_cell


@dataclass
class FakeWorksheet:
    """gspread.Worksheetの最小互換フェイク。`.id` は実物同様sheetId相当の整数。"""

    title: str
    id: int
    rows: list[list[Any]] = field(default_factory=list)


class FakeSheetsGateway:
    """`SheetsGateway` Protocolのインメモリ実装。テストから内部状態を直接検査できる。"""

    def __init__(self) -> None:
        self._worksheets: dict[str, FakeWorksheet] = {}
        self._next_sheet_id = 1
        self.created_charts: list[ChartSpec] = []
        self.created_formats: list[FormatSpec] = []

    def get_or_create_worksheet(self, title: str, *, rows: int, cols: int) -> FakeWorksheet:
        if title not in self._worksheets:
            self._worksheets[title] = FakeWorksheet(title=title, id=self._next_sheet_id)
            self._next_sheet_id += 1
        return self._worksheets[title]

    def replace_all(self, handle: FakeWorksheet, rows: list[list[Any]]) -> None:
        handle.rows = [[_clean_cell(cell) for cell in row] for row in rows]

    def write_cells(self, handle: FakeWorksheet, updates: dict[str, Any]) -> None:
        for a1, value in updates.items():
            row_index, col_index = _parse_a1(a1)
            _ensure_capacity(handle.rows, row_index, col_index)
            handle.rows[row_index][col_index] = _clean_cell(value)

    def ensure_chart(self, handle: FakeWorksheet, spec: ChartSpec) -> None:
        if any(chart.description == spec.description for chart in self.created_charts):
            return
        self.created_charts.append(spec)

    def ensure_conditional_format(self, handle: FakeWorksheet, spec: FormatSpec) -> None:
        if any(
            fmt.range_.sheet_id == spec.range_.sheet_id
            and fmt.range_.a1_range == spec.range_.a1_range
            for fmt in self.created_formats
        ):
            return
        self.created_formats.append(spec)


def _parse_a1(a1_cell: str) -> tuple[int, int]:
    """'B5' のようなA1セル参照を0始まりの (row_index, col_index) に変換する。"""
    match = re.fullmatch(r"([A-Z]+)(\d+)", a1_cell)
    if not match:
        raise ValueError(f"サポート外のA1セル参照です: {a1_cell}")
    col_letters, row_number = match.groups()
    col_index = 0
    for char in col_letters:
        col_index = col_index * 26 + (ord(char) - ord("A") + 1)
    return int(row_number) - 1, col_index - 1


def _ensure_capacity(rows: list[list[Any]], row_index: int, col_index: int) -> None:
    while len(rows) <= row_index:
        rows.append([])
    row = rows[row_index]
    while len(row) <= col_index:
        row.append("")
