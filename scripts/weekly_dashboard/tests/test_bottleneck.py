from __future__ import annotations

import unittest

import pandas as pd

from scripts.weekly_dashboard.bottleneck import OUTPUT_COLUMNS, compute_bottleneck_frame


def _flat_week(week_start: str, week_end: str, *, purchase_cv: int = 40) -> dict:
    return {
        "project": "std",
        "week_start": week_start,
        "week_end": week_end,
        "ad_clicks": 1000,
        "line_registrations": 200,
        "cv_f": 100,
        "monshin_answers": 80,
        "purchase_cv": purchase_cv,
    }


class ComputeBottleneckFrameTests(unittest.TestCase):
    def test_empty_history_returns_empty_frame_with_expected_columns(self) -> None:
        result = compute_bottleneck_frame(pd.DataFrame(columns=["project", "week_start"]))
        self.assertTrue(result.empty)
        self.assertEqual(OUTPUT_COLUMNS, list(result.columns))

    def test_first_week_has_no_bottleneck_verdict(self) -> None:
        history = pd.DataFrame([_flat_week("2026-06-01", "2026-06-07")])
        result = compute_bottleneck_frame(history)
        self.assertEqual(1, len(result))
        self.assertIsNone(result.loc[0, "bottleneck_stage"])
        self.assertIsNone(result.loc[0, "bottleneck_confidence"])

    def test_stable_weeks_are_single_week_noise(self) -> None:
        history = pd.DataFrame(
            [
                _flat_week("2026-06-01", "2026-06-07"),
                _flat_week("2026-06-08", "2026-06-14"),
                _flat_week("2026-06-15", "2026-06-21"),
            ]
        )
        result = compute_bottleneck_frame(history, trailing_weeks=4, threshold_pt=2.0)
        for index in (1, 2):
            self.assertEqual("single_week_noise", result.loc[index, "bottleneck_confidence"])
            self.assertEqual(0.0, result.loc[index, "bottleneck_severity_pt"])

    def test_sustained_purchase_drop_is_confirmed_bottleneck(self) -> None:
        rows = [
            _flat_week("2026-06-01", "2026-06-07"),
            _flat_week("2026-06-08", "2026-06-14"),
            _flat_week("2026-06-15", "2026-06-21"),
            _flat_week("2026-06-22", "2026-06-28"),
            _flat_week("2026-06-29", "2026-07-05", purchase_cv=10),  # 問診→購入が急落
        ]
        result = compute_bottleneck_frame(pd.DataFrame(rows), trailing_weeks=4, threshold_pt=2.0)
        last = result.iloc[-1]
        self.assertEqual("monshin_to_purchase", last["bottleneck_stage"])
        self.assertEqual("confirmed", last["bottleneck_confidence"])
        self.assertLess(last["bottleneck_severity_pt"], -2.0)

    def test_single_week_dip_that_recovers_is_not_confirmed_on_recovery_week(self) -> None:
        rows = [
            _flat_week("2026-06-01", "2026-06-07"),
            _flat_week("2026-06-08", "2026-06-14"),
            _flat_week("2026-06-15", "2026-06-21"),
            _flat_week("2026-06-22", "2026-06-28"),
            _flat_week("2026-06-29", "2026-07-05", purchase_cv=10),  # dip
            _flat_week("2026-07-06", "2026-07-12", purchase_cv=40),  # recovers
        ]
        result = compute_bottleneck_frame(pd.DataFrame(rows), trailing_weeks=4, threshold_pt=2.0)
        recovered = result.iloc[-1]
        # 回復週はWoWが改善方向（プラス）になるため、悪化ステージとしては検出されない。
        self.assertNotEqual("confirmed", recovered["bottleneck_confidence"])

    def test_zero_denominator_week_does_not_crash_rolling_average(self) -> None:
        # monshin_answers=0 の週がある場合、monshin_to_purchase_rate は0除算でNaNになる。
        # pd.NA(pandasのnullable NA)だと後続の.rolling().mean()が例外を投げていた実バグの回帰テスト。
        rows = [
            _flat_week("2026-06-01", "2026-06-07"),
            {**_flat_week("2026-06-08", "2026-06-14"), "monshin_answers": 0, "purchase_cv": 0},
            _flat_week("2026-06-15", "2026-06-21"),
        ]
        result = compute_bottleneck_frame(pd.DataFrame(rows), trailing_weeks=4, threshold_pt=2.0)
        self.assertEqual(3, len(result))
        self.assertTrue(pd.isna(result.loc[1, "monshin_to_purchase_rate"]))

    def test_multiple_projects_are_computed_independently(self) -> None:
        base = [
            _flat_week("2026-06-01", "2026-06-07"),
            _flat_week("2026-06-08", "2026-06-14", purchase_cv=10),
        ]
        std_rows = [dict(r, project="std") for r in base]
        ecp_rows = [dict(r, project="ecp") for r in base]
        history = pd.DataFrame(std_rows + ecp_rows)
        result = compute_bottleneck_frame(history, trailing_weeks=4, threshold_pt=2.0)
        self.assertEqual(4, len(result))
        for project in ("std", "ecp"):
            subset = result[result["project"] == project].sort_values("week_start")
            self.assertEqual(2, len(subset))
            self.assertEqual("monshin_to_purchase", subset.iloc[-1]["bottleneck_stage"])
            self.assertEqual("confirmed", subset.iloc[-1]["bottleneck_confidence"])


if __name__ == "__main__":
    unittest.main()
