"""
Run Barra-first, yearly Alpha-second factor timing backtests.

Workflow:
1. Load the existing CNE6 exposure, factor return and price caches.
2. For each weekly signal date, use Barra timing similarity to keep Top X names.
3. Within the Barra Top X pool, use the yearly selected Alpha factor set to keep Top Y names.

Default parameter grid:
    X = [250, 500, 1000]
    Y = [50, 100]
"""

import argparse
import os
import sys

import pandas as pd


project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from scripts.backtest.run_factor_timing_v3 import load_or_generate_barra_data
from src.strategies.factor_timing_strategy_v3 import FactorTimingStrategy
from src.strategies.yearly_factor_candidate_pool import YearlyFactorCandidatePool
from src.utils.benchmark import load_index_data, compute_weekly_benchmark_returns, compute_relative_returns


OUTPUT_DIR = os.path.join(project_root, "output", "cne6")
CACHE_DIR = os.path.join(OUTPUT_DIR, "data")

YEARLY_FACTOR_RESULT_DIR = r"E:\sharedata\factors\factor_screen_results\yearly_rankic5d_20260526_090335"
YEARLY_SELECTED_FACTORS = os.path.join(YEARLY_FACTOR_RESULT_DIR, "yearly_selected_factors.csv")
FACTOR_VALUE_DIR = r"E:\sharedata\factors\factor_values"

DEFAULT_BARRA_POOL_SIZES = [250, 500, 1000]
DEFAULT_ALPHA_TOP_NS = [50, 100]
DEFAULT_MAX_TURNOVER = 0.50
DEFAULT_TURNOVER_BUFFER_MULTIPLIER = 2.0


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--barra-pool-sizes", type=int, nargs="+", default=DEFAULT_BARRA_POOL_SIZES)
    parser.add_argument("--alpha-top-ns", type=int, nargs="+", default=DEFAULT_ALPHA_TOP_NS)
    parser.add_argument("--pool-size", type=int, default=None, help="Deprecated alias for a single Barra pool size X.")
    parser.add_argument("--alpha-top-n", type=int, default=None, help="Alias for a single Alpha final size Y.")
    parser.add_argument("--turnover-control", action="store_true")
    parser.add_argument("--max-turnover", type=float, default=DEFAULT_MAX_TURNOVER)
    parser.add_argument("--turnover-buffer-multiplier", type=float, default=DEFAULT_TURNOVER_BUFFER_MULTIPLIER)
    parser.add_argument("--filter-bottom-float-cap", type=float, default=0.0)
    parser.add_argument("--filter-bottom-amount", type=float, default=0.0)
    return parser.parse_args()


def _normalize_grid(args):
    barra_pool_sizes = [args.pool_size] if args.pool_size is not None else args.barra_pool_sizes
    alpha_top_ns = [args.alpha_top_n] if args.alpha_top_n is not None else args.alpha_top_ns
    return [int(x) for x in barra_pool_sizes], [int(y) for y in alpha_top_ns]


def _filter_label(args):
    parts = []
    if args.filter_bottom_float_cap > 0:
        parts.append(f"fcapq{int(round(args.filter_bottom_float_cap * 100))}")
    if args.filter_bottom_amount > 0:
        parts.append(f"amtq{int(round(args.filter_bottom_amount * 100))}")
    return "" if not parts else "_" + "_".join(parts)


def _save_outputs(
    strategy,
    portfolio_returns_df,
    optimal_vector_df,
    benchmark_relative,
    stats,
    annual_returns,
    monthly_win_rate,
    suffix,
    title,
    alpha_top_n,
):
    os.makedirs(os.path.join(OUTPUT_DIR, "data"), exist_ok=True)
    os.makedirs(os.path.join(OUTPUT_DIR, "images", "backtest"), exist_ok=True)

    plot_kwargs = {
        "stats": stats,
        "annual_returns": annual_returns,
        "monthly_win_rate": monthly_win_rate,
        "benchmark_data": benchmark_relative,
        "file_suffix": suffix,
        "strategy_title": title,
    }
    if "target_holding_n" in strategy.plot_strategy_performance.__code__.co_varnames:
        plot_kwargs["target_holding_n"] = alpha_top_n
    strategy.plot_strategy_performance(portfolio_returns_df, OUTPUT_DIR, **plot_kwargs)
    strategy.generate_trade_report(os.path.join(OUTPUT_DIR, "data"), file_suffix=suffix)

    portfolio_returns_df.to_csv(
        os.path.join(OUTPUT_DIR, "data", f"portfolio_returns_{suffix}.csv"),
        index=False,
        encoding="utf-8-sig",
    )
    optimal_vector_df.to_csv(
        os.path.join(OUTPUT_DIR, "data", f"optimal_vectors_{suffix}.csv"),
        encoding="utf-8-sig",
    )
    benchmark_relative.to_csv(
        os.path.join(OUTPUT_DIR, "data", f"benchmark_relative_{suffix}.csv"),
        encoding="utf-8-sig",
    )


def run_one_combo(
    barra_pool_size,
    alpha_top_n,
    args,
    pool_provider,
    cumulative_returns_df,
    factor_exposure_df,
    price_df,
    index_data,
    filter_label,
):
    print("\n" + "=" * 100)
    control_label = " + turnover control" if args.turnover_control else ""
    print(f"CNE6 timing: Barra Top {barra_pool_size} -> yearly Alpha Top {alpha_top_n}{control_label}")
    print("=" * 100)

    strategy = FactorTimingStrategy(
        long_prd=20,
        short_prd=5,
        channel_bins=2,
        extreme_value=1,
        top_n=barra_pool_size,
        turnover_control=args.turnover_control,
        max_turnover=args.max_turnover if args.turnover_control else None,
        turnover_buffer_multiplier=args.turnover_buffer_multiplier,
    )
    suffix = f"{strategy.get_param_suffix()}_alpha{alpha_top_n}{filter_label}"

    portfolio_returns_df, optimal_vector_df = strategy.run_weekly_rebalance(
        factor_exposure_df,
        cumulative_returns_df,
        price_df,
        active_screener=pool_provider,
        active_top_n=alpha_top_n,
    )
    if len(portfolio_returns_df) == 0:
        print(f"Warning: no valid rebalance records for Barra {barra_pool_size}, Alpha {alpha_top_n}")
        return None

    stats, annual_returns, monthly_win_rate = strategy.calculate_statistics(portfolio_returns_df)
    for key, value in stats.items():
        print(f"{key:15s}: {value}")

    weekly_dates = [pd.Timestamp(d) for d in sorted(portfolio_returns_df["date"].unique())]
    benchmark_weekly = compute_weekly_benchmark_returns(index_data, weekly_dates)
    benchmark_relative = compute_relative_returns(portfolio_returns_df, benchmark_weekly)

    title = f"CNE6 Barra Top {barra_pool_size} -> Yearly Alpha Top {alpha_top_n}{control_label}"
    _save_outputs(
        strategy,
        portfolio_returns_df,
        optimal_vector_df,
        benchmark_relative,
        stats,
        annual_returns,
        monthly_win_rate,
        suffix,
        title,
        alpha_top_n,
    )

    print("Main outputs:")
    print(f"  - {os.path.join(OUTPUT_DIR, 'data', f'portfolio_returns_{suffix}.csv')}")
    print(f"  - {os.path.join(OUTPUT_DIR, 'images', 'backtest', f'factor_timing_{suffix}.png')}")

    result_row = {
        "barra_pool_size": barra_pool_size,
        "alpha_top_n": alpha_top_n,
        "suffix": suffix,
    }
    result_row.update(stats)
    return result_row, portfolio_returns_df, optimal_vector_df


def main():
    args = parse_args()
    barra_pool_sizes, alpha_top_ns = _normalize_grid(args)
    filter_label = _filter_label(args)

    print("=" * 100)
    print("CNE6 timing grid: Barra first, yearly Alpha second")
    print(f"Barra X values: {barra_pool_sizes}")
    print(f"Alpha Y values: {alpha_top_ns}")
    print("=" * 100)
    if args.turnover_control:
        print(f"Max one-way turnover per rebalance: {args.max_turnover:.0%}")
        print(f"Barra similarity buffer multiplier: {args.turnover_buffer_multiplier:g}x")
    else:
        print("Turnover control: off")
    if args.filter_bottom_float_cap > 0:
        print(f"Float-cap filter: drop bottom {args.filter_bottom_float_cap:.0%}")
    if args.filter_bottom_amount > 0:
        print(f"Amount filter: drop bottom {args.filter_bottom_amount:.0%}")

    print("\nStep 1: load Barra CNE6 cached data...")
    _, cumulative_returns_df, factor_exposure_df, price_df = load_or_generate_barra_data(use_cache=True)
    cumulative_returns_df = cumulative_returns_df.set_index("date")

    print("\nStep 2: initialize yearly Alpha screener...")
    pool_provider = YearlyFactorCandidatePool(
        selected_factors_path=YEARLY_SELECTED_FACTORS,
        factor_root=FACTOR_VALUE_DIR,
        pool_size=max(barra_pool_sizes),
        cache_dir=os.path.join(CACHE_DIR, "yearly_factor_pool"),
        market_filter_df=price_df,
        min_float_cap_quantile=args.filter_bottom_float_cap,
        min_amount_quantile=args.filter_bottom_amount,
    )

    print("\nStep 3: load benchmark data...")
    index_cache = os.path.join(CACHE_DIR, "index_eod.csv")
    index_data = load_index_data(cache_path=index_cache)

    results = {}
    comparison_rows = []
    for barra_pool_size in barra_pool_sizes:
        for alpha_top_n in alpha_top_ns:
            combo_result = run_one_combo(
                barra_pool_size,
                alpha_top_n,
                args,
                pool_provider,
                cumulative_returns_df,
                factor_exposure_df,
                price_df,
                index_data,
                filter_label,
            )
            if combo_result is None:
                continue
            result_row, portfolio_returns_df, optimal_vector_df = combo_result
            comparison_rows.append(result_row)
            results[(barra_pool_size, alpha_top_n)] = {
                "portfolio_returns": portfolio_returns_df,
                "optimal_vectors": optimal_vector_df,
                "stats": result_row,
            }

    if comparison_rows:
        comparison_df = pd.DataFrame(comparison_rows)
        comparison_path = os.path.join(OUTPUT_DIR, "data", f"barra_alpha_grid_comparison{filter_label}.csv")
        comparison_df.to_csv(comparison_path, index=False, encoding="utf-8-sig")
        print("\nGrid comparison saved:")
        print(f"  - {comparison_path}")

    return results


if __name__ == "__main__":
    results = main()
