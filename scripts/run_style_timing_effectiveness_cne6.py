"""
生成 Barra CNE6 风格择时有效性分析。

输出：
1. 逐期逐因子的择时有效性明细
2. 风格择时有效性汇总
3. 风格择时有效性图片表

说明：
如果每期归因明细已经存在，则直接复用，避免重复扫描 factor_exposure_cne6.csv。
"""

import os
import sys

import pandas as pd


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.analysis import style_factor_attribution as core


def get_factor_cols():
    """从 factor_returns 表头读取 CNE6 风格因子列表。"""
    factor_cols = pd.read_csv(core.FACTOR_RETURNS_PATH, nrows=0).columns.tolist()
    return [col for col in factor_cols if col != "date"]


def load_or_build_attribution(factor_cols):
    """优先读取每期归因明细；不存在时重新计算。"""
    if os.path.exists(core.PERIOD_OUTPUT_PATH):
        attribution_df = pd.read_csv(core.PERIOD_OUTPUT_PATH, parse_dates=["date", "signal_date", "next_date"])
        return attribution_df

    portfolio_df = core.load_portfolio_returns()
    attribution_df = core.build_attribution(portfolio_df, factor_cols)
    attribution_df.to_csv(core.PERIOD_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    return attribution_df


def main():
    """主流程：计算并保存风格择时有效性分析。"""
    factor_cols = get_factor_cols()
    attribution_df = load_or_build_attribution(factor_cols)
    timing_detail_df, timing_summary_df = core.build_timing_effectiveness(attribution_df, factor_cols)

    timing_detail_df.to_csv(core.TIMING_EFFECTIVENESS_DETAIL_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    timing_summary_df.to_csv(core.TIMING_EFFECTIVENESS_SUMMARY_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    core.plot_timing_effectiveness_table(timing_summary_df)

    print(f"Saved timing effectiveness detail: {core.TIMING_EFFECTIVENESS_DETAIL_OUTPUT_PATH}")
    print(f"Saved timing effectiveness summary: {core.TIMING_EFFECTIVENESS_SUMMARY_OUTPUT_PATH}")
    print(f"Saved timing effectiveness table: {core.TIMING_EFFECTIVENESS_TABLE_OUTPUT_PATH}")
    print(timing_summary_df.head(12).to_string(index=False))


if __name__ == "__main__":
    main()
