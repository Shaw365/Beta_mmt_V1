import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.optimize import core_parameter_stability as core


LONG_PRD_LIST = (10, 20, 40)
SHORT_PRD_LIST = (3, 5, 10)
CHANNEL_BINS_LIST = (2, 3)
TOP_N_LIST = (80, 100, 120)
EXTREME_VALUE_LIST = (1,)

CAPITAL_LIST = (100_000_000, 300_000_000, 500_000_000)
PARTICIPATION_LIMIT_LIST = (0.05, 0.10, 0.20)
FIXED_COST_BPS = 10
IMPACT_COEF_BPS = 25
TRAIN_YEARS = 3
TEST_YEARS = 1


def main():
    target_df = core.build_parameter_targets(
        long_prd_list=LONG_PRD_LIST,
        short_prd_list=SHORT_PRD_LIST,
        channel_bins_list=CHANNEL_BINS_LIST,
        top_n_list=TOP_N_LIST,
        extreme_value_list=EXTREME_VALUE_LIST,
    )

    detail_df, summary_df, annual_df = core.simulate_targets(
        target_df,
        capital_list=CAPITAL_LIST,
        participation_limit_list=PARTICIPATION_LIMIT_LIST,
        fixed_cost_bps=FIXED_COST_BPS,
        impact_coef_bps=IMPACT_COEF_BPS,
    )
    ranking_df = core.build_parameter_ranking(summary_df, annual_df, target_df)

    fold_df, train_score_df = core.select_walk_forward(
        detail_df,
        target_df,
        train_years=TRAIN_YEARS,
        test_years=TEST_YEARS,
    )
    benchmark_scenarios = []
    for scenario in [core.DEFAULT_SCENARIO] + ranking_df["scenario"].head(5).tolist():
        if scenario not in benchmark_scenarios:
            benchmark_scenarios.append(scenario)

    wf_target_df = core.build_walk_forward_targets(target_df, fold_df, benchmark_scenarios)
    wf_detail_df, wf_summary_df, wf_annual_df = core.simulate_targets(
        wf_target_df,
        capital_list=CAPITAL_LIST,
        participation_limit_list=PARTICIPATION_LIMIT_LIST,
        fixed_cost_bps=FIXED_COST_BPS,
        impact_coef_bps=IMPACT_COEF_BPS,
    )

    os.makedirs(core.DATA_DIR, exist_ok=True)
    target_df.to_csv(core.TARGET_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    detail_df.to_csv(core.DETAIL_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    summary_df.to_csv(core.SUMMARY_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    ranking_df.to_csv(core.RANKING_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    annual_df.to_csv(core.ANNUAL_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    wf_detail_df.to_csv(core.WF_DETAIL_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    wf_summary_df.to_csv(core.WF_SUMMARY_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    wf_annual_df.to_csv(core.WF_ANNUAL_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    fold_df.to_csv(core.WF_FOLD_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    train_score_df.to_csv(core.WF_TRAIN_SCORE_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    core.plot_core_parameter_stability(ranking_df, summary_df, wf_summary_df, fold_df)

    print("Saved:")
    print(f"  {core.TARGET_OUTPUT_PATH}")
    print(f"  {core.DETAIL_OUTPUT_PATH}")
    print(f"  {core.SUMMARY_OUTPUT_PATH}")
    print(f"  {core.RANKING_OUTPUT_PATH}")
    print(f"  {core.ANNUAL_OUTPUT_PATH}")
    print(f"  {core.WF_DETAIL_OUTPUT_PATH}")
    print(f"  {core.WF_SUMMARY_OUTPUT_PATH}")
    print(f"  {core.WF_ANNUAL_OUTPUT_PATH}")
    print(f"  {core.WF_FOLD_OUTPUT_PATH}")
    print(f"  {core.WF_TRAIN_SCORE_OUTPUT_PATH}")
    print(f"  {core.PLOT_OUTPUT_PATH}")
    print()
    print("Full-sample top parameters:")
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
    print(ranking_df[cols].head(15).to_string(index=False))
    print()
    print("Walk-forward folds:")
    print(fold_df.to_string(index=False))
    print()
    print("Walk-forward OOS summary, 10% ADV:")
    view_cols = [
        "scenario",
        "capital",
        "annual_return",
        "max_drawdown",
        "sharpe_ratio",
        "avg_fill_ratio",
        "avg_target_overlap_weight",
        "avg_cash_weight",
    ]
    print(
        wf_summary_df[wf_summary_df["participation_limit"].eq(0.10)][view_cols]
        .sort_values(["scenario", "capital"])
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
