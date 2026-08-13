"""ECPの管理表PDFを日次テーブルに変換する。

## なぜ専用パーサが必要か

`weekly_dashboard.core.parse_management_pdf_text` はSTDの管理表の列順に合わせた
位置決め実装（`values[6]`=CTs, `values[9]`=CV(F) …）で、ECPは列構成が違う
（商品別CV列が無く購入は `実CV` 1本）。そのまま流用すると数値がずれたまま黙って
通ってしまう。

## PDFテキストの実際の形

pypdfの座標付き抽出（`visitor_text`）はセルの約半分しか拾えないため使えない。
フラットな `extract_text()` を使うが、隣接セルが空白なしで連結されることがある。

    2026/07/01 -14,252436,911105.40%13,653414,51218375659 3.59%629 ...
                ^^^^^^^ ^^^^^^^ ^^^^^^^^        ^^^^^^^^^^^^
                垂直粗利 売上    垂直ROAS         Cost+IMP+CTs

カンマ区切りの数値とパーセントは自己区切りなので分離できる。**問題はカンマの無い
整数どうしが隣接する箇所**（IMP と CTs）で、`18375659` が IMP=18375 / CTs=659 の
どこで切れるか字面からは決まらない。

## 分割の決め方（推測しない）

この表は比率も一緒に印字している。それを制約として使う。

    CTR  = CTs   / IMP
    MCVR = CV(F) / CTs

連結トークンを全ての位置で切ってみて、印字されている比率と一致する切り方だけを
採用する。候補が0個または2個以上なら**例外を投げる**（黙って推測しない）。

## レイアウト変化の検出

`問診/決済遷移率` 列はECPでは常に空（`問診回答` が0で0除算になるため）。もし
問診票運用が始まってこの列に値が入ると、以降の列が1つずれる。パース後に
CTR・MCVRの整合性を再検証し、合わなければ例外にする。ずれたまま数字を出さない。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

_ROW_RE = re.compile(r"(\d{4}/\d{2}/\d{2})([月火水木金土日])")
_TOKEN_RE = re.compile(
    r"#DIV/0!|\(?-?\d{1,3}(?:,\d{3})+(?:\.\d+)?\)?%?|\(?-?\d+(?:\.\d+)?\)?%?"
)

# 許容する丸め誤差。表の比率は小数2桁で印字されている。
_RATIO_TOLERANCE = 0.0002


@dataclass(frozen=True)
class Column:
    name: str
    kind: str  # "num" | "pct"


# ECP管理表の列順（日付・曜日・担当医を除く）。
# ⚠️ `問診/決済遷移率` は常に空なのでトークン列に現れない。ここに含めない。
ECP_COLUMNS: tuple[Column, ...] = (
    Column("gross_profit", "num"),      # 垂直粗利
    Column("sales", "num"),             # 売上
    Column("vertical_roas", "pct"),     # 垂直ROAS
    Column("aov", "num"),               # 客単
    Column("ad_cost", "num"),           # Cost
    Column("impressions", "num"),       # IMP
    Column("clicks", "num"),            # CTs
    Column("ctr", "pct"),               # CTR
    Column("cpc", "num"),               # CPC
    Column("cv_f", "num"),              # CV(F)
    Column("mcvr", "pct"),              # MCVR
    Column("mcpa", "num"),              # MCPA
    Column("monshin_answers", "num"),   # 問診回答
    Column("monshin_rate", "pct"),      # 問診遷移率
    Column("purchase_cv", "num"),       # 実CV
    Column("cl_cvr", "pct"),            # CL/CVR
    Column("line_payment_cvr", "pct"),  # LINE/決済CVR
    Column("real_cpa", "num"),          # 実CPA
    Column("alg_fee", "num"),           # ALGfee
    Column("clinic_gross_profit", "num"),  # クリニック粗利（未入金含む）
    Column("total_cost", "num"),        # 総原価（送料/手数料含む）
)

# 連結トークンを切るときに使う制約: (比率列, 分子列, 分母列)
_RATIO_CONSTRAINTS: tuple[tuple[str, str, str], ...] = (
    ("ctr", "clicks", "impressions"),
    ("mcvr", "cv_f", "clicks"),
)

LAYOUTS: dict[str, tuple[Column, ...]] = {"ecp": ECP_COLUMNS}


class ManagementPdfError(ValueError):
    """PDFのレイアウトが想定と違う（＝数値がずれる恐れがある）ことを示す。"""


def parse_number(token: str) -> float | None:
    """管理表の数値表記を数へ。丸括弧は会計表記のマイナスとして扱う。"""
    text = token.strip()
    if not text or text == "#DIV/0!":
        return None
    negative = text.startswith("(") and text.endswith(")")
    percent = text.endswith("%")
    text = text.strip("()").rstrip("%").replace(",", "").strip()
    if not text or text in ("-", "."):
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    if percent:
        value /= 100
    return -value if negative else value


def _is_percent(token: str) -> bool:
    return token.rstrip(")").endswith("%") or token == "#DIV/0!"


def _plain_integer(token: str) -> bool:
    """カンマも符号も小数点も持たない整数（＝隣と連結しうるトークン）。"""
    return token.isdigit()


def _split_candidates(token: str) -> list[tuple[str, str]]:
    return [(token[:index], token[index:]) for index in range(1, len(token))]


def _ratio_matches(numerator: float | None, denominator: float | None, expected: float) -> bool:
    if not numerator or not denominator:
        return False
    return abs(numerator / denominator - expected) <= _RATIO_TOLERANCE


def _assign(tokens: list[str], columns: tuple[Column, ...]) -> dict[str, float | None]:
    return {
        column.name: parse_number(token) for column, token in zip(columns, tokens)
    }


def _resolve_merged_tokens(
    tokens: list[str], columns: tuple[Column, ...], date_text: str
) -> list[str]:
    """トークン数が足りない行で、連結された整数トークンを制約に従って分割する。

    候補が一意に決まらない場合は例外。推測でずれた数値を返さない。
    """
    missing = len(columns) - len(tokens)
    if missing <= 0:
        return tokens

    for _ in range(missing):
        resolved: list[list[str]] = []
        for index, token in enumerate(tokens):
            if not _plain_integer(token) or len(token) < 2:
                continue
            for left, right in _split_candidates(token):
                candidate = [*tokens[:index], left, right, *tokens[index + 1 :]]
                if len(candidate) > len(columns):
                    continue
                if _satisfies_constraints(candidate, columns):
                    resolved.append(candidate)
        unique = {tuple(candidate) for candidate in resolved}
        if len(unique) != 1:
            raise ManagementPdfError(
                f"管理表PDFの行を一意に分解できません（{date_text}）: "
                f"トークン{len(tokens)}個に対し列{len(columns)}個、"
                f"整合する分割候補{len(unique)}通り。tokens={tokens}"
            )
        tokens = list(next(iter(unique)))
    return tokens


def _satisfies_constraints(tokens: list[str], columns: tuple[Column, ...]) -> bool:
    """印字されている比率と、その分子・分母の値が一致するか。

    トークン数が列数に達していない中間状態でも、種別（数値/パーセント）の並びが
    崩れていれば早期に落とす。
    """
    for column, token in zip(columns, tokens):
        if (column.kind == "pct") != _is_percent(token):
            return False
    if len(tokens) < len(columns):
        return True

    values = _assign(tokens, columns)
    checked = 0
    for ratio_name, numerator_name, denominator_name in _RATIO_CONSTRAINTS:
        expected = values.get(ratio_name)
        if expected is None:
            continue
        if not _ratio_matches(values.get(numerator_name), values.get(denominator_name), expected):
            return False
        checked += 1
    return checked > 0


def _verify_row(values: dict[str, float | None], date_text: str) -> None:
    """パース後の整合性再検査。列がずれていればここで落ちる。"""
    for ratio_name, numerator_name, denominator_name in _RATIO_CONSTRAINTS:
        expected = values.get(ratio_name)
        numerator = values.get(numerator_name)
        denominator = values.get(denominator_name)
        if expected is None or not numerator or not denominator:
            continue
        if not _ratio_matches(numerator, denominator, expected):
            raise ManagementPdfError(
                f"管理表PDFの列がずれています（{date_text}）: "
                f"印字された{ratio_name}={expected:.4f} に対し "
                f"{numerator_name}/{denominator_name}="
                f"{numerator / denominator:.4f}。"
                "PDFのレイアウトが変わった可能性があります"
                "（例: 問診票運用が始まり『問診/決済遷移率』列に値が入った）。"
                "CSVエクスポートで再実行してください。"
            )


def parse_management_pdf_text(text: str, layout: str = "ecp") -> pd.DataFrame:
    """管理表PDFの抽出テキストを日次DataFrameへ変換する。

    実績が入っていない行（トークンがほとんど無い未来日）は0行として返し、
    呼び出し側の活動量フィルタで落とす。
    """
    if layout not in LAYOUTS:
        raise ManagementPdfError(
            f"未対応のPDFレイアウトです: {layout!r}（対応: {', '.join(sorted(LAYOUTS))}）"
        )
    columns = LAYOUTS[layout]

    matches = list(_ROW_RE.finditer(text))
    if not matches:
        raise ManagementPdfError(
            "管理表PDFから日付行を検出できません（想定書式: YYYY/MM/DD + 曜日）"
        )

    rows: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        segment_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        tokens = _TOKEN_RE.findall(text[match.end() : segment_end])
        date_text = match.group(1)

        # 実績のない日（0や空欄だけの行）。無理に分解せずゼロ行として通す。
        if len(tokens) < len(columns) - 4:
            values: dict[str, float | None] = {column.name: None for column in columns}
        else:
            tokens = _resolve_merged_tokens(tokens, columns, date_text)
            if len(tokens) > len(columns):
                raise ManagementPdfError(
                    f"管理表PDFの行のトークンが多すぎます（{date_text}）: "
                    f"{len(tokens)}個 > 列{len(columns)}個。tokens={tokens}"
                )
            values = _assign(tokens, columns)
            _verify_row(values, date_text)

        values["date"] = pd.Timestamp(datetime.strptime(date_text, "%Y/%m/%d").date())
        rows.append(values)

    frame = pd.DataFrame(rows)
    return frame.drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
