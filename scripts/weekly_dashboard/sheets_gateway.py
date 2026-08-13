"""Google Sheets書き込みの抽象化レイヤー。

`gspread` を直接importするのは `GspreadSheetsGateway` のみ。`sheets_sync.py` の
ビジネスロジックは `SheetsGateway` Protocol越しにのみ呼び出すため、ネットワーク・
実クレデンシャルなしでテストできる（テスト用実装は tests/fakes.py の
`FakeSheetsGateway`）。

チャート・条件付き書式はGoogle Sheets APIの生のbatch_updateリクエストを組み立てる。
実APIに対する最終確認はロールアウト時のスモークテスト（実施計画§7）で行う。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence

WorksheetHandle = Any  # 実装依存のopaqueな参照（GspreadSheetsGatewayではgspread.Worksheet）


@dataclass(frozen=True)
class SheetRange:
    """特定シート上の矩形範囲。sheet_id はそのシートのgid（Worksheet.id）。

    a1_range はシート名プレフィックスなしのA1範囲（例: "B2:B2000"）。プレフィックス
    文字列からのシート解決はあいまいさを生むため、呼び出し側が sheet_id を明示する。
    """

    sheet_id: int
    a1_range: str


@dataclass(frozen=True)
class ChartSpec:
    """ネイティブチャート定義。description をチャートタイトルとしても使い、
    ensure_chart の重複作成防止（冪等性）のキーにする。"""

    description: str
    chart_type: str  # "LINE" | "COLUMN"
    domain: SheetRange
    series: Sequence[SheetRange]
    anchor_sheet_id: int
    anchor_cell_a1: str  # チャートを貼り付けるシート上のアンカーセル（プレフィックスなし）


@dataclass(frozen=True)
class FormatSpec:
    """条件付き書式定義。description は識別用途のみ（Sheets APIのルール自体には
    description欄がないため、range一致で重複作成を防止する）。"""

    description: str
    range_: SheetRange
    kind: str = "color_scale"


class SheetsGateway(Protocol):
    def get_or_create_worksheet(self, title: str, *, rows: int, cols: int) -> WorksheetHandle: ...

    def replace_all(self, handle: WorksheetHandle, rows: list[list[Any]]) -> None:
        """ヘッダ行含む全データで該当シートを完全上書きする（追記ではない）。"""
        ...

    def write_cells(self, handle: WorksheetHandle, updates: dict[str, Any]) -> None:
        """A1記法セル位置 -> 値、の辞書でピンポイント更新する（Dashboardタブ用）。"""
        ...

    def ensure_chart(self, handle: WorksheetHandle, spec: ChartSpec) -> None:
        """spec.description のチャートが存在しなければ作成する（冪等）。"""
        ...

    def ensure_conditional_format(self, handle: WorksheetHandle, spec: FormatSpec) -> None:
        """spec.range_ と同じ範囲のルールが存在しなければ作成する（冪等）。"""
        ...


def _stringify(value: Any) -> Any:
    """SheetsのJSONペイロードに書けない値（None, NaN）を空文字に変換する。

    NaNはJSON仕様上の妥当な値ではなく、Sheets APIへ生のNaNを送ると失敗しうるため、
    Noneと同様に空文字へ変換する（bottleneck.pyの初週など前週比較不能なセルで発生する）。
    """
    if value is None:
        return ""
    if isinstance(value, float) and value != value:  # NaN は自分自身と等しくない
        return ""
    return value


def _stringify_rows(rows: list[list[Any]]) -> list[list[Any]]:
    return [[_stringify(cell) for cell in row] for row in rows]


class GspreadSheetsGateway:
    """gspread（サービスアカウント認証）を用いた実装。"""

    def __init__(self, *, credentials_path: Path, spreadsheet_id: str) -> None:
        import gspread  # 遅延import: gspreadに依存するのはこのファイルのみ

        if not credentials_path.is_file():
            raise FileNotFoundError(
                f"Google Sheetsサービスアカウント鍵が見つかりません: {credentials_path}"
            )
        self._gspread = gspread
        client = gspread.service_account(filename=str(credentials_path))
        self._spreadsheet = client.open_by_key(spreadsheet_id)

    def get_or_create_worksheet(self, title: str, *, rows: int, cols: int) -> WorksheetHandle:
        try:
            return self._spreadsheet.worksheet(title)
        except self._gspread.exceptions.WorksheetNotFound:
            return self._spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)

    def replace_all(self, handle: WorksheetHandle, rows: list[list[Any]]) -> None:
        handle.clear()
        if not rows:
            return
        needed_rows = len(rows)
        needed_cols = max((len(row) for row in rows), default=0)
        if handle.row_count < needed_rows or handle.col_count < needed_cols:
            handle.resize(
                rows=max(handle.row_count, needed_rows),
                cols=max(handle.col_count, needed_cols),
            )
        handle.update(range_name="A1", values=_stringify_rows(rows))

    def write_cells(self, handle: WorksheetHandle, updates: dict[str, Any]) -> None:
        if not updates:
            return
        batch = [
            {"range": a1, "values": [[_stringify(value)]]} for a1, value in updates.items()
        ]
        handle.batch_update(batch)

    def ensure_chart(self, handle: WorksheetHandle, spec: ChartSpec) -> None:
        if self._chart_exists(spec.description):
            return
        request = {
            "addChart": {
                "chart": {
                    "spec": {
                        "title": spec.description,
                        "basicChart": {
                            "chartType": spec.chart_type,
                            "legendPosition": "BOTTOM_LEGEND",
                            # domain/seriesの範囲は呼び出し側(sheets_sync.py)で常に
                            # ヘッダー行を含めない形（データ行から開始）で渡されるため、
                            # headerCountは0固定。1にすると先頭の実データ行がヘッダー
                            # 扱いされ、データ点が1行しかない場合にseriesごと消える
                            # (Google Sheets API上で実際に発生した不具合)。
                            "headerCount": 0,
                            "domains": [
                                {
                                    "domain": {
                                        "sourceRange": {
                                            "sources": [self._grid_range(spec.domain)]
                                        }
                                    }
                                }
                            ],
                            "series": [
                                {
                                    "series": {
                                        "sourceRange": {"sources": [self._grid_range(series_range)]}
                                    }
                                }
                                for series_range in spec.series
                            ],
                        },
                    },
                    "position": {
                        "overlayPosition": {
                            "anchorCell": self._cell_coordinate(
                                spec.anchor_sheet_id, spec.anchor_cell_a1
                            )
                        }
                    },
                }
            }
        }
        self._spreadsheet.batch_update({"requests": [request]})

    def ensure_conditional_format(self, handle: WorksheetHandle, spec: FormatSpec) -> None:
        target = self._grid_range(spec.range_)
        if self._conditional_format_exists(target):
            return
        request = {
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [target],
                    "gradientRule": {
                        "minpoint": {"color": {"red": 0.96, "green": 0.42, "blue": 0.38}, "type": "MIN"},
                        "midpoint": {
                            "color": {"red": 1.0, "green": 1.0, "blue": 1.0},
                            "type": "NUMBER",
                            "value": "0",
                        },
                        "maxpoint": {"color": {"red": 0.42, "green": 0.72, "blue": 0.47}, "type": "MAX"},
                    },
                },
                "index": 0,
            }
        }
        self._spreadsheet.batch_update({"requests": [request]})

    # --- internal helpers ---------------------------------------------

    def _grid_range(self, range_: SheetRange) -> dict[str, int]:
        from gspread.utils import a1_range_to_grid_range

        grid_range = a1_range_to_grid_range(range_.a1_range)
        grid_range["sheetId"] = range_.sheet_id
        return grid_range

    def _cell_coordinate(self, sheet_id: int, a1_cell: str) -> dict[str, int]:
        from gspread.utils import a1_range_to_grid_range

        grid_range = a1_range_to_grid_range(a1_cell)
        return {
            "sheetId": sheet_id,
            "rowIndex": grid_range["startRowIndex"],
            "columnIndex": grid_range["startColumnIndex"],
        }

    def _chart_exists(self, description: str) -> bool:
        metadata = self._spreadsheet.fetch_sheet_metadata()
        for sheet in metadata.get("sheets", []):
            for chart in sheet.get("charts", []):
                if chart.get("spec", {}).get("title") == description:
                    return True
        return False

    def _conditional_format_exists(self, target: dict[str, int]) -> bool:
        metadata = self._spreadsheet.fetch_sheet_metadata()
        for sheet in metadata.get("sheets", []):
            if sheet.get("properties", {}).get("sheetId") != target["sheetId"]:
                continue
            for rule in sheet.get("conditionalFormats", []):
                for existing_range in rule.get("ranges", []):
                    if (
                        existing_range.get("startRowIndex") == target.get("startRowIndex")
                        and existing_range.get("startColumnIndex") == target.get("startColumnIndex")
                    ):
                        return True
        return False
