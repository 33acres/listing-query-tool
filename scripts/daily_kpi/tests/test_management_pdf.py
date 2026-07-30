from __future__ import annotations

import unittest

import pandas as pd

from scripts.daily_kpi.management_pdf import (
    ManagementPdfError,
    parse_management_pdf_text,
    parse_number,
)

# 実PDF（アフターピル全体管理 - 202606.pdf / 202607.pdf）から抽出した実テキスト。
# IMPとCTsが空白なしで連結されている（16163587 = IMP 16163 + CTs 587）。
_MERGED_ROW = (
    "2026/06/01月 5,663 442,358113.29%15,254390,45316163587 3.63%665 59 10.05%6618 "
    "0 0.00% 29 4.94% 49.15% 13,464 395,890) 46,468) 46,242)"
)
# IMPとCTsが分離しているケース（9197 と 339）
_SPLIT_ROW = (
    "2026/06/16火 249,283465,257273.38%14,539170,1859197 339 3.69%502 32 9.44%5318 "
    "0 0.00% 32 9.44% 100.00%5,318 214,720) 250,537) 45,789)"
)
# 垂直粗利が負の実行（マイナス記号つき）
_NEGATIVE_ROW = (
    "2026/07/04土 -253,466702,76878.29%12,329897,593257461333 5.18%673 156 11.70%5754 "
    "0 0.00% 57 4.28% 36.54% 15,7471,046,760) (343,992)58,642)"
)


class ParseNumberTest(unittest.TestCase):
    def test_handles_the_notations_used_in_the_sheet(self) -> None:
        self.assertEqual(parse_number("442,358"), 442_358)
        self.assertEqual(parse_number("-253,466"), -253_466)
        self.assertEqual(parse_number("659"), 659)
        self.assertAlmostEqual(parse_number("113.29%"), 1.1329)
        self.assertEqual(parse_number("(343,992)"), -343_992)  # 会計表記のマイナス
        self.assertIsNone(parse_number("#DIV/0!"))
        self.assertIsNone(parse_number(""))


class ParseManagementPdfTextTest(unittest.TestCase):
    def test_splits_merged_impressions_and_clicks_using_the_printed_ctr(self) -> None:
        frame = parse_management_pdf_text(_MERGED_ROW)

        row = frame.iloc[0]
        self.assertEqual(row["date"], pd.Timestamp("2026-06-01"))
        # 16163587 は CTR 3.63% と整合する 16163 / 587 に分割される
        self.assertEqual(row["impressions"], 16_163)
        self.assertEqual(row["clicks"], 587)
        self.assertAlmostEqual(row["clicks"] / row["impressions"], row["ctr"], places=4)

    def test_reads_all_columns_needed_by_the_pipeline(self) -> None:
        row = parse_management_pdf_text(_MERGED_ROW).iloc[0]

        self.assertEqual(row["gross_profit"], 5_663)
        self.assertEqual(row["sales"], 442_358)
        self.assertEqual(row["aov"], 15_254)
        self.assertEqual(row["ad_cost"], 390_453)
        self.assertEqual(row["cv_f"], 59)
        self.assertEqual(row["monshin_answers"], 0)
        self.assertEqual(row["purchase_cv"], 29)

    def test_handles_rows_where_tokens_are_already_separated(self) -> None:
        row = parse_management_pdf_text(_SPLIT_ROW).iloc[0]

        self.assertEqual(row["impressions"], 9_197)
        self.assertEqual(row["clicks"], 339)
        self.assertEqual(row["cv_f"], 32)
        self.assertEqual(row["purchase_cv"], 32)

    def test_negative_gross_profit_keeps_its_sign(self) -> None:
        row = parse_management_pdf_text(_NEGATIVE_ROW).iloc[0]

        self.assertEqual(row["gross_profit"], -253_466)
        self.assertEqual(row["sales"], 702_768)
        self.assertEqual(row["impressions"], 25_746)
        self.assertEqual(row["clicks"], 1_333)
        self.assertEqual(row["purchase_cv"], 57)

    def test_multiple_rows_parse_independently(self) -> None:
        frame = parse_management_pdf_text(f"{_MERGED_ROW}{_SPLIT_ROW}")
        self.assertEqual(len(frame), 2)
        self.assertEqual(list(frame["clicks"]), [587, 339])

    def test_a_column_shift_is_rejected_not_silently_parsed(self) -> None:
        """問診票運用が始まって列が1つ増えたケースを模す。

        ずれたまま数値を返すのが最悪なので、印字比率との不整合で落とす。
        """
        shifted = _MERGED_ROW.replace(" 0 0.00% 29 ", " 25 32.00% 29 12.00% ")
        with self.assertRaises(ManagementPdfError) as raised:
            parse_management_pdf_text(shifted)
        self.assertIn("列がずれています", str(raised.exception))

    def test_unresolvable_row_raises_instead_of_guessing(self) -> None:
        # CTRを消すと 16163587 の分割根拠が無くなる
        broken = _MERGED_ROW.replace(" 3.63%", "")
        with self.assertRaises(ManagementPdfError):
            parse_management_pdf_text(broken)

    def test_unknown_layout_is_rejected(self) -> None:
        with self.assertRaises(ManagementPdfError):
            parse_management_pdf_text(_MERGED_ROW, layout="dayvigo")

    def test_text_without_date_rows_raises(self) -> None:
        with self.assertRaises(ManagementPdfError):
            parse_management_pdf_text("見出しだけのPDF")

    def test_empty_future_rows_become_null_rows(self) -> None:
        frame = parse_management_pdf_text(f"{_MERGED_ROW}2026/07/31金 0 0 0 0")
        self.assertEqual(len(frame), 2)
        self.assertTrue(pd.isna(frame.iloc[1]["sales"]))


if __name__ == "__main__":
    unittest.main()
