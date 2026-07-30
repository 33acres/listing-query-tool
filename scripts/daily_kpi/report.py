"""日次KPI表とボトルネック判定を、そのまま読める日本語Markdownに落とす。"""

from __future__ import annotations

from typing import Any

import pandas as pd

from scripts.daily_kpi.bottleneck import cost_band_summary, cpa_band_summary
from scripts.daily_kpi.kpi import ALL_STAGES, STAGES

_DAILY_TABLE_COLUMNS: list[tuple[str, str, str]] = [
    ("date", "日付", "date"),
    ("weekday", "曜", "text"),
    ("ad_cost", "Cost", "yen"),
    ("clicks", "CTs", "int"),
    ("cv_f", "CV(F)", "int"),
    ("registrations", "L登録", "int"),
    ("payment_clicks", "決済クリック", "int"),
    ("purchase_cv", "実CV", "int"),
    ("click_to_cvf_rate", "①ク→登録", "pct"),
    ("cvf_to_payment_click_rate", "②登録→クリック", "pct"),
    ("payment_click_to_purchase_rate", "③クリック→購入", "pct"),
    ("cvf_to_purchase_rate", "通し登録→購入", "pct"),
    ("cpa", "CPA", "yen"),
    ("aov", "客単", "yen"),
    ("gross_profit", "垂直粗利", "yen"),
    ("gross_margin", "粗利率", "pct"),
    ("ng_rate", "処方不可率", "pct"),
]


def _format(value: Any, kind: str) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    if kind == "date":
        return pd.Timestamp(value).strftime("%m/%d")
    if kind == "text":
        return str(value)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if pd.isna(number):
        return "—"
    if kind == "pct":
        return f"{number * 100:.1f}%"
    if kind == "yen":
        return f"{number:,.0f}"
    return f"{number:,.0f}"


def _markdown_table(rows: list[list[str]], header: list[str]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def _daily_table(kpi: pd.DataFrame, days: int) -> str:
    tail = kpi.tail(days)
    header = [label for _, label, _ in _DAILY_TABLE_COLUMNS]
    rows = [
        [_format(row.get(column), kind) for column, _, kind in _DAILY_TABLE_COLUMNS]
        for _, row in tail.iterrows()
    ]
    return _markdown_table(rows, header)


_CONFIDENCE_JA = {
    "confirmed": "🔴 悪化確定",
    "within_noise": "🟡 誤差範囲",
    "no_degradation": "🟢 悪化なし",
}
_AXIS_JA = {"daily": "当日軸", "cohort": "コホート軸", "mixed": "混在軸"}


def _verdict_section(bottleneck: pd.DataFrame, config: dict[str, Any]) -> str:
    settings = config["daily_kpi"]["detection"]
    latest = bottleneck.iloc[-1]
    lines = [
        "## 判定（直近日）",
        "",
        f"- 対象日: **{pd.Timestamp(latest['date']).strftime('%Y-%m-%d')}（{latest['weekday']}）**",
        f"- 判定方式: 直近{settings['rolling_days']}日の合計比 vs その直前{settings['baseline_days']}日の合計比",
    ]
    stage_label = latest.get("bottleneck_stage_label")
    confidence_key = str(latest.get("bottleneck_confidence"))
    if stage_label:
        severity = latest.get("bottleneck_severity_pt")
        confidence = _CONFIDENCE_JA.get(confidence_key, confidence_key)
        axis = _AXIS_JA.get(str(latest.get("bottleneck_axis")), "")
        # 全区間が改善している日もあるので、そのときは「悪化した区間」と書かない
        heading = (
            "最も伸び幅が小さい区間"
            if confidence_key == "no_degradation"
            else "ボトルネック区間"
        )
        lines.append(
            f"- {heading}: **{stage_label}**（{severity:+.1f}pt / {confidence} / {axis}）"
        )
    else:
        lines.append("- ボトルネック区間: 比較可能なベースラインが無いため未判定")

    alerts = str(latest.get("alerts") or "")
    lines.append(f"- 単日アラート: {alerts if alerts else 'なし'}")
    lines.append("")

    recent = bottleneck.tail(7)
    flagged = recent[recent["alert_level"].isin(["alert", "warn"])]
    if flagged.empty:
        lines.append("直近7日でアラート・警告水準の日はありません。")
    else:
        lines.append("### 直近7日の要注意日")
        lines.append("")
        lines.append(
            _markdown_table(
                [
                    [
                        pd.Timestamp(row["date"]).strftime("%m/%d"),
                        str(row["weekday"]),
                        "🔴" if row["alert_level"] == "alert" else "🟡",
                        str(row["alerts"]),
                    ]
                    for _, row in flagged.iterrows()
                ],
                ["日付", "曜", "水準", "内容"],
            )
        )
    return "\n".join(lines)


def _stage_section(bottleneck: pd.DataFrame, validity: dict[str, dict[str, Any]]) -> str:
    latest = bottleneck.iloc[-1]
    rows = []
    for stage in STAGES:
        info = validity.get(stage.key, {})
        if not info.get("judgeable", True):
            note = "⚫️ 判定不能（タグ未運用）"
        elif info.get("valid_from"):
            note = f"{info['valid_from']}以降で比較"
        else:
            note = "全期間で比較"
        rows.append(
            [
                stage.label,
                _AXIS_JA.get(stage.axis, stage.axis),
                _format(latest.get(f"{stage.key}_rate_7d"), "pct"),
                _format(latest.get(f"{stage.key}_baseline"), "pct"),
                (
                    f"{float(latest[f'{stage.key}_delta_pt']):+.1f}pt"
                    if not pd.isna(latest.get(f"{stage.key}_delta_pt"))
                    else "—"
                ),
                note,
            ]
        )
    return "\n".join(
        [
            "## 区間別（直近7日 vs 直前28日）",
            "",
            _markdown_table(
                rows, ["区間", "時間軸", "直近7日", "ベースライン", "差分", "比較可能範囲"]
            ),
            "",
            "Lステップのタグは途中から全登録者に発火するようになったため、付与率が"
            "継続して立ち上がった日を自動検出し、それ以前は判定窓から除外している"
            "（除外しないとタグが無かった期間との比較で偽のボトルネックが出る）。",
        ]
    )


def _band_rows(bands: pd.DataFrame, band_column: str) -> list[list[str]]:
    return [
        [
            str(row[band_column]),
            _format(row["days"], "int"),
            f"{int(row['loss_days'])}日",
            _format(row["click_to_cvf"], "pct"),
            _format(row["cvf_to_purchase"], "pct"),
            _format(row["cpa"], "yen"),
            _format(row["gross_margin"], "pct"),
            _format(row["gross_profit_per_day"], "yen"),
        ]
        for _, row in bands.iterrows()
    ]


_BAND_HEADER = ["帯", "日数", "赤字日", "ク→登録", "登録→購入", "CPA", "粗利率", "垂直粗利/日"]


def _cpa_band_section(kpi: pd.DataFrame) -> str:
    bands = cpa_band_summary(kpi)
    if bands.empty:
        return ""
    return "\n".join(
        [
            "## 実CPA帯別（赤字がどこから始まるか）",
            "",
            _markdown_table(_band_rows(bands, "cpa_band"), _BAND_HEADER),
            "",
            "客単が13,000〜14,000円なので、CPAが客単に迫ると原価分だけ赤字になる。"
            "**赤字の予兆はCPAで見る**（出稿額ではない・下記参照）。",
        ]
    )


def _cost_band_section(kpi: pd.DataFrame) -> str:
    bands = cost_band_summary(kpi)
    if bands.empty:
        return ""
    return "\n".join(
        [
            "## 日次Cost帯別（参考）",
            "",
            _markdown_table(_band_rows(bands, "cost_band"), _BAND_HEADER),
            "",
            "出稿を増やすと「登録→購入」とCPAは悪化するが、**出稿額そのものは赤字と"
            "結びついていない**（高出稿でも量で粗利が出る帯がある）。出稿上限の根拠には"
            "使えないので、判断は上のCPA帯で行うこと。",
        ]
    )


_CONFLICT_LABELS = {
    "ad_cost": "Cost",
    "clicks": "CTs",
    "cv_f": "CV(F)",
    "purchase_cv": "実CV",
    "sales": "売上",
    "gross_profit": "垂直粗利",
}


def _conflict_section(conflicts: pd.DataFrame) -> str:
    if conflicts is None or conflicts.empty:
        return ""
    rows = [
        [
            pd.Timestamp(row["date"]).strftime("%Y-%m-%d"),
            _CONFLICT_LABELS.get(str(row["column"]), str(row["column"])),
            _format(row["adopted_value"], "yen"),
            _format(row["other_value"], "yen"),
            str(row["adopted"]),
        ]
        for _, row in conflicts.iterrows()
    ]
    return "\n".join(
        [
            "## ⚠️ 管理表どうしの食い違い",
            "",
            "同じ日が複数の管理表に載っていて値が違う箇所。新しいエクスポート側を採用している。",
            "",
            _markdown_table(rows, ["日付", "項目", "採用値", "他ファイルの値", "採用元"]),
        ]
    )


def _reconcile_section(kpi: pd.DataFrame) -> str:
    covered = kpi[kpi["lstep_covered"].fillna(True).astype(bool)] if "lstep_covered" in kpi else kpi
    uncovered = kpi[~kpi["lstep_covered"].fillna(True).astype(bool)] if "lstep_covered" in kpi else kpi.iloc[0:0]
    total_cvf = float(covered["cv_f"].sum())
    total_reg = float(covered["registrations"].sum())
    mismatched = covered[~covered["reconciled"].fillna(False).astype(bool)]
    lines = [
        "## 突合（管理表 × Lステップ）",
        "",
        f"- 突合できた期間（{len(covered)}日）合計: 管理表CV(F) {total_cvf:,.0f} 件 / "
        f"Lステップ友だち追加 {total_reg:,.0f} 件（差 {total_reg - total_cvf:+,.0f} 件）",
        f"- 許容乖離を超えた日: {len(mismatched)} 日 / {len(covered)} 日",
    ]
    if not uncovered.empty:
        first = pd.Timestamp(uncovered["date"].min()).strftime("%Y-%m-%d")
        last = pd.Timestamp(uncovered["date"].max()).strftime("%Y-%m-%d")
        lines.append(
            f"- ⚠️ Lステップ未取得日: {len(uncovered)} 日（{first} 〜 {last}）。"
            "管理表のほうが新しいため、この期間のコホート指標（②③・処方不可率）は空欄。"
            "Lステップを再エクスポートすれば埋まる"
        )
    if not mismatched.empty:
        lines += [
            "",
            _markdown_table(
                [
                    [
                        pd.Timestamp(row["date"]).strftime("%m/%d"),
                        _format(row["cv_f"], "int"),
                        _format(row["registrations"], "int"),
                        _format(row["cvf_registration_diff"], "int"),
                    ]
                    for _, row in mismatched.tail(15).iterrows()
                ],
                ["日付", "管理表CV(F)", "L登録", "差"],
            ),
        ]
    paid_tagged = float(kpi["paid_tagged"].sum())
    if paid_tagged == 0:
        lines += [
            "",
            "- ⚠️ Lステップの `ECP_決済済み` タグは全件0件（決済システム→Lステップ連携が未実装）。"
            "購入は管理表の実CVのみが正で、個人単位の購入紐付けはできない。"
            "「③事前決済クリック→購入」は集計値どうしの割り算であり、分母がコホート軸・"
            "分子が当日軸の混在指標。",
        ]
    return "\n".join(lines)


def build_report(
    kpi: pd.DataFrame,
    bottleneck: pd.DataFrame,
    config: dict[str, Any],
    *,
    source_files: list[str],
    validity: dict[str, dict[str, Any]] | None = None,
    conflicts: pd.DataFrame | None = None,
    table_days: int = 14,
) -> str:
    validity = validity or {}
    display_name = config.get("display_name", config["project"])
    start = pd.Timestamp(kpi["date"].min()).strftime("%Y-%m-%d")
    end = pd.Timestamp(kpi["date"].max()).strftime("%Y-%m-%d")
    sections = [
        f"# {display_name} 日次KPI・ボトルネック表",
        "",
        f"対象期間: {start} 〜 {end}（{len(kpi)}日）",
        "入力: " + ", ".join(f"`{name}`" for name in source_files),
        "",
        _verdict_section(bottleneck, config),
        "",
        _stage_section(bottleneck, validity),
        "",
        f"## 日次KPI表（直近{table_days}日）",
        "",
        _daily_table(kpi, table_days),
        "",
        "凡例: ①②③はファネルの隣接区間。②はLステップのコホート軸（友だち追加日基準の到達率）、"
        "③は分母コホート軸・分子当日軸の混在指標。①と通しは管理表の当日実績のみで完結する。",
        "",
        _cpa_band_section(kpi),
        "",
        _cost_band_section(kpi),
        "",
        _reconcile_section(kpi),
        "",
        _conflict_section(conflicts if conflicts is not None else pd.DataFrame()),
        "",
    ]
    stages_note = " / ".join(f"{stage.label}={stage.numerator}÷{stage.denominator}" for stage in ALL_STAGES)
    sections += ["---", "", f"指標定義: {stages_note}", ""]
    return "\n".join(section for section in sections if section is not None)
