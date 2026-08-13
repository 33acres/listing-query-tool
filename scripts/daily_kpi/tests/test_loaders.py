from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.daily_kpi.kpi import build_daily_kpi
from scripts.daily_kpi.loaders import (
    aggregate_lstep_daily,
    load_lstep_frame,
    management_conflicts,
    read_management_daily,
    read_management_frames,
)
from scripts.daily_kpi.tests.fixtures import make_config

_MANAGEMENT_CSV = """進捗or平均,,"3,739,320","14,600,600",,,,,,,,,,,,,,,,,,,,,
目標,,,,,,,,,,,,,,,,,,,,,,,,
,,,,,,,,,,,,,,,,,,,,,,,,
日付,曜日,垂直粗利,売上,垂直ROAS,客単,Cost,IMP,CTs,CTR,CPC,CV(F),MCVR,MCPA,問診回答,問診遷移率,実CV,問診/決済遷移率,CL/CVR,LINE/決済CVR,実CPA,ALGfee,"クリニック粗利
（未入金含む）","総原価
（送料/手数料含む）",担当医
2026/07/01,水,"-14,252","436,911",105.40%,"13,653","414,512",18375,659,3.59%,629,77,11.68%,5383,0,0.00%,32,,4.86%,41.56%,"12,954","516,670 ","(79,759)","36,650 ",A先生
2026/07/02,木,"13,909","580,289",112.17%,"12,895","517,326",23910,827,3.46%,626,103,12.45%,5023,0,0.00%,45,,5.44%,43.69%,"11,496","691,130 ","(110,841)","49,054 ",A先生
2026/07/03,金,0,0,,,0,0,0,,,,,,0,,0,,,,,0 ,0 ,0 ,A先生
"""

_LSTEP_CSV = """登録ID,,,,タグ_1,タグ_2,タグ_3,タグ_4
ID,表示名,対応マーク,友だち追加日時,ECP_事前決済クリック_72時間1回分,ECP_事前決済クリック_120時間1回分,ECP_決済済み,ECP_処方不可_未成年
1,あ,発送済,2026-07-01 10:00:00,1,0,0,0
2,い,,2026-07-01 11:00:00,1,1,0,1
3,う,,2026-07-01 12:00:00,0,0,0,0
4,え,,2026-07-02 09:00:00,0,1,0,0
"""


class ReadManagementDailyTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.input_dir = Path(self._temp.name)
        (self.input_dir / "management-20260728.csv").write_text(
            _MANAGEMENT_CSV, encoding="utf-8-sig"
        )
        self.config = make_config()
        self.config["daily_kpi"]["management"]["header_row"] = 4

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_reads_the_fourth_row_as_header_and_parses_japanese_numbers(self) -> None:
        frame = read_management_daily(self.input_dir, self.config)

        self.assertEqual(len(frame), 2)  # 実績のない7/03は落ちる
        first = frame.iloc[0]
        self.assertEqual(first["date"], pd.Timestamp("2026-07-01"))
        self.assertEqual(first["ad_cost"], 414_512)
        self.assertEqual(first["clicks"], 659)
        self.assertEqual(first["cv_f"], 77)
        self.assertEqual(first["purchase_cv"], 32)  # 実CV → purchase_cv
        self.assertEqual(first["gross_profit"], -14_252)  # カンマ付きマイナス
        self.assertEqual(first["sales"], 436_911)

    def test_missing_file_raises_with_search_patterns(self) -> None:
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaises(FileNotFoundError) as raised:
                read_management_daily(Path(empty), self.config)
            self.assertIn("management*.csv", str(raised.exception))

    def test_wrong_header_row_fails_loudly(self) -> None:
        self.config["daily_kpi"]["management"]["header_row"] = 2
        with self.assertRaises(ValueError) as raised:
            read_management_daily(self.input_dir, self.config)
        self.assertIn("ヘッダー行がずれています", str(raised.exception))

    def test_unverified_pdf_layout_is_rejected_instead_of_misread(self) -> None:
        """列順が違う診療科のPDFを黙って数値ずれで通さないこと。"""
        (self.input_dir / "management-202607.pdf").write_bytes(b"%PDF-1.4 dummy")
        self.config["weekly_dashboard"]["management"]["file_patterns"] = [
            "management*.csv",
            "management*.pdf",
        ]
        with self.assertRaises(ValueError) as raised:
            read_management_daily(self.input_dir, self.config)
        self.assertIn("レイアウトは未検証です", str(raised.exception))

    def test_later_file_wins_for_the_same_date(self) -> None:
        updated = _MANAGEMENT_CSV.replace('"414,512"', '"999,999"')
        (self.input_dir / "management-20260729.csv").write_text(updated, encoding="utf-8-sig")
        frame = read_management_daily(self.input_dir, self.config)
        self.assertEqual(frame.iloc[0]["ad_cost"], 999_999)

    def test_conflicting_values_between_files_are_reported(self) -> None:
        """新しい方を採用しつつ、食い違い自体は黙って捨てない。"""
        updated = _MANAGEMENT_CSV.replace('"414,512"', '"999,999"')
        (self.input_dir / "management-20260729.csv").write_text(updated, encoding="utf-8-sig")
        frames = read_management_frames(self.input_dir, self.config)
        conflicts = management_conflicts(frames)

        row = conflicts[conflicts["column"] == "ad_cost"].iloc[0]
        self.assertEqual(row["date"], pd.Timestamp("2026-07-01"))
        self.assertEqual(row["adopted_value"], 999_999)
        self.assertEqual(row["other_value"], 414_512)
        self.assertEqual(row["adopted"], "management-20260729.csv")

    def test_identical_duplicate_rows_are_not_reported_as_conflicts(self) -> None:
        (self.input_dir / "management-20260729.csv").write_text(
            _MANAGEMENT_CSV, encoding="utf-8-sig"
        )
        conflicts = management_conflicts(read_management_frames(self.input_dir, self.config))
        self.assertTrue(conflicts.empty)


class LstepAggregationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.input_dir = Path(self._temp.name)
        (self.input_dir / "lstep2026.csv").write_text(_LSTEP_CSV, encoding="utf-8")
        self.config = make_config()

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_payment_clicks_count_people_not_tags(self) -> None:
        frame = load_lstep_frame(self.input_dir, self.config)
        daily = aggregate_lstep_daily(frame, self.config)

        july1 = daily[daily["date"] == pd.Timestamp("2026-07-01")].iloc[0]
        self.assertEqual(july1["registrations"], 3)
        # ID2は2タグ立っているが1人として数える
        self.assertEqual(july1["payment_clicks"], 2)
        self.assertEqual(july1["ng_total"], 1)
        self.assertEqual(july1["paid_tagged"], 0)
        # 商品別は延べ（重複あり）
        self.assertEqual(july1["click_a72_1"], 2)
        self.assertEqual(july1["click_a120_1"], 1)

    def test_pii_columns_are_dropped(self) -> None:
        frame = load_lstep_frame(self.input_dir, self.config)
        self.assertNotIn("表示名", frame.columns)
        self.assertNotIn("対応マーク", frame.columns)

    def test_split_files_are_merged_and_deduplicated_by_id(self) -> None:
        (self.input_dir / "lstep2025.csv").write_text(_LSTEP_CSV, encoding="utf-8")
        frame = load_lstep_frame(self.input_dir, self.config)
        self.assertEqual(len(frame), 4)

    def test_missing_files_raise(self) -> None:
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaises(FileNotFoundError):
                load_lstep_frame(Path(empty), self.config)


class BuildDailyKpiTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.input_dir = Path(self._temp.name)
        (self.input_dir / "management-20260728.csv").write_text(
            _MANAGEMENT_CSV, encoding="utf-8-sig"
        )
        (self.input_dir / "lstep2026.csv").write_text(_LSTEP_CSV, encoding="utf-8")
        self.config = make_config()
        self.config["daily_kpi"]["management"]["header_row"] = 4

    def tearDown(self) -> None:
        self._temp.cleanup()

    def _build(self) -> pd.DataFrame:
        management = read_management_daily(self.input_dir, self.config)
        lstep = aggregate_lstep_daily(
            load_lstep_frame(self.input_dir, self.config), self.config
        )
        return build_daily_kpi(
            management, lstep, self.config, as_of=pd.Timestamp("2026-07-10")
        )

    def test_joins_on_date_and_flags_the_reconciliation_gap(self) -> None:
        kpi = self._build()

        july1 = kpi[kpi["date"] == pd.Timestamp("2026-07-01")].iloc[0]
        self.assertEqual(july1["cv_f"], 77)
        self.assertEqual(july1["registrations"], 3)
        # 管理表CV(F)=77 と Lステップ登録=3 は明らかに乖離 → 突合NG
        self.assertEqual(july1["cvf_registration_diff"], -74)
        self.assertFalse(bool(july1["reconciled"]))

    def test_rates_and_maturity_are_computed(self) -> None:
        kpi = self._build()
        july1 = kpi[kpi["date"] == pd.Timestamp("2026-07-01")].iloc[0]

        self.assertAlmostEqual(july1["click_to_cvf_rate"], 77 / 659)
        self.assertAlmostEqual(july1["cvf_to_payment_click_rate"], 2 / 3)
        self.assertAlmostEqual(july1["cpa"], 414_512 / 32)
        self.assertAlmostEqual(july1["gross_margin"], -14_252 / 436_911)
        self.assertEqual(july1["cohort_days_elapsed"], 9)
        self.assertTrue(bool(july1["cohort_mature"]))

    def test_days_missing_from_lstep_get_zero_not_dropped(self) -> None:
        kpi = self._build()
        self.assertEqual(len(kpi), 2)
        self.assertTrue((kpi["registrations"] >= 0).all())

    def test_zero_denominator_yields_nan_not_error(self) -> None:
        management = read_management_daily(self.input_dir, self.config)
        management.loc[management.index[0], "clicks"] = 0
        lstep = aggregate_lstep_daily(
            load_lstep_frame(self.input_dir, self.config), self.config
        )
        kpi = build_daily_kpi(
            management, lstep, self.config, as_of=pd.Timestamp("2026-07-10")
        )
        self.assertTrue(pd.isna(kpi.iloc[0]["click_to_cvf_rate"]))

    def test_empty_management_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_daily_kpi(
                pd.DataFrame(), pd.DataFrame(), self.config, as_of=pd.Timestamp("2026-07-10")
            )


if __name__ == "__main__":
    unittest.main()
