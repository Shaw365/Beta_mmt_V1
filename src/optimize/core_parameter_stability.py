import ast
import contextlib
import io
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

from src.analysis import factor_weight_experiment as base
from src.optimize import execution_capacity_experiment as exec_core
from src.optimize import turnover_control_experiment as turnover_core
from src.strategies.factor_timing_strategy_v3 import FactorTimingStrategy


OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output", "cne6")
DATA_DIR = os.path.join(OUTPUT_DIR, "data")
IMAGE_DIR = os.path.join(OUTPUT_DIR, "images", "optimize")

SUFFIX = "l20_s5_b2_e1_n100"

TARGET_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"core_parameter_stability_targets_{SUFFIX}.csv"
)
DETAIL_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"core_parameter_stability_execution_detail_{SUFFIX}.csv"
)
SUMMARY_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"core_parameter_stability_execution_summary_{SUFFIX}.csv"
)
RANKING_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"core_parameter_stability_ranking_{SUFFIX}.csv"
)
ANNUAL_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"core_parameter_stability_annual_{SUFFIX}.csv"
)
WF_DETAIL_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"core_parameter_stability_walk_forward_detail_{SUFFIX}.csv"
)
WF_SUMMARY_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"core_parameter_stability_walk_forward_summary_{SUFFIX}.csv"
)
WF_ANNUAL_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"core_parameter_stability_walk_forward_annual_{SUFFIX}.csv"
)
WF_FOLD_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"core_parameter_stability_walk_forward_folds_{SUFFIX}.csv"
)
WF_TRAIN_SCORE_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"core_parameter_stability_walk_forward_train_scores_{SUFFIX}.csv"
)
PLOT_OUTPUT_PATH = os.path.join(
    IMAGE_DIR, f"core_parameter_stability_{SUFFIX}.png"
)


DEFAULT_SCENARIO = "p_l20_s5_b2_e1_n100_tc50_buf2"
MAX_TURNOVER = 0.50
BUFFER_MULTIPLIER = 2.0


def _parse_selected_codes(value):
    if isinstance(value, list):
        return value
    if pd.isna(value):
        return []
    return list(ast.literal_eval(value))


def _normalize(series, higher_is_better=True):
    values = series.astype(float)
    if not higher_is_better:
        values = -values
    min_value = values.min()
    max_value = values.max()
    if pd.isna(min_value) or pd.isna(max_value) or min_value == max_value:
        return pd.Series(0.5, index=series.index)
    return (values - min_value) / (max_value - min_value)


def _scenario_name(long_prd, short_prd, channel_bins, extreme_value, top_n):
    return f"p_l{long_prd}_s{short_prd}_b{channel_bins}_e{extreme_value}_n{top_n}_tc50_buf2"


def _load_cumulative_returns():
    path = os.path.join(DATA_DIR, "cumulative_returns_cne6.csv")
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index()


def _build_optimal_vectors(cumulative_returns_df, params):
    strategy = FactorTimingStrategy(
        long_prd=params["long_prd"],
        short_prd=params["short_prd"],
        channel_bins=params["channel_bins"],
        extreme_value=params["extreme_value"],
        top_n=params["top_n"],
        turnover_control=True,
        max_turnover=MAX_TURNOVER,
        turnover_buffer_multiplier=BUFFER_MULTIPLIER,
    )
    # The strategy methods print progress for interactive runs; suppress it inside grids.
    with contextlib.redirect_stdout(io.StringIO()):
        pst_df = strategy.calc_pst(cumulative_returns_df)
        optimal_df = strategy.generate_optimal_vector(pst_df)
    return optimal_df


def build_parameter_targets(
    long_prd_list,
    short_prd_list,
    channel_bins_list,
    top_n_list,
    extreme_value_list=(1,),
):
    portfolio_df = base.load_portfolio_returns()
    price_df = base.load_price_data()
    weekly_returns_df = base.compute_weekly_returns(price_df, portfolio_df)
    suspend_lookup = base.build_suspend_lookup(price_df)
    cumulative_returns_df = _load_cumulative_returns()
    factor_cols = [col for col in cumulative_returns_df.columns if col != "date"]
    exposure_df = base.load_signal_date_exposures(portfolio_df["signal_date"].unique(), factor_cols)
    exposure_by_date = exposure_df.groupby("date", sort=False)

    frames = []
    for long_prd in long_prd_list:
        for short_prd in short_prd_list:
            for channel_bins in channel_bins_list:
                for extreme_value in extreme_value_list:
                    params_without_top_n = {
                        "long_prd": long_prd,
                        "short_prd": short_prd,
                        "channel_bins": channel_bins,
                        "extreme_value": extreme_value,
                    }
                    optimal_df = _build_optimal_vectors(
                        cumulative_returns_df,
                        {**params_without_top_n, "top_n": max(top_n_list)},
                    )

                    for top_n in top_n_list:
                        params = {**params_without_top_n, "top_n": top_n}
                        max_candidate_pool_size = max(
                            top_n,
                            int(np.ceil(top_n * BUFFER_MULTIPLIER)),
                        )
                        contexts = turnover_core.build_period_contexts(
                            portfolio_df,
                            optimal_df,
                            exposure_by_date,
                            suspend_lookup,
                            factor_cols,
                            max_candidate_pool_size=max_candidate_pool_size,
                        )
                        returns_df = turnover_core.run_turnover_control_scenario(
                            MAX_TURNOVER,
                            BUFFER_MULTIPLIER,
                            contexts,
                            weekly_returns_df,
                            top_n=top_n,
                        )
                        scenario = _scenario_name(**params)
                        returns_df["scenario"] = scenario
                        returns_df["description"] = (
                            f"L={long_prd}, S={short_prd}, bins={channel_bins}, "
                            f"E={extreme_value}, top_n={top_n}, tc50_buf2"
                        )
                        for key, value in params.items():
                            returns_df[key] = value
                        frames.append(returns_df)

    target_df = pd.concat(frames, ignore_index=True)
    return target_df


def _scenario_param_map(target_df):
    cols = [
        "scenario",
        "description",
        "long_prd",
        "short_prd",
        "channel_bins",
        "extreme_value",
        "top_n",
        "max_turnover",
        "buffer_multiplier",
    ]
    return target_df[cols].drop_duplicates("scenario")


def build_parameter_ranking(summary_df, annual_df, target_df):
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
        )
    )
    annual_stability = (
        annual_df.groupby("scenario")["annual_return"]
        .std()
        .rename("annual_return_std")
        .reset_index()
    )
    ranking = grouped.merge(annual_stability, on="scenario", how="left")
    ranking = ranking.merge(_scenario_param_map(target_df), on="scenario", how="left")

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

    cols = [
        "scenario",
        "description",
        "long_prd",
        "short_prd",
        "channel_bins",
        "extreme_value",
        "top_n",
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
    ]
    return ranking[cols].sort_values("composite_score", ascending=False).reset_index(drop=True)


def simulate_targets(
    target_df,
    capital_list,
    participation_limit_list,
    fixed_cost_bps=10,
    impact_coef_bps=25,
):
    portfolio_df = base.load_portfolio_returns()
    price_df = base.load_price_data()
    weekly_returns_df = base.compute_weekly_returns(price_df, portfolio_df)
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
    return detail_df, summary_df, annual_df


def build_annual_folds(dates, train_years=3, test_years=1):
    years = sorted(pd.Series(pd.to_datetime(dates)).dt.year.unique())
    folds = []
    for train_start_year in years:
        train_end_year = train_start_year + train_years
        test_end_year = train_end_year + test_years
        if train_end_year > max(years):
            break
        train_years_list = [year for year in years if train_start_year <= year < train_end_year]
        test_years_list = [year for year in years if train_end_year <= year < test_end_year]
        if len(train_years_list) < train_years or not test_years_list:
            continue
        folds.append(
            {
                "fold": len(folds) + 1,
                "train_start_year": train_start_year,
                "train_end_year": train_end_year - 1,
                "test_start_year": train_end_year,
                "test_end_year": test_end_year - 1,
                "train_years": train_years_list,
                "test_years": test_years_list,
            }
        )
    return folds


def select_walk_forward(detail_df, target_df, train_years=3, test_years=1):
    folds = build_annual_folds(target_df["date"], train_years=train_years, test_years=test_years)
    train_score_frames = []
    fold_rows = []
    detail_df = detail_df.copy()
    detail_df["year"] = detail_df["date"].dt.year

    for fold in folds:
        train_detail = detail_df[detail_df["year"].isin(fold["train_years"])].copy()
        train_summary, train_annual = exec_core.summarize_execution(train_detail.drop(columns=["year"]))
        ranking = build_parameter_ranking(train_summary, train_annual, target_df)
        selected = ranking.iloc[0]

        fold_rows.append(
            {
                **{key: value for key, value in fold.items() if not key.endswith("years")},
                "selected_scenario": selected["scenario"],
                "selected_score": selected["composite_score"],
                "selected_mean_annual_return": selected["mean_annual_return"],
                "selected_min_annual_return": selected["min_annual_return"],
                "selected_mean_max_drawdown": selected["mean_max_drawdown"],
            }
        )

        scored = ranking.copy()
        scored.insert(0, "fold", fold["fold"])
        scored.insert(1, "train_start_year", fold["train_start_year"])
        scored.insert(2, "train_end_year", fold["train_end_year"])
        scored.insert(3, "test_start_year", fold["test_start_year"])
        scored["train_rank"] = np.arange(1, len(scored) + 1)
        train_score_frames.append(scored)

    fold_df = pd.DataFrame(fold_rows)
    train_score_df = pd.concat(train_score_frames, ignore_index=True) if train_score_frames else pd.DataFrame()
    return fold_df, train_score_df


def build_walk_forward_targets(target_df, fold_df, benchmark_scenarios):
    if fold_df.empty:
        return pd.DataFrame(columns=target_df.columns)

    first_year = int(fold_df["test_start_year"].min())
    last_year = int(fold_df["test_end_year"].max())
    frames = []
    benchmark = target_df[
        target_df["date"].dt.year.between(first_year, last_year)
        & target_df["scenario"].isin(benchmark_scenarios)
    ].copy()
    benchmark["selected_source_scenario"] = benchmark["scenario"]
    frames.append(benchmark)

    for row in fold_df.itertuples(index=False):
        selected = target_df[
            target_df["scenario"].eq(row.selected_scenario)
            & target_df["date"].dt.year.between(int(row.test_start_year), int(row.test_end_year))
        ].copy()
        selected["selected_source_scenario"] = selected["scenario"]
        selected["scenario"] = "walk_forward_selected"
        selected["description"] = "walk-forward selected core parameters"
        selected["fold"] = row.fold
        frames.append(selected)

    return pd.concat(frames, ignore_index=True).sort_values(["scenario", "date"]).reset_index(drop=True)


def _format_percent(value):
    if pd.isna(value):
        return ""
    return f"{value * 100:.1f}%"


def plot_core_parameter_stability(ranking_df, summary_df, wf_summary_df, wf_fold_df):
    os.makedirs(IMAGE_DIR, exist_ok=True)
    if ranking_df.empty:
        return

    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    fig = plt.figure(figsize=(18, 14))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 1.15], hspace=0.35, wspace=0.25)

    ax_bar = fig.add_subplot(gs[0, 0])
    top_df = ranking_df.head(12).iloc[::-1]
    ax_bar.barh(top_df["scenario"], top_df["composite_score"], color="#3A6F7F")
    ax_bar.set_title("核心参数全样本综合评分 Top 12")
    ax_bar.set_xlabel("综合评分")
    ax_bar.grid(axis="x", alpha=0.25)

    ax_heat = fig.add_subplot(gs[0, 1])
    heat_df = summary_df[
        summary_df["participation_limit"].eq(0.10)
        & summary_df["capital"].eq(500_000_000)
    ].merge(
        ranking_df[["scenario", "long_prd", "short_prd", "channel_bins", "top_n"]],
        on="scenario",
        how="left",
    )
    heat_df = heat_df[
        heat_df["channel_bins"].eq(2)
        & heat_df["top_n"].eq(100)
    ]
    pivot = heat_df.pivot_table(
        index="long_prd",
        columns="short_prd",
        values="annual_return",
        aggfunc="mean",
    ).sort_index()
    if not pivot.empty:
        image = ax_heat.imshow(pivot.values * 100, cmap="RdYlGn", aspect="auto")
        ax_heat.set_xticks(np.arange(len(pivot.columns)))
        ax_heat.set_xticklabels([str(col) for col in pivot.columns])
        ax_heat.set_yticks(np.arange(len(pivot.index)))
        ax_heat.set_yticklabels([str(idx) for idx in pivot.index])
        for i in range(len(pivot.index)):
            for j in range(len(pivot.columns)):
                value = pivot.iloc[i, j]
                ax_heat.text(j, i, f"{value * 100:.1f}%", ha="center", va="center", fontsize=9)
        fig.colorbar(image, ax=ax_heat, fraction=0.046, pad=0.04)
    ax_heat.set_title("固定 bins=2/top_n=100：5亿、10% ADV 净年化")
    ax_heat.set_xlabel("short_prd")
    ax_heat.set_ylabel("long_prd")

    ax_table = fig.add_subplot(gs[1, :])
    table_source = wf_summary_df[
        wf_summary_df["participation_limit"].eq(0.10)
        & wf_summary_df["scenario"].isin([DEFAULT_SCENARIO, "walk_forward_selected"])
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
        ]
    ].copy()
    table_df.columns = ["场景", "资金", "样本外净年化", "最大回撤", "夏普", "成交完成", "目标兑现", "现金"]
    for col in ["样本外净年化", "最大回撤", "成交完成", "目标兑现", "现金"]:
        table_df[col] = table_df[col].map(_format_percent)
    table_df["夏普"] = table_df["夏普"].map(lambda value: f"{value:.2f}")
    selected_path = " / ".join(
        f"{int(row.test_start_year)}:{row.selected_scenario}"
        for row in wf_fold_df.itertuples(index=False)
    )
    ax_table.axis("off")
    ax_table.set_title(f"核心参数 walk-forward 样本外对比（选参路径：{selected_path}）", fontsize=14, fontweight="bold", pad=12)
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
