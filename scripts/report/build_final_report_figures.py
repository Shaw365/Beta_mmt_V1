"""Build compact figures used by the final main strategy report."""

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

BENCHMARK_PATH = DATA_DIR / "benchmark_relative_l20_s5_b2_e1_n100.csv"
NAV_FIGURE_PATH = IMAGE_DIR / "final_main_nav_vs_benchmark_l20_s5_b2_e1_n100.png"
TURNOVER_RANKING_PATH = DATA_DIR / "execution_turnover_revaluation_ranking_l20_s5_b2_e1_n100.csv"
TURNOVER_SUMMARY_PATH = DATA_DIR / "execution_turnover_revaluation_summary_l20_s5_b2_e1_n100.csv"
TURNOVER_SMALL_CAP_SUPPLEMENT_PATH = (
    DATA_DIR / "execution_turnover_revaluation_small_cap_supplement_l20_s5_b2_e1_n100.csv"
)
TURNOVER_FIGURE_PATH = IMAGE_DIR / "final_main_turnover_platform_l20_s5_b2_e1_n100.png"
CAPACITY_SUMMARY_PATH = DATA_DIR / "execution_capacity_summary_l20_s5_b2_e1_n100.csv"
CAPACITY_FIGURE_PATH = IMAGE_DIR / "final_main_capacity_tc50_buf2_l20_s5_b2_e1_n100.png"
CORE_RANKING_PATH = DATA_DIR / "core_parameter_stability_ranking_l20_s5_b2_e1_n100.csv"
CORE_SUMMARY_PATH = DATA_DIR / "core_parameter_stability_execution_summary_l20_s5_b2_e1_n100.csv"
CORE_FIGURE_PATH = IMAGE_DIR / "final_main_core_parameter_stability_l20_s5_b2_e1_n100_tc50_buf2.png"


def configure_matplotlib() -> None:
    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei",
        "SimHei",
        "Noto Sans CJK SC",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False


def build_nav_vs_benchmark() -> Path:
    df = pd.read_csv(BENCHMARK_PATH, parse_dates=["date"]).sort_values("date")
    if df.empty:
        raise ValueError(f"No benchmark data found in {BENCHMARK_PATH}")

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    configure_matplotlib()

    df["strategy_drawdown"] = df["strategy_nav"] / df["strategy_nav"].cummax() - 1.0

    fig, (ax_nav, ax_dd) = plt.subplots(
        2,
        1,
        figsize=(11.2, 6.2),
        sharex=True,
        gridspec_kw={"height_ratios": [3.0, 1.15], "hspace": 0.08},
    )
    series = [
        ("策略", "strategy_nav", "#1f5b9d", 2.4, "-"),
        ("中证500", "csi500_nav", "#7c8a2e", 1.7, "--"),
        ("中证1000", "csi1000_nav", "#c46f2d", 1.7, "--"),
    ]

    for label, col, color, linewidth, linestyle in series:
        ax_nav.plot(
            df["date"],
            df[col],
            label=f"{label}: {df[col].iloc[-1]:.2f}",
            color=color,
            linewidth=linewidth,
            linestyle=linestyle,
        )

    ax_nav.set_title("策略累计净值、基准与回撤", fontsize=15, fontweight="bold", pad=12)
    ax_nav.set_ylabel("累计净值")
    ax_nav.grid(True, axis="y", alpha=0.22)
    ax_nav.spines["top"].set_visible(False)
    ax_nav.spines["right"].set_visible(False)
    ax_nav.legend(loc="upper left", frameon=False, ncol=3)

    final_date = df["date"].iloc[-1]
    for label, col, color, _, _ in series:
        ax_nav.annotate(
            f"{df[col].iloc[-1]:.2f}",
            xy=(final_date, df[col].iloc[-1]),
            xytext=(8, 0),
            textcoords="offset points",
            va="center",
            fontsize=10,
            color=color,
        )

    dd_pct = df["strategy_drawdown"] * 100
    ax_dd.fill_between(df["date"], dd_pct, 0, color="#e04b3f", alpha=0.22, linewidth=0)
    ax_dd.plot(df["date"], dd_pct, color="#e04b3f", linewidth=1.4)
    ax_dd.axhline(0, color="#667085", linewidth=0.8, alpha=0.7)
    ax_dd.set_ylabel("回撤 (%)")
    ax_dd.grid(True, axis="y", alpha=0.22)
    ax_dd.spines["top"].set_visible(False)
    ax_dd.spines["right"].set_visible(False)
    ax_dd.xaxis.set_major_locator(mdates.YearLocator())
    ax_dd.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    min_dd_idx = df["strategy_drawdown"].idxmin()
    min_dd_date = df.loc[min_dd_idx, "date"]
    min_dd_value = dd_pct.loc[min_dd_idx]
    ax_dd.annotate(
        f"{min_dd_value:.1f}%",
        xy=(min_dd_date, min_dd_value),
        xytext=(8, -2),
        textcoords="offset points",
        fontsize=9,
        color="#e04b3f",
        va="top",
    )

    fig.subplots_adjust(top=0.88, bottom=0.12, left=0.08, right=0.96, hspace=0.08)
    fig.savefig(NAV_FIGURE_PATH, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return NAV_FIGURE_PATH


def format_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def build_turnover_platform() -> Path:
    ranking_df = pd.read_csv(TURNOVER_RANKING_PATH)
    summary_df = pd.read_csv(TURNOVER_SUMMARY_PATH)
    if ranking_df.empty or summary_df.empty:
        raise ValueError("Missing turnover revaluation data.")

    extra_frames = []
    if CAPACITY_SUMMARY_PATH.exists():
        capacity_df = pd.read_csv(CAPACITY_SUMMARY_PATH)
        extra_frames.append(
            capacity_df[
                capacity_df["scenario"].isin(["baseline", "tc50_buf2"])
                & (capacity_df["capital"].isin([10_000_000, 30_000_000]))
                & (capacity_df["participation_limit"].round(4) == 0.10)
            ].copy()
        )
    if TURNOVER_SMALL_CAP_SUPPLEMENT_PATH.exists():
        extra_frames.append(pd.read_csv(TURNOVER_SMALL_CAP_SUPPLEMENT_PATH))
    if extra_frames:
        summary_df = (
            pd.concat([summary_df, *extra_frames], ignore_index=True, sort=False)
            .sort_values(["scenario", "capital", "participation_limit"])
            .drop_duplicates(["scenario", "capital", "participation_limit"], keep="last")
        )

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    configure_matplotlib()

    scenarios = ["baseline", "tc50_buf2", "tc50_buf3", "tc50_buf4"]
    colors = {
        "baseline": "#7f8792",
        "tc50_buf2": "#1f5b9d",
        "tc50_buf3": "#2f8f5b",
        "tc50_buf4": "#c46f2d",
    }
    plot_df = summary_df[
        summary_df["scenario"].isin(scenarios)
        & (summary_df["participation_limit"].round(4) == 0.10)
    ].copy()
    capital_order = [10_000_000, 30_000_000, 100_000_000, 300_000_000, 500_000_000]
    capital_labels = ["1000万", "3000万", "1亿", "3亿", "5亿"]
    capital_pos = {capital: idx for idx, capital in enumerate(capital_order)}
    plot_df = plot_df[plot_df["capital"].isin(capital_order)].copy()
    plot_df["capital_pos"] = plot_df["capital"].map(capital_pos)

    fig = plt.figure(figsize=(11.2, 5.4))
    grid = fig.add_gridspec(2, 1, height_ratios=[3.1, 1.35], hspace=0.36)
    ax = fig.add_subplot(grid[0])
    for scenario in scenarios:
        group = plot_df[plot_df["scenario"] == scenario].sort_values("capital_pos")
        ax.plot(
            group["capital_pos"],
            group["annual_return"] * 100,
            marker="o",
            linewidth=2.2,
            label=scenario,
            color=colors[scenario],
        )
    ax.set_title("10% ADV 约束下的容量曲线", fontsize=14, fontweight="bold", pad=10)
    ax.set_xlabel("资金规模")
    ax.set_ylabel("净年化收益（%）")
    ax.set_xticks(range(len(capital_order)))
    ax.set_xticklabels(capital_labels)
    ax.grid(True, alpha=0.22)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(loc="upper right", ncol=4, frameon=False)

    ax_table = fig.add_subplot(grid[1])
    ax_table.axis("off")
    platform_df = ranking_df.set_index("scenario").loc[["tc50_buf2", "tc50_buf3", "tc50_buf4"]].reset_index()
    table_rows = [
        [
            row["scenario"],
            format_pct(row["mean_annual_return"]),
            format_pct(row["min_annual_return"]),
            format_pct(row["mean_max_drawdown"]),
            format_pct(row["mean_fill_ratio"]),
            format_pct(row["mean_target_overlap"]),
            format_pct(row["mean_cash_weight"]),
        ]
        for _, row in platform_df.iterrows()
    ]
    table = ax_table.table(
        cellText=table_rows,
        colLabels=["候选", "平均净年化", "最低净年化", "平均回撤", "成交完成", "目标兑现", "平均现金"],
        loc="center",
        cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.35)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#cfd6e3")
        if row == 0:
            cell.set_facecolor("#2d3f57")
            cell.set_text_props(color="white", weight="bold")
        elif row % 2 == 0:
            cell.set_facecolor("#f3f6fa")

    fig.subplots_adjust(top=0.90, bottom=0.04, left=0.07, right=0.98, hspace=0.46)
    fig.savefig(TURNOVER_FIGURE_PATH, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return TURNOVER_FIGURE_PATH


def build_selected_capacity() -> Path:
    summary_df = pd.read_csv(CAPACITY_SUMMARY_PATH)
    if summary_df.empty:
        raise ValueError("Missing capacity summary data.")

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    configure_matplotlib()

    scenarios = ["baseline", "tc50_buf2"]
    colors = {"baseline": "#7f8792", "tc50_buf2": "#1f5b9d"}
    plot_df = summary_df[
        summary_df["scenario"].isin(scenarios)
        & (summary_df["participation_limit"].round(4) == 0.10)
        & (summary_df["capital"].isin([10_000_000, 30_000_000, 100_000_000]))
    ].copy()
    plot_df["capital_yi"] = plot_df["capital"] / 100_000_000

    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.3))
    ax_return, ax_fill = axes
    for scenario in scenarios:
        group = plot_df[plot_df["scenario"] == scenario].sort_values("capital_yi")
        ax_return.plot(
            group["capital_yi"],
            group["annual_return"] * 100,
            marker="o",
            linewidth=2.3,
            label=scenario,
            color=colors[scenario],
        )
        ax_fill.plot(
            group["capital_yi"],
            group["avg_target_overlap_weight"] * 100,
            marker="o",
            linewidth=2.3,
            label=scenario,
            color=colors[scenario],
        )

    ax_return.set_title("小规模资金 10% ADV 下净年化", fontsize=13.5, fontweight="bold")
    ax_return.set_xlabel("资金规模（亿元）")
    ax_return.set_ylabel("净年化（%）")
    ax_fill.set_title("小规模资金 10% ADV 下目标持仓兑现", fontsize=13.5, fontweight="bold")
    ax_fill.set_xlabel("资金规模（亿元）")
    ax_fill.set_ylabel("目标兑现（%）")
    for ax in axes:
        ax.set_xticks([0.1, 0.3, 1.0])
        ax.set_xticklabels(["1000万", "3000万", "1亿"])
        ax.grid(True, alpha=0.22)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.legend(frameon=False, loc="best")

    fig.tight_layout()
    fig.savefig(CAPACITY_FIGURE_PATH, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return CAPACITY_FIGURE_PATH


def build_core_parameter_stability() -> Path:
    ranking_df = pd.read_csv(CORE_RANKING_PATH)
    summary_df = pd.read_csv(CORE_SUMMARY_PATH)
    if ranking_df.empty or summary_df.empty:
        raise ValueError("Missing core parameter stability data.")

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    configure_matplotlib()

    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.9), gridspec_kw={"width_ratios": [1.05, 1]})
    ax_scatter, ax_heat = axes

    scatter = ax_scatter.scatter(
        -ranking_df["mean_max_drawdown"] * 100,
        ranking_df["mean_annual_return"] * 100,
        c=ranking_df["mean_cash_weight"] * 100,
        s=48 + ranking_df["mean_fill_ratio"] * 45,
        cmap="viridis_r",
        alpha=0.78,
        edgecolors="white",
        linewidths=0.6,
    )
    current_mask = (
        (ranking_df["long_prd"] == 20)
        & (ranking_df["short_prd"] == 5)
        & (ranking_df["channel_bins"] == 2)
        & (ranking_df["top_n"] == 100)
    )
    current = ranking_df[current_mask].iloc[0]
    ax_scatter.scatter(
        [-current["mean_max_drawdown"] * 100],
        [current["mean_annual_return"] * 100],
        s=150,
        facecolors="none",
        edgecolors="#d62728",
        linewidths=2.2,
        label="当前参数",
    )
    ax_scatter.annotate(
        "L20/S5/B2/N100",
        xy=(-current["mean_max_drawdown"] * 100, current["mean_annual_return"] * 100),
        xytext=(8, -12),
        textcoords="offset points",
        fontsize=9.5,
        color="#d62728",
    )
    ax_scatter.set_title("收益-回撤-现金权衡", fontsize=13.5, fontweight="bold", pad=9)
    ax_scatter.set_xlabel("平均最大回撤绝对值（%）")
    ax_scatter.set_ylabel("平均净年化（%）")
    ax_scatter.grid(True, alpha=0.22)
    ax_scatter.spines["top"].set_visible(False)
    ax_scatter.spines["right"].set_visible(False)
    ax_scatter.legend(frameon=False, loc="lower left")
    colorbar = fig.colorbar(scatter, ax=ax_scatter, fraction=0.045, pad=0.02)
    colorbar.set_label("平均现金（%）")

    meta_cols = ["scenario", "long_prd", "short_prd", "channel_bins", "top_n"]
    heat_df = summary_df.merge(ranking_df[meta_cols], on="scenario", how="left")
    heat_df = heat_df[
        (heat_df["capital"] == 500_000_000)
        & (heat_df["participation_limit"].round(4) == 0.10)
        & (heat_df["channel_bins"] == 2)
        & (heat_df["top_n"] == 100)
    ].copy()
    pivot = heat_df.pivot(index="long_prd", columns="short_prd", values="annual_return").sort_index()
    image = ax_heat.imshow(pivot.values * 100, cmap="RdYlGn", aspect="auto")
    ax_heat.set_title("固定 B2/N100：5亿、10% ADV 净年化", fontsize=13.5, fontweight="bold", pad=9)
    ax_heat.set_xticks(range(len(pivot.columns)))
    ax_heat.set_xticklabels(pivot.columns)
    ax_heat.set_yticks(range(len(pivot.index)))
    ax_heat.set_yticklabels(pivot.index)
    ax_heat.set_xlabel("short_prd")
    ax_heat.set_ylabel("long_prd")
    for i, long_prd in enumerate(pivot.index):
        for j, short_prd in enumerate(pivot.columns):
            ax_heat.text(j, i, f"{pivot.iloc[i, j] * 100:.1f}%", ha="center", va="center", fontsize=9)
            if long_prd == 20 and short_prd == 5:
                rect = plt.Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False, edgecolor="#1f5b9d", linewidth=2.2)
                ax_heat.add_patch(rect)
    colorbar_heat = fig.colorbar(image, ax=ax_heat, fraction=0.045, pad=0.02)
    colorbar_heat.set_label("净年化（%）")

    fig.tight_layout()
    fig.savefig(CORE_FIGURE_PATH, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return CORE_FIGURE_PATH


def main() -> None:
    for path in [
        build_nav_vs_benchmark(),
        build_turnover_platform(),
        build_selected_capacity(),
        build_core_parameter_stability(),
    ]:
        print(f"Saved figure: {path}")


if __name__ == "__main__":
    main()
