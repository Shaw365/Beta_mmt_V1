"""
生成 Barra CNE6 风格择时策略的交易成本压力测试。

输出：
1. 不同交易成本假设下的逐期净收益明细
2. 不同交易成本假设下的绩效汇总
3. 不同交易成本假设下的年度表现
4. 交易成本压力测试图
"""

import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.analysis import transaction_cost_stress as core


# 成本档位，单位 bp。这里的 bp 是单边交易成本，10bp = 0.10%。
COST_BPS_LIST = [0, 5, 10, 20, 30, 50, 100]

# 当前策略输出的 turnover 是“单边换手率”。1.0 表示按单边换手口径扣成本；
# 如果想用更保守的买卖双边成交额口径，可以改成 2.0。
TURNOVER_MULTIPLIER = 1.0

# 图里展示的成本档位。摘要 CSV 仍保留 COST_BPS_LIST 中的所有档位。
COST_BPS_TO_PLOT = [0, 10, 20, 50, 100]


def main():
    """主流程：计算并保存交易成本压力测试。"""
    os.makedirs(core.DATA_DIR, exist_ok=True)
    os.makedirs(core.IMAGE_DIR, exist_ok=True)

    portfolio_df = core.load_portfolio_returns()
    detail_df, summary_df, annual_df = core.build_transaction_cost_stress(
        portfolio_df,
        COST_BPS_LIST,
        turnover_multiplier=TURNOVER_MULTIPLIER,
    )

    detail_df.to_csv(core.TRANSACTION_COST_DETAIL_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    summary_df.to_csv(core.TRANSACTION_COST_SUMMARY_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    annual_df.to_csv(core.TRANSACTION_COST_ANNUAL_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    core.plot_transaction_cost_stress(
        detail_df,
        summary_df,
        cost_bps_to_plot=COST_BPS_TO_PLOT,
    )

    print(f"Saved transaction cost detail: {core.TRANSACTION_COST_DETAIL_OUTPUT_PATH}")
    print(f"Saved transaction cost summary: {core.TRANSACTION_COST_SUMMARY_OUTPUT_PATH}")
    print(f"Saved transaction cost annual: {core.TRANSACTION_COST_ANNUAL_OUTPUT_PATH}")
    print(f"Saved transaction cost plot: {core.TRANSACTION_COST_PLOT_OUTPUT_PATH}")
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
