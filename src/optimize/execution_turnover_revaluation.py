import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.optimize import execution_capacity_experiment as exec_core
from src.optimize import turnover_control_experiment as turnover_core


OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output", "cne6")
DATA_DIR = os.path.join(OUTPUT_DIR, "data")
IMAGE_DIR = os.path.join(OUTPUT_DIR, "images", "optimize")

SUFFIX = "l20_s5_b2_e1_n100"

TARGET_RETURNS_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"execution_turnover_revaluation_targets_{SUFFIX}.csv"
)
DETAIL_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"execution_turnover_revaluation_detail_{SUFFIX}.csv"
)
SUMMARY_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"execution_turnover_revaluation_summary_{SUFFIX}.csv"
)
RANKING_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"execution_turnover_revaluation_ranking_{SUFFIX}.csv"
)
ANNUAL_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"execution_turnover_revaluation_annual_{SUFFIX}.csv"
)
PLOT_OUTPUT_PATH = os.path.join(
    IMAGE_DIR, f"execution_turnover_revaluation_{SUFFIX}.png"
)


def _normalize(series, higher_is_better=True):
    values = series.astype(float)
    if not higher_is_better:
        values = -values
    min_value = values.min()
    max_value = values.max()
    if pd.isna(min_value) or pd.isna(max_value) or max_value == min_value:
        return pd.Series(0.5, index=series.index)
    return (values - min_value) / (max_value - min_value)


def _scenario_param_map(target_df):
    cols = ["scenario", "description", "max_turnover", "buffer_multiplier"]
    return target_df[cols].drop_duplicates("scenario")


def build_scenario_ranking(summary_df, annual_df, target_df):
    """按成交约束后的综合表现给换手参数排序。"""
    param_df = _scenario_param_map(target_df)

    grouped = (
        summary_df.groupby("scenario", as_index=False)
        .agg(
            mean_annual_return=("annual_return", "mean"),
            min_annual_return=("annual_return", "min"),
            mean_sharpe=("sharpe_ratio", "mean"),
            mean_max_drawdown=("max_drawdown", "mean"),
            worst_max_drawdown=("max_drawdown", "min"),
            mean_fill_ratio=("avg_fill_ratio", "mean"),
            mean_target_overlap=("avg_target_overlap_weight", "mean"),
            mean_cash_weight=("avg_cash_weight", "mean"),
            mean_cost=("total_cost_arithmetic", "mean"),
            mean_actual_stock_count=("avg_actual_stock_count", "mean"),
        )
    )

    annual_stability = (
        annual_df.groupby("scenario")["annual_return"]
        .std()
        .rename("annual_return_std")
        .reset_index()
    )
    ranking = grouped.merge(annual_stability, on="scenario", how="left")
    ranking = ranking.merge(param_df, on="scenario", how="left")

    ranking["score_return"] = _normalize(ranking["mean_annual_return"])
    ranking["score_tail_return"] = _normalize(ranking["min_annual_return"])
    ranking["score_drawdown"] = _normalize(ranking["mean_max_drawdown"])
    ranking["score_fill"] = _normalize(ranking["mean_fill_ratio"])
    ranking["score_overlap"] = _normalize(ranking["mean_target_overlap"])
    ranking["score_cash"] = _normalize(ranking["mean_cash_weight"], higher_is_better=False)
    ranking["score_stability"] = _normalize(ranking["annual_return_std"], higher_is_better=False)

    ranking["composite_score"] = (
        0.35 * ranking["score_return"]
        + 0.20 * ranking["score_tail_return"]
        + 0.15 * ranking["score_drawdown"]
        + 0.10 * ranking["score_fill"]
        + 0.10 * ranking["score_overlap"]
        + 0.05 * ranking["score_cash"]
        + 0.05 * ranking["score_stability"]
    )

    ordered_cols = [
        "scenario",
        "description",
        "max_turnover",
        "buffer_multiplier",
        "composite_score",
        "mean_annual_return",
        "min_annual_return",
        "mean_sharpe",
        "mean_max_drawdown",
        "worst_max_drawdown",
        "mean_fill_ratio",
        "mean_target_overlap",
        "mean_cash_weight",
        "annual_return_std",
        "mean_cost",
        "mean_actual_stock_count",
    ]
    return ranking[ordered_cols].sort_values("composite_score", ascending=False).reset_index(drop=True)


def run_execution_turnover_revaluation(
    max_turnover_list,
    buffer_multiplier_list,
    capital_list,
    participation_limit_list,
    fixed_cost_bps=10,
    impact_coef_bps=25,
    top_n=100,
):
    """
    先生成扩展换手控制目标持仓，再用成交约束口径重估参数。

    这里不依赖旧的换手控制输出文件，避免覆盖前期归档结果。
    """
    target_df, _, _, _ = turnover_core.run_turnover_control_experiment(
        max_turnover_list=max_turnover_list,
        buffer_multiplier_list=buffer_multiplier_list,
        cost_bps_list=[0],
        top_n=top_n,
    )

    portfolio_df = exec_core.base.load_portfolio_returns()
    price_df = exec_core.base.load_price_data()
    weekly_returns_df = exec_core.base.compute_weekly_returns(price_df, portfolio_df)
    wanted_codes = set()
    for codes in target_df["selected_codes"]:
        wanted_codes.update(codes)
    price_feature_df = exec_core.load_price_features(
        wanted_dates=target_df["date"].unique(),
        wanted_codes=wanted_codes,
    )

    detail_frames = []
    for capital in capital_list:
        for participation_limit in participation_limit_list:
            detail_df, _ = exec_core.simulate_execution_capacity(
                target_df,
                weekly_returns_df,
                price_feature_df,
                capital=capital,
                participation_limit=participation_limit,
                fixed_cost_bps=fixed_cost_bps,
                impact_coef_bps=impact_coef_bps,
            )
            detail_frames.append(detail_df)

    detail_df = pd.concat(detail_frames, ignore_index=True)
    summary_df, annual_df = exec_core.summarize_execution(detail_df)
    ranking_df = build_scenario_ranking(summary_df, annual_df, target_df)
    return target_df, detail_df, summary_df, ranking_df, annual_df


def _format_percent(value):
    if pd.isna(value):
        return ""
    return f"{value * 100:.1f}%"


def _format_number(value):
    if pd.isna(value):
        return ""
    return f"{value:.2f}"


def plot_execution_turnover_revaluation(summary_df, ranking_df):
    os.makedirs(IMAGE_DIR, exist_ok=True)
    if summary_df.empty or ranking_df.empty:
        return

    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    top_scenarios = ranking_df.head(8)["scenario"].tolist()
    plot_df = summary_df[summary_df["scenario"].isin(top_scenarios)].copy()

    fig = plt.figure(figsize=(18, 14))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 1.2], hspace=0.35, wspace=0.25)

    ax_bar = fig.add_subplot(gs[0, 0])
    bar_df = ranking_df.head(10).iloc[::-1]
    ax_bar.barh(bar_df["scenario"], bar_df["composite_score"], color="#3A6F7F")
    ax_bar.set_title("成交约束综合评分 Top 10")
    ax_bar.set_xlabel("综合评分")
    ax_bar.grid(axis="x", alpha=0.25)

    ax_line = fig.add_subplot(gs[0, 1])
    for scenario, group in plot_df.groupby("scenario", sort=False):
        curve = (
            group[group["participation_limit"] == 0.10]
            .sort_values("capital")
            .copy()
        )
        if curve.empty:
            continue
        ax_line.plot(
            curve["capital"] / 100_000_000,
            curve["annual_return"] * 100,
            marker="o",
            linewidth=1.8,
            label=scenario,
        )
    ax_line.set_title("Top 参数在 10% ADV 上限下的容量曲线")
    ax_line.set_xlabel("资金规模（亿元）")
    ax_line.set_ylabel("净年化收益 (%)")
    ax_line.grid(True, alpha=0.25)
    ax_line.legend(fontsize=8, ncol=2)

    ax_table = fig.add_subplot(gs[1, :])
    table_source = ranking_df.head(12).copy()
    table_df = table_source[
        [
            "scenario",
            "composite_score",
            "mean_annual_return",
            "min_annual_return",
            "mean_max_drawdown",
            "mean_fill_ratio",
            "mean_target_overlap",
            "mean_cash_weight",
            "annual_return_std",
        ]
    ].copy()
    table_df.columns = [
        "场景",
        "综合评分",
        "平均净年化",
        "最低净年化",
        "平均回撤",
        "成交完成率",
        "目标兑现",
        "平均现金",
        "年度波动",
    ]
    table_df["综合评分"] = table_df["综合评分"].map(_format_number)
    for col in ["平均净年化", "最低净年化", "平均回撤", "成交完成率", "目标兑现", "平均现金", "年度波动"]:
        table_df[col] = table_df[col].map(_format_percent)

    ax_table.axis("off")
    ax_table.set_title("成交约束下换手参数重估排名", fontsize=15, fontweight="bold", pad=12)
    table = ax_table.table(
        cellText=table_df.values,
        colLabels=table_df.columns,
        cellLoc="center",
        colLoc="center",
        loc="center",
        bbox=[0.0, 0.0, 1.0, 0.92],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8.8)
    table.scale(1.0, 1.22)

    raw_df = table_source.reset_index(drop=True)
    col_index = {name: idx for idx, name in enumerate(table_df.columns)}
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#D0D0D0")
        if row == 0:
            cell.set_facecolor("#2E4057")
            cell.set_text_props(color="white", weight="bold")
            continue
        raw_row = raw_df.iloc[row - 1]
        if col == col_index["场景"]:
            cell.set_facecolor("#F5F5F5")
            cell.set_text_props(weight="bold")
        elif col == col_index["综合评分"]:
            if raw_row["composite_score"] >= 0.75:
                cell.set_facecolor("#DDEFE3")
            elif raw_row["composite_score"] < 0.45:
                cell.set_facecolor("#FBE5E1")
        elif col == col_index["最低净年化"]:
            if raw_row["min_annual_return"] >= 0.20:
                cell.set_facecolor("#DDEFE3")
            elif raw_row["min_annual_return"] < 0.15:
                cell.set_facecolor("#FBE5E1")

    fig.tight_layout()
    fig.savefig(PLOT_OUTPUT_PATH, dpi=200, bbox_inches="tight")
    plt.close(fig)
