"""
生成 Barra CNE6 风格择时策略的交易成本压力测试。

输出：
1. 旧口径：单边换手成本压力测试，保留作对照
2. 新口径：双边成交额 + 首期建仓 + ADV 冲击成本
3. 不同资金规模下的容量衰减结果
"""

import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.analysis import transaction_cost_stress as core


# 成本档位，单位 bp。这里的 bp 是单边交易成本，10bp = 0.10%。
COST_BPS_LIST = [0, 5, 10, 20, 30, 50, 100]

# 当前策略输出的 turnover 是“单边换手率”。1.0 表示按单边换手口径扣成本；
# 如果想用更保守的买卖双边成交额口径，可以改成 2.0。
TURNOVER_MULTIPLIER = 1.0

# 图里展示的成本档位。摘要 CSV 仍保留 COST_BPS_LIST 中的所有档位。
COST_BPS_TO_PLOT = [0, 5, 10, 20]

# 新主口径参数。
REALISTIC_FIXED_COST_BPS = 10
REALISTIC_IMPACT_COEF_BPS = 25
REALISTIC_CAPITAL_LIST = [10_000_000, 30_000_000, 100_000_000, 300_000_000, 500_000_000]


def main():
    """主流程：计算并保存交易成本压力测试。"""
    os.makedirs(core.DATA_DIR, exist_ok=True)
    os.makedirs(core.IMAGE_DIR, exist_ok=True)

    portfolio_df = core.load_portfolio_returns()

    # 旧口径：保留单边换手扣成本结果，便于和原报告对齐。
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

    # 新主口径：固定成本按买卖双边成交额扣除，并加入首期建仓和 ADV 冲击成本。
    liquidity_df = core.load_price_liquidity()
    realistic_detail_df, realistic_summary_df, realistic_annual_df, realistic_trade_df = (
        core.build_realistic_transaction_cost_stress(
            portfolio_df,
            liquidity_df,
            capital_list=REALISTIC_CAPITAL_LIST,
            fixed_cost_bps=REALISTIC_FIXED_COST_BPS,
            impact_coef_bps=REALISTIC_IMPACT_COEF_BPS,
            include_initial_build=True,
        )
    )
    realistic_detail_df.to_csv(
        core.REALISTIC_TRANSACTION_COST_DETAIL_OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )
    realistic_summary_df.to_csv(
        core.REALISTIC_TRANSACTION_COST_SUMMARY_OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )
    realistic_annual_df.to_csv(
        core.REALISTIC_TRANSACTION_COST_ANNUAL_OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )
    realistic_trade_df.to_csv(
        core.REALISTIC_TRANSACTION_COST_TRADE_OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )
    core.plot_transaction_cost_stress(
        realistic_detail_df,
        realistic_summary_df,
        output_path=core.REALISTIC_TRANSACTION_COST_PLOT_OUTPUT_PATH,
    )

    print(f"Saved transaction cost detail: {core.TRANSACTION_COST_DETAIL_OUTPUT_PATH}")
    print(f"Saved transaction cost summary: {core.TRANSACTION_COST_SUMMARY_OUTPUT_PATH}")
    print(f"Saved transaction cost annual: {core.TRANSACTION_COST_ANNUAL_OUTPUT_PATH}")
    print(f"Saved transaction cost plot: {core.TRANSACTION_COST_PLOT_OUTPUT_PATH}")
    print(f"Saved realistic transaction cost detail: {core.REALISTIC_TRANSACTION_COST_DETAIL_OUTPUT_PATH}")
    print(f"Saved realistic transaction cost summary: {core.REALISTIC_TRANSACTION_COST_SUMMARY_OUTPUT_PATH}")
    print(f"Saved realistic transaction cost annual: {core.REALISTIC_TRANSACTION_COST_ANNUAL_OUTPUT_PATH}")
    print(f"Saved realistic transaction trade detail: {core.REALISTIC_TRANSACTION_COST_TRADE_OUTPUT_PATH}")
    print(f"Saved realistic transaction cost plot: {core.REALISTIC_TRANSACTION_COST_PLOT_OUTPUT_PATH}")
    print("\n旧单边口径:")
    print(summary_df.to_string(index=False))
    print("\n新主口径（10bp双边 + 首期建仓 + ADV冲击）:")
    print(realistic_summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
