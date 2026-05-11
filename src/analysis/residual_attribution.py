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
IMAGE_DIR = os.path.join(OUTPUT_DIR, "images")

SUFFIX = "l20_s5_b2_e1_n100"

PORTFOLIO_RETURNS_PATH = os.path.join(DATA_DIR, f"portfolio_returns_{SUFFIX}.csv")
STYLE_ATTRIBUTION_PERIOD_PATH = os.path.join(
    DATA_DIR, f"style_factor_attribution_period_{SUFFIX}.csv"
)
FACTOR_EXPOSURE_PATH = os.path.join(DATA_DIR, "factor_exposure_cne6.csv")
FACTOR_RETURNS_PATH = os.path.join(DATA_DIR, "factor_returns_cne6.csv")
PRICE_DATA_PATH = os.path.join(DATA_DIR, "price_data_cne6.csv")
INDEX_DATA_PATH = os.path.join(DATA_DIR, "index_eod.csv")

RESIDUAL_ATTRIBUTION_PERIOD_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"residual_attribution_period_{SUFFIX}.csv"
)
RESIDUAL_ATTRIBUTION_STOCK_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"residual_attribution_stock_{SUFFIX}.csv"
)
RESIDUAL_ATTRIBUTION_BUCKET_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"residual_attribution_bucket_{SUFFIX}.csv"
)
RESIDUAL_ATTRIBUTION_SUMMARY_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"residual_attribution_summary_{SUFFIX}.csv"
)
RESIDUAL_ATTRIBUTION_PLOT_OUTPUT_PATH = os.path.join(
    IMAGE_DIR, f"residual_attribution_{SUFFIX}.png"
)

INDEX_NAME_MAP = {
    "000905.SH": "csi500",
    "000852.SH": "csi1000",
}

BUCKET_LABELS = ["Q1低暴露", "Q2", "Q3", "Q4", "Q5高暴露"]


def parse_selected_codes(value):
    """还原 portfolio_returns CSV 中保存的持仓股票列表。"""
    if isinstance(value, list):
        return value
    if pd.isna(value):
        return []
    return ast.literal_eval(value)


def load_portfolio_returns():
    """读取策略每期收益和持仓。"""
    df = pd.read_csv(PORTFOLIO_RETURNS_PATH)
    df["date"] = pd.to_datetime(df["date"])
    df["signal_date"] = pd.to_datetime(df["signal_date"])
    df["next_date"] = pd.to_datetime(df["next_date"])
    df["selected_codes"] = df["selected_codes"].apply(parse_selected_codes)
    return df


def load_style_attribution_period():
    """读取此前生成的风格归因逐期明细。"""
    df = pd.read_csv(
        STYLE_ATTRIBUTION_PERIOD_PATH,
        parse_dates=["date", "signal_date", "next_date"],
    )
    return df


def get_factor_cols():
    """从 factor_returns 表头读取 CNE6 风格因子列。"""
    cols = pd.read_csv(FACTOR_RETURNS_PATH, nrows=0).columns.tolist()
    return [col for col in cols if col != "date"]


def load_price_data():
    """读取价格数据，用于计算持有期股票收益。"""
    price_df = pd.read_csv(PRICE_DATA_PATH, usecols=["date", "code", "pct_chg"])
    price_df["date"] = pd.to_datetime(price_df["date"])
    return price_df


def compute_weekly_stock_returns(price_df, portfolio_df):
    """按策略持有期计算每只股票的区间收益。"""
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

    weekly_df = pd.DataFrame(records)
    weekly_df.index.name = "date"
    return weekly_df


def compute_weekly_index_returns(portfolio_df):
    """计算中证500和中证1000在策略持有期内的区间收益。"""
    if not os.path.exists(INDEX_DATA_PATH):
        return pd.DataFrame({"date": portfolio_df["date"]})

    index_df = pd.read_csv(INDEX_DATA_PATH, parse_dates=["date"])
    index_nav = index_df.pivot(index="date", columns="code", values="close").sort_index()
    available_dates = index_nav.index

    records = []
    for row in portfolio_df.itertuples(index=False):
        start_pos = available_dates.get_indexer([row.date], method="nearest")[0]
        end_pos = available_dates.get_indexer([row.next_date], method="nearest")[0]
        if start_pos < 0 or end_pos < 0 or end_pos <= start_pos:
            continue
        returns = index_nav.iloc[end_pos] / index_nav.iloc[start_pos] - 1.0
        record = {"date": row.date}
        for code, name in INDEX_NAME_MAP.items():
            if code in returns.index:
                record[f"{name}_return"] = returns[code]
        records.append(record)

    return pd.DataFrame(records)


def load_signal_date_exposures(signal_dates, factor_cols, bucket_factors):
    """
    读取信号日全市场暴露，并为分组因子计算当日全市场分位。

    这里保留全市场样本是为了让 SIZE/LIQUIDITY 等分组有明确的市场相对含义。
    """
    wanted_dates = {pd.Timestamp(date).strftime("%Y-%m-%d") for date in signal_dates}
    usecols = ["date", "code"] + factor_cols

    records = []
    for chunk in pd.read_csv(FACTOR_EXPOSURE_PATH, usecols=usecols, chunksize=500_000):
        chunk = chunk[chunk["date"].isin(wanted_dates)]
        if not chunk.empty:
            records.append(chunk)

    if not records:
        raise RuntimeError("No factor exposure rows were found for selected signal dates.")

    exposure_df = pd.concat(records, ignore_index=True)
    exposure_df["date"] = pd.to_datetime(exposure_df["date"])

    for factor in bucket_factors:
        if factor not in exposure_df.columns:
            continue
        percentile_col = f"{factor}_percentile"
        bucket_col = f"{factor}_bucket"
        exposure_df[percentile_col] = exposure_df.groupby("date")[factor].rank(pct=True)
        exposure_df[bucket_col] = pd.cut(
            exposure_df[percentile_col],
            bins=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
            labels=BUCKET_LABELS,
            include_lowest=True,
        )

    return exposure_df.sort_values(["date", "code"]).reset_index(drop=True)


def build_stock_and_bucket_residual(
    portfolio_df,
    attribution_df,
    weekly_returns_df,
    exposure_df,
    factor_cols,
    bucket_factors,
):
    """
    构建逐股 residual 和分组 residual。

    单只股票 residual = 股票实际持有期收益 - 股票信号日风格暴露 * 持有期风格因子收益。
    由于组合等权，分组贡献按 1/N 股票权重加总。
    """
    exposure_by_date = exposure_df.groupby("date", sort=False)
    attribution_by_date = attribution_df.set_index("date")

    stock_rows = []
    bucket_rows = []
    period_rows = []

    for row in portfolio_df.itertuples(index=False):
        if row.date not in attribution_by_date.index:
            continue
        if row.date not in weekly_returns_df.index:
            continue
        if row.signal_date not in exposure_by_date.groups:
            continue

        attribution_row = attribution_by_date.loc[row.date]
        selected_returns = weekly_returns_df.loc[row.date, row.selected_codes].dropna()
        if selected_returns.empty:
            continue

        current_exposure = exposure_by_date.get_group(row.signal_date)
        selected_exposure = current_exposure[current_exposure["code"].isin(selected_returns.index)].copy()
        selected_exposure = selected_exposure.merge(
            selected_returns.rename("stock_return"),
            left_on="code",
            right_index=True,
            how="inner",
        )
        if selected_exposure.empty:
            continue

        factor_return_vector = np.array(
            [attribution_row[f"{factor}_factor_return"] for factor in factor_cols],
            dtype=float,
        )
        exposure_matrix = selected_exposure[factor_cols].astype(float).fillna(0.0).values
        selected_exposure["stock_style_return"] = exposure_matrix @ factor_return_vector
        selected_exposure["stock_residual_return"] = (
            selected_exposure["stock_return"] - selected_exposure["stock_style_return"]
        )
        selected_exposure["stock_weight"] = 1.0 / len(selected_exposure)

        stock_style_return = (
            selected_exposure["stock_style_return"] * selected_exposure["stock_weight"]
        ).sum()
        stock_residual_return = (
            selected_exposure["stock_residual_return"] * selected_exposure["stock_weight"]
        ).sum()

        period_rows.append(
            {
                "date": row.date,
                "signal_date": row.signal_date,
                "next_date": row.next_date,
                "selected_stock_count": len(selected_exposure),
                "strategy_return": attribution_row["return"],
                "style_factor_return": attribution_row["style_factor_return"],
                "residual_return": attribution_row["residual_return"],
                "stock_model_style_return": stock_style_return,
                "stock_model_residual_return": stock_residual_return,
                "style_static_vs_stock_gap": attribution_row["style_factor_return"] - stock_style_return,
                "residual_static_vs_stock_gap": attribution_row["residual_return"] - stock_residual_return,
            }
        )

        selected_exposure["date"] = row.date
        selected_exposure["signal_date"] = row.signal_date
        selected_exposure["next_date"] = row.next_date
        stock_cols = [
            "date",
            "signal_date",
            "next_date",
            "code",
            "stock_weight",
            "stock_return",
            "stock_style_return",
            "stock_residual_return",
        ]
        for factor in bucket_factors:
            for suffix in ["", "_percentile", "_bucket"]:
                col = f"{factor}{suffix}"
                if col in selected_exposure.columns:
                    stock_cols.append(col)
        stock_rows.append(selected_exposure[stock_cols])

        for factor in bucket_factors:
            bucket_col = f"{factor}_bucket"
            if bucket_col not in selected_exposure.columns:
                continue
            for bucket, group in selected_exposure.groupby(bucket_col, observed=True):
                bucket_weight = group["stock_weight"].sum()
                actual_contribution = (group["stock_return"] * group["stock_weight"]).sum()
                style_contribution = (group["stock_style_return"] * group["stock_weight"]).sum()
                residual_contribution = (group["stock_residual_return"] * group["stock_weight"]).sum()
                bucket_rows.append(
                    {
                        "date": row.date,
                        "signal_date": row.signal_date,
                        "next_date": row.next_date,
                        "bucket_factor": factor,
                        "bucket": str(bucket),
                        "stock_count": len(group),
                        "bucket_weight": bucket_weight,
                        "actual_contribution": actual_contribution,
                        "style_contribution": style_contribution,
                        "residual_contribution": residual_contribution,
                    }
                )

    stock_df = pd.concat(stock_rows, ignore_index=True) if stock_rows else pd.DataFrame()
    bucket_df = pd.DataFrame(bucket_rows)
    period_stock_df = pd.DataFrame(period_rows)
    return stock_df, bucket_df, period_stock_df


def build_residual_period_detail(attribution_df, period_stock_df, weekly_returns_df, index_weekly_df):
    """合并风格 residual、全市场等权收益和指数收益，形成逐期 residual 拆解。"""
    period_df = attribution_df[
        ["date", "signal_date", "next_date", "return", "style_factor_return", "residual_return"]
    ].copy()
    period_df = period_df.rename(columns={"return": "strategy_return"})

    universe_return = weekly_returns_df.mean(axis=1, skipna=True).rename("universe_equal_weight_return")
    universe_df = universe_return.reset_index().rename(columns={"index": "date"})
    period_df = period_df.merge(universe_df, on="date", how="left")
    period_df = period_df.merge(index_weekly_df, on="date", how="left")
    period_df = period_df.merge(
        period_stock_df[
            [
                "date",
                "selected_stock_count",
                "stock_model_style_return",
                "stock_model_residual_return",
                "style_static_vs_stock_gap",
                "residual_static_vs_stock_gap",
            ]
        ],
        on="date",
        how="left",
    )

    period_df["residual_after_universe"] = (
        period_df["residual_return"] - period_df["universe_equal_weight_return"]
    )
    if "csi500_return" in period_df.columns:
        period_df["residual_after_csi500"] = period_df["residual_return"] - period_df["csi500_return"]
    if "csi1000_return" in period_df.columns:
        period_df["residual_after_csi1000"] = period_df["residual_return"] - period_df["csi1000_return"]
    period_df["strategy_excess_universe"] = (
        period_df["strategy_return"] - period_df["universe_equal_weight_return"]
    )
    return period_df


def summarize_components(period_df):
    """汇总 residual 的主要可加组件。"""
    total_strategy = period_df["strategy_return"].sum()
    component_specs = [
        ("STYLE_TOTAL", "style_factor_return", "风格因子解释部分"),
        ("RESIDUAL_TOTAL", "residual_return", "策略收益减去风格解释后的 residual"),
        ("UNIVERSE_COMMON", "universe_equal_weight_return", "全市场等权收益，近似回归截距/共同项"),
        ("SELECTION_AFTER_UNIVERSE", "residual_after_universe", "residual 扣除全市场等权收益后的选股残差"),
        ("STOCK_MODEL_RESIDUAL", "stock_model_residual_return", "逐股实际收益减逐股风格预测后的 residual"),
    ]
    if "csi500_return" in period_df.columns:
        component_specs.append(("CSI500_COMMON", "csi500_return", "中证500区间收益"))
        component_specs.append(("RESIDUAL_AFTER_CSI500", "residual_after_csi500", "residual 扣除中证500后的剩余"))
    if "csi1000_return" in period_df.columns:
        component_specs.append(("CSI1000_COMMON", "csi1000_return", "中证1000区间收益"))
        component_specs.append(("RESIDUAL_AFTER_CSI1000", "residual_after_csi1000", "residual 扣除中证1000后的剩余"))

    rows = []
    for component, col, description in component_specs:
        if col not in period_df.columns:
            continue
        total = period_df[col].sum()
        rows.append(
            {
                "component": component,
                "description": description,
                "total_contribution": total,
                "pct_of_strategy_arithmetic": total / total_strategy,
                "avg_weekly_return": period_df[col].mean(),
                "positive_rate": (period_df[col] > 0).mean(),
            }
        )

    rows.append(
        {
            "component": "STRATEGY_TOTAL",
            "description": "策略算术收益合计",
            "total_contribution": total_strategy,
            "pct_of_strategy_arithmetic": 1.0,
            "avg_weekly_return": period_df["strategy_return"].mean(),
            "positive_rate": (period_df["strategy_return"] > 0).mean(),
        }
    )
    return pd.DataFrame(rows)


def summarize_buckets(bucket_df):
    """汇总不同暴露分组对 residual 的贡献。"""
    if bucket_df.empty:
        return pd.DataFrame()

    summary = (
        bucket_df.groupby(["bucket_factor", "bucket"], observed=True)
        .agg(
            periods=("date", "nunique"),
            avg_bucket_weight=("bucket_weight", "mean"),
            total_actual_contribution=("actual_contribution", "sum"),
            total_style_contribution=("style_contribution", "sum"),
            total_residual_contribution=("residual_contribution", "sum"),
            avg_residual_contribution=("residual_contribution", "mean"),
        )
        .reset_index()
    )
    factor_total = summary.groupby("bucket_factor")["total_residual_contribution"].transform("sum")
    summary["pct_of_bucket_factor_residual"] = summary["total_residual_contribution"] / factor_total
    return summary.sort_values(["bucket_factor", "bucket"]).reset_index(drop=True)


def _format_percent(value):
    if pd.isna(value):
        return ""
    return f"{value * 100:.1f}%"


def plot_residual_attribution(period_df, component_summary_df, bucket_summary_df):
    """绘制 residual 归因总览图。"""
    os.makedirs(IMAGE_DIR, exist_ok=True)
    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    fig = plt.figure(figsize=(16, 13), constrained_layout=True)
    gs = fig.add_gridspec(3, 1, height_ratios=[1.3, 1.0, 1.6])

    ax_line = fig.add_subplot(gs[0])
    line_cols = [
        ("strategy_return", "策略算术累计"),
        ("style_factor_return", "风格累计"),
        ("residual_return", "Residual累计"),
        ("universe_equal_weight_return", "全市场等权累计"),
        ("residual_after_universe", "Residual扣全市场"),
    ]
    for col, label in line_cols:
        if col in period_df.columns:
            ax_line.plot(period_df["date"], period_df[col].cumsum(), label=label, linewidth=1.8)
    ax_line.axhline(0, color="black", linewidth=0.8)
    ax_line.set_title("Residual 归因：时间序列累计贡献")
    ax_line.set_ylabel("算术累计收益")
    ax_line.grid(True, alpha=0.25)
    ax_line.legend(loc="upper left", ncol=3, fontsize=9)

    ax_bar = fig.add_subplot(gs[1])
    bar_df = component_summary_df[
        component_summary_df["component"].isin(
            ["STYLE_TOTAL", "UNIVERSE_COMMON", "SELECTION_AFTER_UNIVERSE", "RESIDUAL_TOTAL"]
        )
    ].copy()
    colors = bar_df["total_contribution"].map(lambda value: "#2E8B57" if value >= 0 else "#C44E52")
    ax_bar.barh(bar_df["component"], bar_df["total_contribution"] * 100.0, color=colors)
    ax_bar.axvline(0, color="black", linewidth=0.8)
    ax_bar.set_title("Residual 主拆解")
    ax_bar.set_xlabel("算术累计贡献 (%)")
    ax_bar.grid(axis="x", alpha=0.25)

    ax_heat = fig.add_subplot(gs[2])
    if not bucket_summary_df.empty:
        matrix = bucket_summary_df.pivot(
            index="bucket_factor",
            columns="bucket",
            values="total_residual_contribution",
        ).fillna(0.0)
        matrix = matrix[[label for label in BUCKET_LABELS if label in matrix.columns]]
        values = matrix.values * 100.0
        bound = max(abs(values.min()), abs(values.max())) if values.size else 1.0
        image = ax_heat.imshow(values, cmap="RdYlGn", aspect="auto", vmin=-bound, vmax=bound)
        ax_heat.set_xticks(range(len(matrix.columns)))
        ax_heat.set_xticklabels(matrix.columns)
        ax_heat.set_yticks(range(len(matrix.index)))
        ax_heat.set_yticklabels(matrix.index)
        ax_heat.set_title("按信号日市场暴露分组的 residual 贡献")
        for y in range(values.shape[0]):
            for x in range(values.shape[1]):
                ax_heat.text(x, y, f"{values[y, x]:.1f}", ha="center", va="center", fontsize=9)
        colorbar = fig.colorbar(image, ax=ax_heat)
        colorbar.set_label("算术累计 residual 贡献 (%)")
    else:
        ax_heat.axis("off")

    fig.savefig(RESIDUAL_ATTRIBUTION_PLOT_OUTPUT_PATH, dpi=200, bbox_inches="tight")
    plt.close(fig)


def run_residual_attribution(bucket_factors):
    """主流程：生成 residual 归因明细、汇总和图表。"""
    portfolio_df = load_portfolio_returns()
    attribution_df = load_style_attribution_period()
    factor_cols = get_factor_cols()
    price_df = load_price_data()

    weekly_returns_df = compute_weekly_stock_returns(price_df, portfolio_df)
    index_weekly_df = compute_weekly_index_returns(portfolio_df)
    exposure_df = load_signal_date_exposures(portfolio_df["signal_date"].unique(), factor_cols, bucket_factors)

    stock_df, bucket_period_df, period_stock_df = build_stock_and_bucket_residual(
        portfolio_df,
        attribution_df,
        weekly_returns_df,
        exposure_df,
        factor_cols,
        bucket_factors,
    )
    period_df = build_residual_period_detail(
        attribution_df,
        period_stock_df,
        weekly_returns_df,
        index_weekly_df,
    )
    component_summary_df = summarize_components(period_df)
    bucket_summary_df = summarize_buckets(bucket_period_df)
    plot_residual_attribution(period_df, component_summary_df, bucket_summary_df)

    return period_df, stock_df, bucket_summary_df, component_summary_df
