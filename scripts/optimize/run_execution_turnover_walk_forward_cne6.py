import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.optimize import execution_turnover_walk_forward as core


TRAIN_YEARS = 3
TEST_YEARS = 1
CANDIDATE_SCENARIOS = None
BENCHMARK_SCENARIOS = ("baseline", "tc50_buf2", "tc50_buf3", "tc50_buf4")
CAPITAL_LIST = (100_000_000, 300_000_000, 500_000_000)
PARTICIPATION_LIMIT_LIST = (0.05, 0.10, 0.20)
FIXED_COST_BPS = 10
IMPACT_COEF_BPS = 25


def main():
    (
        detail_df,
        summary_df,
        annual_df,
        fold_df,
        train_score_df,
        fold_summary_df,
        fold_annual_df,
    ) = core.run_execution_turnover_walk_forward(
        train_years=TRAIN_YEARS,
        test_years=TEST_YEARS,
        candidate_scenarios=CANDIDATE_SCENARIOS,
        benchmark_scenarios=BENCHMARK_SCENARIOS,
        capital_list=CAPITAL_LIST,
        participation_limit_list=PARTICIPATION_LIMIT_LIST,
        fixed_cost_bps=FIXED_COST_BPS,
        impact_coef_bps=IMPACT_COEF_BPS,
    )

    os.makedirs(core.DATA_DIR, exist_ok=True)
    detail_df.to_csv(core.DETAIL_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    summary_df.to_csv(core.SUMMARY_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    annual_df.to_csv(core.ANNUAL_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    fold_df.to_csv(core.FOLD_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    train_score_df.to_csv(core.TRAIN_SCORE_OUTPUT_PATH, index=False, encoding="utf-8-sig")

    fold_summary_path = core.SUMMARY_OUTPUT_PATH.replace("_summary_", "_fold_summary_")
    fold_annual_path = core.ANNUAL_OUTPUT_PATH.replace("_annual_", "_fold_annual_")
    fold_summary_df.to_csv(fold_summary_path, index=False, encoding="utf-8-sig")
    fold_annual_df.to_csv(fold_annual_path, index=False, encoding="utf-8-sig")

    core.plot_execution_turnover_walk_forward(summary_df, annual_df, fold_df, train_score_df)

    print("Saved:")
    print(f"  {core.DETAIL_OUTPUT_PATH}")
    print(f"  {core.SUMMARY_OUTPUT_PATH}")
    print(f"  {core.ANNUAL_OUTPUT_PATH}")
    print(f"  {core.FOLD_OUTPUT_PATH}")
    print(f"  {core.TRAIN_SCORE_OUTPUT_PATH}")
    print(f"  {fold_summary_path}")
    print(f"  {fold_annual_path}")
    print(f"  {core.PLOT_OUTPUT_PATH}")
    print()
    print("Selected scenarios:")
    print(fold_df.to_string(index=False))
    print()
    print("OOS summary, 10% ADV:")
    cols = [
        "scenario",
        "capital",
        "annual_return",
        "max_drawdown",
        "sharpe_ratio",
        "avg_fill_ratio",
        "avg_target_overlap_weight",
        "avg_cash_weight",
        "total_cost_arithmetic",
    ]
    view = summary_df[summary_df["participation_limit"].eq(0.10)][cols].copy()
    print(view.sort_values(["scenario", "capital"]).to_string(index=False))


if __name__ == "__main__":
    main()
