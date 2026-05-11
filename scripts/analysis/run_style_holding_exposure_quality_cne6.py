"""
生成 Barra CNE6 持仓内部风格暴露质量分析。

输出：
1. 逐期逐因子的持仓暴露质量明细
2. 持仓暴露质量汇总表
3. 持仓暴露质量图片表

说明：
这张表不是看组合平均暴露，而是深入到每一期选中的股票内部，观察有多少股票
真的暴露在后续赚钱的风格方向上，以及风格贡献是否过度集中在少数高暴露股票上。
"""

import os
import sys

import pandas as pd


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.analysis import style_factor_attribution as core


# 暴露强度阈值：|暴露| 位于当日全市场前 20% 的股票，定义为“高暴露股票”。
STRENGTH_QUANTILE = 0.8


def get_factor_cols():
    """从 factor_returns 表头读取 CNE6 风格因子列。"""
    factor_cols = pd.read_csv(core.FACTOR_RETURNS_PATH, nrows=0).columns.tolist()
    return [col for col in factor_cols if col != "date"]


def load_or_build_attribution(portfolio_df, factor_cols):
    """优先读取每期归因明细；不存在时重新计算。"""
    if os.path.exists(core.PERIOD_OUTPUT_PATH):
        return pd.read_csv(core.PERIOD_OUTPUT_PATH, parse_dates=["date", "signal_date", "next_date"])

    attribution_df = core.build_attribution(portfolio_df, factor_cols)
    attribution_df.to_csv(core.PERIOD_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    return attribution_df


def main():
    """主流程：计算并保存持仓内部暴露质量分析。"""
    portfolio_df = core.load_portfolio_returns()
    factor_cols = get_factor_cols()
    attribution_df = load_or_build_attribution(portfolio_df, factor_cols)

    quality_detail_df, quality_summary_df = core.build_holding_exposure_quality(
        attribution_df,
        portfolio_df,
        factor_cols,
        strength_quantile=STRENGTH_QUANTILE,
    )

    quality_detail_df.to_csv(
        core.HOLDING_EXPOSURE_QUALITY_DETAIL_OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )
    quality_summary_df.to_csv(
        core.HOLDING_EXPOSURE_QUALITY_SUMMARY_OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )
    core.plot_holding_exposure_quality_table(quality_summary_df, strength_quantile=STRENGTH_QUANTILE)

    print(f"Saved holding exposure quality detail: {core.HOLDING_EXPOSURE_QUALITY_DETAIL_OUTPUT_PATH}")
    print(f"Saved holding exposure quality summary: {core.HOLDING_EXPOSURE_QUALITY_SUMMARY_OUTPUT_PATH}")
    print(f"Saved holding exposure quality table: {core.HOLDING_EXPOSURE_QUALITY_TABLE_OUTPUT_PATH}")
    print(quality_summary_df.head(12).to_string(index=False))


if __name__ == "__main__":
    main()
