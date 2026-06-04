"""Build the baseline pre/post execution-constraint curve for the Alpha report."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "output" / "cne6" / "data"
IMAGE_DIR = PROJECT_ROOT / "output" / "cne6" / "images" / "report"
SUFFIX = "l20_s5_b2_e1_n500_alpha50"
OUTPUT_PATH = IMAGE_DIR / f"final_main_baseline_constraint_curve_{SUFFIX}.png"


def configure_matplotlib() -> None:
    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def period_end_nav(df: pd.DataFrame, return_col: str) -> pd.DataFrame:
    df = df.sort_values("date").copy()
    nav = (1.0 + df[return_col]).cumprod()
    dates = [df["date"].iloc[0]] + df["next_date"].tolist()
    values = [1.0] + nav.tolist()
    return pd.DataFrame({"date": pd.to_datetime(dates), "nav": values})


def fmt_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def main() -> None:
    configure_matplotlib()
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    raw_df = pd.read_csv(
        DATA_DIR / f"portfolio_returns_{SUFFIX}.csv",
        parse_dates=["date", "next_date"],
    )
    execution_df = pd.read_csv(
        DATA_DIR / f"execution_turnover_revaluation_detail_{SUFFIX}.csv",
        parse_dates=["date", "next_date"],
    )
    summary_df = pd.read_csv(DATA_DIR / f"execution_turnover_revaluation_summary_{SUFFIX}.csv")
    raw_metric_df = pd.read_csv(DATA_DIR / "barra_alpha_grid_comparison.csv")

    constrained_df = execution_df[
        execution_df["scenario"].eq("baseline")
        & execution_df["capital"].eq(10_000_000)
        & execution_df["participation_limit"].round(4).eq(0.10)
    ].copy()
    if constrained_df.empty:
        raise ValueError("No baseline execution rows found for 1000万/10% ADV.")

    raw_nav = period_end_nav(raw_df, "return").rename(columns={"nav": "raw_nav"})
    constrained_nav = period_end_nav(constrained_df, "net_return").rename(columns={"nav": "constrained_nav"})
    plot_df = raw_nav.merge(constrained_nav, on="date", how="inner")
    plot_df["drag_ratio"] = plot_df["constrained_nav"] / plot_df["raw_nav"]

    raw_metric = raw_metric_df[raw_metric_df["suffix"].eq(SUFFIX)].iloc[0]
    constrained_metric = summary_df[
        summary_df["scenario"].eq("baseline")
        & summary_df["capital"].eq(10_000_000)
        & summary_df["participation_limit"].round(4).eq(0.10)
    ].iloc[0]

    final_raw = plot_df["raw_nav"].iloc[-1]
    final_constrained = plot_df["constrained_nav"].iloc[-1]
    final_ratio = plot_df["drag_ratio"].iloc[-1]

    fig = plt.figure(figsize=(11.8, 7.1))
    grid = fig.add_gridspec(3, 1, height_ratios=[3.0, 0.95, 1.05], hspace=0.18)
    ax_nav = fig.add_subplot(grid[0])
    ax_table = fig.add_subplot(grid[1])
    ax_drag = fig.add_subplot(grid[2], sharex=ax_nav)

    ax_nav.plot(
        plot_df["date"],
        plot_df["raw_nav"],
        color="#1f5b9d",
        linewidth=2.25,
        label=f"约束前 baseline（期末净值 {final_raw:.2f}）",
    )
    ax_nav.plot(
        plot_df["date"],
        plot_df["constrained_nav"],
        color="#c43b32",
        linewidth=2.25,
        label=f"约束后 baseline（1000万/10% ADV，期末净值 {final_constrained:.2f}）",
    )
    ax_nav.axhline(1.0, color="#6b7280", linewidth=1.0, linestyle="--", alpha=0.65)
    ax_nav.set_title("baseline 成本与成交约束前后回测曲线", fontsize=15, fontweight="bold", pad=12)
    ax_nav.set_ylabel("累计净值")
    ax_nav.grid(True, alpha=0.24)
    ax_nav.legend(loc="upper left", frameon=False)
    ax_nav.text(
        plot_df["date"].iloc[-1],
        final_constrained,
        f"  执行后约为原始净值的 {final_ratio:.1%}",
        va="center",
        ha="left",
        fontsize=9.5,
        color="#4b5563",
    )

    ax_table.axis("off")
    metric_rows = [
        [
            "约束前 baseline",
            f"{raw_metric['annual_return_pct']:.1f}%",
            f"{raw_metric['sharpe']:.2f}",
            f"最大回撤 {raw_metric['max_drawdown_pct']:.1f}%",
            f"平均单边换手\n{raw_metric['avg_turnover_pct']:.1f}%",
            "未计入",
        ],
        [
            "约束后 baseline\n1000万/10% ADV",
            fmt_pct(constrained_metric["annual_return"]),
            f"{constrained_metric['sharpe_ratio']:.2f}",
            f"最大回撤 {fmt_pct(constrained_metric['max_drawdown'])}",
            f"成交完成 {fmt_pct(constrained_metric['avg_fill_ratio'])}\n平均现金 {fmt_pct(constrained_metric['avg_cash_weight'])}",
            f"算术累计成本\n{fmt_pct(constrained_metric['total_cost_arithmetic'])}",
        ],
    ]
    metric_table = ax_table.table(
        cellText=metric_rows,
        colLabels=["口径", "年化收益", "夏普比率", "回撤", "执行指标", "成本指标"],
        colWidths=[0.18, 0.13, 0.13, 0.17, 0.22, 0.17],
        cellLoc="center",
        loc="center",
    )
    metric_table.auto_set_font_size(False)
    metric_table.set_fontsize(9.3)
    metric_table.scale(1, 1.46)
    for (row, col), cell in metric_table.get_celld().items():
        cell.set_edgecolor("#cfd6e3")
        cell.set_linewidth(0.8)
        if row == 0:
            cell.set_facecolor("#dce8f3")
            cell.set_text_props(color="#064f9e", weight="bold")
        elif row == 2:
            cell.set_facecolor("#f3f6fb")
        else:
            cell.set_facecolor("#ffffff")
        if row > 0 and col == 0:
            cell.set_text_props(weight="bold")

    ax_drag.plot(plot_df["date"], plot_df["drag_ratio"] * 100, color="#6b7280", linewidth=1.8)
    ax_drag.fill_between(
        plot_df["date"],
        plot_df["drag_ratio"] * 100,
        100,
        where=(plot_df["drag_ratio"] < 1),
        color="#d8dee8",
        alpha=0.65,
    )
    ax_drag.axhline(100, color="#9ca3af", linewidth=0.9, linestyle="--")
    ax_drag.set_ylabel("约束后/约束前")
    ax_drag.set_xlabel("日期")
    ax_drag.grid(True, alpha=0.20)
    ax_drag.yaxis.set_major_formatter(lambda value, _: f"{value:.0f}%")

    for ax in [ax_nav, ax_drag]:
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    ax_drag.xaxis.set_major_locator(mdates.YearLocator())
    ax_drag.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.subplots_adjust(top=0.90, bottom=0.11, left=0.08, right=0.96)
    fig.savefig(OUTPUT_PATH, dpi=220, bbox_inches="tight")
    plt.close(fig)
    print(f"PNG: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
