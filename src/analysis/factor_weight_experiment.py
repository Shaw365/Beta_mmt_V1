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

OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output", "cne6")
DATA_DIR = os.path.join(OUTPUT_DIR, "data")
IMAGE_DIR = os.path.join(OUTPUT_DIR, "images", "optimize")

SUFFIX = "l20_s5_b2_e1_n100"

PORTFOLIO_RETURNS_PATH = os.path.join(DATA_DIR, f"portfolio_returns_{SUFFIX}.csv")
OPTIMAL_VECTORS_PATH = os.path.join(DATA_DIR, f"optimal_vectors_{SUFFIX}.csv")
FACTOR_EXPOSURE_PATH = os.path.join(DATA_DIR, "factor_exposure_cne6.csv")
PRICE_DATA_PATH = os.path.join(DATA_DIR, "price_data_cne6.csv")

FACTOR_WEIGHT_EXPERIMENT_RETURNS_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"factor_weight_experiment_returns_{SUFFIX}.csv"
)
FACTOR_WEIGHT_EXPERIMENT_SUMMARY_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"factor_weight_experiment_summary_{SUFFIX}.csv"
)
FACTOR_WEIGHT_EXPERIMENT_ANNUAL_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"factor_weight_experiment_annual_{SUFFIX}.csv"
)
FACTOR_WEIGHT_EXPERIMENT_WEIGHTS_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"factor_weight_experiment_weights_{SUFFIX}.csv"
)
FACTOR_WEIGHT_EXPERIMENT_PLOT_OUTPUT_PATH = os.path.join(
    IMAGE_DIR, f"factor_weight_experiment_{SUFFIX}.png"
)


def parse_selected_codes(value):
    """还原 portfolio_returns CSV 中保存的持仓股票列表。"""
    if isinstance(value, list):
        return value
    if pd.isna(value):
        return []
    return ast.literal_eval(value)


def load_portfolio_returns():
    """读取原始策略收益，用它的换仓日和信号日作为实验日历。"""
    df = pd.read_csv(PORTFOLIO_RETURNS_PATH)
    df["date"] = pd.to_datetime(df["date"])
    df["signal_date"] = pd.to_datetime(df["signal_date"])
    df["next_date"] = pd.to_datetime(df["next_date"])
    df["selected_codes"] = df["selected_codes"].apply(parse_selected_codes)
    return df


def load_optimal_vectors():
    """读取原始择时信号生成的理想风格向量。"""
    optimal_df = pd.read_csv(OPTIMAL_VECTORS_PATH)
    optimal_df["date"] = pd.to_datetime(optimal_df["date"])
    factor_cols = [col for col in optimal_df.columns if col != "date"]
    optimal_df = optimal_df.set_index("date").sort_index()
    return optimal_df, factor_cols


def load_price_data():
    """读取价格数据，用于复刻周度收益和停牌过滤。"""
    header_cols = pd.read_csv(PRICE_DATA_PATH, nrows=0).columns.tolist()
    usecols = ["date", "code", "pct_chg"]
    if "is_suspend" in header_cols:
        usecols.append("is_suspend")

    price_df = pd.read_csv(PRICE_DATA_PATH, usecols=usecols)
    price_df["date"] = pd.to_datetime(price_df["date"])
    return price_df


def compute_weekly_returns(price_df, portfolio_df):
    """按原策略口径预计算每个换仓周期内的股票收益。"""
    price_pivot = price_df.pivot(index="date", columns="code", values="pct_chg").sort_index()
    nav_df = (1.0 + price_pivot).cumprod()
    available_dates = nav_df.index

    records = []
    for row in portfolio_df.itertuples(index=False):
        start_pos = available_dates.get_indexer([row.date], method="nearest")[0]
        end_pos = available_dates.get_indexer([row.next_date], method="nearest")[0]
        if start_pos < 0 or end_pos < 0 or end_pos <= start_pos:
            continue

        weekly_return = nav_df.iloc[end_pos] / nav_df.iloc[start_pos] - 1.0
        weekly_return.name = row.date
        records.append(weekly_return)

    weekly_returns_df = pd.DataFrame(records)
    weekly_returns_df.index.name = "date"
    return weekly_returns_df


def build_suspend_lookup(price_df):
    """构建每个交易日停牌股票集合。"""
    if "is_suspend" not in price_df.columns:
        return {}
    return (
        price_df[price_df["is_suspend"] == 1]
        .groupby("date")["code"]
        .apply(set)
        .to_dict()
    )


def load_signal_date_exposures(signal_dates, factor_cols):
    """
    读取所有信号日的全市场因子暴露。

    因子暴露文件较大，这里只保留实验真正会用到的信号日。
    """
    wanted_dates = {pd.Timestamp(date).strftime("%Y-%m-%d") for date in signal_dates}
    usecols = ["date", "code"] + factor_cols

    records = []
    for chunk in pd.read_csv(FACTOR_EXPOSURE_PATH, usecols=usecols, chunksize=500_000):
        chunk = chunk[chunk["date"].isin(wanted_dates)]
        if not chunk.empty:
            records.append(chunk)

    if not records:
        raise RuntimeError("No factor exposure rows were found for experiment signal dates.")

    exposure_df = pd.concat(records, ignore_index=True)
    exposure_df["date"] = pd.to_datetime(exposure_df["date"])
    return exposure_df.sort_values(["date", "code"]).reset_index(drop=True)


def build_factor_weights(factor_cols, scenarios):
    """将脚本传入的场景配置展开成因子权重表。"""
    rows = []
    for scenario in scenarios:
        default_weight = scenario.get("default_weight", 1.0)
        overrides = scenario.get("weights", {})
        for factor in factor_cols:
            rows.append(
                {
                    "scenario": scenario["name"],
                    "description": scenario.get("description", ""),
                    "factor": factor,
                    "weight": overrides.get(factor, default_weight),
                }
            )
    return pd.DataFrame(rows)


def _weighted_cosine_scores(candidate_df, optimal_vector, factor_cols, weights):
    """计算带因子重要性权重的余弦相似度。"""
    weight_vector = np.array([weights.get(factor, 1.0) for factor in factor_cols], dtype=float)
    optimal = optimal_vector[factor_cols].astype(float).values
    active = (weight_vector > 0) & np.isfinite(optimal)

    if not active.any():
        return np.zeros(len(candidate_df))

    x = candidate_df.loc[:, np.array(factor_cols)[active]].astype(float).fillna(0.0).values
    y = optimal[active]
    w = weight_vector[active]

    numerator = (x * (w * y)).sum(axis=1)
    norm_x = np.sqrt((x * x * w).sum(axis=1))
    norm_y = np.sqrt((y * y * w).sum())
    denominator = norm_x * norm_y
    return np.divide(numerator, denominator, out=np.zeros(len(candidate_df)), where=denominator != 0)


def _calculate_turnover(prev_stocks, current_stocks):
    if len(prev_stocks) == 0 or len(current_stocks) == 0:
        return 0.0
    sold = set(prev_stocks) - set(current_stocks)
    return min(len(sold) / len(prev_stocks), 1.0)


def run_single_factor_weight_scenario(
    scenario,
    portfolio_df,
    optimal_df,
    exposure_by_date,
    weekly_returns_df,
    suspend_lookup,
    factor_cols,
    top_n=100,
):
    """在一个因子权重场景下重新选股并计算组合收益。"""
    weights = {
        factor: scenario.get("weights", {}).get(factor, scenario.get("default_weight", 1.0))
        for factor in factor_cols
    }
    active_factor_count = sum(weight > 0 for weight in weights.values())
    prev_stocks = []
    records = []

    for row in portfolio_df.itertuples(index=False):
        if row.signal_date not in optimal_df.index:
            continue
        if row.signal_date not in exposure_by_date.groups:
            continue
        if row.date not in weekly_returns_df.index:
            continue

        candidate_df = exposure_by_date.get_group(row.signal_date).copy()
        suspended_codes = suspend_lookup.get(row.date, set())
        if suspended_codes:
            candidate_df = candidate_df[~candidate_df["code"].isin(suspended_codes)]
        if candidate_df.empty:
            continue

        scores = _weighted_cosine_scores(
            candidate_df,
            optimal_df.loc[row.signal_date],
            factor_cols,
            weights,
        )
        candidate_df["similarity"] = scores
        selected_codes = candidate_df.nlargest(top_n, "similarity")["code"].tolist()

        stock_returns = weekly_returns_df.loc[row.date, selected_codes].dropna()
        if stock_returns.empty:
            continue

        selected_codes = stock_returns.index.tolist()
        portfolio_return = stock_returns.mean()
        turnover = _calculate_turnover(prev_stocks, selected_codes)
        baseline_codes = set(row.selected_codes)
        baseline_overlap = len(set(selected_codes) & baseline_codes) / len(selected_codes)

        records.append(
            {
                "scenario": scenario["name"],
                "description": scenario.get("description", ""),
                "date": row.date,
                "signal_date": row.signal_date,
                "next_date": row.next_date,
                "return": portfolio_return,
                "num_stocks": len(selected_codes),
                "turnover": turnover,
                "active_factor_count": active_factor_count,
                "baseline_overlap": baseline_overlap,
                "selected_codes": selected_codes,
            }
        )
        prev_stocks = selected_codes

    return pd.DataFrame(records)


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


def summarize_factor_weight_experiment(returns_df, net_cost_bps=10, risk_free_rate=0.03):
    """汇总各因子权重场景的毛收益和成本后收益。"""
    summary_rows = []
    annual_rows = []
    cost_rate = net_cost_bps / 10_000.0

    for scenario, group in returns_df.groupby("scenario", sort=False):
        group = group.sort_values("date").copy()
        gross_metrics = _calculate_metrics(group["return"], group["date"], risk_free_rate=risk_free_rate)
        net_return = (1.0 - group["turnover"] * cost_rate) * (1.0 + group["return"]) - 1.0
        net_metrics = _calculate_metrics(net_return, group["date"], risk_free_rate=risk_free_rate)

        summary_rows.append(
            {
                "scenario": scenario,
                "description": group["description"].iloc[0],
                "periods": len(group),
                "active_factor_count": group["active_factor_count"].iloc[0],
                "final_nav": gross_metrics["final_nav"],
                "annual_return": gross_metrics["annual_return"],
                "annual_volatility": gross_metrics["annual_volatility"],
                "sharpe_ratio": gross_metrics["sharpe_ratio"],
                "max_drawdown": gross_metrics["max_drawdown"],
                "win_rate": gross_metrics["win_rate"],
                "avg_turnover": group["turnover"].mean(),
                "avg_baseline_overlap": group["baseline_overlap"].mean(),
                "net_cost_bps": net_cost_bps,
                "net_final_nav": net_metrics["final_nav"],
                "net_annual_return": net_metrics["annual_return"],
                "net_sharpe_ratio": net_metrics["sharpe_ratio"],
                "net_max_drawdown": net_metrics["max_drawdown"],
            }
        )

        annual_source = group[["date", "return", "turnover"]].copy()
        annual_source["net_return"] = (
            (1.0 - annual_source["turnover"] * cost_rate) * (1.0 + annual_source["return"]) - 1.0
        )
        annual_source["year"] = annual_source["date"].dt.year
        for year, year_group in annual_source.groupby("year"):
            annual_rows.append(
                {
                    "scenario": scenario,
                    "year": year,
                    "weeks": len(year_group),
                    "annual_return": (1.0 + year_group["return"]).prod() - 1.0,
                    "net_annual_return": (1.0 + year_group["net_return"]).prod() - 1.0,
                    "avg_turnover": year_group["turnover"].mean(),
                    "win_rate": (year_group["return"] > 0).mean(),
                }
            )

    summary_df = pd.DataFrame(summary_rows)
    baseline = summary_df[summary_df["scenario"] == "baseline_all_factors"]
    if not baseline.empty:
        baseline_row = baseline.iloc[0]
        summary_df["annual_return_diff_vs_baseline"] = (
            summary_df["annual_return"] - baseline_row["annual_return"]
        )
        summary_df["net_annual_return_diff_vs_baseline"] = (
            summary_df["net_annual_return"] - baseline_row["net_annual_return"]
        )
        summary_df["turnover_diff_vs_baseline"] = summary_df["avg_turnover"] - baseline_row["avg_turnover"]
        summary_df["max_drawdown_diff_vs_baseline"] = (
            summary_df["max_drawdown"] - baseline_row["max_drawdown"]
        )

    summary_df = summary_df.sort_values("net_annual_return", ascending=False).reset_index(drop=True)
    annual_df = pd.DataFrame(annual_rows).sort_values(["scenario", "year"]).reset_index(drop=True)
    return summary_df, annual_df


def run_factor_weight_experiment(scenarios, top_n=100, net_cost_bps=10):
    """运行全部因子剔除/降权场景。"""
    portfolio_df = load_portfolio_returns()
    optimal_df, factor_cols = load_optimal_vectors()
    price_df = load_price_data()
    weekly_returns_df = compute_weekly_returns(price_df, portfolio_df)
    suspend_lookup = build_suspend_lookup(price_df)
    exposure_df = load_signal_date_exposures(portfolio_df["signal_date"].unique(), factor_cols)
    exposure_by_date = exposure_df.groupby("date", sort=False)

    returns_list = []
    for scenario in scenarios:
        scenario_returns = run_single_factor_weight_scenario(
            scenario,
            portfolio_df,
            optimal_df,
            exposure_by_date,
            weekly_returns_df,
            suspend_lookup,
            factor_cols,
            top_n=top_n,
        )
        returns_list.append(scenario_returns)

    returns_df = pd.concat(returns_list, ignore_index=True)
    summary_df, annual_df = summarize_factor_weight_experiment(returns_df, net_cost_bps=net_cost_bps)
    weights_df = build_factor_weights(factor_cols, scenarios)
    return returns_df, summary_df, annual_df, weights_df


def _format_percent(value):
    if pd.isna(value):
        return ""
    return f"{value * 100:.1f}%"


def _format_number(value):
    if pd.isna(value):
        return ""
    return f"{value:.2f}"


def plot_factor_weight_experiment(returns_df, summary_df, scenarios_to_plot=None):
    """绘制因子剔除/降权实验的净值曲线和摘要表。"""
    os.makedirs(IMAGE_DIR, exist_ok=True)
    if returns_df.empty or summary_df.empty:
        return

    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    if scenarios_to_plot is None:
        scenarios_to_plot = summary_df["scenario"].tolist()

    fig, (ax_nav, ax_table) = plt.subplots(
        2,
        1,
        figsize=(17, 11),
        gridspec_kw={"height_ratios": [2.6, 1.5]},
    )

    for scenario in scenarios_to_plot:
        group = returns_df[returns_df["scenario"] == scenario].sort_values("date")
        if group.empty:
            continue
        nav = (1.0 + group["return"]).cumprod()
        linewidth = 2.4 if scenario == "baseline_all_factors" else 1.6
        ax_nav.plot(group["date"], nav, label=scenario, linewidth=linewidth)

    ax_nav.set_title("因子剔除/降权实验：毛收益净值曲线")
    ax_nav.set_ylabel("累计净值")
    ax_nav.grid(True, alpha=0.25)
    ax_nav.legend(loc="upper left", ncol=2, fontsize=9)

    table_source = summary_df
    if scenarios_to_plot is not None:
        table_source = summary_df[summary_df["scenario"].isin(scenarios_to_plot)].copy()

    table_df = table_source[
        [
            "scenario",
            "active_factor_count",
            "annual_return",
            "net_annual_return",
            "max_drawdown",
            "avg_turnover",
            "avg_baseline_overlap",
            "net_annual_return_diff_vs_baseline",
        ]
    ].copy()
    table_df.columns = [
        "场景",
        "有效因子",
        "毛年化",
        "10bp净年化",
        "最大回撤",
        "平均换手",
        "与原持仓重合",
        "净年化差",
    ]
    for col in ["毛年化", "10bp净年化", "最大回撤", "平均换手", "与原持仓重合", "净年化差"]:
        table_df[col] = table_df[col].map(_format_percent)

    ax_table.axis("off")
    ax_table.set_title("实验摘要", fontsize=15, fontweight="bold", pad=12)
    table = ax_table.table(
        cellText=table_df.values,
        colLabels=table_df.columns,
        cellLoc="center",
        colLoc="center",
        loc="center",
        bbox=[0.0, 0.0, 1.0, 0.9],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8.5)
    table.scale(1.0, 1.2)

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
        elif col in [col_index["毛年化"], col_index["10bp净年化"], col_index["净年化差"]]:
            metric_name = {
                col_index["毛年化"]: "annual_return",
                col_index["10bp净年化"]: "net_annual_return",
                col_index["净年化差"]: "net_annual_return_diff_vs_baseline",
            }[col]
            value = raw_row[metric_name]
            if value > 0:
                cell.set_facecolor("#E4F4E8")
            elif value < 0:
                cell.set_facecolor("#FBE7E5")
        elif col == col_index["最大回撤"]:
            if raw_row["max_drawdown"] <= -0.25:
                cell.set_facecolor("#FBE7E5")
            elif raw_row["max_drawdown"] >= -0.15:
                cell.set_facecolor("#E4F4E8")

    fig.tight_layout()
    fig.savefig(FACTOR_WEIGHT_EXPERIMENT_PLOT_OUTPUT_PATH, dpi=200, bbox_inches="tight")
    plt.close(fig)
