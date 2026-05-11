"""
生成 Barra CNE6 风格因子分时段收益归因。

输出：
1. 分时段风格归因汇总
2. 带策略净值区间标注的分时段归因热力图

说明：
如果每期归因明细已经存在，则直接复用，避免重复扫描 factor_exposure_cne6.csv。
"""

import os
import sys

import pandas as pd


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.analysis import style_factor_attribution as core


# 分时段设置：
# 这里按策略净值曲线的形态拆成“平稳收益期 + 两段跃迁期”。
# 如果想测试其他口径，只需要改这里的起止日期后重新运行脚本。
REGIMES = [
    ("steady_2020_to_2024_pre_jump", "2020-02-17", "2024-09-18"),
    ("jump_2024_q4", "2024-09-23", "2024-12-09"),
    ("jump_2025_mid", "2025-04-07", "2025-09-29"),
]


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
    """主流程：计算并保存分时段风格收益归因。"""
    factor_cols = get_factor_cols()
    attribution_df = load_or_build_attribution(factor_cols)
    regime_summary_df = core.summarize_regimes(attribution_df, factor_cols, REGIMES)

    regime_summary_df.to_csv(core.REGIME_SUMMARY_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    core.plot_regime_summary(regime_summary_df, attribution_df, REGIMES)

    print(f"Saved regime attribution summary: {core.REGIME_SUMMARY_OUTPUT_PATH}")
    print(f"Saved regime attribution plot: {core.REGIME_PLOT_OUTPUT_PATH}")
    print(regime_summary_df.groupby("regime").head(8).to_string(index=False))


if __name__ == "__main__":
    main()
