import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.optimize import execution_turnover_revaluation as core


MAX_TURNOVER_LIST = [0.20, 0.30, 0.40, 0.50, 0.60]
BUFFER_MULTIPLIER_LIST = [1.5, 2.0, 3.0, 4.0]
CAPITAL_LIST = [100_000_000, 300_000_000, 500_000_000]
PARTICIPATION_LIMIT_LIST = [0.05, 0.10, 0.20]
FIXED_COST_BPS = 10
IMPACT_COEF_BPS = 25
TOP_N = 100


def main():
    target_df, detail_df, summary_df, ranking_df, annual_df = (
        core.run_execution_turnover_revaluation(
            max_turnover_list=MAX_TURNOVER_LIST,
            buffer_multiplier_list=BUFFER_MULTIPLIER_LIST,
            capital_list=CAPITAL_LIST,
            participation_limit_list=PARTICIPATION_LIMIT_LIST,
            fixed_cost_bps=FIXED_COST_BPS,
            impact_coef_bps=IMPACT_COEF_BPS,
            top_n=TOP_N,
        )
    )

    os.makedirs(core.DATA_DIR, exist_ok=True)
    target_df.to_csv(core.TARGET_RETURNS_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    detail_df.to_csv(core.DETAIL_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    summary_df.to_csv(core.SUMMARY_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    ranking_df.to_csv(core.RANKING_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    annual_df.to_csv(core.ANNUAL_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    core.plot_execution_turnover_revaluation(summary_df, ranking_df)

    print("Saved:")
    print(f"  {core.TARGET_RETURNS_OUTPUT_PATH}")
    print(f"  {core.DETAIL_OUTPUT_PATH}")
    print(f"  {core.SUMMARY_OUTPUT_PATH}")
    print(f"  {core.RANKING_OUTPUT_PATH}")
    print(f"  {core.ANNUAL_OUTPUT_PATH}")
    print(f"  {core.PLOT_OUTPUT_PATH}")
    print()
    print("Top scenarios:")
    cols = [
        "scenario",
        "composite_score",
        "mean_annual_return",
        "min_annual_return",
        "mean_max_drawdown",
        "mean_fill_ratio",
        "mean_target_overlap",
        "mean_cash_weight",
    ]
    print(ranking_df[cols].head(12).to_string(index=False))


if __name__ == "__main__":
    main()
