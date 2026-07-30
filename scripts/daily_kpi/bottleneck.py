"""日次KPI表から「どの区間が詰まっているか」を自動判定する。

日次の単日CVRは分母が小さくノイズが支配的なので、判定は必ず移動平均で行う。

  区間CVR(7日) = 直近7日の分子合計 / 直近7日の分母合計
  ベースライン  = その7日窓の直前28日の分子合計 / 分母合計
  悪化幅(pt)    = 区間CVR(7日) - ベースライン

比率の平均ではなく「合計の比」を使うのは、分母が極端に小さい日に引っ張られない
ようにするため（単日CV(F)が数件の日が実データに存在する）。

コホート軸（Lステップ由来）の区間は、友だち追加から日が浅い日を窓に入れると
必ず見かけ上悪化する。config.daily_kpi.cohort_maturity_days に達していない日は
マスクして窓から除外する。

CVRのトレンド判定とは別に、単日で見て明らかに損している日（出稿過多・粗利
マイナス・突合乖離）はガードレールとしてフラグを立てる。
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from scripts.daily_kpi.kpi import STAGES, Stage, detect_tag_activation, stage_activation

_STAGE_BY_KEY = {stage.key: stage for stage in STAGES}

OUTPUT_COLUMNS = [
    "date",
    "weekday",
    "ad_cost",
    "clicks",
    "cv_f",
    "payment_clicks",
    "purchase_cv",
    "gross_profit",
    "gross_margin",
    *[
        column
        for stage in STAGES
        for column in (
            f"{stage.key}_rate_7d",
            f"{stage.key}_baseline",
            f"{stage.key}_delta_pt",
        )
    ],
    "bottleneck_stage",
    "bottleneck_stage_label",
    "bottleneck_axis",
    "bottleneck_severity_pt",
    "bottleneck_confidence",
    "alert_level",
    "alerts",
]

_TEXT_COLUMNS = {
    "date",
    "weekday",
    "bottleneck_stage",
    "bottleneck_stage_label",
    "bottleneck_axis",
    "bottleneck_confidence",
    "alert_level",
    "alerts",
}


def _masked(series: pd.Series, keep: pd.Series) -> pd.Series:
    """keep が False の行を NaN にする（rolling集計から除外させる）。"""
    return series.where(keep, other=float("nan")).astype("float64")


def _rolling_ratio(
    numerator: pd.Series, denominator: pd.Series, window: int, *, offset: int = 0
) -> pd.Series:
    """直近window日（offset日ずらし）の合計比。NaN行は窓から自動的に外れる。"""
    numerator_sum = numerator.shift(offset).rolling(window=window, min_periods=1).sum()
    denominator_sum = denominator.shift(offset).rolling(window=window, min_periods=1).sum()
    return numerator_sum / denominator_sum.replace(0, float("nan"))


def _stage_frames(
    kpi: pd.DataFrame,
    stage: Stage,
    *,
    rolling_days: int,
    baseline_days: int,
    valid_from: pd.Timestamp | None,
    judgeable: bool,
    max_plausible_rate: float,
) -> tuple[pd.Series, pd.Series]:
    """区間の移動CVRとベースラインを返す。判定不能なら全NaN。

    窓から外すのは2種類の日:
    - コホート未成熟日（友だち追加から日が浅く到達率がまだ伸びる）
    - タグ運用開始前の日（0件なのは実績ではなく計測していないだけ）
    """
    empty = pd.Series(float("nan"), index=kpi.index, dtype="float64")
    if not judgeable:
        return empty, empty

    numerator = pd.to_numeric(kpi[stage.numerator], errors="coerce").astype("float64")
    denominator = pd.to_numeric(kpi[stage.denominator], errors="coerce").astype("float64")
    if stage.axis in ("cohort", "mixed"):
        keep = kpi["cohort_mature"].fillna(False).astype(bool)
        if valid_from is not None:
            keep = keep & (kpi["date"] >= valid_from)
        numerator = _masked(numerator, keep)
        denominator = _masked(denominator, keep)

    rate = _rolling_ratio(numerator, denominator, rolling_days)
    baseline = _rolling_ratio(numerator, denominator, baseline_days, offset=rolling_days)

    # ありえない値（>120%等）が出た窓は、両者が同じ母集団を指していない証拠。
    # 比較不能としてNaNに倒す（誤ったボトルネック判定を作らないため）。
    rate = rate.where(rate <= max_plausible_rate, other=float("nan"))
    baseline = baseline.where(baseline <= max_plausible_rate, other=float("nan"))
    return rate, baseline


def _classify_row(
    deltas: dict[str, float | None], threshold_pt: float
) -> tuple[str | None, float | None, str | None]:
    """最も悪化した区間をボトルネックとし、閾値超えなら confirmed とする。"""
    candidates = {
        key: value
        for key, value in deltas.items()
        if value is not None and not pd.isna(value)
    }
    if not candidates:
        return None, None, None
    worst = min(candidates, key=lambda key: candidates[key])
    severity = float(candidates[worst])
    if severity >= 0:
        return worst, severity, "no_degradation"
    confidence = "confirmed" if abs(severity) >= threshold_pt else "within_noise"
    return worst, severity, confidence


def _row_alerts(row: pd.Series, guardrails: dict[str, Any]) -> tuple[str, list[str]]:
    """CVRトレンドとは独立した単日ガードレール。"""
    alerts: list[str] = []
    level = "ok"

    ad_cost = float(row.get("ad_cost") or 0)
    if ad_cost >= float(guardrails["daily_cost_alert"]):
        alerts.append(f"出稿過多:Cost {ad_cost:,.0f}円（アラート閾値超）")
        level = "alert"
    elif ad_cost >= float(guardrails["daily_cost_warn"]):
        alerts.append(f"出稿注意:Cost {ad_cost:,.0f}円（警告閾値超）")
        level = "warn" if level == "ok" else level

    gross_profit = float(row.get("gross_profit") or 0)
    if gross_profit < 0:
        alerts.append(f"垂直粗利マイナス {gross_profit:,.0f}円")
        level = "alert"

    gross_margin = row.get("gross_margin")
    sales = float(row.get("sales") or 0)
    if (
        sales > 0
        and gross_margin is not None
        and not pd.isna(gross_margin)
        and float(gross_margin) < float(guardrails["min_gross_margin"])
    ):
        alerts.append(f"粗利率低下 {float(gross_margin) * 100:.1f}%")
        level = "alert" if level == "alert" else "warn"

    if not bool(row.get("reconciled", True)):
        diff = row.get("cvf_registration_diff")
        alerts.append(
            f"突合乖離:Lステップ登録数−管理表CV(F)={float(diff or 0):+.0f}件"
        )
        level = "alert" if level == "alert" else "warn"

    if not bool(row.get("cohort_mature", True)):
        alerts.append("コホート未成熟（Lステップ由来の到達率は確定値ではない）")

    return level, alerts


def stage_validity(kpi: pd.DataFrame, config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """区間ごとの「いつから比較可能か」を返す（レポート・監査ログ用）。"""
    activation = detect_tag_activation(kpi, config)
    validity: dict[str, dict[str, Any]] = {}
    for stage in STAGES:
        valid_from, judgeable = stage_activation(stage, activation)
        validity[stage.key] = {
            "label": stage.label,
            "axis": stage.axis,
            "judgeable": judgeable,
            "valid_from": None if valid_from is None else valid_from.strftime("%Y-%m-%d"),
        }
    return validity


def compute_daily_bottleneck(kpi: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """日次KPI表に区間別の悪化幅・ボトルネック判定・単日アラートを付けて返す。"""
    settings = config["daily_kpi"]["detection"]
    guardrails = config["daily_kpi"]["guardrails"]
    rolling_days = int(settings["rolling_days"])
    baseline_days = int(settings["baseline_days"])
    threshold_pt = float(settings["threshold_pt"])
    max_plausible_rate = float(settings["max_plausible_rate"])

    if kpi.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    frame = kpi.sort_values("date").reset_index(drop=True).copy()
    activation = detect_tag_activation(frame, config)
    result = frame[
        [
            "date",
            "weekday",
            "ad_cost",
            "clicks",
            "cv_f",
            "payment_clicks",
            "purchase_cv",
            "gross_profit",
            "gross_margin",
        ]
    ].copy()

    for stage in STAGES:
        valid_from, judgeable = stage_activation(stage, activation)
        rate, baseline = _stage_frames(
            frame,
            stage,
            rolling_days=rolling_days,
            baseline_days=baseline_days,
            valid_from=valid_from,
            judgeable=judgeable,
            max_plausible_rate=max_plausible_rate,
        )
        result[f"{stage.key}_rate_7d"] = rate
        result[f"{stage.key}_baseline"] = baseline
        result[f"{stage.key}_delta_pt"] = (rate - baseline) * 100

    stages_key: list[str | None] = []
    stages_label: list[str | None] = []
    stages_axis: list[str | None] = []
    severities: list[float | None] = []
    confidences: list[str | None] = []
    levels: list[str] = []
    alert_texts: list[str] = []

    for index in range(len(result)):
        deltas = {
            stage.key: result.loc[index, f"{stage.key}_delta_pt"] for stage in STAGES
        }
        key, severity, confidence = _classify_row(deltas, threshold_pt)
        stage = _STAGE_BY_KEY.get(key) if key else None
        stages_key.append(key)
        stages_label.append(stage.label if stage else None)
        stages_axis.append(stage.axis if stage else None)
        severities.append(severity)
        confidences.append(confidence)

        level, alerts = _row_alerts(frame.loc[index], guardrails)
        if confidence == "confirmed":
            level = "alert"
            alerts.insert(
                0, f"{stage.label if stage else key}が{severity:+.1f}pt悪化"
            )
        levels.append(level)
        alert_texts.append(" / ".join(alerts))

    result["bottleneck_stage"] = stages_key
    result["bottleneck_stage_label"] = stages_label
    result["bottleneck_axis"] = stages_axis
    result["bottleneck_severity_pt"] = severities
    result["bottleneck_confidence"] = confidences
    result["alert_level"] = levels
    result["alerts"] = alert_texts

    for column in result.columns:
        if column in _TEXT_COLUMNS:
            continue
        result[column] = pd.to_numeric(result[column], errors="coerce")
    return result[OUTPUT_COLUMNS]


def cost_band_summary(kpi: pd.DataFrame, bands: list[int] | None = None) -> pd.DataFrame:
    """日次Cost帯ごとの歩留りと粗利。「1日いくらまで出して良いか」を出す。

    出稿量を上げても広告クリック→登録はほぼ一定なのに登録→購入が崩れる、という
    ECPの構造をそのまま表にする。
    """
    if kpi.empty:
        return pd.DataFrame()
    bands = bands or [250_000, 350_000, 450_000, 600_000]
    labels = (
        [f"〜{bands[0] // 10_000}万"]
        + [
            f"{lower // 10_000}〜{upper // 10_000}万"
            for lower, upper in zip(bands, bands[1:])
        ]
        + [f"{bands[-1] // 10_000}万〜"]
    )
    frame = kpi.copy()
    frame["cost_band"] = pd.cut(
        frame["ad_cost"],
        bins=[-float("inf"), *bands, float("inf")],
        labels=labels,
        ordered=True,
    )
    grouped = frame.groupby("cost_band", observed=False).agg(
        days=("date", "count"),
        ad_cost=("ad_cost", "sum"),
        clicks=("clicks", "sum"),
        cv_f=("cv_f", "sum"),
        purchase_cv=("purchase_cv", "sum"),
        sales=("sales", "sum"),
        gross_profit=("gross_profit", "sum"),
    )
    grouped = grouped[grouped["days"] > 0].copy()
    grouped["click_to_cvf"] = grouped["cv_f"] / grouped["clicks"].replace(0, float("nan"))
    grouped["cvf_to_purchase"] = grouped["purchase_cv"] / grouped["cv_f"].replace(
        0, float("nan")
    )
    grouped["cpa"] = grouped["ad_cost"] / grouped["purchase_cv"].replace(0, float("nan"))
    grouped["gross_profit_per_day"] = grouped["gross_profit"] / grouped["days"]
    return grouped.reset_index()
