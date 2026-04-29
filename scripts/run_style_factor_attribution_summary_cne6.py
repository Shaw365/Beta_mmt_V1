"""
生成 Barra CNE6 风格因子全样本收益归因。

输出：
1. 每期风格归因明细
2. 全样本风格归因汇总
3. 全样本风格归因条形图
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


def main():
    """主流程：计算并保存全样本风格收益归因。"""
    portfolio_df = core.load_portfolio_returns()
    factor_cols = get_factor_cols()

    attribution_df = core.build_attribution(portfolio_df, factor_cols)
    summary_df = core.summarize(attribution_df, factor_cols)

    attribution_df.to_csv(core.PERIOD_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    summary_df.to_csv(core.SUMMARY_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    core.plot_summary(summary_df)

    print(f"Saved period attribution: {core.PERIOD_OUTPUT_PATH}")
    print(f"Saved attribution summary: {core.SUMMARY_OUTPUT_PATH}")
    print(f"Saved attribution plot: {core.PLOT_OUTPUT_PATH}")
    print(summary_df.head(12).to_string(index=False))


if __name__ == "__main__":
    main()
