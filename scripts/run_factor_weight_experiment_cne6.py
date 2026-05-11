"""
生成 Barra CNE6 风格择时策略的因子剔除/降权实验。

输出：
1. 各实验场景的逐期收益
2. 各实验场景的绩效汇总
3. 各实验场景的年度表现
4. 各实验场景的因子权重表
5. 因子剔除/降权实验图

说明：
这是样本内诊断实验，用来观察“剔除或降权某些风格因子”对策略收益、
回撤和换手的影响；它不等同于可直接上线的参数选择。
"""

import os
import sys

import pandas as pd


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.analysis import factor_weight_experiment as core


TOP_N = 100
NET_COST_BPS = 20

PROBLEM_FACTORS = ["TOPSI", "STOQ", "HISTVOL"]
NEGATIVE_CONTRIBUTION_FACTORS = ["TOPSI", "STOQ", "HISTVOL", "SP", "MLEV", "STOM"]
CORE_CONTRIBUTION_FACTORS = ["LIQUIDITY", "SIZE", "BETA", "RESVOL", "RESMOM", "MIDCAP", "CAPX"]
SECONDARY_POSITIVE_FACTORS = ["SEASON", "ROE", "CFP", "EYIELD", "LP", "BTOP"]


def make_weights(factors, weight):
    """生成一组因子权重覆盖项。"""
    return {factor: weight for factor in factors}


MAIN_SCENARIOS = [
    {
        "name": "baseline_all_factors",
        "description": "原始全部风格因子等权",
        "default_weight": 1.0,
        "weights": {},
    },
    {
        "name": "drop_3_problem",
        "description": "剔除 TOPSI/STOQ/HISTVOL",
        "default_weight": 1.0,
        "weights": make_weights(PROBLEM_FACTORS, 0.0),
    },
    {
        "name": "drop_6_negative",
        "description": "剔除全样本负贡献因子",
        "default_weight": 1.0,
        "weights": make_weights(NEGATIVE_CONTRIBUTION_FACTORS, 0.0),
    },
    {
        "name": "downweight_problem",
        "description": "问题因子降权而不完全剔除",
        "default_weight": 1.0,
        "weights": {
            **make_weights(PROBLEM_FACTORS, 0.25),
            **make_weights(["SP", "MLEV", "STOM"], 0.50),
        },
    },
    {
        "name": "boost_core_downweight_problem",
        "description": "核心贡献因子加权，问题因子降权",
        "default_weight": 1.0,
        "weights": {
            **make_weights(CORE_CONTRIBUTION_FACTORS, 1.50),
            **make_weights(PROBLEM_FACTORS, 0.25),
            **make_weights(["SP", "MLEV", "STOM"], 0.50),
        },
    },
    {
        "name": "core_positive_only",
        "description": "只保留核心和次级正贡献因子",
        "default_weight": 0.0,
        "weights": {
            **make_weights(CORE_CONTRIBUTION_FACTORS, 1.00),
            **make_weights(SECONDARY_POSITIVE_FACTORS, 0.75),
        },
    },
]

SCENARIOS_TO_PLOT = [scenario["name"] for scenario in MAIN_SCENARIOS]


def get_factor_cols():
    """从 optimal_vectors 表头读取实验因子列表。"""
    factor_cols = pd.read_csv(core.OPTIMAL_VECTORS_PATH, nrows=0).columns.tolist()
    return [col for col in factor_cols if col != "date"]


def build_single_factor_drop_scenarios():
    """生成单因子剔除留一法场景。"""
    scenarios = []
    for factor in get_factor_cols():
        scenarios.append(
            {
                "name": f"drop_one_{factor}",
                "description": f"只剔除 {factor}",
                "default_weight": 1.0,
                "weights": {factor: 0.0},
            }
        )
    return scenarios


def main():
    """主流程：运行并保存因子剔除/降权实验。"""
    os.makedirs(core.DATA_DIR, exist_ok=True)
    os.makedirs(core.IMAGE_DIR, exist_ok=True)

    scenarios = MAIN_SCENARIOS + build_single_factor_drop_scenarios()
    returns_df, summary_df, annual_df, weights_df = core.run_factor_weight_experiment(
        scenarios,
        top_n=TOP_N,
        net_cost_bps=NET_COST_BPS,
    )

    returns_df.to_csv(core.FACTOR_WEIGHT_EXPERIMENT_RETURNS_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    summary_df.to_csv(core.FACTOR_WEIGHT_EXPERIMENT_SUMMARY_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    annual_df.to_csv(core.FACTOR_WEIGHT_EXPERIMENT_ANNUAL_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    weights_df.to_csv(core.FACTOR_WEIGHT_EXPERIMENT_WEIGHTS_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    core.plot_factor_weight_experiment(
        returns_df,
        summary_df,
        scenarios_to_plot=SCENARIOS_TO_PLOT,
    )

    print(f"Saved factor weight experiment returns: {core.FACTOR_WEIGHT_EXPERIMENT_RETURNS_OUTPUT_PATH}")
    print(f"Saved factor weight experiment summary: {core.FACTOR_WEIGHT_EXPERIMENT_SUMMARY_OUTPUT_PATH}")
    print(f"Saved factor weight experiment annual: {core.FACTOR_WEIGHT_EXPERIMENT_ANNUAL_OUTPUT_PATH}")
    print(f"Saved factor weight experiment weights: {core.FACTOR_WEIGHT_EXPERIMENT_WEIGHTS_OUTPUT_PATH}")
    print(f"Saved factor weight experiment plot: {core.FACTOR_WEIGHT_EXPERIMENT_PLOT_OUTPUT_PATH}")
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
