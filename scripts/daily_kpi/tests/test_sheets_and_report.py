from __future__ import annotations

import unittest

from scripts.daily_kpi.bottleneck import (
    OUTPUT_COLUMNS,
    compute_daily_bottleneck,
    stage_validity,
)
from scripts.daily_kpi.report import build_report
from scripts.daily_kpi.sheets import sync_daily
from scripts.daily_kpi.tests.fixtures import make_config, make_kpi
from scripts.weekly_dashboard.tests.fakes import FakeSheetsGateway


class SyncDailyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = make_config()
        self.kpi = make_kpi(days=10)
        self.bottleneck = compute_daily_bottleneck(self.kpi, self.config)
        self.gateway = FakeSheetsGateway()

    def test_writes_both_tabs_with_headers(self) -> None:
        sync_daily(self.gateway, self.config, kpi=self.kpi, bottleneck=self.bottleneck)

        kpi_sheet = self.gateway.get_or_create_worksheet("DailyKPI", rows=1, cols=1)
        bottleneck_sheet = self.gateway.get_or_create_worksheet(
            "DailyBottleneck", rows=1, cols=1
        )
        self.assertEqual(kpi_sheet.rows[0], list(self.kpi.columns))
        self.assertEqual(len(kpi_sheet.rows), len(self.kpi) + 1)
        self.assertEqual(bottleneck_sheet.rows[0], OUTPUT_COLUMNS)
        self.assertEqual(len(bottleneck_sheet.rows), len(self.bottleneck) + 1)

    def test_dates_are_written_as_iso_strings(self) -> None:
        sync_daily(self.gateway, self.config, kpi=self.kpi, bottleneck=self.bottleneck)
        kpi_sheet = self.gateway.get_or_create_worksheet("DailyKPI", rows=1, cols=1)
        self.assertEqual(kpi_sheet.rows[1][0], "2026-05-01")

    def test_rerun_replaces_instead_of_appending(self) -> None:
        sync_daily(self.gateway, self.config, kpi=self.kpi, bottleneck=self.bottleneck)
        sync_daily(self.gateway, self.config, kpi=self.kpi, bottleneck=self.bottleneck)
        kpi_sheet = self.gateway.get_or_create_worksheet("DailyKPI", rows=1, cols=1)
        self.assertEqual(len(kpi_sheet.rows), len(self.kpi) + 1)

    def test_delta_columns_get_a_color_scale(self) -> None:
        sync_daily(self.gateway, self.config, kpi=self.kpi, bottleneck=self.bottleneck)
        descriptions = {spec.description for spec in self.gateway.created_formats}
        self.assertIn("daily_bottleneck_click_to_cvf_delta_pt_color_scale", descriptions)


class BuildReportTest(unittest.TestCase):
    def test_report_contains_the_key_sections(self) -> None:
        config = make_config()
        kpi = make_kpi(days=40)
        bottleneck = compute_daily_bottleneck(kpi, config)
        report = build_report(
            kpi,
            bottleneck,
            config,
            source_files=["management.csv", "lstep2026.csv"],
            validity=stage_validity(kpi, config),
        )

        for heading in (
            "## 判定（直近日）",
            "## 区間別（直近7日 vs 直前28日）",
            "## 日次KPI表",
            "## 日次Cost帯別",
            "## 突合（管理表 × Lステップ）",
        ):
            self.assertIn(heading, report)
        self.assertIn("テスト外来", report)
        self.assertIn("management.csv", report)

    def test_flat_data_is_not_described_as_degraded(self) -> None:
        config = make_config()
        kpi = make_kpi(days=40)
        bottleneck = compute_daily_bottleneck(kpi, config)
        report = build_report(kpi, bottleneck, config, source_files=[])

        self.assertIn("最も伸び幅が小さい区間", report)
        self.assertNotIn("ボトルネック区間: **", report)

    def test_degraded_data_is_described_as_a_bottleneck(self) -> None:
        config = make_config()
        kpi = make_kpi(days=40)
        kpi.loc[kpi.index[-7:], "purchase_cv"] = 10.0
        bottleneck = compute_daily_bottleneck(kpi, config)
        report = build_report(kpi, bottleneck, config, source_files=[])

        self.assertIn("ボトルネック区間", report)
        self.assertIn("🔴 悪化確定", report)


if __name__ == "__main__":
    unittest.main()
