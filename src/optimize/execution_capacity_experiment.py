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

from src.analysis import factor_weight_experiment as base
from src.analysis import transaction_cost_stress as cost_core


OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output", "cne6")
DATA_DIR = os.path.join(OUTPUT_DIR, "data")
IMAGE_DIR = os.path.join(OUTPUT_DIR, "images", "optimize")

SUFFIX = "l20_s5_b2_e1_n100"

TURNOVER_RETURNS_PATH = os.path.join(
    DATA_DIR, f"turnover_control_experiment_returns_{SUFFIX}.csv"
)

DETAIL_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"execution_capacity_detail_{SUFFIX}.csv"
)
SUMMARY_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"execution_capacity_summary_{SUFFIX}.csv"
)
TRADE_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"execution_capacity_trade_detail_{SUFFIX}.csv"
)
ANNUAL_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"execution_capacity_annual_{SUFFIX}.csv"
)
PLOT_OUTPUT_PATH = os.path.join(
    IMAGE_DIR, f"execution_capacity_experiment_{SUFFIX}.png"
)


def parse_selected_codes(value):
    if isinstance(value, list):
        return value
    if pd.isna(value):
        return []
    return ast.literal_eval(value)


def load_target_returns(scenarios):
    """读取目标持仓序列，通常来自换手控制实验输出。"""
    df = pd.read_csv(TURNOVER_RETURNS_PATH)
    df["date"] = pd.to_datetime(df["date"])
    df["signal_date"] = pd.to_datetime(df["signal_date"])
    df["next_date"] = pd.to_datetime(df["next_date"])
    df["selected_codes"] = df["selected_codes"].apply(parse_selected_codes)
    return df[df["scenario"].isin(scenarios)].sort_values(["scenario", "date"]).reset_index(drop=True)


def load_price_features(wanted_dates=None, wanted_codes=None, adv_window=20, min_periods=5):
    """读取成交额、涨跌幅、停牌，并生成交易日前可见 ADV。"""
    header_cols = pd.read_csv(base.PRICE_DATA_PATH, nrows=0).columns.tolist()
    usecols = ["date", "code", "pct_chg", "amount"]
    if "is_suspend" in header_cols:
        usecols.append("is_suspend")
    price_df = pd.read_csv(base.PRICE_DATA_PATH, usecols=usecols)
    price_df["date"] = pd.to_datetime(price_df["date"])
    if "is_suspend" not in price_df.columns:
        price_df["is_suspend"] = 0

    price_df = price_df.sort_values(["code", "date"]).reset_index(drop=True)
    shifted_amount = price_df.groupby("code")["amount"].shift(1)
    price_df["adv_amount"] = (
        shifted_amount.groupby(price_df["code"])
        .rolling(adv_window, min_periods=min_periods)
        .mean()
        .reset_index(level=0, drop=True)
    )
    if wanted_dates is not None:
        wanted_dates = set(pd.to_datetime(list(wanted_dates)))
        price_df = price_df[price_df["date"].isin(wanted_dates)]
    if wanted_codes is not None:
        wanted_codes = set(wanted_codes)
        price_df = price_df[price_df["code"].isin(wanted_codes)]
    return price_df[["date", "code", "pct_chg", "is_suspend", "adv_amount"]]


def _limit_threshold(code):
    """用代码前缀近似区分 10% 和 20% 涨跌停。"""
    code = str(code)
    if code.startswith(("300", "301", "688")):
        return 0.195
    return 0.095


def _is_blocked_by_limit(code, pct_chg, side):
    if pd.isna(pct_chg):
        return False
    threshold = _limit_threshold(code)
    if side == "buy":
        return pct_chg >= threshold
    return pct_chg <= -threshold


def _target_equal_weights(codes):
    if not codes:
        return {}
    weight = 1.0 / len(codes)
    return {code: weight for code in codes}


def _calculate_metrics(returns, dates, risk_free_rate=0.03):
    nav = (1.0 + returns).cumprod()
    years = (dates.max() - dates.min()).days / 365.25
    cumulative_return = nav.iloc[-1] - 1.0
    annual_return = (1.0 + cumulative_return) ** (1.0 / years) - 1.0 if years > 0 else np.nan
    annual_volatility = returns.std() * np.sqrt(52.0)
    sharpe_ratio = (
        (annual_return - risk_free_rate) / annual_volatility
        if annual_volatility and annual_volatility != 0
        else np.nan
    )
    max_drawdown = (nav / nav.cummax() - 1.0).min()
    return {
        "final_nav": nav.iloc[-1],
        "cumulative_return": cumulative_return,
        "annual_return": annual_return,
        "annual_volatility": annual_volatility,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown": max_drawdown,
        "win_rate": (returns > 0).mean(),
    }


def _execute_transition(
    prev_weights,
    cash_weight,
    target_weights,
    date,
    capital,
    participation_limit,
    price_feature_map,
    fixed_cost_bps,
    impact_coef_bps,
):
    """按 ADV 和涨跌停约束，从实际持仓向目标持仓部分调仓。"""
    fixed_cost_rate = fixed_cost_bps / 10_000.0
    impact_coef_rate = impact_coef_bps / 10_000.0

    all_codes = sorted(set(prev_weights) | set(target_weights))
    desired_sells = {}
    desired_buys = {}
    trade_rows = []

    for code in all_codes:
        delta = target_weights.get(code, 0.0) - prev_weights.get(code, 0.0)
        if delta < -1e-12:
            desired_sells[code] = -delta
        elif delta > 1e-12:
            desired_buys[code] = delta

    new_weights = dict(prev_weights)
    available_cash = cash_weight
    period_fixed_cost = 0.0
    period_impact_cost = 0.0
    desired_trade_weight = sum(desired_sells.values()) + sum(desired_buys.values())
    executed_trade_weight = 0.0
    blocked_trade_weight = 0.0
    capped_trade_weight = 0.0
    missing_adv_weight = 0.0
    max_participation = np.nan
    weighted_participation = 0.0
    weighted_participation_base = 0.0

    def executable_weight(code, desired_weight, side):
        nonlocal missing_adv_weight
        features = price_feature_map.get((date, code), {})
        pct_chg = features.get("pct_chg", np.nan)
        is_suspend = features.get("is_suspend", 0)
        adv_amount = features.get("adv_amount", np.nan)
        if is_suspend == 1 or _is_blocked_by_limit(code, pct_chg, side):
            return 0.0, adv_amount, "blocked"
        if pd.isna(adv_amount) or adv_amount <= 0:
            missing_adv_weight += desired_weight
            return 0.0, adv_amount, "missing_adv"
        cap_weight = participation_limit * adv_amount / capital
        return min(desired_weight, cap_weight), adv_amount, "ok"

    sell_exec = {}
    for code, desired_weight in desired_sells.items():
        exec_weight, adv_amount, status = executable_weight(code, desired_weight, "sell")
        if status != "ok":
            blocked_trade_weight += desired_weight
        elif exec_weight < desired_weight:
            capped_trade_weight += desired_weight - exec_weight
        if exec_weight > 0:
            sell_exec[code] = exec_weight
            new_weights[code] = max(new_weights.get(code, 0.0) - exec_weight, 0.0)
            available_cash += exec_weight
            executed_trade_weight += exec_weight
            participation = (exec_weight * capital) / adv_amount
            max_participation = participation if pd.isna(max_participation) else max(max_participation, participation)
            weighted_participation += exec_weight * participation
            weighted_participation_base += exec_weight
            period_fixed_cost += exec_weight * fixed_cost_rate
            period_impact_cost += exec_weight * impact_coef_rate * np.sqrt(max(participation, 0.0))
        trade_rows.append(
            {
                "date": date,
                "code": code,
                "side": "sell",
                "desired_weight": desired_weight,
                "executed_weight": exec_weight,
                "unfilled_weight": desired_weight - exec_weight,
                "adv_amount": adv_amount,
                "participation": (exec_weight * capital / adv_amount) if exec_weight > 0 and adv_amount > 0 else np.nan,
                "status": status,
            }
        )

    buy_candidates = []
    for code, desired_weight in desired_buys.items():
        exec_capacity, adv_amount, status = executable_weight(code, desired_weight, "buy")
        if status != "ok":
            blocked_trade_weight += desired_weight
        elif exec_capacity < desired_weight:
            capped_trade_weight += desired_weight - exec_capacity
        buy_candidates.append((code, desired_weight, exec_capacity, adv_amount, status))

    total_buy_capacity = sum(item[2] for item in buy_candidates)
    buy_scale = min(1.0, available_cash / total_buy_capacity) if total_buy_capacity > 0 else 0.0
    for code, desired_weight, exec_capacity, adv_amount, status in buy_candidates:
        exec_weight = exec_capacity * buy_scale
        if exec_weight > 0:
            new_weights[code] = new_weights.get(code, 0.0) + exec_weight
            available_cash -= exec_weight
            executed_trade_weight += exec_weight
            participation = (exec_weight * capital) / adv_amount
            max_participation = participation if pd.isna(max_participation) else max(max_participation, participation)
            weighted_participation += exec_weight * participation
            weighted_participation_base += exec_weight
            period_fixed_cost += exec_weight * fixed_cost_rate
            period_impact_cost += exec_weight * impact_coef_rate * np.sqrt(max(participation, 0.0))
        unfilled_weight = desired_weight - exec_weight
        trade_rows.append(
            {
                "date": date,
                "code": code,
                "side": "buy",
                "desired_weight": desired_weight,
                "executed_weight": exec_weight,
                "unfilled_weight": unfilled_weight,
                "adv_amount": adv_amount,
                "participation": (exec_weight * capital / adv_amount) if exec_weight > 0 and adv_amount > 0 else np.nan,
                "status": status if buy_scale == 1.0 or exec_capacity == 0 else "cash_limited",
            }
        )

    new_weights = {code: weight for code, weight in new_weights.items() if weight > 1e-10}
    avg_participation = (
        weighted_participation / weighted_participation_base
        if weighted_participation_base > 0
        else np.nan
    )
    period_cost = period_fixed_cost + period_impact_cost
    stats = {
        "cash_weight": max(available_cash, 0.0),
        "desired_trade_weight": desired_trade_weight,
        "executed_trade_weight": executed_trade_weight,
        "unfilled_trade_weight": max(desired_trade_weight - executed_trade_weight, 0.0),
        "fill_ratio": executed_trade_weight / desired_trade_weight if desired_trade_weight > 0 else 1.0,
        "blocked_trade_weight": blocked_trade_weight,
        "capped_trade_weight": capped_trade_weight,
        "missing_adv_weight": missing_adv_weight,
        "period_fixed_cost": period_fixed_cost,
        "period_impact_cost": period_impact_cost,
        "period_cost": period_cost,
        "avg_participation": avg_participation,
        "max_participation": max_participation,
    }
    return new_weights, max(available_cash, 0.0), stats, trade_rows


def _apply_period_return(weights, cash_weight, weekly_returns):
    if not weights:
        return cash_weight - 1.0, {}, cash_weight
    gross_end = cash_weight
    end_values = {}
    for code, weight in weights.items():
        stock_return = weekly_returns.get(code, np.nan)
        if pd.isna(stock_return):
            stock_return = 0.0
        end_value = weight * (1.0 + stock_return)
        end_values[code] = end_value
        gross_end += end_value

    if gross_end <= 0:
        return -1.0, {}, 0.0
    gross_return = gross_end - 1.0
    next_weights = {code: value / gross_end for code, value in end_values.items() if value > 1e-10}
    next_cash = cash_weight / gross_end
    return gross_return, next_weights, next_cash


def simulate_execution_capacity(
    target_df,
    weekly_returns_df,
    price_feature_df,
    capital,
    participation_limit,
    fixed_cost_bps=10,
    impact_coef_bps=25,
):
    price_feature_map = (
        price_feature_df.set_index(["date", "code"])[["pct_chg", "is_suspend", "adv_amount"]]
        .to_dict("index")
    )
    detail_rows = []
    trade_rows = []

    for scenario, group in target_df.groupby("scenario", sort=False):
        weights = {}
        cash_weight = 1.0
        group = group.sort_values("date")
        for row in group.itertuples(index=False):
            if row.date not in weekly_returns_df.index:
                continue
            target_weights = _target_equal_weights(row.selected_codes)
            weights, cash_weight, trade_stats, trades = _execute_transition(
                weights,
                cash_weight,
                target_weights,
                row.date,
                capital,
                participation_limit,
                price_feature_map,
                fixed_cost_bps,
                impact_coef_bps,
            )
            weekly_returns = weekly_returns_df.loc[row.date]
            gross_return, next_weights, next_cash = _apply_period_return(weights, cash_weight, weekly_returns)
            net_return = (1.0 - trade_stats["period_cost"]) * (1.0 + gross_return) - 1.0
            target_set = set(row.selected_codes)
            actual_set = set(weights)
            target_overlap_weight = sum(weight for code, weight in weights.items() if code in target_set)
            detail_rows.append(
                {
                    "scenario": scenario,
                    "date": row.date,
                    "signal_date": row.signal_date,
                    "next_date": row.next_date,
                    "capital": capital,
                    "participation_limit": participation_limit,
                    "fixed_cost_bps": fixed_cost_bps,
                    "impact_coef_bps": impact_coef_bps,
                    "gross_return": gross_return,
                    "net_return": net_return,
                    "cash_weight": cash_weight,
                    "actual_stock_count": len(actual_set),
                    "target_stock_count": len(target_set),
                    "actual_target_overlap_count": len(actual_set & target_set),
                    "actual_target_overlap_weight": target_overlap_weight,
                    **trade_stats,
                }
            )
            for trade in trades:
                trade.update(
                    {
                        "scenario": scenario,
                        "capital": capital,
                        "participation_limit": participation_limit,
                    }
                )
                trade_rows.append(trade)

            weights = next_weights
            cash_weight = next_cash

    return pd.DataFrame(detail_rows), pd.DataFrame(trade_rows)


def summarize_execution(detail_df):
    rows = []
    annual_rows = []
    for keys, group in detail_df.groupby(["scenario", "capital", "participation_limit"], sort=False):
        scenario, capital, participation_limit = keys
        group = group.sort_values("date")
        metrics = _calculate_metrics(group["net_return"], group["date"])
        metrics.update(
            {
                "scenario": scenario,
                "capital": capital,
                "participation_limit": participation_limit,
                "periods": len(group),
                "avg_fill_ratio": group["fill_ratio"].mean(),
                "avg_unfilled_trade_weight": group["unfilled_trade_weight"].mean(),
                "total_unfilled_trade_weight": group["unfilled_trade_weight"].sum(),
                "avg_cash_weight": group["cash_weight"].mean(),
                "avg_actual_stock_count": group["actual_stock_count"].mean(),
                "avg_target_overlap_weight": group["actual_target_overlap_weight"].mean(),
                "avg_period_cost": group["period_cost"].mean(),
                "total_cost_arithmetic": group["period_cost"].sum(),
                "total_fixed_cost_arithmetic": group["period_fixed_cost"].sum(),
                "total_impact_cost_arithmetic": group["period_impact_cost"].sum(),
                "avg_participation": group["avg_participation"].mean(),
                "p95_participation": group["avg_participation"].quantile(0.95),
                "max_participation": group["max_participation"].max(),
            }
        )
        rows.append(metrics)

        annual_source = group[["date", "net_return", "period_cost", "unfilled_trade_weight", "fill_ratio"]].copy()
        annual_source["year"] = annual_source["date"].dt.year
        for year, year_group in annual_source.groupby("year"):
            annual_rows.append(
                {
                    "scenario": scenario,
                    "capital": capital,
                    "participation_limit": participation_limit,
                    "year": year,
                    "weeks": len(year_group),
                    "annual_return": (1.0 + year_group["net_return"]).prod() - 1.0,
                    "annual_cost_arithmetic": year_group["period_cost"].sum(),
                    "avg_fill_ratio": year_group["fill_ratio"].mean(),
                    "total_unfilled_trade_weight": year_group["unfilled_trade_weight"].sum(),
                }
            )
    summary_df = pd.DataFrame(rows).sort_values(["scenario", "capital", "participation_limit"])
    annual_df = pd.DataFrame(annual_rows).sort_values(["scenario", "capital", "participation_limit", "year"])
    return summary_df, annual_df


def run_execution_capacity_experiment(
    scenarios,
    capital_list,
    participation_limit_list,
    fixed_cost_bps=10,
    impact_coef_bps=25,
):
    target_df = load_target_returns(scenarios)
    portfolio_df = base.load_portfolio_returns()
    price_df = base.load_price_data()
    weekly_returns_df = base.compute_weekly_returns(price_df, portfolio_df)
    wanted_codes = set()
    for codes in target_df["selected_codes"]:
        wanted_codes.update(codes)
    price_feature_df = load_price_features(
        wanted_dates=target_df["date"].unique(),
        wanted_codes=wanted_codes,
    )

    detail_frames = []
    trade_frames = []
    for capital in capital_list:
        for participation_limit in participation_limit_list:
            detail_df, trade_df = simulate_execution_capacity(
                target_df,
                weekly_returns_df,
                price_feature_df,
                capital=capital,
                participation_limit=participation_limit,
                fixed_cost_bps=fixed_cost_bps,
                impact_coef_bps=impact_coef_bps,
            )
            detail_frames.append(detail_df)
            trade_frames.append(trade_df)

    detail_df = pd.concat(detail_frames, ignore_index=True)
    trade_df = pd.concat(trade_frames, ignore_index=True)
    summary_df, annual_df = summarize_execution(detail_df)
    return detail_df, summary_df, trade_df, annual_df


def _format_percent(value):
    if pd.isna(value):
        return ""
    return f"{value * 100:.1f}%"


def _format_number(value):
    if pd.isna(value):
        return ""
    return f"{value:.2f}"


def plot_execution_capacity(summary_df):
    os.makedirs(IMAGE_DIR, exist_ok=True)
    if summary_df.empty:
        return

    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    scenarios = summary_df["scenario"].unique().tolist()
    fig = plt.figure(figsize=(18, 13))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 1.15], hspace=0.35, wspace=0.25)

    ax_line = fig.add_subplot(gs[0, 0])
    for scenario in scenarios:
        scenario_df = summary_df[summary_df["scenario"] == scenario]
        for limit, group in scenario_df.groupby("participation_limit"):
            group = group.sort_values("capital")
            ax_line.plot(
                group["capital"] / 100_000_000,
                group["annual_return"] * 100,
                marker="o",
                linewidth=1.8,
                label=f"{scenario} / ADV {limit:.0%}",
            )
    ax_line.set_title("成交约束后净年化：资金规模敏感性")
    ax_line.set_xlabel("资金规模（亿元）")
    ax_line.set_ylabel("净年化收益 (%)")
    ax_line.grid(True, alpha=0.25)
    ax_line.legend(fontsize=8)

    ax_fill = fig.add_subplot(gs[0, 1])
    for scenario in scenarios:
        scenario_df = summary_df[summary_df["scenario"] == scenario]
        for limit, group in scenario_df.groupby("participation_limit"):
            group = group.sort_values("capital")
            ax_fill.plot(
                group["capital"] / 100_000_000,
                group["avg_fill_ratio"] * 100,
                marker="s",
                linewidth=1.7,
                label=f"{scenario} / ADV {limit:.0%}",
            )
    ax_fill.set_title("平均成交完成率")
    ax_fill.set_xlabel("资金规模（亿元）")
    ax_fill.set_ylabel("成交完成率 (%)")
    ax_fill.set_ylim(0, 105)
    ax_fill.grid(True, alpha=0.25)

    ax_table = fig.add_subplot(gs[1, :])
    table_source = summary_df[
        (summary_df["capital"].isin([100_000_000, 300_000_000, 500_000_000]))
        & (summary_df["participation_limit"].isin([0.05, 0.10, 0.20]))
    ].copy()
    table_source = table_source.sort_values(["scenario", "capital", "participation_limit"])
    table_df = table_source[
        [
            "scenario",
            "capital",
            "participation_limit",
            "annual_return",
            "sharpe_ratio",
            "max_drawdown",
            "avg_fill_ratio",
            "avg_target_overlap_weight",
            "avg_cash_weight",
            "total_cost_arithmetic",
        ]
    ].copy()
    table_df.columns = [
        "场景",
        "规模",
        "ADV上限",
        "净年化",
        "夏普",
        "最大回撤",
        "成交完成率",
        "目标持仓兑现",
        "平均现金",
        "累计成本",
    ]
    table_df["规模"] = table_df["规模"].map(lambda value: f"{value / 100_000_000:g}亿")
    for col in ["ADV上限", "净年化", "最大回撤", "成交完成率", "目标持仓兑现", "平均现金", "累计成本"]:
        table_df[col] = table_df[col].map(_format_percent)
    table_df["夏普"] = table_df["夏普"].map(_format_number)

    ax_table.axis("off")
    ax_table.set_title("成交可实现性与容量约束摘要", fontsize=15, fontweight="bold", pad=12)
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
        if col in [col_index["场景"], col_index["规模"], col_index["ADV上限"]]:
            cell.set_facecolor("#F5F5F5")
            if col == col_index["场景"]:
                cell.set_text_props(weight="bold")
        elif col == col_index["净年化"]:
            value = raw_row["annual_return"]
            if value >= 0.25:
                cell.set_facecolor("#DDEFE3")
            elif value >= 0.18:
                cell.set_facecolor("#FFF6D8")
            else:
                cell.set_facecolor("#FBE5E1")
        elif col == col_index["成交完成率"]:
            value = raw_row["avg_fill_ratio"]
            if value >= 0.95:
                cell.set_facecolor("#DDEFE3")
            elif value < 0.80:
                cell.set_facecolor("#FBE5E1")

    fig.tight_layout()
    fig.savefig(PLOT_OUTPUT_PATH, dpi=200, bbox_inches="tight")
    plt.close(fig)
