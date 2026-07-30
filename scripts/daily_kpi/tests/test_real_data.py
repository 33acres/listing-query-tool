"""実データがローカルに揃っているときだけ走る突合テスト。

CIや他マシンでは入力が無いのでスキップする（`unittest.skipUnless`）。
検証内容は「同じ月の管理表を PDF から読んでも CSV から読んでも同じ数字になる」。
PDFは列順を決め打ちして読むので、この一致がパーサの正しさの担保になる。
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import pandas as pd
from pypdf import PdfReader

from scripts.daily_kpi.management_pdf import parse_management_pdf_text

_PDF_DIR = Path("/Users/yuya/onemedical/ECP/docs/data")
_CSV_DIR = Path(__file__).resolve().parents[3] / "output/ecp/2026-07-28/raw"

_PDF_202606 = _PDF_DIR / "アフターピル全体管理【あしたのクリニック】 - 202606.pdf"
_CSV_202606 = _CSV_DIR / "management-202606.csv"

_COMPARED = [
    "gross_profit",
    "sales",
    "aov",
    "ad_cost",
    "impressions",
    "clicks",
    "cv_f",
    "monshin_answers",
    "purchase_cv",
]

_CSV_TO_CANONICAL = {
    "垂直粗利": "gross_profit",
    "売上": "sales",
    "客単": "aov",
    "Cost": "ad_cost",
    "IMP": "impressions",
    "CTs": "clicks",
    "CV(F)": "cv_f",
    "問診回答": "monshin_answers",
    "実CV": "purchase_cv",
}


def _read_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig", skiprows=3)
    frame.columns = [re.sub(r"\s+", "", str(column)) for column in frame.columns]
    frame = frame[frame["日付"].notna()].copy()
    result = pd.DataFrame({"date": pd.to_datetime(frame["日付"], errors="coerce")})
    for source, canonical in _CSV_TO_CANONICAL.items():
        result[canonical] = pd.to_numeric(
            frame[source]
            .astype(str)
            .str.replace(",", "", regex=False)
            .str.replace("%", "", regex=False)
            .str.strip()
            .replace({"": None, "nan": None, "#DIV/0!": None}),
            errors="coerce",
        )
    return result.dropna(subset=["date"])


def _read_pdf(path: Path) -> pd.DataFrame:
    text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    return parse_management_pdf_text(text, "ecp")


@unittest.skipUnless(
    _PDF_202606.is_file() and _CSV_202606.is_file(),
    "実データ（ECP/docs/data のPDFと output/ecp/.../raw のCSV）が無い環境",
)
class PdfMatchesCsvTest(unittest.TestCase):
    def test_every_overlapping_day_and_column_matches(self) -> None:
        pdf = _read_pdf(_PDF_202606)
        csv = _read_csv(_CSV_202606)
        merged = pdf.merge(csv, on="date", suffixes=("_pdf", "_csv"))

        self.assertGreaterEqual(len(merged), 30, "突合対象日が少なすぎる")
        for column in _COMPARED:
            difference = (
                merged[f"{column}_pdf"].fillna(0) - merged[f"{column}_csv"].fillna(0)
            ).abs()
            self.assertLessEqual(
                float(difference.max()),
                0.51,
                f"{column} がPDFとCSVで一致しない（最大差 {difference.max()}）",
            )

    def test_printed_ratios_are_internally_consistent(self) -> None:
        """CTR = CTs/IMP、MCVR = CV(F)/CTs が全行で成立していること。"""
        pdf = _read_pdf(_PDF_202606)
        active = pdf[pdf["clicks"].fillna(0) > 0]

        self.assertGreaterEqual(len(active), 30)
        for _, row in active.iterrows():
            self.assertAlmostEqual(
                row["clicks"] / row["impressions"], row["ctr"], places=3
            )
            self.assertAlmostEqual(row["cv_f"] / row["clicks"], row["mcvr"], places=3)


if __name__ == "__main__":
    unittest.main()
