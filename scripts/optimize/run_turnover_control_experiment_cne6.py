"""
运行 Barra CNE6 风格择时策略的换手控制参数网格实验。

实验内容对应 `docs/BETA_MMT_V1_CNE6策略优化实验记录.md` 的 1.3：
1. max_turnover = 20% / 30% / 40% / 50%
2. turnover_buffer_multiplier = 1.5 / 2.0 / 3.0
3. 对每个场景计算交易成本压力测试结果
4. 输出收益、回撤、换手、持仓重合度和相似度变化
"""

import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.optimize import turnover_control_experiment as core


MAX_TURNOVER_LIST = [0.20, 0.30, 0.40, 0.50]
BUFFER_MULTIPLIER_LIST = [1.5, 2.0, 3.0]
COST_BPS_LIST = [0, 5, 10, 20, 50, 100]
TOP_N = 100


def main():
    """主流程：运行换手控制网格实验并保存结果。"""
    os.makedirs(core.DATA_DIR, exist_ok=True)
    os.makedirs(core.IMAGE_DIR, exist_ok=True)

    returns_df, summary_df, cost_df, annual_df = core.run_turnover_control_experiment(
        max_turnover_list=MAX_TURNOVER_LIST,
        buffer_multiplier_list=BUFFER_MULTIPLIER_LIST,
        cost_bps_list=COST_BPS_LIST,
        top_n=TOP_N,
    )

    returns_df.to_csv(core.RETURNS_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    summary_df.to_csv(core.SUMMARY_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    cost_df.to_csv(core.COST_STRESS_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    annual_df.to_csv(core.ANNUAL_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    core.plot_turnover_control_experiment(summary_df, cost_df)

    print(f"Saved returns: {core.RETURNS_OUTPUT_PATH}")
    print(f"Saved summary: {core.SUMMARY_OUTPUT_PATH}")
    print(f"Saved cost stress: {core.COST_STRESS_OUTPUT_PATH}")
    print(f"Saved annual: {core.ANNUAL_OUTPUT_PATH}")
    print(f"Saved plot: {core.PLOT_OUTPUT_PATH}")
    print(summary_df.head(12).to_string(index=False))


if __name__ == "__main__":
    main()
