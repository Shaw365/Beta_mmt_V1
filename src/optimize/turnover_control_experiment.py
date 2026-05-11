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
from src.strategies.factor_timing_strategy_v3 import FactorTimingStrategy


OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output", "cne6")
DATA_DIR = os.path.join(OUTPUT_DIR, "data")
IMAGE_DIR = os.path.join(OUTPUT_DIR, "images", "optimize")

SUFFIX = "l20_s5_b2_e1_n100"

RETURNS_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"turnover_control_experiment_returns_{SUFFIX}.csv"
)
SUMMARY_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"turnover_control_experiment_summary_{SUFFIX}.csv"
)
COST_STRESS_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"turnover_control_experiment_cost_stress_{SUFFIX}.csv"
)
ANNUAL_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"turnover_control_experiment_annual_{SUFFIX}.csv"
)
PLOT_OUTPUT_PATH = os.path.join(
    IMAGE_DIR, f"turnover_control_experiment_{SUFFIX}.png"
)


def _max_drawdown(nav):
    return (nav / nav.cummax() - 1.0).min()


def _calculate_metrics(returns, dates, risk_free_rate=0.03):
    nav = (1.0 + returns).cumprod()
    cumulative_return = nav.iloc[-1] - 1.0
    years = (dates.max() - dates.min()).days / 365.25
    annual_return = (1.0 + cumulative_return) ** (1.0 / years) - 1.0 if years > 0 else np.nan
    annual_volatility = returns.std() * np.sqrt(52.0)
    sharpe_ratio = (
        (annual_return - risk_free_rate) / annual_volatility
        if annual_volatility and annual_volatility != 0
        else np.nan
    )
    return {
        "final_nav": nav.iloc[-1],
        "cumulative_return": cumulative_return,
        "annual_return": annual_return,
        "annual_volatility": annual_volatility,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown": _max_drawdown(nav),
        "win_rate": (returns > 0).mean(),
    }


def _calculate_turnover(prev_stocks, current_stocks):
    if len(prev_stocks) == 0 or len(current_stocks) == 0:
        return 0.0
    sold = set(prev_stocks) - set(current_stocks)
    return min(len(sold) / len(prev_stocks), 1.0)


def _format_buffer(buffer_multiplier):
    return f"{buffer_multiplier:g}".replace(".", "p")


def _scenario_name(max_turnover, buffer_multiplier):
    turnover_label = int(round(max_turnover * 100))
    return f"tc{turnover_label}_buf{_format_buffer(buffer_multiplier)}"


def _equal_weight_scores(candidate_df, optimal_vector, factor_cols):
    values = candidate_df.loc[:, factor_cols].astype(float).fillna(0.0).values
    target = optimal_vector[factor_cols].astype(float).values
    numerator = values @ target
    denominator = np.linalg.norm(values, axis=1) * np.linalg.norm(target)
    return np.divide(numerator, denominator, out=np.zeros(len(candidate_df)), where=denominator != 0)


def build_period_contexts(
    portfolio_df,
    optimal_df,
    exposure_by_date,
    suspend_lookup,
    factor_cols,
    max_candidate_pool_size,
):
    """为每个换仓周期预先计算相似度排名，供不同换手参数复用。"""
    contexts = []

    for row in portfolio_df.itertuples(index=False):
        if row.signal_date not in optimal_df.index:
            continue
        if row.signal_date not in exposure_by_date.groups:
            continue

        candidate_df = exposure_by_date.get_group(row.signal_date).copy()
        suspended_codes = suspend_lookup.get(row.date, set())
        if suspended_codes:
            candidate_df = candidate_df[~candidate_df["code"].isin(suspended_codes)]
        if candidate_df.empty:
            continue

        candidate_df["similarity"] = _equal_weight_scores(
            candidate_df,
            optimal_df.loc[row.signal_date],
            factor_cols,
        )
        candidate_df = candidate_df.sort_values("similarity", ascending=False).reset_index(drop=True)
        candidate_df["rank"] = np.arange(1, len(candidate_df) + 1)

        score_map = dict(zip(candidate_df["code"], candidate_df["similarity"]))
        rank_map = dict(zip(candidate_df["code"], candidate_df["rank"]))
        contexts.append(
            {
                "date": row.date,
                "signal_date": row.signal_date,
                "next_date": row.next_date,
                "baseline_codes": list(row.selected_codes),
                "suspended_codes": suspended_codes,
                "candidate_codes": candidate_df.head(max_candidate_pool_size)["code"].tolist(),
                "score_map": score_map,
                "rank_map": rank_map,
            }
        )

    return contexts


def _selected_quality(selected_codes, context):
    score_values = [context["score_map"].get(code, np.nan) for code in selected_codes]
    rank_values = [context["rank_map"].get(code, np.nan) for code in selected_codes]
    score_series = pd.Series(score_values, dtype="float64")
    rank_series = pd.Series(rank_values, dtype="float64")
    return {
        "avg_similarity": score_series.mean(),
        "median_similarity": score_series.median(),
        "avg_rank": rank_series.mean(),
        "missing_similarity_count": int(score_series.isna().sum()),
    }


def build_baseline_returns(portfolio_df, weekly_returns_df, contexts):
    """用原始持仓构造baseline，方便和换手控制版本放在同一张汇总表里。"""
    context_by_date = {context["date"]: context for context in contexts}
    prev_stocks = []
    records = []

    for row in portfolio_df.itertuples(index=False):
        if row.date not in weekly_returns_df.index or row.date not in context_by_date:
            continue
        selected_codes = list(row.selected_codes)
        stock_returns = weekly_returns_df.loc[row.date, selected_codes].dropna()
        if stock_returns.empty:
            continue

        turnover = _calculate_turnover(prev_stocks, selected_codes)
        quality = _selected_quality(selected_codes, context_by_date[row.date])
        records.append(
            {
                "scenario": "baseline",
                "description": "原始策略",
                "max_turnover": np.nan,
                "buffer_multiplier": np.nan,
                "date": row.date,
                "signal_date": row.signal_date,
                "next_date": row.next_date,
                "return": stock_returns.mean(),
                "num_stocks": len(selected_codes),
                "turnover": turnover,
                "baseline_overlap": 1.0,
                "retained_old_count": len(set(prev_stocks) & set(selected_codes)) if prev_stocks else 0,
                "retained_outside_candidate_count": 0,
                "selected_codes": selected_codes,
                **quality,
            }
        )
        prev_stocks = selected_codes

    return pd.DataFrame(records)


def run_turnover_control_scenario(
    max_turnover,
    buffer_multiplier,
    contexts,
    weekly_returns_df,
    top_n=100,
):
    """在一组换手控制参数下模拟组合收益。"""
    strategy = FactorTimingStrategy(
        top_n=top_n,
        turnover_control=True,
        max_turnover=max_turnover,
        turnover_buffer_multiplier=buffer_multiplier,
    )
    scenario = _scenario_name(max_turnover, buffer_multiplier)
    candidate_pool_size = strategy.get_turnover_candidate_pool_size()
    prev_stocks = []
    records = []

    for context in contexts:
        current_date = context["date"]
        if current_date not in weekly_returns_df.index:
            continue

        candidate_codes = context["candidate_codes"][:candidate_pool_size]
        selected_codes = strategy.apply_turnover_control(
            prev_stocks,
            candidate_codes,
            target_n=top_n,
            blocked_codes=context["suspended_codes"],
        )

        stock_returns = weekly_returns_df.loc[current_date, selected_codes].dropna()
        if stock_returns.empty:
            continue

        turnover = _calculate_turnover(prev_stocks, selected_codes)
        baseline_codes = set(context["baseline_codes"])
        selected_set = set(selected_codes)
        candidate_set = set(candidate_codes)
        old_set = set(prev_stocks)
        quality = _selected_quality(selected_codes, context)

        records.append(
            {
                "scenario": scenario,
                "description": f"max_turnover={max_turnover:.0%}, buffer={buffer_multiplier:g}x",
                "max_turnover": max_turnover,
                "buffer_multiplier": buffer_multiplier,
                "date": current_date,
                "signal_date": context["signal_date"],
                "next_date": context["next_date"],
                "return": stock_returns.mean(),
                "num_stocks": len(selected_codes),
                "turnover": turnover,
                "baseline_overlap": len(selected_set & baseline_codes) / len(selected_codes),
                "retained_old_count": len(old_set & selected_set) if prev_stocks else 0,
                "retained_outside_candidate_count": len((old_set & selected_set) - candidate_set),
                "selected_codes": selected_codes,
                **quality,
            }
        )
        prev_stocks = selected_codes

    return pd.DataFrame(records)


def build_cost_stress(returns_df, cost_bps_list, risk_free_rate=0.03):
    summary_rows = []
    annual_rows = []

    for scenario, group in returns_df.groupby("scenario", sort=False):
        group = group.sort_values("date").copy()
        gross_metrics = _calculate_metrics(group["return"], group["date"], risk_free_rate)

        for cost_bps in cost_bps_list:
            cost_rate = cost_bps / 10_000.0
            period_cost = group["turnover"] * cost_rate
            net_return = (1.0 - period_cost) * (1.0 + group["return"]) - 1.0
            net_metrics = _calculate_metrics(net_return, group["date"], risk_free_rate)
            summary_rows.append(
                {
                    "scenario": scenario,
                    "description": group["description"].iloc[0],
                    "max_turnover": group["max_turnover"].iloc[0],
                    "buffer_multiplier": group["buffer_multiplier"].iloc[0],
                    "cost_bps": cost_bps,
                    "periods": len(group),
                    "avg_turnover": group["turnover"].mean(),
                    "avg_baseline_overlap": group["baseline_overlap"].mean(),
                    "avg_similarity": group["avg_similarity"].mean(),
                    "avg_rank": group["avg_rank"].mean(),
                    "avg_retained_outside_candidate_count": group["retained_outside_candidate_count"].mean(),
                    "gross_final_nav": gross_metrics["final_nav"],
                    "gross_annual_return": gross_metrics["annual_return"],
                    "gross_sharpe_ratio": gross_metrics["sharpe_ratio"],
                    "gross_max_drawdown": gross_metrics["max_drawdown"],
                    "net_final_nav": net_metrics["final_nav"],
                    "net_annual_return": net_metrics["annual_return"],
                    "net_sharpe_ratio": net_metrics["sharpe_ratio"],
                    "net_max_drawdown": net_metrics["max_drawdown"],
                    "annual_return_drag": gross_metrics["annual_return"] - net_metrics["annual_return"],
                }
            )

            annual_source = group[["date", "return", "turnover"]].copy()
            annual_source["net_return"] = net_return
            annual_source["year"] = annual_source["date"].dt.year
            for year, year_group in annual_source.groupby("year"):
                annual_rows.append(
                    {
                        "scenario": scenario,
                        "cost_bps": cost_bps,
                        "year": year,
                        "weeks": len(year_group),
                        "annual_return": (1.0 + year_group["return"]).prod() - 1.0,
                        "net_annual_return": (1.0 + year_group["net_return"]).prod() - 1.0,
                        "avg_turnover": year_group["turnover"].mean(),
                        "win_rate": (year_group["net_return"] > 0).mean(),
                    }
                )

    cost_df = pd.DataFrame(summary_rows)
    annual_df = pd.DataFrame(annual_rows)
    return cost_df, annual_df


def build_compact_summary(cost_df, key_costs=(20, 50)):
    """整理成一行一个场景的摘要表，便于阅读和写报告。"""
    gross_cols = [
        "scenario",
        "description",
        "max_turnover",
        "buffer_multiplier",
        "periods",
        "avg_turnover",
        "avg_baseline_overlap",
        "avg_similarity",
        "avg_rank",
        "avg_retained_outside_candidate_count",
        "gross_final_nav",
        "gross_annual_return",
        "gross_sharpe_ratio",
        "gross_max_drawdown",
    ]
    summary_df = (
        cost_df[cost_df["cost_bps"] == 0][gross_cols]
        .copy()
        .sort_values("scenario")
        .reset_index(drop=True)
    )

    for cost_bps in key_costs:
        part = cost_df[cost_df["cost_bps"] == cost_bps][
            ["scenario", "net_final_nav", "net_annual_return", "net_sharpe_ratio", "net_max_drawdown"]
        ].copy()
        part = part.rename(
            columns={
                "net_final_nav": f"net_final_nav_{cost_bps}bp",
                "net_annual_return": f"net_annual_return_{cost_bps}bp",
                "net_sharpe_ratio": f"net_sharpe_ratio_{cost_bps}bp",
                "net_max_drawdown": f"net_max_drawdown_{cost_bps}bp",
            }
        )
        summary_df = summary_df.merge(part, on="scenario", how="left")

    baseline = summary_df[summary_df["scenario"] == "baseline"]
    if not baseline.empty:
        baseline_row = baseline.iloc[0]
        summary_df["turnover_reduction_vs_baseline"] = baseline_row["avg_turnover"] - summary_df["avg_turnover"]
        summary_df["gross_annual_return_diff_vs_baseline"] = (
            summary_df["gross_annual_return"] - baseline_row["gross_annual_return"]
        )
        for cost_bps in key_costs:
            col = f"net_annual_return_{cost_bps}bp"
            summary_df[f"{col}_diff_vs_baseline"] = summary_df[col] - baseline_row[col]

    sort_col = "net_annual_return_10bp" if "net_annual_return_10bp" in summary_df.columns else "gross_annual_return"
    return summary_df.sort_values(sort_col, ascending=False).reset_index(drop=True)


def run_turnover_control_experiment(
    max_turnover_list,
    buffer_multiplier_list,
    cost_bps_list,
    top_n=100,
):
    portfolio_df = base.load_portfolio_returns()
    optimal_df, factor_cols = base.load_optimal_vectors()
    price_df = base.load_price_data()
    weekly_returns_df = base.compute_weekly_returns(price_df, portfolio_df)
    suspend_lookup = base.build_suspend_lookup(price_df)
    exposure_df = base.load_signal_date_exposures(portfolio_df["signal_date"].unique(), factor_cols)
    exposure_by_date = exposure_df.groupby("date", sort=False)

    max_buffer = max(buffer_multiplier_list)
    max_candidate_pool_size = max(top_n, int(np.ceil(top_n * max_buffer)))
    contexts = build_period_contexts(
        portfolio_df,
        optimal_df,
        exposure_by_date,
        suspend_lookup,
        factor_cols,
        max_candidate_pool_size=max_candidate_pool_size,
    )

    returns_list = [build_baseline_returns(portfolio_df, weekly_returns_df, contexts)]
    for max_turnover in max_turnover_list:
        for buffer_multiplier in buffer_multiplier_list:
            returns_list.append(
                run_turnover_control_scenario(
                    max_turnover,
                    buffer_multiplier,
                    contexts,
                    weekly_returns_df,
                    top_n=top_n,
                )
            )

    returns_df = pd.concat(returns_list, ignore_index=True)
    cost_df, annual_df = build_cost_stress(returns_df, cost_bps_list)
    summary_df = build_compact_summary(cost_df, key_costs=(5, 10, 20, 50, 100))
    return returns_df, summary_df, cost_df, annual_df


def _format_percent(value):
    if pd.isna(value):
        return ""
    return f"{value * 100:.1f}%"


def _format_number(value):
    if pd.isna(value):
        return ""
    return f"{value:.2f}"


def plot_turnover_control_experiment(summary_df, cost_df):
    os.makedirs(IMAGE_DIR, exist_ok=True)
    if summary_df.empty:
        return

    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    experiment_df = summary_df[summary_df["scenario"] != "baseline"].copy()
    baseline = summary_df[summary_df["scenario"] == "baseline"]

    fig = plt.figure(figsize=(18, 13))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 1.15], hspace=0.35, wspace=0.25)

    ax_scatter = fig.add_subplot(gs[0, 0])
    if not baseline.empty:
        b = baseline.iloc[0]
        ax_scatter.scatter(
            b["avg_turnover"] * 100,
            b["net_annual_return_10bp"] * 100,
            s=180,
            marker="*",
            color="#D62728",
            label="baseline",
            zorder=4,
        )
    colors = {
        0.20: "#1f77b4",
        0.30: "#ff7f0e",
        0.40: "#2ca02c",
        0.50: "#d62728",
    }
    markers = {
        1.5: "o",
        2.0: "s",
        3.0: "^",
    }
    for max_turnover, group in experiment_df.groupby("max_turnover"):
        for buffer_multiplier, subgroup in group.groupby("buffer_multiplier"):
            ax_scatter.scatter(
                subgroup["avg_turnover"] * 100,
                subgroup["net_annual_return_10bp"] * 100,
                s=110,
                marker=markers.get(float(buffer_multiplier), "o"),
                color=colors.get(round(float(max_turnover), 2), "#666666"),
                alpha=0.78,
                edgecolors="white",
                linewidths=0.8,
            )
    ax_scatter.set_title("10bp净年化 vs 平均换手")
    ax_scatter.set_xlabel("平均单边换手率 (%)")
    ax_scatter.set_ylabel("10bp净年化收益 (%)")
    ax_scatter.grid(True, alpha=0.25)

    color_handles = [
        plt.Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            label=f"max {max_turnover:.0%}",
            markerfacecolor=color,
            markeredgecolor="white",
            markersize=9,
        )
        for max_turnover, color in colors.items()
    ]
    marker_handles = [
        plt.Line2D(
            [0],
            [0],
            marker=marker,
            color="#555555",
            linestyle="None",
            label=f"buffer {buffer_multiplier:g}x",
            markersize=8,
        )
        for buffer_multiplier, marker in markers.items()
    ]
    baseline_handle = plt.Line2D(
        [0],
        [0],
        marker="*",
        color="w",
        label="baseline",
        markerfacecolor="#D62728",
        markeredgecolor="#D62728",
        markersize=14,
    )
    legend1 = ax_scatter.legend(
        handles=[baseline_handle] + color_handles,
        loc="upper left",
        fontsize=9,
        title="换手上限",
    )
    ax_scatter.add_artist(legend1)
    ax_scatter.legend(
        handles=marker_handles,
        loc="lower right",
        fontsize=9,
        title="缓冲倍数",
    )

    ax_heat = fig.add_subplot(gs[0, 1])
    heat_df = experiment_df.pivot(
        index="max_turnover",
        columns="buffer_multiplier",
        values="net_annual_return_10bp",
    ).sort_index(ascending=False)
    im = ax_heat.imshow(heat_df.values * 100, cmap="RdYlGn", aspect="auto")
    ax_heat.set_title("10bp净年化收益热力图")
    ax_heat.set_xlabel("候选池缓冲倍数")
    ax_heat.set_ylabel("单期最大换手")
    ax_heat.set_xticks(range(len(heat_df.columns)))
    ax_heat.set_xticklabels([f"{value:g}x" for value in heat_df.columns])
    ax_heat.set_yticks(range(len(heat_df.index)))
    ax_heat.set_yticklabels([f"{value:.0%}" for value in heat_df.index])
    for i in range(heat_df.shape[0]):
        for j in range(heat_df.shape[1]):
            ax_heat.text(j, i, f"{heat_df.values[i, j] * 100:.1f}%", ha="center", va="center", fontsize=9)
    fig.colorbar(im, ax=ax_heat, fraction=0.046, pad=0.04)

    ax_table = fig.add_subplot(gs[1, :])
    table_source = summary_df.head(10).copy()
    table_df = table_source[
        [
            "scenario",
            "avg_turnover",
            "turnover_reduction_vs_baseline",
            "gross_annual_return",
            "net_annual_return_5bp",
            "net_annual_return_10bp",
            "net_annual_return_20bp",
            "gross_max_drawdown",
            "avg_baseline_overlap",
            "avg_similarity",
        ]
    ].copy()
    table_df.columns = [
        "场景",
        "平均换手",
        "换手下降",
        "毛年化",
        "5bp净年化",
        "10bp净年化",
        "20bp净年化",
        "最大回撤",
        "与基准持仓重合",
        "平均相似度",
    ]
    for col in ["平均换手", "换手下降", "毛年化", "5bp净年化", "10bp净年化", "20bp净年化", "最大回撤", "与基准持仓重合"]:
        table_df[col] = table_df[col].map(_format_percent)
    table_df["平均相似度"] = table_df["平均相似度"].map(_format_number)

    ax_table.axis("off")
    ax_table.set_title("换手控制实验摘要（按10bp净年化排序）", fontsize=15, fontweight="bold", pad=12)
    table = ax_table.table(
        cellText=table_df.values,
        colLabels=table_df.columns,
        cellLoc="center",
        colLoc="center",
        loc="center",
        bbox=[0.0, 0.0, 1.0, 0.92],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1.0, 1.25)

    raw_df = table_source.reset_index(drop=True)
    col_index = {name: idx for idx, name in enumerate(table_df.columns)}
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#D0D0D0")
        if row == 0:
            cell.set_facecolor("#2E4057")
            cell.set_text_props(color="white", weight="bold")
            continue

        raw_row = raw_df.iloc[row - 1]
        scenario_name = raw_row["scenario"]
        if scenario_name == "baseline":
            cell.set_text_props(weight="bold")

        if col == col_index["场景"]:
            cell.set_facecolor("#F5F5F5")
            cell.set_text_props(weight="bold")
        elif col in [col_index["毛年化"], col_index["5bp净年化"], col_index["10bp净年化"]]:
            metric_name = {
                col_index["毛年化"]: "gross_annual_return",
                col_index["5bp净年化"]: "net_annual_return_5bp",
                col_index["10bp净年化"]: "net_annual_return_10bp",
            }[col]
            value = raw_row[metric_name]
            if value >= 0.30:
                cell.set_facecolor("#DDEFE3")
            elif value >= 0.25:
                cell.set_facecolor("#EEF7E8")
            elif value >= 0.20:
                cell.set_facecolor("#FFF6D8")
            else:
                cell.set_facecolor("#FBE5E1")

    fig.tight_layout()
    fig.savefig(PLOT_OUTPUT_PATH, dpi=200, bbox_inches="tight")
    plt.close(fig)
