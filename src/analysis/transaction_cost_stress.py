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
IMAGE_DIR = os.path.join(OUTPUT_DIR, "images")

SUFFIX = "l20_s5_b2_e1_n100"

PORTFOLIO_RETURNS_PATH = os.path.join(DATA_DIR, f"portfolio_returns_{SUFFIX}.csv")

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


def load_portfolio_returns():
    """读取策略每期收益和换手率。"""
    df = pd.read_csv(PORTFOLIO_RETURNS_PATH)
    df["date"] = pd.to_datetime(df["date"])
    df["signal_date"] = pd.to_datetime(df["signal_date"])
    df["next_date"] = pd.to_datetime(df["next_date"])
    return df


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


def _format_percent(value):
    if pd.isna(value):
        return ""
    return f"{value * 100:.1f}%"


def _format_number(value):
    if pd.isna(value):
        return ""
    return f"{value:.2f}"


def plot_transaction_cost_stress(detail_df, summary_df, cost_bps_to_plot=None):
    """绘制交易成本压力测试净值曲线和摘要表。"""
    os.makedirs(IMAGE_DIR, exist_ok=True)
    if detail_df.empty or summary_df.empty:
        return

    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    if cost_bps_to_plot is None:
        cost_bps_to_plot = summary_df["cost_bps"].tolist()

    fig, (ax_nav, ax_table) = plt.subplots(
        2,
        1,
        figsize=(15, 11),
        gridspec_kw={"height_ratios": [2.5, 1.5]},
    )

    for cost_bps in cost_bps_to_plot:
        curve = detail_df[detail_df["cost_bps"] == cost_bps]
        if curve.empty:
            continue
        label = "毛收益" if cost_bps == 0 else f"{cost_bps:g}bp"
        linewidth = 2.4 if cost_bps == 0 else 1.6
        ax_nav.plot(curve["date"], curve["net_nav"], label=label, linewidth=linewidth)

    ax_nav.set_title("交易成本压力测试：净值曲线")
    ax_nav.set_ylabel("累计净值")
    ax_nav.grid(True, alpha=0.25)
    ax_nav.legend(loc="upper left", ncol=4)

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
    for col in ["累计收益", "年化收益", "年化拖累", "年化波动", "最大回撤", "累计成本"]:
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
        if col == col_index["单边成本"]:
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
    fig.savefig(TRANSACTION_COST_PLOT_OUTPUT_PATH, dpi=200, bbox_inches="tight")
    plt.close(fig)
