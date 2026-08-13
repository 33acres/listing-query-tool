from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

from scripts.daily_kpi.bottleneck import compute_daily_bottleneck
from scripts.daily_kpi.main import main, update_history
from scripts.daily_kpi.tests.fixtures import make_config, make_kpi
from scripts.daily_kpi.tests.test_loaders import _LSTEP_CSV, _MANAGEMENT_CSV


class UpdateHistoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.path = Path(self._temp.name) / "history.csv"
        self.config = make_config()
        self.kpi = make_kpi(days=5)
        self.bottleneck = compute_daily_bottleneck(self.kpi, self.config)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_creates_the_file_with_judgement_columns(self) -> None:
        history = update_history(self.path, "ecp", self.kpi, self.bottleneck)

        self.assertTrue(self.path.exists())
        self.assertEqual(len(history), 5)
        self.assertEqual(history.iloc[0]["project"], "ecp")
        for column in ("alert_level", "bottleneck_confidence", "bottleneck_severity_pt"):
            self.assertIn(column, history.columns)

    def test_rerunning_the_same_dates_replaces_instead_of_duplicating(self) -> None:
        update_history(self.path, "ecp", self.kpi, self.bottleneck)
        updated = self.kpi.copy()
        updated["purchase_cv"] = 99.0
        history = update_history(
            self.path, "ecp", updated, compute_daily_bottleneck(updated, self.config)
        )

        self.assertEqual(len(history), 5)
        self.assertTrue((history["purchase_cv"] == 99.0).all())

    def test_other_projects_are_preserved(self) -> None:
        update_history(self.path, "std", self.kpi, self.bottleneck)
        history = update_history(self.path, "ecp", self.kpi, self.bottleneck)

        self.assertEqual(len(history), 10)
        self.assertEqual(set(history["project"]), {"ecp", "std"})

    def test_new_dates_are_appended_to_existing_ones(self) -> None:
        update_history(self.path, "ecp", self.kpi, self.bottleneck)
        later = make_kpi(days=5, start="2026-05-06")
        history = update_history(
            self.path, "ecp", later, compute_daily_bottleneck(later, self.config)
        )

        self.assertEqual(len(history), 10)
        self.assertEqual(history["date"].iloc[-1], "2026-05-10")


class MainEndToEndTest(unittest.TestCase):
    """CLIを通した一連の流れ（読み込み→突合→判定→出力）を検証する。"""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        root = Path(self._temp.name)
        self.input_dir = root / "raw"
        self.output_dir = root / "out"
        self.input_dir.mkdir()
        (self.input_dir / "management-20260728.csv").write_text(
            _MANAGEMENT_CSV, encoding="utf-8-sig"
        )
        (self.input_dir / "lstep2026.csv").write_text(_LSTEP_CSV, encoding="utf-8")
        self.history = root / "history.csv"
        self.config = make_config()
        self.config["daily_kpi"]["management"]["header_row"] = 4

    def tearDown(self) -> None:
        self._temp.cleanup()

    def _run(self) -> int:
        argv = [
            "main",
            "--project",
            "ecp",
            "--run-date",
            "2026-07-10",
            "--input-dir",
            str(self.input_dir),
            "--output-dir",
            str(self.output_dir),
            "--history-file",
            str(self.history),
        ]
        with mock.patch("sys.argv", argv), mock.patch(
            "scripts.daily_kpi.main.load_config", return_value=self.config
        ):
            return main()

    def test_writes_all_four_artifacts(self) -> None:
        self.assertEqual(self._run(), 0)

        names = self.config["daily_kpi"]["output_files"]
        for key in ("kpi", "bottleneck", "report", "audit"):
            self.assertTrue((self.output_dir / names[key]).is_file(), key)
        self.assertTrue(self.history.is_file())

        kpi = pd.read_csv(self.output_dir / names["kpi"])
        self.assertEqual(len(kpi), 2)
        meta = json.loads((self.output_dir / names["audit"]).read_text())
        self.assertEqual(meta["days"], 2)
        self.assertEqual(meta["date_range"], ["2026-07-01", "2026-07-02"])
        self.assertIn("management-20260728.csv", meta["sources"])
        self.assertIn("stage_validity", meta)

    def test_does_not_touch_google_sheets_without_the_flag(self) -> None:
        with mock.patch("scripts.daily_kpi.sheets.sync_daily") as sync:
            self._run()
        sync.assert_not_called()

    def test_cohort_maturity_is_measured_from_the_lstep_export_date(self) -> None:
        """後日パイプラインを回してもコホートは成熟しない。

        タグの状態はエクスポート時点で凍結されている。run_dateを基準にすると
        48時間タッチが届いていないコホートを成熟済みと誤判定する。
        """
        self._run()  # --run-date 2026-07-10、Lステップの最終日は 2026-07-02
        kpi = pd.read_csv(
            self.output_dir / self.config["daily_kpi"]["output_files"]["kpi"],
            parse_dates=["date"],
        )
        july1 = kpi[kpi["date"] == pd.Timestamp("2026-07-01")].iloc[0]

        # 実行日(7/10)基準なら経過9日で成熟だが、エクスポート日(7/02)基準では1日
        self.assertEqual(july1["cohort_days_elapsed"], 1)
        self.assertFalse(bool(july1["cohort_mature"]))

    def test_missing_input_directory_fails_loudly(self) -> None:
        self.input_dir.rename(self.input_dir.parent / "moved")
        with self.assertRaises(FileNotFoundError):
            self._run()


if __name__ == "__main__":
    unittest.main()
