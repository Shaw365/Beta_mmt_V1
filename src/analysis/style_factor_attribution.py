import ast
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 输出目录与参数后缀，和 run_factor_timing_v3.py 生成的结果保持一致
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output", "cne6")
DATA_DIR = os.path.join(OUTPUT_DIR, "data")
IMAGE_DIR = os.path.join(OUTPUT_DIR, "images")

SUFFIX = "l20_s5_b2_e1_n100"

# 输入数据：
# 1. portfolio_returns: 策略每期实际持仓和组合收益
# 2. factor_exposure: 股票在信号日的 Barra CNE6 风格暴露
# 3. factor_returns: Barra CNE6 风格因子日收益
PORTFOLIO_RETURNS_PATH = os.path.join(DATA_DIR, f"portfolio_returns_{SUFFIX}.csv")
FACTOR_EXPOSURE_PATH = os.path.join(DATA_DIR, "factor_exposure_cne6.csv")
FACTOR_RETURNS_PATH = os.path.join(DATA_DIR, "factor_returns_cne6.csv")
OPTIMAL_VECTORS_PATH = os.path.join(DATA_DIR, f"optimal_vectors_{SUFFIX}.csv")

# 输出数据：
# period: 每个调仓周期的风格因子贡献明细
# summary: 全样本风格因子贡献汇总
# regime_summary: 分时段风格因子贡献汇总
PERIOD_OUTPUT_PATH = os.path.join(DATA_DIR, f"style_factor_attribution_period_{SUFFIX}.csv")
SUMMARY_OUTPUT_PATH = os.path.join(DATA_DIR, f"style_factor_attribution_summary_{SUFFIX}.csv")
PLOT_OUTPUT_PATH = os.path.join(IMAGE_DIR, f"style_factor_attribution_summary_{SUFFIX}.png")
REGIME_SUMMARY_OUTPUT_PATH = os.path.join(DATA_DIR, f"style_factor_attribution_regime_summary_{SUFFIX}.csv")
REGIME_PLOT_OUTPUT_PATH = os.path.join(IMAGE_DIR, f"style_factor_attribution_regime_summary_{SUFFIX}.png")
TIMING_EFFECTIVENESS_DETAIL_OUTPUT_PATH = os.path.join(DATA_DIR, f"style_timing_effectiveness_detail_{SUFFIX}.csv")
TIMING_EFFECTIVENESS_SUMMARY_OUTPUT_PATH = os.path.join(DATA_DIR, f"style_timing_effectiveness_summary_{SUFFIX}.csv")
TIMING_EFFECTIVENESS_TABLE_OUTPUT_PATH = os.path.join(IMAGE_DIR, f"style_timing_effectiveness_table_{SUFFIX}.png")
HOLDING_EXPOSURE_QUALITY_DETAIL_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"style_holding_exposure_quality_detail_{SUFFIX}.csv"
)
HOLDING_EXPOSURE_QUALITY_SUMMARY_OUTPUT_PATH = os.path.join(
    DATA_DIR, f"style_holding_exposure_quality_summary_{SUFFIX}.csv"
)
HOLDING_EXPOSURE_QUALITY_TABLE_OUTPUT_PATH = os.path.join(
    IMAGE_DIR, f"style_holding_exposure_quality_table_{SUFFIX}.png"
)

def parse_selected_codes(value):
    """将 CSV 中保存的股票列表字符串还原为 Python list。"""
    if isinstance(value, list):
        return value
    if pd.isna(value):
        return []
    return ast.literal_eval(value)


def load_portfolio_returns():
    """加载策略周度收益，并还原每期实际持仓股票列表。"""
    df = pd.read_csv(PORTFOLIO_RETURNS_PATH)
    df["date"] = pd.to_datetime(df["date"])
    df["signal_date"] = pd.to_datetime(df["signal_date"])
    df["next_date"] = pd.to_datetime(df["next_date"])
    df["selected_codes"] = df["selected_codes"].apply(parse_selected_codes)
    return df


def compute_factor_weekly_returns(portfolio_df, factor_cols):
    """
    将 Barra CNE6 因子日收益转换为和策略持有期一致的区间收益。

    归因使用的是策略每期从 date 持有到 next_date 的收益，因此因子收益
    也要按同样的区间复合，避免用日频收益直接和周度组合收益相乘。
    """
    factor_returns = pd.read_csv(FACTOR_RETURNS_PATH, parse_dates=["date"])
    factor_returns = factor_returns.sort_values("date").set_index("date")
    factor_nav = (1.0 + factor_returns[factor_cols]).cumprod()

    records = []
    available_dates = factor_nav.index
    for row in portfolio_df.itertuples(index=False):
        start_pos = available_dates.get_indexer([row.date], method="nearest")[0]
        end_pos = available_dates.get_indexer([row.next_date], method="nearest")[0]
        if start_pos < 0 or end_pos < 0 or end_pos <= start_pos:
            continue
        weekly_return = factor_nav.iloc[end_pos] / factor_nav.iloc[start_pos] - 1.0
        weekly_return.name = row.date
        records.append(weekly_return)

    weekly_df = pd.DataFrame(records)
    weekly_df.index.name = "date"
    return weekly_df.reset_index()


def load_selected_exposures(portfolio_df, factor_cols):
    """
    读取每期实际持仓在 signal_date 的平均风格暴露。

    factor_exposure_cne6.csv 文件较大，这里按 chunk 流式读取，只保留
    策略实际选中的股票和信号日期，避免一次性把 3GB+ 暴露数据载入内存。
    """
    wanted = {}
    for row in portfolio_df.itertuples(index=False):
        date_key = row.signal_date.strftime("%Y-%m-%d")
        wanted.setdefault(date_key, set()).update(row.selected_codes)

    exposure_records = []
    usecols = ["date", "code"] + factor_cols
    for chunk in pd.read_csv(FACTOR_EXPOSURE_PATH, usecols=usecols, chunksize=500_000):
        chunk = chunk[chunk["date"].isin(wanted)]
        if chunk.empty:
            continue
        keep_mask = chunk.apply(lambda row: row["code"] in wanted[row["date"]], axis=1)
        kept = chunk.loc[keep_mask]
        if not kept.empty:
            exposure_records.append(kept)

    if not exposure_records:
        raise RuntimeError("No matching factor exposure rows were found for selected holdings.")

    exposure_df = pd.concat(exposure_records, ignore_index=True)
    exposure_df["date"] = pd.to_datetime(exposure_df["date"])

    avg_exposure = (
        exposure_df.groupby("date", as_index=False)[factor_cols]
        .mean()
        .rename(columns={"date": "signal_date"})
    )
    avg_exposure["matched_stock_count"] = exposure_df.groupby("date")["code"].nunique().values
    return avg_exposure


def build_attribution(portfolio_df, factor_cols):
    """
    构建每期风格收益归因。

    核心口径：
        单因子贡献 = 组合在信号日的等权平均因子暴露 * 持有期因子收益

    style_factor_return 是所有 CNE6 风格因子贡献之和；
    residual_return 是策略实际收益减去风格因子解释部分，包含个股特异收益、
    行业/国家因子缺失、模型误差以及线性归因近似带来的差异。
    """
    factor_weekly = compute_factor_weekly_returns(portfolio_df, factor_cols)
    avg_exposure = load_selected_exposures(portfolio_df, factor_cols)

    result = portfolio_df[["date", "signal_date", "next_date", "return", "num_stocks", "turnover"]].copy()
    result = result.merge(factor_weekly, on="date", how="left", suffixes=("", "_factor_return"))
    result = result.merge(avg_exposure, on="signal_date", how="left", suffixes=("_factor_return", "_exposure"))

    contribution_cols = []
    for factor in factor_cols:
        factor_return_col = f"{factor}_factor_return"
        exposure_col = f"{factor}_exposure"
        if factor_return_col not in result.columns:
            result = result.rename(columns={factor: factor_return_col})
        result[f"{factor}_contribution"] = result[exposure_col] * result[factor_return_col]
        contribution_cols.append(f"{factor}_contribution")

    result["style_factor_return"] = result[contribution_cols].sum(axis=1)
    result["residual_return"] = result["return"] - result["style_factor_return"]
    return result


def summarize(attribution_df, factor_cols):
    """汇总一段样本内各风格因子的算术累计贡献。"""
    rows = []
    total_strategy_return = attribution_df["return"].sum()
    total_style_return = attribution_df["style_factor_return"].sum()
    for factor in factor_cols:
        contribution = attribution_df[f"{factor}_contribution"].sum()
        avg_abs_exposure = attribution_df[f"{factor}_exposure"].abs().mean()
        avg_factor_return = attribution_df[f"{factor}_factor_return"].mean()
        rows.append(
            {
                "factor": factor,
                "total_contribution": contribution,
                "contribution_pct_of_strategy_arithmetic": contribution / total_strategy_return,
                "contribution_pct_of_style_arithmetic": contribution / total_style_return,
                "avg_abs_exposure": avg_abs_exposure,
                "avg_weekly_factor_return": avg_factor_return,
            }
        )

    summary = pd.DataFrame(rows).sort_values("total_contribution", ascending=False)

    residual = attribution_df["residual_return"].sum()
    summary = pd.concat(
        [
            summary,
            pd.DataFrame(
                [
                    {
                        "factor": "STYLE_TOTAL",
                        "total_contribution": total_style_return,
                        "contribution_pct_of_strategy_arithmetic": total_style_return / total_strategy_return,
                        "contribution_pct_of_style_arithmetic": 1.0,
                        "avg_abs_exposure": pd.NA,
                        "avg_weekly_factor_return": pd.NA,
                    },
                    {
                        "factor": "RESIDUAL",
                        "total_contribution": residual,
                        "contribution_pct_of_strategy_arithmetic": residual / total_strategy_return,
                        "contribution_pct_of_style_arithmetic": pd.NA,
                        "avg_abs_exposure": pd.NA,
                        "avg_weekly_factor_return": pd.NA,
                    },
                    {
                        "factor": "STRATEGY_TOTAL",
                        "total_contribution": total_strategy_return,
                        "contribution_pct_of_strategy_arithmetic": 1.0,
                        "contribution_pct_of_style_arithmetic": pd.NA,
                        "avg_abs_exposure": pd.NA,
                        "avg_weekly_factor_return": pd.NA,
                    },
                ]
            ),
        ],
        ignore_index=True,
    )
    return summary


def summarize_regimes(attribution_df, factor_cols, regimes):
    """按传入的时间段配置分别做风格收益归因汇总。"""
    regime_summaries = []

    for regime_name, start_date, end_date in regimes:
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)
        regime_df = attribution_df[(attribution_df["date"] >= start) & (attribution_df["date"] <= end)].copy()
        if regime_df.empty:
            continue

        summary = summarize(regime_df, factor_cols)
        summary.insert(0, "regime", regime_name)
        summary.insert(1, "start_date", start_date)
        summary.insert(2, "end_date", end_date)
        summary.insert(3, "weeks", len(regime_df))
        summary.insert(4, "geometric_strategy_return", (1.0 + regime_df["return"]).prod() - 1.0)
        summary.insert(5, "arithmetic_strategy_return", regime_df["return"].sum())
        summary.insert(6, "arithmetic_style_return", regime_df["style_factor_return"].sum())
        summary.insert(7, "arithmetic_residual_return", regime_df["residual_return"].sum())
        regime_summaries.append(summary)

    if not regime_summaries:
        return pd.DataFrame()
    return pd.concat(regime_summaries, ignore_index=True)


def _signed_hit(left, right):
    """判断两个数值方向是否一致；任一侧为 0 或缺失时不计入命中率分母。"""
    left_sign = np.sign(left)
    right_sign = np.sign(right)
    valid = (left_sign != 0) & (right_sign != 0) & pd.notna(left_sign) & pd.notna(right_sign)
    if not valid:
        return np.nan
    return left_sign == right_sign


def build_timing_effectiveness(attribution_df, factor_cols):
    """
    构建风格择时有效性明细和汇总。

    三个核心问题：
    1. 信号命中：optimal_vector 的方向和后续因子收益方向是否一致；
    2. 暴露兑现：实际持仓平均暴露方向是否和 optimal_vector 一致；
    3. 持仓命中：实际持仓平均暴露方向和后续因子收益方向是否一致。
    """
    optimal_df = pd.read_csv(OPTIMAL_VECTORS_PATH, parse_dates=["date"])
    optimal_df = optimal_df.rename(columns={"date": "signal_date"})

    base_cols = ["date", "signal_date", "next_date"]
    merged = attribution_df[base_cols].merge(
        optimal_df[["signal_date"] + factor_cols],
        on="signal_date",
        how="left",
    )

    detail_rows = []
    for factor in factor_cols:
        factor_df = merged[base_cols + [factor]].copy()
        factor_df = factor_df.rename(columns={factor: "signal"})
        factor_df["factor"] = factor
        factor_df["exposure"] = attribution_df[f"{factor}_exposure"].values
        factor_df["factor_return"] = attribution_df[f"{factor}_factor_return"].values
        factor_df["contribution"] = attribution_df[f"{factor}_contribution"].values

        factor_df["signal_direction"] = np.sign(factor_df["signal"])
        factor_df["exposure_direction"] = np.sign(factor_df["exposure"])
        factor_df["factor_return_direction"] = np.sign(factor_df["factor_return"])

        factor_df["signal_hit"] = [
            _signed_hit(signal, factor_return)
            for signal, factor_return in zip(factor_df["signal"], factor_df["factor_return"])
        ]
        factor_df["exposure_alignment"] = [
            _signed_hit(signal, exposure)
            for signal, exposure in zip(factor_df["signal"], factor_df["exposure"])
        ]
        factor_df["exposure_hit"] = [
            _signed_hit(exposure, factor_return)
            for exposure, factor_return in zip(factor_df["exposure"], factor_df["factor_return"])
        ]

        # 正数代表方向押对后的风格收益；不乘持仓暴露，用来单独评估“择时方向”。
        factor_df["signal_direction_factor_return"] = factor_df["signal_direction"] * factor_df["factor_return"]
        factor_df["signal_weighted_factor_return"] = factor_df["signal"] * factor_df["factor_return"]
        factor_df["exposure_direction_factor_return"] = factor_df["exposure_direction"] * factor_df["factor_return"]
        factor_df["positive_contribution"] = factor_df["contribution"] > 0
        detail_rows.append(factor_df)

    detail_df = pd.concat(detail_rows, ignore_index=True)

    summary_rows = []
    for factor, group in detail_df.groupby("factor", sort=False):
        summary_rows.append(
            {
                "factor": factor,
                "periods": len(group),
                "signal_hit_rate": group["signal_hit"].mean(),
                "signal_exposure_alignment_rate": group["exposure_alignment"].mean(),
                "exposure_hit_rate": group["exposure_hit"].mean(),
                "positive_contribution_rate": group["positive_contribution"].mean(),
                "signal_direction_factor_return_sum": group["signal_direction_factor_return"].sum(),
                "signal_weighted_factor_return_sum": group["signal_weighted_factor_return"].sum(),
                "exposure_direction_factor_return_sum": group["exposure_direction_factor_return"].sum(),
                "raw_factor_return_sum": group["factor_return"].sum(),
                "total_contribution": group["contribution"].sum(),
                "avg_signal": group["signal"].mean(),
                "avg_abs_signal": group["signal"].abs().mean(),
                "avg_exposure": group["exposure"].mean(),
                "avg_abs_exposure": group["exposure"].abs().mean(),
                "avg_factor_return": group["factor_return"].mean(),
            }
        )

    summary_df = pd.DataFrame(summary_rows)
    summary_df = summary_df.sort_values("signal_direction_factor_return_sum", ascending=False)
    return detail_df, summary_df


def load_selected_exposure_detail_with_percentiles(portfolio_df, factor_cols, strength_quantile=0.8):
    """
    读取每期选中股票的逐股风格暴露，并给出它在当日全市场中的暴露强度分位。

    这里不只保留选中股票，而是先保留所有信号日的全市场暴露，用全市场样本计算
    |暴露|分位数；随后再筛出策略实际持仓。这样可以区分“方向对”与“暴露是否足够强”。
    """
    wanted = {}
    for row in portfolio_df.itertuples(index=False):
        date_key = row.signal_date.strftime("%Y-%m-%d")
        wanted.setdefault(date_key, set()).update(row.selected_codes)

    exposure_records = []
    usecols = ["date", "code"] + factor_cols
    wanted_dates = set(wanted)
    for chunk in pd.read_csv(FACTOR_EXPOSURE_PATH, usecols=usecols, chunksize=500_000):
        chunk = chunk[chunk["date"].isin(wanted_dates)]
        if not chunk.empty:
            exposure_records.append(chunk)

    if not exposure_records:
        raise RuntimeError("No matching factor exposure rows were found for signal dates.")

    exposure_df = pd.concat(exposure_records, ignore_index=True)

    percentile_cols = []
    threshold_cols = []
    for factor in factor_cols:
        percentile_col = f"{factor}_abs_percentile"
        threshold_col = f"{factor}_strong_threshold"
        abs_exposure = exposure_df[factor].abs()
        exposure_df[percentile_col] = abs_exposure.groupby(exposure_df["date"]).rank(pct=True)
        exposure_df[threshold_col] = abs_exposure.groupby(exposure_df["date"]).transform(
            lambda series: series.quantile(strength_quantile)
        )
        percentile_cols.append(percentile_col)
        threshold_cols.append(threshold_col)

    selected_mask = exposure_df.apply(lambda row: row["code"] in wanted[row["date"]], axis=1)
    selected_exposure_df = exposure_df.loc[
        selected_mask, ["date", "code"] + factor_cols + percentile_cols + threshold_cols
    ].copy()
    selected_exposure_df["date"] = pd.to_datetime(selected_exposure_df["date"])
    selected_exposure_df = selected_exposure_df.rename(columns={"date": "signal_date"})
    return selected_exposure_df


def build_holding_exposure_quality(attribution_df, portfolio_df, factor_cols, strength_quantile=0.8):
    """
    构建逐期逐因子的持仓内部暴露质量表。

    这张表回答的是：同一期选中的股票内部，究竟是多数股票都暴露在后续赚钱方向，
    还是少数高暴露股票把组合平均暴露拉到了正确方向。
    """
    selected_exposure_df = load_selected_exposure_detail_with_percentiles(
        portfolio_df, factor_cols, strength_quantile=strength_quantile
    )

    period_info = attribution_df[["date", "signal_date", "next_date"]].copy()
    detail_rows = []

    for factor in factor_cols:
        factor_period = period_info.copy()
        factor_period["factor"] = factor
        factor_period["signal"] = attribution_df.get(factor, pd.Series(np.nan, index=attribution_df.index))
        factor_period["avg_exposure"] = attribution_df[f"{factor}_exposure"].values
        factor_period["factor_return"] = attribution_df[f"{factor}_factor_return"].values
        factor_period["portfolio_factor_contribution"] = attribution_df[f"{factor}_contribution"].values

        factor_selected = selected_exposure_df[
            ["signal_date", "code", factor, f"{factor}_abs_percentile"]
        ].rename(columns={factor: "stock_exposure", f"{factor}_abs_percentile": "abs_exposure_percentile"})

        factor_selected = factor_selected.merge(
            factor_period[
                [
                    "date",
                    "signal_date",
                    "next_date",
                    "factor",
                    "factor_return",
                    "portfolio_factor_contribution",
                ]
            ],
            on="signal_date",
            how="left",
        )

        factor_selected["stock_contribution"] = factor_selected["stock_exposure"] * factor_selected["factor_return"]
        factor_selected["correct_direction"] = [
            _signed_hit(exposure, factor_return)
            for exposure, factor_return in zip(
                factor_selected["stock_exposure"], factor_selected["factor_return"]
            )
        ]
        factor_selected["strong_exposure"] = factor_selected["abs_exposure_percentile"] >= strength_quantile
        factor_selected["strong_correct"] = (
            (factor_selected["correct_direction"] == True) & factor_selected["strong_exposure"]
        )

        rows = []
        for (_, signal_date), group in factor_selected.groupby(["factor", "signal_date"], sort=False):
            factor_period_row = factor_period[factor_period["signal_date"] == signal_date].iloc[0]
            abs_stock_contribution = group["stock_contribution"].abs()
            total_abs_stock_contribution = abs_stock_contribution.sum()
            top_n = max(1, int(np.ceil(len(group) * 0.2)))
            top_abs_group = group.reindex(group["stock_exposure"].abs().sort_values(ascending=False).index).head(top_n)
            correct_mask = group["correct_direction"] == True
            wrong_mask = group["correct_direction"] == False
            wrong_group = group[wrong_mask]

            rows.append(
                {
                    "date": factor_period_row["date"],
                    "signal_date": signal_date,
                    "next_date": factor_period_row["next_date"],
                    "factor": factor,
                    "selected_stock_count": group["code"].nunique(),
                    "avg_exposure": factor_period_row["avg_exposure"],
                    "median_exposure": group["stock_exposure"].median(),
                    "avg_abs_exposure": group["stock_exposure"].abs().mean(),
                    "factor_return": factor_period_row["factor_return"],
                    "portfolio_factor_contribution": factor_period_row["portfolio_factor_contribution"],
                    "correct_direction_stock_pct": correct_mask.mean(),
                    "wrong_direction_stock_pct": wrong_mask.mean(),
                    "strong_stock_pct": group["strong_exposure"].mean(),
                    "strong_correct_stock_pct": group["strong_correct"].mean(),
                    "top_abs_exposure_contribution_share": (
                        top_abs_group["stock_contribution"].abs().sum() / total_abs_stock_contribution
                        if total_abs_stock_contribution != 0
                        else np.nan
                    ),
                    "wrong_direction_contribution_drag": (
                        wrong_group["stock_contribution"].sum() / len(group)
                        if len(group) > 0
                        else np.nan
                    ),
                }
            )
        detail_rows.append(pd.DataFrame(rows))

    detail_df = pd.concat(detail_rows, ignore_index=True)

    summary_rows = []
    for factor, group in detail_df.groupby("factor", sort=False):
        summary_rows.append(
            {
                "factor": factor,
                "periods": len(group),
                "avg_correct_direction_stock_pct": group["correct_direction_stock_pct"].mean(),
                "avg_strong_stock_pct": group["strong_stock_pct"].mean(),
                "avg_strong_correct_stock_pct": group["strong_correct_stock_pct"].mean(),
                "avg_top_abs_exposure_contribution_share": group[
                    "top_abs_exposure_contribution_share"
                ].mean(),
                "avg_abs_exposure": group["avg_abs_exposure"].mean(),
                "median_abs_avg_exposure": group["avg_exposure"].abs().median(),
                "total_contribution": group["portfolio_factor_contribution"].sum(),
                "avg_factor_return": group["factor_return"].mean(),
            }
        )

    summary_df = pd.DataFrame(summary_rows).sort_values(
        ["avg_strong_correct_stock_pct", "total_contribution"], ascending=False
    )
    return detail_df, summary_df


def plot_summary(summary_df):
    """绘制全样本风格因子贡献条形图。"""
    os.makedirs(IMAGE_DIR, exist_ok=True)
    plot_df = summary_df[~summary_df["factor"].isin(["STYLE_TOTAL", "RESIDUAL", "STRATEGY_TOTAL"])].copy()
    plot_df = plot_df.sort_values("total_contribution")

    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    colors = plot_df["total_contribution"].map(lambda x: "#2E8B57" if x >= 0 else "#C44E52")
    fig, ax = plt.subplots(figsize=(12, 8))
    ax.barh(plot_df["factor"], plot_df["total_contribution"] * 100.0, color=colors)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_title("Barra CNE6 风格因子收益归因")
    ax.set_xlabel("累计贡献（算术累加，%）")
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(PLOT_OUTPUT_PATH, dpi=200)
    plt.close(fig)


def plot_regime_summary(regime_summary_df, attribution_df, regimes):
    """绘制带净值曲线联动的不同时段风格因子贡献热力图。"""
    os.makedirs(IMAGE_DIR, exist_ok=True)
    plot_df = regime_summary_df[
        ~regime_summary_df["factor"].isin(["STYLE_TOTAL", "RESIDUAL", "STRATEGY_TOTAL"])
    ].copy()
    if plot_df.empty:
        return

    matrix = plot_df.pivot(index="factor", columns="regime", values="total_contribution").fillna(0.0)
    matrix = matrix[[regime[0] for regime in regimes if regime[0] in matrix.columns]]
    matrix = matrix.loc[matrix.abs().sum(axis=1).sort_values(ascending=False).index]

    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    regime_meta = (
        regime_summary_df[regime_summary_df["factor"] == "STRATEGY_TOTAL"]
        .set_index("regime")
        .to_dict("index")
    )
    col_labels = []
    for regime_name in matrix.columns:
        meta = regime_meta.get(regime_name, {})
        start_date = meta.get("start_date", "")
        end_date = meta.get("end_date", "")
        regime_return = meta.get("geometric_strategy_return", 0.0)
        col_labels.append(f"{regime_name}\n{start_date} ~ {end_date}\n策略 {regime_return:.1%}")

    fig = plt.figure(figsize=(14, 11), constrained_layout=True)
    gs = fig.add_gridspec(2, 1, height_ratios=[1.0, 2.2], hspace=0.32)

    # 上半部分：策略累计净值，并用色块标出归因分段，和下方热力图列形成对应
    ax_nav = fig.add_subplot(gs[0])
    nav_df = attribution_df[["date", "return"]].copy()
    nav_df["cumulative_return"] = (1.0 + nav_df["return"]).cumprod()
    ax_nav.plot(nav_df["date"], nav_df["cumulative_return"], color="#2E86AB", linewidth=2.0, label="策略累计净值")

    colors = ["#F4A261", "#8AB17D", "#6D9DC5", "#E76F51", "#B56576"]
    ymax = nav_df["cumulative_return"].max()
    for idx, (regime_name, start_date, end_date) in enumerate(regimes):
        if regime_name not in matrix.columns:
            continue
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)
        color = colors[idx % len(colors)]
        ax_nav.axvspan(start, end, color=color, alpha=0.22, label=regime_name)
        regime_nav = nav_df[(nav_df["date"] >= start) & (nav_df["date"] <= end)]
        if not regime_nav.empty:
            x_mid = start + (end - start) / 2
            y_text = min(regime_nav["cumulative_return"].max() * 1.05, ymax * 1.08)
            ax_nav.text(x_mid, y_text, str(idx + 1), ha="center", va="bottom", fontsize=11, fontweight="bold")

    ax_nav.set_title("策略累计净值与归因分段")
    ax_nav.set_ylabel("累计净值")
    ax_nav.grid(True, alpha=0.25)
    ax_nav.legend(loc="upper left", ncol=2, fontsize=8)
    ax_nav.xaxis.set_major_locator(mdates.YearLocator())
    ax_nav.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    # 下半部分：每个分段内的风格因子算术累计贡献
    ax = fig.add_subplot(gs[1])
    values = matrix.values * 100.0
    bound = max(abs(values.min()), abs(values.max()))
    image = ax.imshow(values, cmap="RdYlGn", aspect="auto", vmin=-bound, vmax=bound)

    ax.set_xticks(range(len(matrix.columns)))
    ax.set_xticklabels(col_labels, rotation=0, ha="center")
    ax.set_yticks(range(len(matrix.index)))
    ax.set_yticklabels(matrix.index)
    ax.set_title("Barra CNE6 风格因子分时段收益归因")

    for y in range(values.shape[0]):
        for x in range(values.shape[1]):
            ax.text(x, y, f"{values[y, x]:.1f}", ha="center", va="center", fontsize=8)

    colorbar = fig.colorbar(image, ax=ax)
    colorbar.set_label("算术累计贡献 (%)")
    fig.savefig(REGIME_PLOT_OUTPUT_PATH, dpi=200)
    plt.close(fig)


def _format_percent(value):
    if pd.isna(value):
        return ""
    return f"{value * 100:.1f}%"


def _format_number(value):
    if pd.isna(value):
        return ""
    return f"{value:.2f}"


def plot_timing_effectiveness_table(effectiveness_summary_df):
    """绘制风格择时有效性汇总表。"""
    os.makedirs(IMAGE_DIR, exist_ok=True)
    if effectiveness_summary_df.empty:
        return

    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    display_df = effectiveness_summary_df.copy()
    display_df = display_df.sort_values("signal_direction_factor_return_sum", ascending=False)
    display_df = display_df[
        [
            "factor",
            "signal_hit_rate",
            "signal_exposure_alignment_rate",
            "exposure_hit_rate",
            "signal_direction_factor_return_sum",
            "exposure_direction_factor_return_sum",
            "total_contribution",
            "avg_abs_signal",
            "avg_abs_exposure",
        ]
    ]

    display_df.columns = [
        "因子",
        "信号命中率",
        "信号-持仓一致率",
        "持仓命中率",
        "信号方向收益",
        "暴露方向收益",
        "实际贡献",
        "平均|信号|",
        "平均|暴露|",
    ]

    rate_cols = ["信号命中率", "信号-持仓一致率", "持仓命中率"]
    return_cols = ["信号方向收益", "暴露方向收益", "实际贡献"]
    for col in rate_cols + return_cols:
        display_df[col] = display_df[col].map(_format_percent)
    for col in ["平均|信号|", "平均|暴露|"]:
        display_df[col] = display_df[col].map(_format_number)

    fig, (ax, ax_note) = plt.subplots(
        2,
        1,
        figsize=(18, 13.5),
        gridspec_kw={"height_ratios": [4.3, 1.1]},
    )
    ax.axis("off")
    ax_note.axis("off")
    ax.set_title("Barra CNE6 风格择时有效性表", fontsize=18, fontweight="bold", pad=18)

    table = ax.table(
        cellText=display_df.values,
        colLabels=display_df.columns,
        cellLoc="center",
        colLoc="center",
        loc="center",
        bbox=[0.0, 0.0, 1.0, 0.94],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1.0, 1.25)

    raw_df = effectiveness_summary_df.sort_values("signal_direction_factor_return_sum", ascending=False).reset_index(drop=True)
    col_index = {name: idx for idx, name in enumerate(display_df.columns)}
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#D0D0D0")
        if row == 0:
            cell.set_facecolor("#2E4057")
            cell.set_text_props(color="white", weight="bold")
            continue

        raw_row = raw_df.iloc[row - 1]
        if col == col_index["因子"]:
            cell.set_facecolor("#F5F5F5")
            cell.set_text_props(weight="bold")
        elif col in [col_index["信号命中率"], col_index["信号-持仓一致率"], col_index["持仓命中率"]]:
            metric_name = {
                col_index["信号命中率"]: "signal_hit_rate",
                col_index["信号-持仓一致率"]: "signal_exposure_alignment_rate",
                col_index["持仓命中率"]: "exposure_hit_rate",
            }[col]
            value = raw_row[metric_name]
            if value >= 0.55:
                cell.set_facecolor("#E4F4E8")
            elif value <= 0.45:
                cell.set_facecolor("#FBE7E5")
        elif col in [col_index["信号方向收益"], col_index["暴露方向收益"], col_index["实际贡献"]]:
            metric_name = {
                col_index["信号方向收益"]: "signal_direction_factor_return_sum",
                col_index["暴露方向收益"]: "exposure_direction_factor_return_sum",
                col_index["实际贡献"]: "total_contribution",
            }[col]
            value = raw_row[metric_name]
            if value > 0:
                cell.set_facecolor("#E4F4E8")
            elif value < 0:
                cell.set_facecolor("#FBE7E5")

    note_rows = [
        ["信号命中率", "sign(optimal_vector) 与后续因子收益方向一致的比例", "检验择时信号本身是否押对"],
        ["信号-持仓一致率", "sign(optimal_vector) 与实际持仓平均暴露方向一致的比例", "检验选股后是否兑现了想要的风格方向"],
        ["持仓命中率", "sign(实际持仓平均暴露) 与后续因子收益方向一致的比例", "检验实际持仓风格方向是否赚钱"],
        ["信号方向收益", "sign(optimal_vector) × 后续因子收益的累计值", "不乘实际暴露，单独评估择时方向"],
        ["暴露方向收益", "sign(实际持仓平均暴露) × 后续因子收益的累计值", "只看实际持仓方向，不看暴露大小"],
        ["实际贡献", "实际持仓平均暴露 × 后续因子收益的累计值", "真实风格归因口径，包含暴露大小"],
        ["平均|信号| / 平均|暴露|", "择时信号和实际持仓风格暴露的平均绝对强度", "衡量信号强弱与持仓风格浓度"],
        ["标色规则", "命中率 >= 55% 或收益/贡献为正标绿；命中率 <= 45% 或收益/贡献为负标红", "白色表示中性区间或数值接近 0"],
    ]
    note_table = ax_note.table(
        cellText=note_rows,
        colLabels=["指标", "定义", "用途 / 判读"],
        cellLoc="left",
        colLoc="center",
        loc="center",
        colWidths=[0.18, 0.48, 0.34],
        bbox=[0.0, 0.0, 1.0, 0.98],
    )
    note_table.auto_set_font_size(False)
    note_table.set_fontsize(9)
    note_table.scale(1.0, 1.2)

    for (row, col), cell in note_table.get_celld().items():
        cell.set_edgecolor("#D0D0D0")
        if row == 0:
            cell.set_facecolor("#4A5568")
            cell.set_text_props(color="white", weight="bold", ha="center")
        elif col == 0:
            cell.set_facecolor("#F5F5F5")
            cell.set_text_props(weight="bold")
        else:
            cell.set_facecolor("#FAFAFA")

    fig.savefig(TIMING_EFFECTIVENESS_TABLE_OUTPUT_PATH, dpi=200, bbox_inches="tight")
    plt.close(fig)


def plot_holding_exposure_quality_table(quality_summary_df, strength_quantile=0.8):
    """绘制持仓内部暴露质量汇总表。"""
    os.makedirs(IMAGE_DIR, exist_ok=True)
    if quality_summary_df.empty:
        return

    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    display_df = quality_summary_df.copy()
    display_df = display_df.sort_values(
        ["avg_strong_correct_stock_pct", "total_contribution"], ascending=False
    )
    display_df = display_df[
        [
            "factor",
            "avg_correct_direction_stock_pct",
            "avg_strong_stock_pct",
            "avg_strong_correct_stock_pct",
            "avg_top_abs_exposure_contribution_share",
            "avg_abs_exposure",
            "total_contribution",
        ]
    ]
    display_df.columns = [
        "因子",
        "方向正确股票占比",
        "高暴露股票占比",
        "高暴露且方向正确",
        "前20%高暴露贡献占比",
        "平均|暴露|",
        "实际贡献",
    ]

    rate_cols = [
        "方向正确股票占比",
        "高暴露股票占比",
        "高暴露且方向正确",
        "前20%高暴露贡献占比",
        "实际贡献",
    ]
    for col in rate_cols:
        display_df[col] = display_df[col].map(_format_percent)
    display_df["平均|暴露|"] = display_df["平均|暴露|"].map(_format_number)

    fig, (ax, ax_note) = plt.subplots(
        2,
        1,
        figsize=(16, 12),
        gridspec_kw={"height_ratios": [4.2, 1.1]},
    )
    ax.axis("off")
    ax_note.axis("off")
    ax.set_title("Barra CNE6 持仓内部风格暴露质量表", fontsize=18, fontweight="bold", pad=18)

    table = ax.table(
        cellText=display_df.values,
        colLabels=display_df.columns,
        cellLoc="center",
        colLoc="center",
        loc="center",
        bbox=[0.0, 0.0, 1.0, 0.94],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1.0, 1.25)

    raw_df = quality_summary_df.sort_values(
        ["avg_strong_correct_stock_pct", "total_contribution"], ascending=False
    ).reset_index(drop=True)
    col_index = {name: idx for idx, name in enumerate(display_df.columns)}
    high_exposure_base = 1.0 - strength_quantile
    high_exposure_green = high_exposure_base + 0.05
    high_exposure_red = max(high_exposure_base - 0.05, 0.0)
    high_correct_base = high_exposure_base * 0.5
    high_correct_green = high_correct_base + 0.03
    high_correct_red = max(high_correct_base - 0.03, 0.0)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#D0D0D0")
        if row == 0:
            cell.set_facecolor("#2E4057")
            cell.set_text_props(color="white", weight="bold")
            continue

        raw_row = raw_df.iloc[row - 1]
        if col == col_index["因子"]:
            cell.set_facecolor("#F5F5F5")
            cell.set_text_props(weight="bold")
        elif col in [
            col_index["方向正确股票占比"],
            col_index["高暴露股票占比"],
            col_index["高暴露且方向正确"],
        ]:
            metric_name = {
                col_index["方向正确股票占比"]: "avg_correct_direction_stock_pct",
                col_index["高暴露股票占比"]: "avg_strong_stock_pct",
                col_index["高暴露且方向正确"]: "avg_strong_correct_stock_pct",
            }[col]
            value = raw_row[metric_name]
            if col == col_index["方向正确股票占比"]:
                green_threshold = 0.55
                red_threshold = 0.45
            elif col == col_index["高暴露股票占比"]:
                green_threshold = high_exposure_green
                red_threshold = high_exposure_red
            else:
                green_threshold = high_correct_green
                red_threshold = high_correct_red

            if value >= green_threshold:
                cell.set_facecolor("#E4F4E8")
            elif value <= red_threshold:
                cell.set_facecolor("#FBE7E5")
        elif col == col_index["前20%高暴露贡献占比"]:
            value = raw_row["avg_top_abs_exposure_contribution_share"]
            if value <= 0.35:
                cell.set_facecolor("#E4F4E8")
            elif value >= 0.55:
                cell.set_facecolor("#FBE7E5")
        elif col == col_index["实际贡献"]:
            value = raw_row["total_contribution"]
            if value > 0:
                cell.set_facecolor("#E4F4E8")
            elif value < 0:
                cell.set_facecolor("#FBE7E5")

    note_rows = [
        ["方向正确股票占比", "每期选中股票中，sign(股票暴露) 与后续因子收益方向一致的比例", "看持仓内部是否多数股票押对方向"],
        ["高暴露股票占比", "股票 |暴露| 位于当日全市场前 20% 的比例", "看策略是否选到了风格特征足够鲜明的股票"],
        ["高暴露且方向正确", "同时满足高暴露与方向正确的股票比例", "衡量高风格暴露是否真的落在赚钱方向"],
        ["前20%高暴露贡献占比", "持仓内 |暴露| 最高 20% 股票贡献的绝对值占比", "越高越说明归因更依赖少数股票"],
        ["实际贡献", "平均持仓暴露 × 后续因子收益的累计值", "与风格收益归因表中的口径一致"],
        [
            "标色规则",
            f"方向正确 >=55% 绿、<=45% 红；高暴露以 {high_exposure_base:.0%} 为基准，>={high_exposure_green:.0%} 绿、<={high_exposure_red:.0%} 红",
            f"高暴露命中以 {high_correct_base:.0%} 为基准，>={high_correct_green:.0%} 绿、<={high_correct_red:.0%} 红；集中度高红",
        ],
    ]
    note_table = ax_note.table(
        cellText=note_rows,
        colLabels=["指标", "定义", "用途 / 判读"],
        cellLoc="left",
        colLoc="center",
        loc="center",
        colWidths=[0.20, 0.48, 0.32],
        bbox=[0.0, 0.0, 1.0, 0.98],
    )
    note_table.auto_set_font_size(False)
    note_table.set_fontsize(9)
    note_table.scale(1.0, 1.2)

    for (row, col), cell in note_table.get_celld().items():
        cell.set_edgecolor("#D0D0D0")
        if row == 0:
            cell.set_facecolor("#4A5568")
            cell.set_text_props(color="white", weight="bold", ha="center")
        elif col == 0:
            cell.set_facecolor("#F5F5F5")
            cell.set_text_props(weight="bold")
        else:
            cell.set_facecolor("#FAFAFA")

    fig.savefig(HOLDING_EXPOSURE_QUALITY_TABLE_OUTPUT_PATH, dpi=200, bbox_inches="tight")
    plt.close(fig)


def main(regimes):
    """主流程：加载数据、计算归因、保存汇总和图片。"""
    os.makedirs(DATA_DIR, exist_ok=True)
    portfolio_df = load_portfolio_returns()

    # 因子列直接从 factor_returns 表头获取，避免手工维护 CNE6 因子列表
    factor_cols = pd.read_csv(FACTOR_RETURNS_PATH, nrows=0).columns.tolist()
    factor_cols = [col for col in factor_cols if col != "date"]

    attribution_df = build_attribution(portfolio_df, factor_cols)
    summary_df = summarize(attribution_df, factor_cols)
    regime_summary_df = summarize_regimes(attribution_df, factor_cols, regimes)
    timing_detail_df, timing_summary_df = build_timing_effectiveness(attribution_df, factor_cols)
    quality_detail_df, quality_summary_df = build_holding_exposure_quality(attribution_df, portfolio_df, factor_cols)

    attribution_df.to_csv(PERIOD_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    summary_df.to_csv(SUMMARY_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    regime_summary_df.to_csv(REGIME_SUMMARY_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    timing_detail_df.to_csv(TIMING_EFFECTIVENESS_DETAIL_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    timing_summary_df.to_csv(TIMING_EFFECTIVENESS_SUMMARY_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    quality_detail_df.to_csv(HOLDING_EXPOSURE_QUALITY_DETAIL_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    quality_summary_df.to_csv(HOLDING_EXPOSURE_QUALITY_SUMMARY_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    plot_summary(summary_df)
    plot_regime_summary(regime_summary_df, attribution_df, regimes)
    plot_timing_effectiveness_table(timing_summary_df)
    plot_holding_exposure_quality_table(quality_summary_df)

    print(f"Saved period attribution: {PERIOD_OUTPUT_PATH}")
    print(f"Saved attribution summary: {SUMMARY_OUTPUT_PATH}")
    print(f"Saved attribution plot: {PLOT_OUTPUT_PATH}")
    print(f"Saved regime attribution summary: {REGIME_SUMMARY_OUTPUT_PATH}")
    print(f"Saved regime attribution plot: {REGIME_PLOT_OUTPUT_PATH}")
    print(f"Saved timing effectiveness detail: {TIMING_EFFECTIVENESS_DETAIL_OUTPUT_PATH}")
    print(f"Saved timing effectiveness summary: {TIMING_EFFECTIVENESS_SUMMARY_OUTPUT_PATH}")
    print(f"Saved timing effectiveness table: {TIMING_EFFECTIVENESS_TABLE_OUTPUT_PATH}")
    print(f"Saved holding exposure quality detail: {HOLDING_EXPOSURE_QUALITY_DETAIL_OUTPUT_PATH}")
    print(f"Saved holding exposure quality summary: {HOLDING_EXPOSURE_QUALITY_SUMMARY_OUTPUT_PATH}")
    print(f"Saved holding exposure quality table: {HOLDING_EXPOSURE_QUALITY_TABLE_OUTPUT_PATH}")
    print(summary_df.head(12).to_string(index=False))
    print(regime_summary_df.groupby("regime").head(8).to_string(index=False))
    print(timing_summary_df.head(12).to_string(index=False))
    print(quality_summary_df.head(12).to_string(index=False))


if __name__ == "__main__":
    raise SystemExit("Please run one of the scripts in scripts/ and pass the regime configuration there.")
