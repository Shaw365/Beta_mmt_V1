"""Build figure 5.1 with Alpha and original strategy NAV/drawdown comparison."""

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
ALPHA_SUFFIX = "l20_s5_b2_e1_n500_alpha50"
ORIGINAL_SUFFIX = "l20_s5_b2_e1_n100"
OUTPUT_PATH = IMAGE_DIR / f"final_main_nav_vs_benchmark_{ALPHA_SUFFIX}.png"


def configure_matplotlib() -> None:
    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def load_strategy_nav(suffix: str, nav_col: str) -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / f"portfolio_returns_{suffix}.csv", parse_dates=["date"]).sort_values("date")
    df[nav_col] = (1.0 + df["return"]).cumprod()
    return df[["date", nav_col]]


def main() -> None:
    configure_matplotlib()
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    benchmark_df = pd.read_csv(
        DATA_DIR / f"benchmark_relative_{ALPHA_SUFFIX}.csv",
        parse_dates=["date"],
    ).sort_values("date")
    alpha_nav = load_strategy_nav(ALPHA_SUFFIX, "alpha_nav")
    original_nav = load_strategy_nav(ORIGINAL_SUFFIX, "original_nav")

    df = (
        benchmark_df[["date", "csi500_nav", "csi1000_nav"]]
        .merge(alpha_nav, on="date", how="inner")
        .merge(original_nav, on="date", how="inner")
        .sort_values("date")
    )
    if df.empty:
        raise ValueError("No overlapping NAV data found for figure 5.1.")

    df["alpha_drawdown"] = df["alpha_nav"] / df["alpha_nav"].cummax() - 1.0
    df["original_drawdown"] = df["original_nav"] / df["original_nav"].cummax() - 1.0

    fig, (ax_nav, ax_dd) = plt.subplots(
        2,
        1,
        figsize=(11.6, 6.4),
        sharex=True,
        gridspec_kw={"height_ratios": [3.05, 1.20], "hspace": 0.08},
    )

    nav_series = [
        ("Alpha版", "alpha_nav", "#1f5b9d", 2.35, "-"),
        ("原始策略", "original_nav", "#7b61a8", 2.00, "-"),
        ("中证500", "csi500_nav", "#7c8a2e", 1.55, "--"),
        ("中证1000", "csi1000_nav", "#c46f2d", 1.55, "--"),
    ]
    for label, col, color, linewidth, linestyle in nav_series:
        ax_nav.plot(
            df["date"],
            df[col],
            label=f"{label}: {df[col].iloc[-1]:.2f}",
            color=color,
            linewidth=linewidth,
            linestyle=linestyle,
        )

    final_date = df["date"].iloc[-1]
    for _label, col, color, _linewidth, _linestyle in nav_series:
        ax_nav.annotate(
            f"{df[col].iloc[-1]:.2f}",
            xy=(final_date, df[col].iloc[-1]),
            xytext=(8, 0),
            textcoords="offset points",
            va="center",
            fontsize=9.5,
            color=color,
        )

    ax_nav.set_title("Barra Top100 与 Barra Top500 -> Alpha Top50：累计净值、基准与回撤", fontsize=14.5, fontweight="bold", pad=12)
    ax_nav.set_ylabel("累计净值")
    ax_nav.grid(True, axis="y", alpha=0.22)
    ax_nav.spines["top"].set_visible(False)
    ax_nav.spines["right"].set_visible(False)
    ax_nav.legend(loc="upper left", frameon=False, ncol=4)

    dd_series = [
        ("Alpha版回撤", "alpha_drawdown", "#e04b3f", 1.45, 0.18),
        ("原始策略回撤", "original_drawdown", "#7b61a8", 1.35, 0.10),
    ]
    for label, col, color, linewidth, alpha in dd_series:
        dd_pct = df[col] * 100
        ax_dd.fill_between(df["date"], dd_pct, 0, color=color, alpha=alpha, linewidth=0)
        ax_dd.plot(df["date"], dd_pct, color=color, linewidth=linewidth, label=label)

        min_dd_idx = df[col].idxmin()
        ax_dd.annotate(
            f"{dd_pct.loc[min_dd_idx]:.1f}%",
            xy=(df.loc[min_dd_idx, "date"], dd_pct.loc[min_dd_idx]),
            xytext=(8, -2),
            textcoords="offset points",
            fontsize=8.8,
            color=color,
            va="top",
        )

    ax_dd.axhline(0, color="#667085", linewidth=0.8, alpha=0.7)
    ax_dd.set_ylabel("回撤 (%)")
    ax_dd.grid(True, axis="y", alpha=0.22)
    ax_dd.spines["top"].set_visible(False)
    ax_dd.spines["right"].set_visible(False)
    ax_dd.legend(loc="lower left", frameon=False, ncol=2)
    ax_dd.xaxis.set_major_locator(mdates.YearLocator())
    ax_dd.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    fig.subplots_adjust(top=0.88, bottom=0.12, left=0.08, right=0.95, hspace=0.08)
    fig.savefig(OUTPUT_PATH, dpi=220, bbox_inches="tight")
    plt.close(fig)
    print(f"PNG: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
