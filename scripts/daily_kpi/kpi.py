"""管理表（当日軸）とLステップ（コホート軸）を日付で突合し、日次KPI表を組む。

axis の意味（区間ごとに時間軸が違うので明示している）:
- "daily"  : 分子・分母ともに管理表の同日実績。素直に日次で読める
- "cohort" : 分子・分母ともにLステップの同一コホート（友だち追加日基準）
- "mixed"  : 分母がコホート・分子が当日実績。ECPは緊急避妊薬で登録から購入までが
             即日に寄るため近似として使えるが、日をまたぐ購入がある分だけ
             歩留りが上下する。単日の値ではなく移動平均で読むこと
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

_WEEKDAY_JA = ["月", "火", "水", "木", "金", "土", "日"]


@dataclass(frozen=True)
class Stage:
    key: str
    label: str
    numerator: str
    denominator: str
    axis: str


# ファネルの隣接区間。ECPは管理表の「問診回答」が全日0なのでSTDの5段ではなく4段。
STAGES: list[Stage] = [
    Stage("click_to_cvf", "広告クリック→LINE登録", "cv_f", "clicks", "daily"),
    Stage(
        "cvf_to_payment_click",
        "LINE登録→事前決済クリック",
        "payment_clicks",
        "registrations",
        "cohort",
    ),
    Stage(
        "payment_click_to_purchase",
        "事前決済クリック→購入",
        "purchase_cv",
        "payment_clicks",
        "mixed",
    ),
]

# 通しの歩留り（区間判定には使わず、全体の推移把握用）
THROUGHPUT_STAGES: list[Stage] = [
    Stage("cvf_to_purchase", "LINE登録→購入（通し）", "purchase_cv", "cv_f", "daily"),
]

ALL_STAGES = STAGES + THROUGHPUT_STAGES

KPI_COLUMNS = [
    "date",
    "weekday",
    # 管理表（当日軸）
    "ad_cost",
    "impressions",
    "clicks",
    "cv_f",
    "purchase_cv",
    "sales",
    "gross_profit",
    "aov",
    # Lステップ（コホート軸）
    "registrations",
    "payment_clicks",
    "ng_total",
    "paid_tagged",
    # 突合
    "cvf_registration_diff",
    "cvf_registration_diff_rate",
    "reconciled",
    "lstep_covered",
    # 効率
    "ctr",
    "cpc",
    "cpa",
    "roas",
    "gross_margin",
    "ng_rate",
    # 区間CVR
    *[f"{stage.key}_rate" for stage in ALL_STAGES],
    # データ成熟度
    "cohort_days_elapsed",
    "cohort_mature",
]


# Lステップのタグ付与から導出される列。タグ運用が始まった日より前は
# 「0件」ではなく「計測していない」なので、判定の窓から外す必要がある。
LSTEP_TAG_COLUMNS = ("payment_clicks", "paid_tagged", "ng_total")


def detect_tag_activation(
    kpi: pd.DataFrame, config: dict[str, Any]
) -> dict[str, pd.Timestamp | None]:
    """各タグ列が「継続して付与されるようになった日」を自動検出する。

    ルールは単純で説明可能なものにしてある: 登録数に対する7日移動の付与率が
    min_tag_coverage 以上である状態が **直近まで途切れず続いている** 最初の日。
    末尾から遡って判定するため、運用開始前の偶発的な数件では活性化しない。

    一度も閾値を超えない列は None（＝その列を使う区間は判定不能）を返す。
    """
    threshold = float(config["daily_kpi"]["detection"]["min_tag_coverage"])
    window = int(config["daily_kpi"]["detection"]["rolling_days"])
    frame = kpi.sort_values("date").reset_index(drop=True)
    registrations = pd.to_numeric(frame["registrations"], errors="coerce").astype("float64")
    registration_sum = registrations.rolling(window=window, min_periods=1).sum()

    activation: dict[str, pd.Timestamp | None] = {}
    for column in LSTEP_TAG_COLUMNS:
        if column not in frame.columns:
            activation[column] = None
            continue
        tagged = pd.to_numeric(frame[column], errors="coerce").astype("float64")
        coverage = tagged.rolling(window=window, min_periods=1).sum() / registration_sum.replace(
            0, float("nan")
        )
        above = (coverage >= threshold).fillna(False).to_numpy()
        if not above.any() or not above[-1]:
            activation[column] = None
            continue
        index = len(above) - 1
        while index > 0 and above[index - 1]:
            index -= 1
        activation[column] = pd.Timestamp(frame.loc[index, "date"])
    return activation


def stage_activation(
    stage: Stage, activation: dict[str, pd.Timestamp | None]
) -> tuple[pd.Timestamp | None, bool]:
    """区間の有効開始日と、判定可能かどうかを返す。

    区間が使うLステップ由来の列すべてが活性化して初めて比較できる。
    どれか1つでも未活性なら (None, False)。
    """
    involved = [
        column
        for column in (stage.numerator, stage.denominator)
        if column in LSTEP_TAG_COLUMNS
    ]
    if not involved:
        return None, True
    dates = [activation.get(column) for column in involved]
    if any(value is None for value in dates):
        return None, False
    return max(value for value in dates if value is not None), True


def _safe_div(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """0除算はNaNへ。pd.NAではなくfloat NaNを使う（rolling().mean()が扱えるため）。"""
    return numerator / denominator.replace(0, float("nan"))


def build_daily_kpi(
    management: pd.DataFrame,
    lstep_daily: pd.DataFrame,
    config: dict[str, Any],
    *,
    as_of: pd.Timestamp,
    lstep_covered_through: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """管理表の日次行を土台に、Lステップのコホート集計を左結合してKPI表を作る。

    管理表に無い日（=まだ管理表に行が無い直近日）は落とす。管理表が実績の正なので、
    Lステップだけ存在する日を混ぜると売上ゼロの偽の悪化日ができてしまう。
    """
    if management.empty:
        raise ValueError("管理表の実績行が0件です（未来日のみのエクスポートになっていないか確認してください）")

    frame = management.merge(lstep_daily, on="date", how="left")
    for column in ("registrations", "payment_clicks", "paid_tagged", "ng_total"):
        if column not in frame.columns:
            frame[column] = 0
        frame[column] = frame[column].fillna(0)

    frame["weekday"] = frame["date"].dt.weekday.map(lambda index: _WEEKDAY_JA[index])

    # Lステップのエクスポートがどの日まで含んでいるか。管理表のほうが新しいのは
    # 日常的に起きるので、その日を「突合乖離」ではなく「未取得」として扱う。
    if lstep_covered_through is None:
        frame["lstep_covered"] = True
    else:
        frame["lstep_covered"] = frame["date"] <= pd.Timestamp(lstep_covered_through).normalize()

    # 突合: 管理表CV(F)とLステップ友だち追加数は同じものを指すはず
    frame["cvf_registration_diff"] = frame["registrations"] - frame["cv_f"]
    frame["cvf_registration_diff_rate"] = _safe_div(
        frame["cvf_registration_diff"].abs(), frame["cv_f"]
    )
    tolerance = float(config["daily_kpi"]["guardrails"]["reconcile_tolerance"])
    frame["reconciled"] = (
        frame["cvf_registration_diff_rate"].fillna(1.0) <= tolerance
    )
    # 未取得日は突合の合否を問わない（Lステップ側にまだデータが無いだけ）
    frame.loc[~frame["lstep_covered"], "reconciled"] = True

    frame["ctr"] = _safe_div(frame["clicks"], frame["impressions"])
    frame["cpc"] = _safe_div(frame["ad_cost"], frame["clicks"])
    frame["cpa"] = _safe_div(frame["ad_cost"], frame["purchase_cv"])
    frame["roas"] = _safe_div(frame["sales"], frame["ad_cost"])
    frame["gross_margin"] = _safe_div(frame["gross_profit"], frame["sales"])
    frame["ng_rate"] = _safe_div(frame["ng_total"], frame["registrations"])

    for stage in ALL_STAGES:
        frame[f"{stage.key}_rate"] = _safe_div(frame[stage.numerator], frame[stage.denominator])

    maturity_days = int(config["daily_kpi"]["cohort_maturity_days"])
    frame["cohort_days_elapsed"] = (as_of.normalize() - frame["date"]).dt.days
    frame["cohort_mature"] = frame["cohort_days_elapsed"] >= maturity_days

    extra = [
        column
        for column in frame.columns
        if column.startswith(("click_", "reach_", "ng_")) and column not in KPI_COLUMNS
    ]
    return frame[[*KPI_COLUMNS, *sorted(extra)]].sort_values("date").reset_index(drop=True)


def product_mix(lstep_daily: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """事前決済クリックの商品別内訳（延べ・重複あり）。客単改善の余地を見る用。"""
    keys = list(config.get("click_tags", {}).keys())
    columns = [f"click_{key}" for key in keys if f"click_{key}" in lstep_daily.columns]
    if not columns:
        return pd.DataFrame(columns=["product", "clicks", "share"])
    totals = lstep_daily[columns].sum()
    frame = pd.DataFrame({"product": [column[len("click_") :] for column in columns],
                          "clicks": totals.to_numpy()})
    frame["share"] = _safe_div(frame["clicks"], pd.Series([frame["clicks"].sum()] * len(frame)))
    return frame.sort_values("clicks", ascending=False).reset_index(drop=True)
