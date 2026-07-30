"""日次KPIテスト用の設定・データ生成ヘルパー。"""

from __future__ import annotations

from typing import Any

import pandas as pd


def make_config(**overrides: Any) -> dict[str, Any]:
    config: dict[str, Any] = {
        "project": "ecp",
        "display_name": "テスト外来",
        "drive": {"folder_id": "folder", "required_files": {"lstep": "lstep.csv", "ads": "ads.csv"}},
        "column_mapping": {"added_at": "友だち追加日時"},
        "click_tags": {
            "a72_1": "ECP_事前決済クリック_72時間1回分",
            "a120_1": "ECP_事前決済クリック_120時間1回分",
        },
        "status_tags": {"paid": "ECP_決済済み"},
        "branch_tags": {"ng_minor": "ECP_処方不可_未成年"},
        "tags": {"step1": "ECP_診察誘導_STEP1"},
        "weekly_dashboard": {
            "lstep": {"header_row": 2, "encodings": ["utf-8"]},
            "management": {
                "file_patterns": ["management*.csv"],
                "column_aliases": {
                    "date": ["日付"],
                    "gross_profit": ["垂直粗利"],
                    "sales": ["売上"],
                    "ad_cost": ["Cost"],
                    "impressions": ["IMP"],
                    "clicks": ["CTs"],
                    "cv_f": ["CV(F)"],
                    "monshin_answers": ["問診回答"],
                    "purchase_cv": ["実CV"],
                    "aov": ["客単"],
                },
            },
        },
        "daily_kpi": {
            "input_root": "in/{project}/{run_date}",
            "output_root": "out/{project}/{run_date}",
            "history_root": "out/{project}/history.csv",
            "output_files": {
                "kpi": "daily_kpi.csv",
                "bottleneck": "daily_bottleneck.csv",
                "report": "daily_report.md",
                "audit": "daily_meta.json",
            },
            "lstep": {"file_patterns": ["lstep*.csv"]},
            "management": {"header_row": 1},
            "cohort_maturity_days": 3,
            "detection": {
                "rolling_days": 7,
                "baseline_days": 28,
                "threshold_pt": 2.0,
                "min_tag_coverage": 0.15,
                "max_plausible_rate": 1.2,
            },
            "guardrails": {
                "cpa_warn": 11_500,
                "cpa_alert": 12_000,
                "daily_cost_warn": 400_000,
                "min_gross_margin": 0.20,
                "reconcile_tolerance": 0.05,
            },
        },
        "google_sheets": {
            "worksheets": {"daily_kpi": "DailyKPI", "daily_bottleneck": "DailyBottleneck"}
        },
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(config.get(key), dict):
            config[key] = {**config[key], **value}
        else:
            config[key] = value
    return config


def make_kpi(
    days: int = 60,
    *,
    start: str = "2026-05-01",
    clicks: int = 500,
    cv_f: int = 65,
    payment_clicks: int = 42,
    purchase_cv: int = 36,
    ad_cost: int = 300_000,
    sales: int = 500_000,
    gross_profit: int = 150_000,
    as_of: str | None = None,
) -> pd.DataFrame:
    """平坦な日次KPI表。テストごとに必要な日だけ書き換えて使う。"""
    dates = pd.date_range(start=start, periods=days, freq="D")
    reference = pd.Timestamp(as_of) if as_of else dates[-1] + pd.Timedelta(days=1)
    frame = pd.DataFrame(
        {
            "date": dates,
            "weekday": [["月", "火", "水", "木", "金", "土", "日"][d.weekday()] for d in dates],
            "ad_cost": float(ad_cost),
            "impressions": 20_000.0,
            "clicks": float(clicks),
            "cv_f": float(cv_f),
            "purchase_cv": float(purchase_cv),
            "sales": float(sales),
            "gross_profit": float(gross_profit),
            "aov": 13_000.0,
            "registrations": float(cv_f),
            "payment_clicks": float(payment_clicks),
            "ng_total": 10.0,
            "paid_tagged": 0.0,
        }
    )
    frame["cvf_registration_diff"] = frame["registrations"] - frame["cv_f"]
    frame["cvf_registration_diff_rate"] = 0.0
    frame["reconciled"] = True
    frame["lstep_covered"] = True
    frame["ctr"] = frame["clicks"] / frame["impressions"]
    frame["cpc"] = frame["ad_cost"] / frame["clicks"]
    frame["cpa"] = frame["ad_cost"] / frame["purchase_cv"]
    frame["roas"] = frame["sales"] / frame["ad_cost"]
    frame["gross_margin"] = frame["gross_profit"] / frame["sales"]
    frame["ng_rate"] = frame["ng_total"] / frame["registrations"]
    frame["click_to_cvf_rate"] = frame["cv_f"] / frame["clicks"]
    frame["cvf_to_payment_click_rate"] = frame["payment_clicks"] / frame["registrations"]
    frame["payment_click_to_purchase_rate"] = frame["purchase_cv"] / frame["payment_clicks"]
    frame["cvf_to_purchase_rate"] = frame["purchase_cv"] / frame["cv_f"]
    frame["cohort_days_elapsed"] = (reference.normalize() - frame["date"]).dt.days
    frame["cohort_mature"] = frame["cohort_days_elapsed"] >= 3
    return frame
