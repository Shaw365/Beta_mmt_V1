import os
import sys
import ast

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
IMAGE_DIR = os.path.join(OUTPUT_DIR, "images", "analysis")

SUFFIX = "l20_s5_b2_e1_n100"

PORTFOLIO_RETURNS_PATH = os.path.join(DATA_DIR, f"portfolio_returns_{SUFFIX}.csv")
PRICE_DATA_PATH = os.path.join(DATA_DIR, "price_data_cne6.csv")

TRANSACTION_COST_DETAIL_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"transaction_cost_stress_detail_{SUFFIX}.csv"
)
TRANSACTION_COST_SUMMARY_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"transaction_cost_stress_summary_{SUFFIX}.csv"
)
TRANSACTION_COST_ANNUAL_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"transaction_cost_stress_annual_{SUFFIX}.csv"
)
TRANSACTION_COST_PLOT_OUTPUT_PATH = os.path.join(
    IMAGE_DIR, f"transaction_cost_stress_{SUFFIX}.png"
)
REALISTIC_TRANSACTION_COST_DETAIL_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"transaction_cost_realistic_detail_{SUFFIX}.csv"
)
REALISTIC_TRANSACTION_COST_SUMMARY_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"transaction_cost_realistic_summary_{SUFFIX}.csv"
)
REALISTIC_TRANSACTION_COST_ANNUAL_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"transaction_cost_realistic_annual_{SUFFIX}.csv"
)
REALISTIC_TRANSACTION_COST_TRADE_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"transaction_cost_realistic_trade_detail_{SUFFIX}.csv"
)
REALISTIC_TRANSACTION_COST_PLOT_OUTPUT_PATH = os.path.join(
    IMAGE_DIR, f"transaction_cost_realistic_{SUFFIX}.png"
)


def load_portfolio_returns():
    """读取策略每期收益和换手率。"""
    df = pd.read_csv(PORTFOLIO_RETURNS_PATH)
    df["date"] = pd.to_datetime(df["date"])
    df["signal_date"] = pd.to_datetime(df["signal_date"])
    df["next_date"] = pd.to_datetime(df["next_date"])
    if "selected_codes" in df.columns:
        df["selected_codes"] = df["selected_codes"].apply(parse_selected_codes)
    return df


def parse_selected_codes(value):
    """还原 portfolio_returns CSV 中保存的持仓股票列表。"""
    if isinstance(value, list):
        return value
    if pd.isna(value):
        return []
    return ast.literal_eval(value)


def load_price_liquidity(adv_window=20, min_periods=5):
    """
    读取成交额并生成交易日前可见的 ADV。

    ADV 使用每只股票截至前一交易日的滚动均值，避免用到当日成交额。
    """
    price_df = pd.read_csv(PRICE_DATA_PATH, usecols=["date", "code", "amount"])
    price_df["date"] = pd.to_datetime(price_df["date"])
    price_df = price_df.sort_values(["code", "date"]).reset_index(drop=True)
    shifted_amount = price_df.groupby("code")["amount"].shift(1)
    price_df["adv_amount"] = (
        shifted_amount.groupby(price_df["code"])
        .rolling(adv_window, min_periods=min_periods)
        .mean()
        .reset_index(level=0, drop=True)
    )
    return price_df[["date", "code", "adv_amount"]]


def _max_drawdown(nav_series):
    running_max = nav_series.cummax()
    drawdown = nav_series / running_max - 1.0
    return drawdown.min()


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


def build_transaction_cost_stress(
    portfolio_df,
    cost_bps_list,
    turnover_multiplier=1.0,
    risk_free_rate=0.03,
):
    """
    构建交易成本压力测试明细和汇总。

    turnover_multiplier 控制成本使用的换手口径：
    1.0 表示直接使用策略里记录的单边换手率；
    2.0 表示把卖出和买入两侧成交金额都计入成本，更保守。
    """
    base_df = portfolio_df.sort_values("date").reset_index(drop=True).copy()

    gross_metrics = _calculate_metrics(base_df["return"], base_df["date"], risk_free_rate=risk_free_rate)

    detail_rows = []
    summary_rows = []
    annual_rows = []

    for cost_bps in cost_bps_list:
        cost_rate = cost_bps / 10_000.0
        period_cost = base_df["turnover"] * turnover_multiplier * cost_rate
        net_return = (1.0 - period_cost) * (1.0 + base_df["return"]) - 1.0
        net_nav = (1.0 + net_return).cumprod()
        gross_nav = (1.0 + base_df["return"]).cumprod()
        drawdown = net_nav / net_nav.cummax() - 1.0

        scenario_df = base_df[
            ["date", "signal_date", "next_date", "return", "turnover", "num_stocks"]
        ].copy()
        scenario_df["cost_bps"] = cost_bps
        scenario_df["turnover_multiplier"] = turnover_multiplier
        scenario_df["period_cost"] = period_cost
        scenario_df["net_return"] = net_return
        scenario_df["gross_nav"] = gross_nav
        scenario_df["net_nav"] = net_nav
        scenario_df["drawdown"] = drawdown
        detail_rows.append(scenario_df)

        metrics = _calculate_metrics(net_return, base_df["date"], risk_free_rate=risk_free_rate)
        metrics.update(
            {
                "cost_bps": cost_bps,
                "turnover_multiplier": turnover_multiplier,
                "avg_turnover": base_df["turnover"].mean(),
                "avg_period_cost": period_cost.mean(),
                "total_cost_arithmetic": period_cost.sum(),
                "annual_return_drag": gross_metrics["annual_return"] - metrics["annual_return"],
                "final_nav_drag": gross_metrics["final_nav"] - metrics["final_nav"],
            }
        )
        summary_rows.append(metrics)

        annual_source = scenario_df[["date", "net_return", "period_cost"]].copy()
        annual_source["year"] = annual_source["date"].dt.year
        for year, group in annual_source.groupby("year"):
            annual_rows.append(
                {
                    "cost_bps": cost_bps,
                    "turnover_multiplier": turnover_multiplier,
                    "year": year,
                    "weeks": len(group),
                    "annual_return": (1.0 + group["net_return"]).prod() - 1.0,
                    "annual_cost_arithmetic": group["period_cost"].sum(),
                    "win_rate": (group["net_return"] > 0).mean(),
                    "max_drawdown": _max_drawdown((1.0 + group["net_return"]).cumprod()),
                }
            )

    detail_df = pd.concat(detail_rows, ignore_index=True)
    summary_df = pd.DataFrame(summary_rows).sort_values("cost_bps")
    annual_df = pd.DataFrame(annual_rows).sort_values(["cost_bps", "year"])
    return detail_df, summary_df, annual_df


def _build_trade_profile(portfolio_df, liquidity_df, capital):
    """
    根据实际持仓变动估算每期买入、卖出和 ADV 占比。

    组合按等权处理；第一期若纳入建仓成本，会产生 100% 买入成交。
    """
    liquidity = liquidity_df.set_index(["date", "code"])["adv_amount"]
    rows = []
    trade_rows = []
    prev_codes = []

    for row in portfolio_df.sort_values("date").itertuples(index=False):
        current_codes = list(row.selected_codes)
        prev_weight = {code: 1.0 / len(prev_codes) for code in prev_codes} if prev_codes else {}
        current_weight = {code: 1.0 / len(current_codes) for code in current_codes} if current_codes else {}
        all_codes = sorted(set(prev_weight) | set(current_weight))

        buy_weight = 0.0
        sell_weight = 0.0
        weighted_participation = 0.0
        valid_trade_weight = 0.0
        max_participation = np.nan
        missing_adv_weight = 0.0
        impact_cost_base = 0.0

        for code in all_codes:
            delta_weight = current_weight.get(code, 0.0) - prev_weight.get(code, 0.0)
            trade_weight = abs(delta_weight)
            if trade_weight == 0:
                continue

            side = "buy" if delta_weight > 0 else "sell"
            if side == "buy":
                buy_weight += trade_weight
            else:
                sell_weight += trade_weight

            adv_amount = liquidity.get((row.date, code), np.nan)
            trade_amount = trade_weight * capital
            participation = trade_amount / adv_amount if adv_amount and adv_amount > 0 else np.nan
            if pd.isna(participation):
                missing_adv_weight += trade_weight
            else:
                valid_trade_weight += trade_weight
                weighted_participation += trade_weight * participation
                max_participation = (
                    participation
                    if pd.isna(max_participation)
                    else max(max_participation, participation)
                )
                impact_cost_base += trade_weight * np.sqrt(max(participation, 0.0))

            trade_rows.append(
                {
                    "date": row.date,
                    "code": code,
                    "side": side,
                    "trade_weight": trade_weight,
                    "trade_amount": trade_amount,
                    "adv_amount": adv_amount,
                    "participation": participation,
                }
            )

        traded_weight = buy_weight + sell_weight
        avg_participation = (
            weighted_participation / valid_trade_weight if valid_trade_weight > 0 else np.nan
        )
        rows.append(
            {
                "date": row.date,
                "buy_weight": buy_weight,
                "sell_weight": sell_weight,
                "traded_weight": traded_weight,
                "avg_participation": avg_participation,
                "max_participation": max_participation,
                "missing_adv_weight": missing_adv_weight,
                "impact_cost_base": impact_cost_base,
            }
        )
        prev_codes = current_codes

    profile_df = pd.DataFrame(rows)
    trade_df = pd.DataFrame(trade_rows)
    return profile_df, trade_df


def build_realistic_transaction_cost_stress(
    portfolio_df,
    liquidity_df,
    capital_list,
    fixed_cost_bps=10,
    impact_coef_bps=25,
    include_initial_build=True,
    risk_free_rate=0.03,
):
    """
    构建更接近实盘的成本口径。

    固定成本按买入+卖出双边成交额扣除；冲击成本使用平方根模型：
    impact_bps = impact_coef_bps * sqrt(trade_amount / ADV)。
    """
    base_df = portfolio_df.sort_values("date").reset_index(drop=True).copy()
    gross_metrics = _calculate_metrics(base_df["return"], base_df["date"], risk_free_rate=risk_free_rate)
    fixed_cost_rate = fixed_cost_bps / 10_000.0
    impact_coef_rate = impact_coef_bps / 10_000.0

    detail_rows = []
    summary_rows = []
    annual_rows = []
    trade_rows = []

    for capital in capital_list:
        profile_df, trade_df = _build_trade_profile(base_df, liquidity_df, capital)
        cost_df = base_df.merge(profile_df, on="date", how="left")

        cost_df["cost_traded_weight"] = cost_df["traded_weight"]
        if not include_initial_build and len(cost_df) > 0:
            first_idx = cost_df.index[0]
            cost_df.loc[first_idx, "cost_traded_weight"] = 0.0

        cost_df["period_fixed_cost"] = cost_df["cost_traded_weight"] * fixed_cost_rate
        cost_df["period_impact_cost"] = cost_df["impact_cost_base"] * impact_coef_rate
        if not include_initial_build and len(cost_df) > 0:
            first_idx = cost_df.index[0]
            cost_df.loc[first_idx, "period_impact_cost"] = 0.0

        cost_df["period_cost"] = cost_df["period_fixed_cost"] + cost_df["period_impact_cost"]
        cost_df["net_return"] = (1.0 - cost_df["period_cost"]) * (1.0 + cost_df["return"]) - 1.0
        cost_df["gross_nav"] = (1.0 + cost_df["return"]).cumprod()
        cost_df["net_nav"] = (1.0 + cost_df["net_return"]).cumprod()
        cost_df["drawdown"] = cost_df["net_nav"] / cost_df["net_nav"].cummax() - 1.0

        scenario = f"realistic_{fixed_cost_bps}bp_cap{int(capital / 10_000):g}w"
        cost_df["scenario"] = scenario
        cost_df["cost_model"] = "double_side_build_impact"
        cost_df["capital"] = capital
        cost_df["fixed_cost_bps"] = fixed_cost_bps
        cost_df["impact_coef_bps"] = impact_coef_bps
        cost_df["include_initial_build"] = include_initial_build
        detail_rows.append(cost_df)

        if not trade_df.empty:
            trade_tmp = trade_df.copy()
            trade_tmp["scenario"] = scenario
            trade_tmp["capital"] = capital
            trade_rows.append(trade_tmp)

        metrics = _calculate_metrics(cost_df["net_return"], cost_df["date"], risk_free_rate=risk_free_rate)
        metrics.update(
            {
                "scenario": scenario,
                "cost_model": "double_side_build_impact",
                "capital": capital,
                "fixed_cost_bps": fixed_cost_bps,
                "impact_coef_bps": impact_coef_bps,
                "include_initial_build": include_initial_build,
                "avg_turnover": base_df["turnover"].mean(),
                "avg_traded_weight": cost_df["cost_traded_weight"].mean(),
                "avg_period_fixed_cost": cost_df["period_fixed_cost"].mean(),
                "avg_period_impact_cost": cost_df["period_impact_cost"].mean(),
                "avg_period_cost": cost_df["period_cost"].mean(),
                "total_fixed_cost_arithmetic": cost_df["period_fixed_cost"].sum(),
                "total_impact_cost_arithmetic": cost_df["period_impact_cost"].sum(),
                "total_cost_arithmetic": cost_df["period_cost"].sum(),
                "avg_participation": cost_df["avg_participation"].mean(),
                "p95_participation": cost_df["avg_participation"].quantile(0.95),
                "max_participation": cost_df["max_participation"].max(),
                "missing_adv_weight": cost_df["missing_adv_weight"].sum(),
                "annual_return_drag": gross_metrics["annual_return"] - metrics["annual_return"],
                "final_nav_drag": gross_metrics["final_nav"] - metrics["final_nav"],
            }
        )
        summary_rows.append(metrics)

        annual_source = cost_df[["date", "net_return", "period_cost", "period_fixed_cost", "period_impact_cost"]].copy()
        annual_source["year"] = annual_source["date"].dt.year
        for year, group in annual_source.groupby("year"):
            annual_rows.append(
                {
                    "scenario": scenario,
                    "cost_model": "double_side_build_impact",
                    "capital": capital,
                    "fixed_cost_bps": fixed_cost_bps,
                    "impact_coef_bps": impact_coef_bps,
                    "year": year,
                    "weeks": len(group),
                    "annual_return": (1.0 + group["net_return"]).prod() - 1.0,
                    "annual_cost_arithmetic": group["period_cost"].sum(),
                    "annual_fixed_cost_arithmetic": group["period_fixed_cost"].sum(),
                    "annual_impact_cost_arithmetic": group["period_impact_cost"].sum(),
                    "win_rate": (group["net_return"] > 0).mean(),
                    "max_drawdown": _max_drawdown((1.0 + group["net_return"]).cumprod()),
                }
            )

    detail_df = pd.concat(detail_rows, ignore_index=True)
    summary_df = pd.DataFrame(summary_rows).sort_values("capital")
    annual_df = pd.DataFrame(annual_rows).sort_values(["capital", "year"])
    trade_detail_df = pd.concat(trade_rows, ignore_index=True) if trade_rows else pd.DataFrame()
    return detail_df, summary_df, annual_df, trade_detail_df


def _format_percent(value):
    if pd.isna(value):
        return ""
    return f"{value * 100:.1f}%"


def _format_number(value):
    if pd.isna(value):
        return ""
    return f"{value:.2f}"


def plot_transaction_cost_stress(detail_df, summary_df, cost_bps_to_plot=None, output_path=None):
    """绘制交易成本压力测试净值曲线和摘要表。"""
    os.makedirs(IMAGE_DIR, exist_ok=True)
    if detail_df.empty or summary_df.empty:
        return

    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    if cost_bps_to_plot is None and "cost_bps" in summary_df.columns:
        cost_bps_to_plot = summary_df["cost_bps"].tolist()

    fig, (ax_nav, ax_table) = plt.subplots(
        2,
        1,
        figsize=(15, 11),
        gridspec_kw={"height_ratios": [2.5, 1.5]},
    )

    if "cost_bps" not in detail_df.columns:
        plot_scenarios = summary_df["scenario"].tolist()
    else:
        plot_scenarios = cost_bps_to_plot

    for item in plot_scenarios:
        if "cost_bps" in detail_df.columns:
            curve = detail_df[detail_df["cost_bps"] == item]
            label = "毛收益" if item == 0 else f"{item:g}bp"
            linewidth = 2.4 if item == 0 else 1.6
        else:
            curve = detail_df[detail_df["scenario"] == item]
            row = summary_df[summary_df["scenario"] == item].iloc[0]
            label = f"{row['capital'] / 100_000_000:g}亿"
            linewidth = 1.8
        if curve.empty:
            continue
        ax_nav.plot(curve["date"], curve["net_nav"], label=label, linewidth=linewidth)

    ax_nav.set_title("交易成本压力测试：净值曲线")
    ax_nav.set_ylabel("累计净值")
    ax_nav.grid(True, alpha=0.25)
    ax_nav.legend(loc="upper left", ncol=4)

    if "capital" in summary_df.columns:
        table_df = summary_df[
            [
                "capital",
                "final_nav",
                "annual_return",
                "annual_return_drag",
                "sharpe_ratio",
                "max_drawdown",
                "total_fixed_cost_arithmetic",
                "total_impact_cost_arithmetic",
                "p95_participation",
            ]
        ].copy()
        table_df.columns = [
            "资金规模",
            "期末净值",
            "年化收益",
            "年化拖累",
            "夏普",
            "最大回撤",
            "固定成本",
            "冲击成本",
            "P95参与率",
        ]
        table_df["资金规模"] = table_df["资金规模"].map(lambda value: f"{value / 100_000_000:g}亿")
        percent_cols = ["年化收益", "年化拖累", "最大回撤", "固定成本", "冲击成本", "P95参与率"]
    else:
        table_df = summary_df[
            [
                "cost_bps",
                "final_nav",
                "cumulative_return",
                "annual_return",
                "annual_return_drag",
                "annual_volatility",
                "sharpe_ratio",
                "max_drawdown",
                "total_cost_arithmetic",
            ]
        ].copy()
        table_df.columns = [
            "单边成本",
            "期末净值",
            "累计收益",
            "年化收益",
            "年化拖累",
            "年化波动",
            "夏普",
            "最大回撤",
            "累计成本",
        ]
        table_df["单边成本"] = table_df["单边成本"].map(lambda value: f"{value:g}bp")
        percent_cols = ["累计收益", "年化收益", "年化拖累", "年化波动", "最大回撤", "累计成本"]
    for col in percent_cols:
        table_df[col] = table_df[col].map(_format_percent)
    for col in ["期末净值", "夏普"]:
        table_df[col] = table_df[col].map(_format_number)

    ax_table.axis("off")
    ax_table.set_title("成本敏感性摘要", fontsize=15, fontweight="bold", pad=12)
    table = ax_table.table(
        cellText=table_df.values,
        colLabels=table_df.columns,
        cellLoc="center",
        colLoc="center",
        loc="center",
        bbox=[0.0, 0.0, 1.0, 0.9],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1.0, 1.25)

    raw_df = summary_df.reset_index(drop=True)
    col_index = {name: idx for idx, name in enumerate(table_df.columns)}
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#D0D0D0")
        if row == 0:
            cell.set_facecolor("#2E4057")
            cell.set_text_props(color="white", weight="bold")
            continue

        raw_row = raw_df.iloc[row - 1]
        scenario_col = "资金规模" if "资金规模" in col_index else "单边成本"
        if col == col_index[scenario_col]:
            cell.set_facecolor("#F5F5F5")
            cell.set_text_props(weight="bold")
        elif col == col_index["年化收益"]:
            if raw_row["annual_return"] >= 0.25:
                cell.set_facecolor("#E4F4E8")
            elif raw_row["annual_return"] <= 0.10:
                cell.set_facecolor("#FBE7E5")
        elif col == col_index["最大回撤"]:
            if raw_row["max_drawdown"] <= -0.25:
                cell.set_facecolor("#FBE7E5")
            elif raw_row["max_drawdown"] >= -0.15:
                cell.set_facecolor("#E4F4E8")
        elif col == col_index["夏普"]:
            if raw_row["sharpe_ratio"] >= 1.0:
                cell.set_facecolor("#E4F4E8")
            elif raw_row["sharpe_ratio"] <= 0.5:
                cell.set_facecolor("#FBE7E5")

    fig.tight_layout()
    fig.savefig(output_path or TRANSACTION_COST_PLOT_OUTPUT_PATH, dpi=200, bbox_inches="tight")
    plt.close(fig)
