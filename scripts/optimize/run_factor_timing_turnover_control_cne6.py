"""
运行 Barra CNE6 风格择时策略的换手控制版本。

本脚本不覆盖原始基准策略结果，会生成带有 `_tc{换手上限}_buf{缓冲倍数}` 后缀的新输出。
默认设置：
1. 单期最大单边换手率 30%
2. 候选池缓冲倍数 2.0，即先在 Top 200 候选池中尽量保留旧持仓
"""

import os
import sys

import pandas as pd


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.backtest.run_factor_timing_v3 import CACHE_DIR, OUTPUT_DIR, load_or_generate_barra_data
from src.strategies.factor_timing_strategy_v3 import FactorTimingStrategy
from src.utils.benchmark import (
    compute_relative_returns,
    compute_weekly_benchmark_returns,
    load_index_data,
)


# 换手控制参数。后续可以围绕这两个参数做网格实验。
MAX_TURNOVER = 0.30
TURNOVER_BUFFER_MULTIPLIER = 2.0


def main():
    """主流程：运行换手控制版策略，并保存独立后缀的结果。"""
    print("=" * 100)
    print("Barra CNE6 风格择时策略：换手控制版本")
    print("=" * 100)
    print(f"单期最大单边换手率: {MAX_TURNOVER:.0%}")
    print(f"候选池缓冲倍数: {TURNOVER_BUFFER_MULTIPLIER:g}x")

    factor_returns_df, cumulative_returns_df, factor_exposure_df, price_df = load_or_generate_barra_data(
        use_cache=True
    )

    strategy = FactorTimingStrategy(
        long_prd=20,
        short_prd=5,
        channel_bins=2,
        extreme_value=1,
        top_n=100,
        turnover_control=True,
        max_turnover=MAX_TURNOVER,
        turnover_buffer_multiplier=TURNOVER_BUFFER_MULTIPLIER,
    )

    portfolio_returns_df, optimal_vector_df = strategy.run_weekly_rebalance(
        factor_exposure_df,
        cumulative_returns_df.set_index("date"),
        price_df,
    )

    stats, annual_returns, monthly_win_rate = strategy.calculate_statistics(portfolio_returns_df)

    index_cache = os.path.join(CACHE_DIR, "index_eod.csv")
    index_data = load_index_data(cache_path=index_cache)
    weekly_dates = [pd.Timestamp(d) for d in sorted(portfolio_returns_df["date"].unique())]
    benchmark_weekly = compute_weekly_benchmark_returns(index_data, weekly_dates)
    benchmark_relative = compute_relative_returns(portfolio_returns_df, benchmark_weekly)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    data_dir = os.path.join(OUTPUT_DIR, "data")
    os.makedirs(data_dir, exist_ok=True)

    suffix = strategy.get_param_suffix()
    strategy.plot_strategy_performance(
        portfolio_returns_df,
        OUTPUT_DIR,
        stats=stats,
        annual_returns=annual_returns,
        monthly_win_rate=monthly_win_rate,
        benchmark_data=benchmark_relative,
        strategy_title=(
            "风格因子择时策略-换手控制版 "
            f"(L={strategy.long_prd}, S={strategy.short_prd}, "
            f"max turnover={MAX_TURNOVER:.0%}, buffer={TURNOVER_BUFFER_MULTIPLIER:g}x)"
        ),
    )
    strategy.generate_trade_report(data_dir)

    portfolio_returns_df.to_csv(
        os.path.join(data_dir, f"portfolio_returns_{suffix}.csv"),
        index=False,
        encoding="utf-8-sig",
    )
    optimal_vector_df.to_csv(
        os.path.join(data_dir, f"optimal_vectors_{suffix}.csv"),
        encoding="utf-8-sig",
    )
    benchmark_relative.to_csv(
        os.path.join(data_dir, f"benchmark_relative_{suffix}.csv"),
        encoding="utf-8-sig",
    )

    print("\n换手控制版本运行完成")
    print(f"输出后缀: {suffix}")
    print(f"策略收益: {os.path.join(data_dir, f'portfolio_returns_{suffix}.csv')}")
    print(f"策略图表: {os.path.join(OUTPUT_DIR, 'images', 'backtest', f'factor_timing_{suffix}.png')}")
    print(f"交易记录: {os.path.join(data_dir, f'交易记录_{suffix}.xlsx')}")

    return portfolio_returns_df, optimal_vector_df, stats


if __name__ == "__main__":
    main()
