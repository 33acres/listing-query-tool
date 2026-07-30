from __future__ import annotations

import unittest

import pandas as pd

from scripts.daily_kpi.bottleneck import (
    OUTPUT_COLUMNS,
    compute_daily_bottleneck,
    cost_band_summary,
    stage_validity,
)
from scripts.daily_kpi.kpi import detect_tag_activation
from scripts.daily_kpi.tests.fixtures import make_config, make_kpi


class ComputeDailyBottleneckTest(unittest.TestCase):
    def test_flat_history_reports_no_degradation(self) -> None:
        config = make_config()
        result = compute_daily_bottleneck(make_kpi(), config)

        self.assertEqual(list(result.columns), OUTPUT_COLUMNS)
        latest = result.iloc[-1]
        self.assertEqual(latest["bottleneck_confidence"], "no_degradation")
        self.assertAlmostEqual(latest["click_to_cvf_delta_pt"], 0.0, places=6)
        self.assertEqual(latest["alert_level"], "ok")

    def test_detects_the_stage_that_dropped(self) -> None:
        config = make_config()
        kpi = make_kpi()
        # 直近7日だけ決済クリック→購入を落とす（36/42=85.7% → 21/42=50%）
        kpi.loc[kpi.index[-7:], "purchase_cv"] = 21.0
        result = compute_daily_bottleneck(kpi, config)

        latest = result.iloc[-1]
        self.assertEqual(latest["bottleneck_stage"], "payment_click_to_purchase")
        self.assertEqual(latest["bottleneck_confidence"], "confirmed")
        self.assertLess(latest["bottleneck_severity_pt"], -30)
        self.assertEqual(latest["alert_level"], "alert")
        self.assertIn("悪化", latest["alerts"])

    def test_small_drop_stays_within_noise(self) -> None:
        config = make_config()
        kpi = make_kpi()
        # 65/500=13.0% → 64/500=12.8%（-0.2pt）は閾値2.0pt未満
        kpi.loc[kpi.index[-7:], "cv_f"] = 64.0
        kpi.loc[kpi.index[-7:], "registrations"] = 64.0
        result = compute_daily_bottleneck(kpi, config)

        latest = result.iloc[-1]
        self.assertEqual(latest["bottleneck_stage"], "click_to_cvf")
        self.assertEqual(latest["bottleneck_confidence"], "within_noise")

    def test_rate_uses_ratio_of_sums_not_mean_of_ratios(self) -> None:
        """分母が極端に小さい日に判定が引きずられないこと。"""
        config = make_config()
        kpi = make_kpi()
        # 1日だけ極小ボリューム＆CVR0%。比率の平均なら-1.9pt級の影響が出るが、
        # 合計の比なら分母1件ぶんの影響しか受けない。
        last = kpi.index[-1]
        kpi.loc[last, ["clicks", "cv_f", "registrations"]] = [1.0, 0.0, 0.0]
        result = compute_daily_bottleneck(kpi, config)

        latest = result.iloc[-1]
        self.assertGreater(latest["click_to_cvf_delta_pt"], -0.1)

    def test_immature_cohort_days_are_excluded_from_windows(self) -> None:
        """直近日のコホートが未成熟でも、コホート軸の区間は悪化と判定しない。"""
        config = make_config()
        kpi = make_kpi(as_of="2026-06-30")  # 最終日=6/29 → 経過1日で未成熟
        # 未成熟な直近2日だけ到達率が低い（まだタグが付き終わっていない状態を模す）
        kpi.loc[kpi.index[-2:], "payment_clicks"] = 2.0
        result = compute_daily_bottleneck(kpi, config)

        latest = result.iloc[-1]
        self.assertAlmostEqual(latest["cvf_to_payment_click_delta_pt"], 0.0, places=6)
        self.assertIn("コホート未成熟", latest["alerts"])

    def test_pre_tag_rollout_days_do_not_create_fake_bottleneck(self) -> None:
        """タグ運用開始前（付与0件）の期間をベースラインにしないこと。

        実データで踏んだ不具合の回帰テスト: 6月はタグ未運用で決済クリックが0件
        だったため、ベースラインが198%になり毎日「-25pt悪化」と誤判定していた。
        """
        config = make_config()
        kpi = make_kpi(days=60)
        rollout = kpi.index[:30]
        kpi.loc[rollout, "payment_clicks"] = 0.0  # 前半30日はタグ未運用

        activation = detect_tag_activation(kpi, config)
        self.assertIsNotNone(activation["payment_clicks"])
        self.assertGreaterEqual(
            pd.Timestamp(activation["payment_clicks"]), kpi.loc[kpi.index[30], "date"]
        )

        result = compute_daily_bottleneck(kpi, config)
        latest = result.iloc[-1]
        self.assertLessEqual(latest["payment_click_to_purchase_baseline"], 1.2)
        self.assertNotEqual(latest["bottleneck_confidence"], "confirmed")

    def test_stage_is_unjudgeable_when_tag_never_fires(self) -> None:
        config = make_config()
        kpi = make_kpi()
        kpi["payment_clicks"] = 0.0
        result = compute_daily_bottleneck(kpi, config)
        validity = stage_validity(kpi, config)

        self.assertFalse(validity["cvf_to_payment_click"]["judgeable"])
        self.assertTrue(pd.isna(result.iloc[-1]["cvf_to_payment_click_delta_pt"]))
        # 当日軸の区間は影響を受けず判定が続く
        self.assertTrue(validity["click_to_cvf"]["judgeable"])
        self.assertEqual(result.iloc[-1]["bottleneck_stage"], "click_to_cvf")

    def test_empty_input_returns_empty_frame_with_columns(self) -> None:
        result = compute_daily_bottleneck(pd.DataFrame(), make_config())
        self.assertTrue(result.empty)
        self.assertEqual(list(result.columns), OUTPUT_COLUMNS)


class GuardrailTest(unittest.TestCase):
    def test_overspend_day_raises_alert(self) -> None:
        config = make_config()
        kpi = make_kpi()
        kpi.loc[kpi.index[-1], "ad_cost"] = 700_000.0
        result = compute_daily_bottleneck(kpi, config)

        latest = result.iloc[-1]
        self.assertEqual(latest["alert_level"], "alert")
        self.assertIn("出稿過多", latest["alerts"])

    def test_warn_level_for_the_warning_band(self) -> None:
        config = make_config()
        kpi = make_kpi()
        kpi.loc[kpi.index[-1], "ad_cost"] = 500_000.0
        latest = compute_daily_bottleneck(kpi, config).iloc[-1]

        self.assertEqual(latest["alert_level"], "warn")
        self.assertIn("出稿注意", latest["alerts"])

    def test_negative_gross_profit_raises_alert(self) -> None:
        config = make_config()
        kpi = make_kpi()
        kpi.loc[kpi.index[-1], "gross_profit"] = -50_000.0
        kpi.loc[kpi.index[-1], "gross_margin"] = -0.1
        latest = compute_daily_bottleneck(kpi, config).iloc[-1]

        self.assertEqual(latest["alert_level"], "alert")
        self.assertIn("垂直粗利マイナス", latest["alerts"])

    def test_reconcile_mismatch_is_surfaced(self) -> None:
        config = make_config()
        kpi = make_kpi()
        kpi.loc[kpi.index[-1], "reconciled"] = False
        kpi.loc[kpi.index[-1], "cvf_registration_diff"] = -20.0
        latest = compute_daily_bottleneck(kpi, config).iloc[-1]

        self.assertIn("突合乖離", latest["alerts"])
        self.assertEqual(latest["alert_level"], "warn")


class CostBandSummaryTest(unittest.TestCase):
    def test_bands_split_by_daily_spend(self) -> None:
        kpi = make_kpi(days=10, ad_cost=200_000)
        kpi.loc[kpi.index[:3], "ad_cost"] = 800_000.0
        kpi.loc[kpi.index[:3], "gross_profit"] = -30_000.0
        bands = cost_band_summary(kpi)

        top = bands[bands["cost_band"] == "60万〜"].iloc[0]
        self.assertEqual(top["days"], 3)
        self.assertLess(top["gross_profit_per_day"], 0)
        low = bands[bands["cost_band"] == "〜25万"].iloc[0]
        self.assertEqual(low["days"], 7)

    def test_empty_input_returns_empty(self) -> None:
        self.assertTrue(cost_band_summary(pd.DataFrame()).empty)


if __name__ == "__main__":
    unittest.main()
