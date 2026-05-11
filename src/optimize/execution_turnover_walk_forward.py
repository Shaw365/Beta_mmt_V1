import ast
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
from src.optimize import execution_turnover_revaluation as reval_core


OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output", "cne6")
DATA_DIR = os.path.join(OUTPUT_DIR, "data")
IMAGE_DIR = os.path.join(OUTPUT_DIR, "images", "optimize")

SUFFIX = "l20_s5_b2_e1_n100"

DETAIL_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"execution_turnover_walk_forward_detail_{SUFFIX}.csv"
)
SUMMARY_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"execution_turnover_walk_forward_summary_{SUFFIX}.csv"
)
ANNUAL_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"execution_turnover_walk_forward_annual_{SUFFIX}.csv"
)
FOLD_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"execution_turnover_walk_forward_folds_{SUFFIX}.csv"
)
TRAIN_SCORE_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"execution_turnover_walk_forward_train_scores_{SUFFIX}.csv"
)
PLOT_OUTPUT_PATH = os.path.join(
    IMAGE_DIR, f"execution_turnover_walk_forward_{SUFFIX}.png"
)


def _parse_selected_codes(value):
    if isinstance(value, list):
        return value
    if pd.isna(value):
        return []
    parsed = ast.literal_eval(value)
    return list(parsed)


def load_revaluation_outputs():
    target_df = pd.read_csv(reval_core.TARGET_RETURNS_OUTPUT_PATH)
    detail_df = pd.read_csv(reval_core.DETAIL_OUTPUT_PATH, parse_dates=["date", "signal_date", "next_date"])
    target_df["date"] = pd.to_datetime(target_df["date"])
    target_df["signal_date"] = pd.to_datetime(target_df["signal_date"])
    target_df["next_date"] = pd.to_datetime(target_df["next_date"])
    target_df["selected_codes"] = target_df["selected_codes"].map(_parse_selected_codes)
    return target_df, detail_df


def build_annual_folds(dates, train_years=3, test_years=1):
    years = sorted(pd.Series(pd.to_datetime(dates)).dt.year.unique())
    folds = []
    for train_start_year in years:
        train_end_year = train_start_year + train_years
        test_end_year = train_end_year + test_years
        if train_end_year > max(years):
            break
        train_mask_years = [year for year in years if train_start_year <= year < train_end_year]
        test_mask_years = [year for year in years if train_end_year <= year < test_end_year]
        if len(train_mask_years) < train_years or not test_mask_years:
            continue
        folds.append(
            {
                "fold": len(folds) + 1,
                "train_start_year": train_start_year,
                "train_end_year": train_end_year - 1,
                "test_start_year": train_end_year,
                "test_end_year": test_end_year - 1,
                "train_years": train_mask_years,
                "test_years": test_mask_years,
            }
        )
    return folds


def _candidate_scenarios(target_df, candidate_scenarios):
    if candidate_scenarios is not None:
        return list(candidate_scenarios)
    return sorted(
        scenario
        for scenario in target_df["scenario"].dropna().unique()
        if scenario != "baseline"
    )


def _select_by_train_window(detail_df, target_df, folds, candidate_scenarios):
    fold_rows = []
    score_frames = []
    detail_df = detail_df.copy()
    detail_df["year"] = detail_df["date"].dt.year

    for fold in folds:
        train_detail = detail_df[
            detail_df["scenario"].isin(candidate_scenarios)
            & detail_df["year"].isin(fold["train_years"])
        ].copy()
        train_summary, train_annual = exec_core.summarize_execution(train_detail)
        train_ranking = reval_core.build_scenario_ranking(train_summary, train_annual, target_df)
        selected = train_ranking.iloc[0]

        fold_rows.append(
            {
                **{key: value for key, value in fold.items() if not key.endswith("years")},
                "selected_scenario": selected["scenario"],
                "selected_score": selected["composite_score"],
                "selected_mean_annual_return": selected["mean_annual_return"],
                "selected_min_annual_return": selected["min_annual_return"],
                "selected_mean_max_drawdown": selected["mean_max_drawdown"],
                "selected_mean_fill_ratio": selected["mean_fill_ratio"],
                "selected_mean_target_overlap": selected["mean_target_overlap"],
                "selected_mean_cash_weight": selected["mean_cash_weight"],
            }
        )

        scored = train_ranking.copy()
        scored.insert(0, "fold", fold["fold"])
        scored.insert(1, "train_start_year", fold["train_start_year"])
        scored.insert(2, "train_end_year", fold["train_end_year"])
        scored.insert(3, "test_start_year", fold["test_start_year"])
        scored.insert(4, "test_end_year", fold["test_end_year"])
        scored["train_rank"] = np.arange(1, len(scored) + 1)
        score_frames.append(scored)

    fold_df = pd.DataFrame(fold_rows)
    score_df = pd.concat(score_frames, ignore_index=True) if score_frames else pd.DataFrame()
    return fold_df, score_df


def _build_oos_targets(target_df, fold_df, benchmark_scenarios):
    if fold_df.empty:
        return pd.DataFrame(columns=target_df.columns)

    first_test_year = int(fold_df["test_start_year"].min())
    last_test_year = int(fold_df["test_end_year"].max())
    oos_mask = target_df["date"].dt.year.between(first_test_year, last_test_year)
    frames = []

    benchmark = target_df[oos_mask & target_df["scenario"].isin(benchmark_scenarios)].copy()
    benchmark["fold"] = benchmark["date"].dt.year.map(
        {
            year: row.fold
            for row in fold_df.itertuples(index=False)
            for year in range(int(row.test_start_year), int(row.test_end_year) + 1)
        }
    )
    benchmark["selected_source_scenario"] = benchmark["scenario"]
    frames.append(benchmark)

    for row in fold_df.itertuples(index=False):
        test_years = range(int(row.test_start_year), int(row.test_end_year) + 1)
        selected = target_df[
            target_df["scenario"].eq(row.selected_scenario)
            & target_df["date"].dt.year.isin(test_years)
        ].copy()
        selected["selected_source_scenario"] = selected["scenario"]
        selected["scenario"] = "walk_forward_selected"
        selected["description"] = "walk-forward selected turnover parameter"
        selected["fold"] = row.fold
        frames.append(selected)

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(["scenario", "date"]).reset_index(drop=True)
    return combined


def _add_fold_metadata(detail_df, target_df):
    metadata = target_df[["scenario", "date", "fold", "selected_source_scenario"]].drop_duplicates()
    result = detail_df.merge(metadata, on=["scenario", "date"], how="left")
    return result


def _summarize_by_fold(detail_df):
    frames = []
    annual_frames = []
    for fold, group in detail_df.groupby("fold", sort=True):
        summary, annual = exec_core.summarize_execution(group.drop(columns=["fold", "selected_source_scenario"]))
        summary.insert(0, "fold", int(fold))
        summary.insert(1, "test_year", int(group["date"].dt.year.min()))
        annual.insert(0, "fold", int(fold))
        frames.append(summary)
        annual_frames.append(annual)
    summary_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    annual_df = pd.concat(annual_frames, ignore_index=True) if annual_frames else pd.DataFrame()
    return summary_df, annual_df


def run_execution_turnover_walk_forward(
    train_years=3,
    test_years=1,
    candidate_scenarios=None,
    benchmark_scenarios=("baseline", "tc50_buf2", "tc50_buf3", "tc50_buf4"),
    capital_list=(100_000_000, 300_000_000, 500_000_000),
    participation_limit_list=(0.05, 0.10, 0.20),
    fixed_cost_bps=10,
    impact_coef_bps=25,
):
    target_df, full_detail_df = load_revaluation_outputs()
    candidate_scenarios = _candidate_scenarios(target_df, candidate_scenarios)
    folds = build_annual_folds(target_df["date"], train_years=train_years, test_years=test_years)
    fold_df, train_score_df = _select_by_train_window(
        full_detail_df,
        target_df,
        folds,
        candidate_scenarios,
    )
    oos_target_df = _build_oos_targets(target_df, fold_df, benchmark_scenarios)

    portfolio_df = exec_core.base.load_portfolio_returns()
    price_df = exec_core.base.load_price_data()
    weekly_returns_df = exec_core.base.compute_weekly_returns(price_df, portfolio_df)
    wanted_codes = set()
    for codes in oos_target_df["selected_codes"]:
        wanted_codes.update(codes)
    price_feature_df = exec_core.load_price_features(
        wanted_dates=oos_target_df["date"].unique(),
        wanted_codes=wanted_codes,
    )

    detail_frames = []
    for capital in capital_list:
        for participation_limit in participation_limit_list:
            detail_df, _ = exec_core.simulate_execution_capacity(
                oos_target_df,
                weekly_returns_df,
                price_feature_df,
                capital=capital,
                participation_limit=participation_limit,
                fixed_cost_bps=fixed_cost_bps,
                impact_coef_bps=impact_coef_bps,
            )
            detail_frames.append(detail_df)

    detail_df = pd.concat(detail_frames, ignore_index=True)
    detail_df = _add_fold_metadata(detail_df, oos_target_df)
    summary_df, annual_df = exec_core.summarize_execution(
        detail_df.drop(columns=["fold", "selected_source_scenario"])
    )
    fold_summary_df, fold_annual_df = _summarize_by_fold(detail_df)
    return detail_df, summary_df, annual_df, fold_df, train_score_df, fold_summary_df, fold_annual_df


def _format_percent(value):
    if pd.isna(value):
        return ""
    return f"{value * 100:.1f}%"


def plot_execution_turnover_walk_forward(summary_df, annual_df, fold_df, train_score_df):
    os.makedirs(IMAGE_DIR, exist_ok=True)
    if summary_df.empty:
        return

    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    scenarios = ["baseline", "tc50_buf2", "tc50_buf3", "tc50_buf4", "walk_forward_selected"]
    colors = {
        "baseline": "#A23B3B",
        "tc50_buf2": "#3A6F7F",
        "tc50_buf3": "#2E8B57",
        "tc50_buf4": "#7A5C99",
        "walk_forward_selected": "#D88C2D",
    }

    fig = plt.figure(figsize=(18, 13))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 1.05], hspace=0.32, wspace=0.25)

    ax_curve = fig.add_subplot(gs[0, 0])
    curve_df = summary_df[
        summary_df["scenario"].isin(scenarios)
        & summary_df["participation_limit"].eq(0.10)
    ].copy()
    for scenario in scenarios:
        group = curve_df[curve_df["scenario"].eq(scenario)].sort_values("capital")
        if group.empty:
            continue
        ax_curve.plot(
            group["capital"] / 100_000_000,
            group["annual_return"] * 100,
            marker="o",
            linewidth=2,
            label=scenario,
            color=colors.get(scenario),
        )
    ax_curve.set_title("样本外 10% ADV 容量曲线")
    ax_curve.set_xlabel("资金规模（亿元）")
    ax_curve.set_ylabel("净年化收益 (%)")
    ax_curve.grid(True, alpha=0.25)
    ax_curve.legend(fontsize=8)

    ax_annual = fig.add_subplot(gs[0, 1])
    annual_plot = annual_df[
        annual_df["scenario"].isin(scenarios)
        & annual_df["capital"].eq(500_000_000)
        & annual_df["participation_limit"].eq(0.10)
    ].copy()
    width = 0.15
    years = sorted(annual_plot["year"].unique())
    x = np.arange(len(years))
    for idx, scenario in enumerate(scenarios):
        group = annual_plot[annual_plot["scenario"].eq(scenario)].set_index("year")
        values = [group.loc[year, "annual_return"] * 100 if year in group.index else np.nan for year in years]
        ax_annual.bar(x + (idx - 2) * width, values, width=width, label=scenario, color=colors.get(scenario))
    ax_annual.set_xticks(x)
    ax_annual.set_xticklabels([str(year) for year in years])
    ax_annual.set_title("样本外年度收益：5亿、10% ADV")
    ax_annual.set_ylabel("年度收益 (%)")
    ax_annual.grid(axis="y", alpha=0.25)
    ax_annual.legend(fontsize=8)

    ax_table = fig.add_subplot(gs[1, :])
    table_source = summary_df[
        summary_df["scenario"].isin(scenarios)
        & summary_df["participation_limit"].eq(0.10)
    ].copy()
    table_source["capital_label"] = (table_source["capital"] / 100_000_000).map(lambda value: f"{value:.0f}亿")
    table_source = table_source.sort_values(["scenario", "capital"])
    table_df = table_source[
        [
            "scenario",
            "capital_label",
            "annual_return",
            "max_drawdown",
            "sharpe_ratio",
            "avg_fill_ratio",
            "avg_target_overlap_weight",
            "avg_cash_weight",
            "total_cost_arithmetic",
        ]
    ].copy()
    table_df.columns = [
        "场景",
        "资金",
        "净年化",
        "最大回撤",
        "夏普",
        "成交完成",
        "目标兑现",
        "现金",
        "累计成本",
    ]
    for col in ["净年化", "最大回撤", "成交完成", "目标兑现", "现金", "累计成本"]:
        table_df[col] = table_df[col].map(_format_percent)
    table_df["夏普"] = table_df["夏普"].map(lambda value: f"{value:.2f}")

    ax_table.axis("off")
    selected_text = " / ".join(
        f"{int(row.test_start_year)}:{row.selected_scenario}"
        for row in fold_df.itertuples(index=False)
    )
    ax_table.set_title(f"Walk-forward 样本外对比（选参路径：{selected_text}）", fontsize=14, fontweight="bold", pad=12)
    table = ax_table.table(
        cellText=table_df.values,
        colLabels=table_df.columns,
        cellLoc="center",
        colLoc="center",
        loc="center",
        bbox=[0.0, 0.0, 1.0, 0.92],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8.5)
    table.scale(1.0, 1.18)

    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#D0D0D0")
        if row == 0:
            cell.set_facecolor("#2E4057")
            cell.set_text_props(color="white", weight="bold")
        elif table_df.iloc[row - 1, 0] == "walk_forward_selected":
            cell.set_facecolor("#FFF3D6")

    fig.tight_layout()
    fig.savefig(PLOT_OUTPUT_PATH, dpi=200, bbox_inches="tight")
    plt.close(fig)
