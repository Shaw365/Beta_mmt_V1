"""
运行成交可实现性与容量约束实验。

实验目标：
1. 对 baseline 和 tc50_buf2 目标持仓应用 ADV 参与率上限；
2. 用涨跌停近似规则限制不可成交买卖；
3. 在不同资金规模下重新计算实际成交后的收益、成本和成交完成率。
"""

import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.optimize import execution_capacity_experiment as core


SCENARIOS = ["baseline", "tc50_buf2"]
CAPITAL_LIST = [10_000_000, 30_000_000, 100_000_000, 300_000_000, 500_000_000]
PARTICIPATION_LIMIT_LIST = [0.05, 0.10, 0.20]
FIXED_COST_BPS = 10
IMPACT_COEF_BPS = 25


def main():
    os.makedirs(core.DATA_DIR, exist_ok=True)
    os.makedirs(core.IMAGE_DIR, exist_ok=True)

    detail_df, summary_df, trade_df, annual_df = core.run_execution_capacity_experiment(
        scenarios=SCENARIOS,
        capital_list=CAPITAL_LIST,
        participation_limit_list=PARTICIPATION_LIMIT_LIST,
        fixed_cost_bps=FIXED_COST_BPS,
        impact_coef_bps=IMPACT_COEF_BPS,
    )

    detail_df.to_csv(core.DETAIL_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    summary_df.to_csv(core.SUMMARY_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    trade_df.to_csv(core.TRADE_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    annual_df.to_csv(core.ANNUAL_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    core.plot_execution_capacity(summary_df)

    print(f"Saved detail: {core.DETAIL_OUTPUT_PATH}")
    print(f"Saved summary: {core.SUMMARY_OUTPUT_PATH}")
    print(f"Saved trade detail: {core.TRADE_OUTPUT_PATH}")
    print(f"Saved annual: {core.ANNUAL_OUTPUT_PATH}")
    print(f"Saved plot: {core.PLOT_OUTPUT_PATH}")
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
