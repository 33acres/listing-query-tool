from __future__ import annotations

import unittest

import pandas as pd

from scripts.weekly_dashboard.bottleneck import compute_bottleneck_frame
from scripts.weekly_dashboard.core import HISTORY_COLUMNS
from scripts.weekly_dashboard.sheets_sync import sync_all
from scripts.weekly_dashboard.tests.fakes import FakeSheetsGateway

CONFIG = {
    "project": "std",
    "display_name": "あしたのクリニック オンライン性病外来",
    "google_sheets": {
        "worksheets": {"dashboard": "Dashboard", "history": "History", "bottleneck": "Bottleneck"},
    },
}

_MANAGEMENT_COLUMNS = [
    "date", "gross_profit", "sales", "ad_cost", "impressions", "clicks",
    "cv_f", "monshin_answers", "treat_drug_cv", "test_light_cv",
    "test_basic_cv", "test_standard_cv", "test_full_cv", "purchase_cv",
]


def _history_row(week_start: str, week_end: str, *, purchase_cv: int = 40) -> dict:
    ad_clicks = 1000
    line_registrations = 200
    cv_f = 100
    monshin_answers = 80
    return {
        "project": "std",
        "week_start": week_start,
        "week_end": week_end,
        "ad_clicks": ad_clicks,
        "line_registrations": line_registrations,
        "cv_f": cv_f,
        "monshin_answers": monshin_answers,
        "purchase_cv": purchase_cv,
        "line_registration_rate": line_registrations / ad_clicks,
        "cv_f_rate": cv_f / ad_clicks,
        "monshin_answer_rate": monshin_answers / ad_clicks,
        "purchase_rate": purchase_cv / ad_clicks,
    }


class SyncAllTests(unittest.TestCase):
    def setUp(self) -> None:
        self.history = pd.DataFrame(
            [
                _history_row("2026-06-01", "2026-06-07"),
                _history_row("2026-06-08", "2026-06-14"),
                _history_row("2026-06-15", "2026-06-21"),
                _history_row("2026-06-22", "2026-06-28"),
                _history_row("2026-06-29", "2026-07-05", purchase_cv=10),
            ]
        )
        self.bottleneck = compute_bottleneck_frame(self.history, trailing_weeks=4, threshold_pt=2.0)
        self.current_row = self.history.iloc[-1].to_dict()
        self.management_detail = pd.DataFrame(columns=_MANAGEMENT_COLUMNS)

    def _sync(self, gateway: FakeSheetsGateway) -> None:
        sync_all(
            gateway,
            CONFIG,
            current_row=self.current_row,
            history=self.history,
            bottleneck=self.bottleneck,
            management_detail=self.management_detail,
        )

    def test_history_tab_mirrors_history_columns_in_order(self) -> None:
        gateway = FakeSheetsGateway()
        self._sync(gateway)
        history_sheet = gateway.get_or_create_worksheet("History", rows=10, cols=10)
        self.assertEqual(HISTORY_COLUMNS, history_sheet.rows[0])
        self.assertEqual(1 + len(self.history), len(history_sheet.rows))

    def test_rerun_is_idempotent_no_duplicate_rows(self) -> None:
        gateway = FakeSheetsGateway()
        self._sync(gateway)
        history_sheet = gateway.get_or_create_worksheet("History", rows=10, cols=10)
        bottleneck_sheet = gateway.get_or_create_worksheet("Bottleneck", rows=10, cols=10)
        first_history_rows = [list(r) for r in history_sheet.rows]
        first_bottleneck_rows = [list(r) for r in bottleneck_sheet.rows]

        self._sync(gateway)  # 同じデータで再実行

        self.assertEqual(first_history_rows, history_sheet.rows)
        self.assertEqual(first_bottleneck_rows, bottleneck_sheet.rows)

    def test_dashboard_callout_reflects_latest_bottleneck_row(self) -> None:
        gateway = FakeSheetsGateway()
        self._sync(gateway)
        dashboard_sheet = gateway.get_or_create_worksheet("Dashboard", rows=60, cols=12)
        latest_bottleneck = self.bottleneck.iloc[-1]

        # B9/C9 = 段階ラベル, B11/C11 = 確度（0始まりindexなので行9→8, 行11→10）
        self.assertEqual("段階", dashboard_sheet.rows[8][1])
        self.assertEqual(latest_bottleneck["bottleneck_stage_label"], dashboard_sheet.rows[8][2])
        self.assertEqual("確度", dashboard_sheet.rows[10][1])
        self.assertEqual(latest_bottleneck["bottleneck_confidence"], dashboard_sheet.rows[10][2])
        self.assertEqual("confirmed", latest_bottleneck["bottleneck_confidence"])

    def test_charts_created_exactly_once_and_not_duplicated_on_rerun(self) -> None:
        gateway = FakeSheetsGateway()
        self._sync(gateway)
        self.assertEqual(2, len(gateway.created_charts))  # チャートA(推移) + チャートB(今週ファネル)
        descriptions_after_first = sorted(chart.description for chart in gateway.created_charts)

        self._sync(gateway)  # 再実行してもチャートは増えない

        self.assertEqual(2, len(gateway.created_charts))
        self.assertEqual(
            descriptions_after_first, sorted(chart.description for chart in gateway.created_charts)
        )

    def test_bottleneck_delta_columns_get_conditional_format(self) -> None:
        gateway = FakeSheetsGateway()
        self._sync(gateway)
        formatted_ranges = {fmt.description for fmt in gateway.created_formats}
        self.assertIn("bottleneck_ad_clicks_delta_wow_pct_color_scale", formatted_ranges)
        self.assertIn("bottleneck_monshin_to_purchase_delta_wow_pt_color_scale", formatted_ranges)


if __name__ == "__main__":
    unittest.main()
