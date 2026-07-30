"""週次ファネル履歴からステージ間CVRの変化を計算し、ボトルネック段階を判定する。

`core.HISTORY_COLUMNS` 形式（project, week_start, week_end, ad_clicks,
line_registrations, cv_f, monshin_answers, purchase_cv, ...）の DataFrame のみを
入力とする純粋関数群。ネットワーク・ファイルIOへの依存はなく、単体テストしやすい。

売上・粗利列は funnel_history.csv に含まれないため、商品構成・粗利率レバーの分解
（spec D8のフル版）は対象外。将来 HISTORY_COLUMNS に売上/粗利を追加すれば拡張できる。
"""

from __future__ import annotations

from typing import Any

import pandas as pd

# (段階キー, 日本語ラベル, 分子列, 分母列) — 隣接ステージ間の実CVR
MARGINAL_STAGES: list[tuple[str, str, str, str]] = [
    ("click_to_line", "広告クリック→LINE登録", "line_registrations", "ad_clicks"),
    ("line_to_cvf", "LINE登録→CV(F)", "cv_f", "line_registrations"),
    ("cvf_to_monshin", "CV(F)→問診回答", "monshin_answers", "cv_f"),
    ("monshin_to_purchase", "問診回答→購入CV", "purchase_cv", "monshin_answers"),
]

_STAGE_KEYS = [stage for stage, _, _, _ in MARGINAL_STAGES]
_STAGE_LABELS = {stage: label for stage, label, _, _ in MARGINAL_STAGES}

OUTPUT_COLUMNS = [
    "project",
    "week_start",
    "week_end",
    "ad_clicks",
    "ad_clicks_delta_wow_pct",
    "ad_clicks_delta_avg4_pct",
    *[
        column
        for stage in _STAGE_KEYS
        for column in (
            f"{stage}_rate",
            f"{stage}_delta_wow_pt",
            f"{stage}_delta_avg4_pt",
        )
    ],
    "bottleneck_stage",
    "bottleneck_stage_label",
    "bottleneck_severity_pt",
    "bottleneck_confidence",
]

_NON_NUMERIC_COLUMNS = {
    "project",
    "week_start",
    "week_end",
    "ad_clicks",
    "bottleneck_stage",
    "bottleneck_stage_label",
    "bottleneck_confidence",
}


def _nan_to_none(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return float(value)


def _trailing_average(series: pd.Series, window: int) -> pd.Series:
    """直前window週分（当該週を除く）のトレーリング平均。"""
    return series.shift(1).rolling(window=window, min_periods=1).mean()


def _classify(
    wow_by_stage: dict[str, float | None],
    avg4_by_stage: dict[str, float | None],
    threshold_pt: float,
) -> tuple[str | None, float | None, str | None]:
    """WoWで最も悪化した段階をボトルネック候補とし、確度を判定する。

    直近weeks平均比でも同方向かつ両方が閾値以上悪化していれば "confirmed"、
    そうでなければ単週ノイズとして "single_week_noise" を返す。
    比較可能な前週データが一つもない場合は (None, None, None)。
    """
    candidates = {
        stage: value
        for stage, value in wow_by_stage.items()
        if value is not None and not pd.isna(value)
    }
    if not candidates:
        return None, None, None

    worst_stage = min(candidates, key=lambda stage: candidates[stage])
    severity = candidates[worst_stage]
    avg4_value = avg4_by_stage.get(worst_stage)

    confirmed = (
        severity < 0
        and avg4_value is not None
        and not pd.isna(avg4_value)
        and avg4_value < 0
        and abs(severity) >= threshold_pt
        and abs(avg4_value) >= threshold_pt
    )
    confidence = "confirmed" if confirmed else "single_week_noise"
    return worst_stage, float(severity), confidence


def _compute_project_frame(
    group: pd.DataFrame, *, trailing_weeks: int, threshold_pt: float
) -> pd.DataFrame:
    group = group.sort_values("week_start").reset_index(drop=True)

    result = pd.DataFrame(
        {
            "project": group["project"],
            "week_start": group["week_start"],
            "week_end": group["week_end"],
            "ad_clicks": group["ad_clicks"],
        }
    )

    # 0除算はfloat("nan")(numpy NaN)に倒す。pd.NA(pandasのnullable NA)は
    # .rolling().mean()が扱えず例外になるため使わない
    # (monshin_answers=0の週が実データに存在し、実行時に踏んだ実バグ)。
    prior_clicks = group["ad_clicks"].shift(1).replace(0, float("nan"))
    result["ad_clicks_delta_wow_pct"] = (group["ad_clicks"] - prior_clicks) / prior_clicks

    avg4_clicks = _trailing_average(group["ad_clicks"], trailing_weeks).replace(0, float("nan"))
    result["ad_clicks_delta_avg4_pct"] = (group["ad_clicks"] - avg4_clicks) / avg4_clicks

    for stage, _, numerator_col, denominator_col in MARGINAL_STAGES:
        rate = group[numerator_col] / group[denominator_col].replace(0, float("nan"))
        result[f"{stage}_rate"] = rate
        result[f"{stage}_delta_wow_pt"] = rate.diff() * 100
        result[f"{stage}_delta_avg4_pt"] = (rate - _trailing_average(rate, trailing_weeks)) * 100

    bottleneck_stage: list[str | None] = []
    bottleneck_label: list[str | None] = []
    bottleneck_severity: list[float | None] = []
    bottleneck_confidence: list[str | None] = []
    for index in range(len(result)):
        wow_by_stage = {stage: result.loc[index, f"{stage}_delta_wow_pt"] for stage in _STAGE_KEYS}
        avg4_by_stage = {stage: result.loc[index, f"{stage}_delta_avg4_pt"] for stage in _STAGE_KEYS}
        stage_key, severity, confidence = _classify(wow_by_stage, avg4_by_stage, threshold_pt)
        bottleneck_stage.append(stage_key)
        bottleneck_label.append(_STAGE_LABELS.get(stage_key) if stage_key else None)
        bottleneck_severity.append(severity)
        bottleneck_confidence.append(confidence)

    result["bottleneck_stage"] = bottleneck_stage
    result["bottleneck_stage_label"] = bottleneck_label
    result["bottleneck_severity_pt"] = bottleneck_severity
    result["bottleneck_confidence"] = bottleneck_confidence
    return result


def compute_bottleneck_frame(
    history: pd.DataFrame,
    *,
    trailing_weeks: int = 4,
    threshold_pt: float = 2.0,
) -> pd.DataFrame:
    """週次ファネル履歴から隣接ステージ間CVRの変化とボトルネック段階を計算する。

    history は `core.HISTORY_COLUMNS` 形式（project, week_start, week_end, ad_clicks,
    line_registrations, cv_f, monshin_answers, purchase_cv を含む）を想定する。
    project ごとに week_start 昇順で処理し、各週について:
    - 4つの隣接ステージ間CVR（クリック→登録・登録→CVF・CVF→問診・問診→購入）
    - それぞれの前週比(pt)・直近trailing_weeks週平均比(pt)
    - 広告クリック数の前週比・直近平均比(%)
    - 最も悪化した段階を bottleneck_stage とし、前週比・トレンド比の両方が
      threshold_pt 以上悪化していれば bottleneck_confidence="confirmed"、
      そうでなければ "single_week_noise" とする。
    を算出する。
    """
    if history.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    parts = [
        _compute_project_frame(group, trailing_weeks=trailing_weeks, threshold_pt=threshold_pt)
        for _, group in history.groupby("project", sort=False)
    ]
    combined = pd.concat(parts, ignore_index=True)
    combined = combined.sort_values(["project", "week_start"]).reset_index(drop=True)

    for column in combined.columns:
        if column in _NON_NUMERIC_COLUMNS:
            continue
        combined[column] = combined[column].map(_nan_to_none)

    return combined[OUTPUT_COLUMNS]
