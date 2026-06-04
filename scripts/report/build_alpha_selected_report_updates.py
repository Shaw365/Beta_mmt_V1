"""Build report artifacts for the Barra Top500 -> Alpha Top50 version.

The existing chapter 6-8 experiments were built around the Barra-only n100
portfolio. This script keeps those outputs intact and writes a parallel set
with the l20_s5_b2_e1_n500_alpha50 suffix.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis import factor_weight_experiment as base
from src.optimize import core_parameter_stability as core_stability
from src.optimize import execution_capacity_experiment as exec_core
from src.optimize import execution_turnover_revaluation as turnover_reval
from src.optimize import turnover_control_experiment as turnover_core
from src.strategies.factor_timing_strategy_v3 import FactorTimingStrategy
from src.strategies.yearly_factor_candidate_pool import YearlyFactorCandidatePool
from scripts.report import build_2026_case_analysis as case2026


OUTPUT_DIR = PROJECT_ROOT / "output" / "cne6"
DATA_DIR = OUTPUT_DIR / "data"
IMAGE_DIR = OUTPUT_DIR / "images" / "report"
OPT_IMAGE_DIR = OUTPUT_DIR / "images" / "optimize"

BASE_SUFFIX = "l20_s5_b2_e1_n500_alpha50"
BASE_SCENARIO = "p_l20_s5_b2_x500_y50_baseline"

BARRA_POOL_SIZE = 500
ALPHA_TOP_N = 50
MAX_TURNOVER_LIST = [0.20, 0.30, 0.40, 0.50, 0.60]
BUFFER_MULTIPLIER_LIST = [1.0, 2.0, 3.0, 4.0]
CAPITAL_LIST = [100_000_000, 300_000_000, 500_000_000]
REPORT_CAPITAL_LIST = [10_000_000, 30_000_000, 100_000_000]
SMALL_CAPITAL_LIST = [10_000_000, 30_000_000, 100_000_000, 300_000_000, 500_000_000]
PARTICIPATION_LIMIT_LIST = [0.05, 0.10, 0.20]
FIXED_COST_BPS = 10
IMPACT_COEF_BPS = 25

YEARLY_FACTOR_RESULT_DIR = Path(r"E:\sharedata\factors\factor_screen_results\yearly_rankic5d_20260526_090335")
YEARLY_SELECTED_FACTORS = YEARLY_FACTOR_RESULT_DIR / "yearly_selected_factors.csv"
FACTOR_VALUE_DIR = Path(r"E:\sharedata\factors\factor_values")


class AlphaFastFactorTimingStrategy(case2026.FastFactorTimingStrategy):
    """Fast 2026 strategy variant compatible with the current selection API."""

    def select_stocks(
        self,
        factor_exposure_df,
        optimal_vector,
        signal_date,
        trade_date,
        suspended_codes=None,
        candidate_pool_size=None,
        allowed_codes=None,
    ):
        suspended_codes = set(suspended_codes or [])
        allowed_codes = set(allowed_codes) if allowed_codes is not None else None
        current_data = self._get_signal_exposure(signal_date)
        if current_data is None or current_data.empty:
            print(f"Warning: no factor exposure for signal date {signal_date}")
            return []

        if suspended_codes:
            current_data = current_data[~current_data["code"].isin(suspended_codes)]
        if allowed_codes is not None:
            current_data = current_data[current_data["code"].isin(allowed_codes)]
        if current_data.empty:
            return []

        factors = optimal_vector.index.tolist()
        matrix = current_data[factors].to_numpy(dtype=float, copy=False)
        opt = optimal_vector.to_numpy(dtype=float, copy=False)
        opt_norm = np.linalg.norm(opt)
        row_norm = np.linalg.norm(matrix, axis=1)
        denom = row_norm * opt_norm
        similarity = np.zeros(len(current_data), dtype=float)
        valid = denom > 0
        similarity[valid] = matrix[valid].dot(opt) / denom[valid]

        pool_size = candidate_pool_size if candidate_pool_size is not None else self.top_n
        ranked = (
            pd.DataFrame({"code": current_data["code"].to_numpy(), "similarity": similarity})
            .sort_values(["similarity", "code"], ascending=[False, True])
            .head(pool_size)
        )
        return ranked["code"].tolist()


def retarget_base_suffix(suffix: str = BASE_SUFFIX) -> None:
    base.SUFFIX = suffix
    base.PORTFOLIO_RETURNS_PATH = str(DATA_DIR / f"portfolio_returns_{suffix}.csv")
    base.OPTIMAL_VECTORS_PATH = str(DATA_DIR / f"optimal_vectors_{suffix}.csv")
    base.FACTOR_EXPOSURE_PATH = str(DATA_DIR / "factor_exposure_cne6.csv")
    base.PRICE_DATA_PATH = str(DATA_DIR / "price_data_cne6.csv")


def configure_matplotlib() -> None:
    font_path = r"C:\Windows\Fonts\simhei.ttf"
    if os.path.exists(font_path):
        plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
    else:
        plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def parse_codes(value):
    return exec_core.parse_selected_codes(value)


def load_alpha_screener() -> YearlyFactorCandidatePool:
    return YearlyFactorCandidatePool(
        selected_factors_path=YEARLY_SELECTED_FACTORS,
        factor_root=FACTOR_VALUE_DIR,
        pool_size=BARRA_POOL_SIZE,
        cache_dir=DATA_DIR / "yearly_factor_pool",
    )


def calculate_turnover(prev_stocks, current_stocks) -> float:
    if len(prev_stocks) == 0 or len(current_stocks) == 0:
        return 0.0
    return min(len(set(prev_stocks) - set(current_stocks)) / len(prev_stocks), 1.0)


def build_alpha_baseline_returns(
    contexts: list[dict],
    weekly_returns_df: pd.DataFrame,
    top_n: int = ALPHA_TOP_N,
) -> pd.DataFrame:
    """Build no-turnover-control returns from Alpha-ranked candidate codes."""
    prev_stocks = []
    records = []
    for context in contexts:
        current_date = context["date"]
        if current_date not in weekly_returns_df.index:
            continue

        selected_codes = list(context["candidate_codes"][:top_n])
        stock_returns = weekly_returns_df.loc[current_date, selected_codes].dropna()
        if stock_returns.empty:
            continue

        turnover = calculate_turnover(prev_stocks, selected_codes)
        quality = turnover_core._selected_quality(selected_codes, context)
        records.append(
            {
                "scenario": "baseline",
                "description": "Barra Top500 -> Alpha Top50 baseline",
                "max_turnover": np.nan,
                "buffer_multiplier": np.nan,
                "date": current_date,
                "signal_date": context["signal_date"],
                "next_date": context["next_date"],
                "return": stock_returns.mean(),
                "num_stocks": len(selected_codes),
                "turnover": turnover,
                "baseline_overlap": 1.0,
                "retained_old_count": len(set(prev_stocks) & set(selected_codes)) if prev_stocks else 0,
                "retained_outside_candidate_count": 0,
                "selected_codes": selected_codes,
                **quality,
            }
        )
        prev_stocks = selected_codes
    return pd.DataFrame(records)


def build_alpha_contexts(
    portfolio_df: pd.DataFrame,
    optimal_df: pd.DataFrame,
    factor_cols: list[str],
    weekly_returns_df: pd.DataFrame,
    suspend_lookup: dict,
    alpha_screener: YearlyFactorCandidatePool,
    barra_pool_size: int = BARRA_POOL_SIZE,
    alpha_top_n: int = ALPHA_TOP_N,
    max_candidate_pool_size: int = 200,
    exposure_df: pd.DataFrame | None = None,
) -> list[dict]:
    if exposure_df is None:
        exposure_df = base.load_signal_date_exposures(portfolio_df["signal_date"].unique(), factor_cols)
    exposure_df = exposure_df.copy()
    exposure_df["date"] = pd.to_datetime(exposure_df["date"])
    exposure_df["code"] = exposure_df["code"].astype(str)
    exposure_by_date = exposure_df.groupby("date", sort=False)

    contexts = []
    for row in portfolio_df.itertuples(index=False):
        signal_date = pd.Timestamp(row.signal_date)
        current_date = pd.Timestamp(row.date)
        if signal_date not in optimal_df.index or current_date not in weekly_returns_df.index:
            continue
        if signal_date not in exposure_by_date.groups:
            continue

        current = exposure_by_date.get_group(signal_date).copy()
        suspended_codes = suspend_lookup.get(current_date, set())
        if suspended_codes:
            current = current[~current["code"].isin(suspended_codes)]
        if current.empty:
            continue

        current["similarity"] = turnover_core._equal_weight_scores(current, optimal_df.loc[signal_date], factor_cols)
        barra_codes = current.sort_values(["similarity", "code"], ascending=[False, True]).head(barra_pool_size)[
            "code"
        ].tolist()
        alpha_scores = alpha_screener.score_candidates(signal_date, barra_codes)
        if alpha_scores.empty:
            continue
        alpha_scores = alpha_scores.head(max(max_candidate_pool_size, alpha_top_n)).copy()
        alpha_scores["rank"] = np.arange(1, len(alpha_scores) + 1)
        candidate_codes = alpha_scores.head(max_candidate_pool_size)["code"].astype(str).tolist()
        score_map = dict(zip(alpha_scores["code"].astype(str), alpha_scores["score"]))
        rank_map = dict(zip(alpha_scores["code"].astype(str), alpha_scores["rank"]))

        baseline_codes = list(getattr(row, "selected_codes", []))
        if not baseline_codes:
            baseline_codes = alpha_scores.head(alpha_top_n)["code"].astype(str).tolist()

        contexts.append(
            {
                "date": current_date,
                "signal_date": signal_date,
                "next_date": pd.Timestamp(row.next_date),
                "baseline_codes": baseline_codes,
                "suspended_codes": suspended_codes,
                "candidate_codes": candidate_codes,
                "score_map": score_map,
                "rank_map": rank_map,
            }
        )

    return contexts


def simulate_target_df(
    target_df: pd.DataFrame,
    weekly_returns_df: pd.DataFrame,
    capital_list: list[int],
    participation_limit_list: list[float],
):
    wanted_codes = set()
    for codes in target_df["selected_codes"]:
        wanted_codes.update(codes)
    price_feature_df = exec_core.load_price_features(
        wanted_dates=target_df["date"].unique(),
        wanted_codes=wanted_codes,
    )

    detail_frames = []
    trade_frames = []
    for capital in capital_list:
        for participation_limit in participation_limit_list:
            detail_df, trade_df = exec_core.simulate_execution_capacity(
                target_df,
                weekly_returns_df,
                price_feature_df,
                capital=capital,
                participation_limit=participation_limit,
                fixed_cost_bps=0,
                impact_coef_bps=IMPACT_COEF_BPS,
            )
            detail_df = apply_buy_only_fixed_cost(detail_df, trade_df, fixed_cost_bps=FIXED_COST_BPS)
            detail_frames.append(detail_df)
            trade_frames.append(trade_df)
    detail_df = pd.concat(detail_frames, ignore_index=True)
    trade_df = pd.concat(trade_frames, ignore_index=True) if trade_frames else pd.DataFrame()
    summary_df, annual_df = exec_core.summarize_execution(detail_df)
    return detail_df, summary_df, trade_df, annual_df


def apply_buy_only_fixed_cost(
    detail_df: pd.DataFrame,
    trade_df: pd.DataFrame,
    fixed_cost_bps: float,
) -> pd.DataFrame:
    """Apply buy-side fixed cost only; skip fixed cost on each scenario's initial build."""
    if detail_df.empty:
        return detail_df

    detail_df = detail_df.copy()
    key_cols = ["scenario", "capital", "participation_limit", "date"]
    detail_df["date"] = pd.to_datetime(detail_df["date"])

    if trade_df.empty:
        detail_df["period_fixed_cost"] = 0.0
    else:
        trade_df = trade_df.copy()
        trade_df["date"] = pd.to_datetime(trade_df["date"])
        buy_cost = (
            trade_df[trade_df["side"].eq("buy")]
            .groupby(key_cols, as_index=False)["executed_weight"]
            .sum()
        )
        buy_cost["period_fixed_cost"] = buy_cost["executed_weight"] * (fixed_cost_bps / 10_000.0)
        buy_cost = buy_cost.drop(columns=["executed_weight"])

        first_dates = (
            detail_df.groupby(["scenario", "capital", "participation_limit"], as_index=False)["date"]
            .min()
            .rename(columns={"date": "first_date"})
        )
        buy_cost = buy_cost.merge(first_dates, on=["scenario", "capital", "participation_limit"], how="left")
        buy_cost.loc[buy_cost["date"].eq(buy_cost["first_date"]), "period_fixed_cost"] = 0.0
        buy_cost = buy_cost.drop(columns=["first_date"])

        detail_df = detail_df.drop(columns=["period_fixed_cost"], errors="ignore").merge(
            buy_cost,
            on=key_cols,
            how="left",
        )
        detail_df["period_fixed_cost"] = detail_df["period_fixed_cost"].fillna(0.0)

    detail_df["fixed_cost_bps"] = fixed_cost_bps
    detail_df["period_cost"] = detail_df["period_fixed_cost"] + detail_df["period_impact_cost"]
    detail_df["net_return"] = (1.0 - detail_df["period_cost"]) * (1.0 + detail_df["gross_return"]) - 1.0
    return detail_df


def build_turnover_and_capacity() -> dict[str, pd.DataFrame]:
    print("Building Alpha turnover-control targets...")
    retarget_base_suffix()
    portfolio_df = base.load_portfolio_returns()
    optimal_df, factor_cols = base.load_optimal_vectors()
    price_df = base.load_price_data()
    weekly_returns_df = base.compute_weekly_returns(price_df, portfolio_df)
    suspend_lookup = base.build_suspend_lookup(price_df)
    alpha_screener = load_alpha_screener()

    max_buffer = max(BUFFER_MULTIPLIER_LIST)
    contexts = build_alpha_contexts(
        portfolio_df,
        optimal_df,
        factor_cols,
        weekly_returns_df,
        suspend_lookup,
        alpha_screener,
        max_candidate_pool_size=int(np.ceil(ALPHA_TOP_N * max_buffer)),
    )
    baseline_df = build_alpha_baseline_returns(contexts, weekly_returns_df, top_n=ALPHA_TOP_N)
    baseline_df["description"] = "Barra Top500 -> Alpha Top50"

    returns_frames = [baseline_df]
    for max_turnover in MAX_TURNOVER_LIST:
        for buffer_multiplier in BUFFER_MULTIPLIER_LIST:
            returns_frames.append(
                turnover_core.run_turnover_control_scenario(
                    max_turnover,
                    buffer_multiplier,
                    contexts,
                    weekly_returns_df,
                    top_n=ALPHA_TOP_N,
                )
            )
    returns_df = pd.concat(returns_frames, ignore_index=True)
    cost_df, turnover_annual_df = turnover_core.build_cost_stress(returns_df, [0, 5, 10, 20, 50, 100])
    turnover_summary_df = turnover_core.build_compact_summary(cost_df, key_costs=(5, 10, 20, 50, 100))

    print("Simulating execution turnover revaluation...")
    reval_detail_df, reval_summary_df, _trade_df, reval_annual_df = simulate_target_df(
        returns_df,
        weekly_returns_df,
        REPORT_CAPITAL_LIST,
        PARTICIPATION_LIMIT_LIST,
    )
    ranking_df = turnover_reval.build_scenario_ranking(reval_summary_df, reval_annual_df, returns_df)

    print("Simulating selected capacity curve...")
    selected_target_df = returns_df[
        returns_df["scenario"].isin(["baseline", "tc60_buf1", "tc60_buf2", "tc60_buf3", "tc60_buf4"])
    ].copy()
    capacity_detail_df, capacity_summary_df, capacity_trade_df, capacity_annual_df = simulate_target_df(
        selected_target_df,
        weekly_returns_df,
        SMALL_CAPITAL_LIST,
        PARTICIPATION_LIMIT_LIST,
    )

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    outputs = {
        f"turnover_control_experiment_returns_{BASE_SUFFIX}.csv": returns_df,
        f"turnover_control_experiment_summary_{BASE_SUFFIX}.csv": turnover_summary_df,
        f"turnover_control_experiment_cost_stress_{BASE_SUFFIX}.csv": cost_df,
        f"turnover_control_experiment_annual_{BASE_SUFFIX}.csv": turnover_annual_df,
        f"execution_turnover_revaluation_targets_{BASE_SUFFIX}.csv": returns_df,
        f"execution_turnover_revaluation_detail_{BASE_SUFFIX}.csv": reval_detail_df,
        f"execution_turnover_revaluation_summary_{BASE_SUFFIX}.csv": reval_summary_df,
        f"execution_turnover_revaluation_ranking_{BASE_SUFFIX}.csv": ranking_df,
        f"execution_turnover_revaluation_annual_{BASE_SUFFIX}.csv": reval_annual_df,
        f"execution_capacity_detail_{BASE_SUFFIX}.csv": capacity_detail_df,
        f"execution_capacity_summary_{BASE_SUFFIX}.csv": capacity_summary_df,
        f"execution_capacity_trade_detail_{BASE_SUFFIX}.csv": capacity_trade_df,
        f"execution_capacity_annual_{BASE_SUFFIX}.csv": capacity_annual_df,
    }
    for name, df in outputs.items():
        df.to_csv(DATA_DIR / name, index=False, encoding="utf-8-sig")

    build_turnover_platform_figure(ranking_df, reval_summary_df, capacity_summary_df)
    build_capacity_figure(capacity_summary_df)
    return {
        "returns": returns_df,
        "ranking": ranking_df,
        "reval_summary": reval_summary_df,
        "capacity_summary": capacity_summary_df,
        "weekly_returns": weekly_returns_df,
        "price_df": price_df,
    }


def build_parameter_optimal_vectors(cumulative_returns_df: pd.DataFrame, params: dict) -> pd.DataFrame:
    strategy = FactorTimingStrategy(
        long_prd=params["long_prd"],
        short_prd=params["short_prd"],
        channel_bins=params["channel_bins"],
        extreme_value=1,
        top_n=BARRA_POOL_SIZE,
    )
    with contextlib.redirect_stdout(io.StringIO()):
        pst_df = strategy.calc_pst(cumulative_returns_df)
        return strategy.generate_optimal_vector(pst_df)


def build_core_parameter_stability() -> dict[str, pd.DataFrame]:
    print("Building Alpha core-parameter stability grid...")
    retarget_base_suffix()
    portfolio_df = base.load_portfolio_returns()
    price_df = base.load_price_data()
    weekly_returns_df = base.compute_weekly_returns(price_df, portfolio_df)
    suspend_lookup = base.build_suspend_lookup(price_df)
    cumulative_returns_df = pd.read_csv(DATA_DIR / "cumulative_returns_cne6.csv", parse_dates=["date"])
    factor_cols = [col for col in cumulative_returns_df.columns if col != "date"]
    cumulative_returns_df = cumulative_returns_df.set_index("date").sort_index()
    exposure_df = base.load_signal_date_exposures(portfolio_df["signal_date"].unique(), factor_cols)
    alpha_screener = load_alpha_screener()

    frames = []
    for long_prd in [10, 20, 40]:
        for short_prd in [3, 5, 10]:
            for channel_bins in [2, 3]:
                params = {"long_prd": long_prd, "short_prd": short_prd, "channel_bins": channel_bins}
                optimal_df = build_parameter_optimal_vectors(cumulative_returns_df, params)
                contexts = build_alpha_contexts(
                    portfolio_df,
                    optimal_df,
                    factor_cols,
                    weekly_returns_df,
                    suspend_lookup,
                    alpha_screener,
                    max_candidate_pool_size=ALPHA_TOP_N * 2,
                    exposure_df=exposure_df,
                )
                returns_df = build_alpha_baseline_returns(contexts, weekly_returns_df, top_n=ALPHA_TOP_N)
                scenario = f"p_l{long_prd}_s{short_prd}_b{channel_bins}_x500_y50_baseline"
                returns_df["scenario"] = scenario
                returns_df["description"] = (
                    f"L={long_prd}, S={short_prd}, bins={channel_bins}, X=500, Y=50, baseline"
                )
                returns_df["long_prd"] = long_prd
                returns_df["short_prd"] = short_prd
                returns_df["channel_bins"] = channel_bins
                returns_df["extreme_value"] = 1
                returns_df["top_n"] = ALPHA_TOP_N
                returns_df["barra_pool_size"] = BARRA_POOL_SIZE
                returns_df["alpha_top_n"] = ALPHA_TOP_N
                frames.append(returns_df)

    target_df = pd.concat(frames, ignore_index=True)
    detail_df, summary_df, _trade_df, annual_df = simulate_target_df(
        target_df,
        weekly_returns_df,
        CAPITAL_LIST,
        PARTICIPATION_LIMIT_LIST,
    )
    ranking_df = core_stability.build_parameter_ranking(summary_df, annual_df, target_df)
    fold_df, train_score_df = core_stability.select_walk_forward(detail_df, target_df, train_years=3, test_years=1)

    benchmark_scenarios = []
    for scenario in [BASE_SCENARIO] + ranking_df["scenario"].head(5).tolist():
        if scenario not in benchmark_scenarios:
            benchmark_scenarios.append(scenario)
    wf_target_df = core_stability.build_walk_forward_targets(target_df, fold_df, benchmark_scenarios)
    wf_detail_df, wf_summary_df, _wf_trade_df, wf_annual_df = simulate_target_df(
        wf_target_df,
        weekly_returns_df,
        CAPITAL_LIST,
        PARTICIPATION_LIMIT_LIST,
    )

    outputs = {
        f"core_parameter_stability_targets_{BASE_SUFFIX}.csv": target_df,
        f"core_parameter_stability_execution_detail_{BASE_SUFFIX}.csv": detail_df,
        f"core_parameter_stability_execution_summary_{BASE_SUFFIX}.csv": summary_df,
        f"core_parameter_stability_ranking_{BASE_SUFFIX}.csv": ranking_df,
        f"core_parameter_stability_annual_{BASE_SUFFIX}.csv": annual_df,
        f"core_parameter_stability_walk_forward_detail_{BASE_SUFFIX}.csv": wf_detail_df,
        f"core_parameter_stability_walk_forward_summary_{BASE_SUFFIX}.csv": wf_summary_df,
        f"core_parameter_stability_walk_forward_annual_{BASE_SUFFIX}.csv": wf_annual_df,
        f"core_parameter_stability_walk_forward_folds_{BASE_SUFFIX}.csv": fold_df,
        f"core_parameter_stability_walk_forward_train_scores_{BASE_SUFFIX}.csv": train_score_df,
    }
    for name, df in outputs.items():
        df.to_csv(DATA_DIR / name, index=False, encoding="utf-8-sig")

    build_core_figure(ranking_df, summary_df)
    return {
        "target": target_df,
        "ranking": ranking_df,
        "summary": summary_df,
        "wf_summary": wf_summary_df,
        "folds": fold_df,
    }


def build_2026_case() -> dict[str, pd.DataFrame]:
    print("Building Alpha 2026 case analysis...")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    end_date = case2026.get_latest_case_end_date()
    incremental_factor_returns, incremental_exposure, incremental_price, factor_cols = (
        case2026.build_incremental_barra_data(case2026.INCREMENTAL_START_DATE, end_date)
    )
    factor_returns = case2026.combine_factor_returns(incremental_factor_returns)
    cumulative_returns = case2026.build_cumulative_returns(factor_returns, factor_cols)
    price_df = case2026.combine_price_data(incremental_price)

    weekly_dates, all_dates = case2026.build_weekly_dates(price_df)
    signal_dates = case2026.get_signal_dates(weekly_dates, all_dates)
    historical_exposure = case2026.load_historical_signal_exposures(signal_dates, factor_cols)
    incremental_signal_exposure = incremental_exposure[
        incremental_exposure["date"].isin(pd.to_datetime(signal_dates))
    ][["date", "code"] + factor_cols].copy()
    signal_exposure = pd.concat([historical_exposure, incremental_signal_exposure], ignore_index=True).drop_duplicates(
        ["date", "code"], keep="last"
    )

    weekly_strategy = AlphaFastFactorTimingStrategy(
        long_prd=20,
        short_prd=5,
        channel_bins=2,
        extreme_value=1,
        top_n=BARRA_POOL_SIZE,
    )
    weekly_returns_df = weekly_strategy.precompute_weekly_returns(price_df, weekly_dates)
    alpha_screener = load_alpha_screener()

    baseline_strategy = AlphaFastFactorTimingStrategy(
        long_prd=20,
        short_prd=5,
        channel_bins=2,
        extreme_value=1,
        top_n=BARRA_POOL_SIZE,
        exposure_df=signal_exposure,
        weekly_returns_df=weekly_returns_df,
    )
    baseline_df, optimal_df = baseline_strategy.run_weekly_rebalance(
        signal_exposure,
        cumulative_returns.set_index("date"),
        price_df,
        active_screener=alpha_screener,
        active_top_n=ALPHA_TOP_N,
    )

    suspend_lookup = base.build_suspend_lookup(price_df[["date", "code", "pct_chg", "is_suspend"]])
    contexts = build_alpha_contexts(
        baseline_df,
        optimal_df,
        factor_cols,
        weekly_returns_df,
        suspend_lookup,
        alpha_screener,
        max_candidate_pool_size=ALPHA_TOP_N * 2,
        exposure_df=signal_exposure,
    )
    tc_df = turnover_core.run_turnover_control_scenario(
        0.50,
        2.0,
        contexts,
        weekly_returns_df,
        top_n=ALPHA_TOP_N,
    )
    tc_df["scenario"] = "tc50_buf2"

    target_df = pd.concat(
        [baseline_df.assign(scenario="baseline"), tc_df],
        ignore_index=True,
    )
    price_feature_df = case2026.build_price_features(price_df, target_df)
    execution_detail, _trade_detail = exec_core.simulate_execution_capacity(
        target_df=target_df,
        weekly_returns_df=weekly_returns_df,
        price_feature_df=price_feature_df,
        capital=case2026.CAPITAL,
        participation_limit=case2026.PARTICIPATION_LIMIT,
        fixed_cost_bps=FIXED_COST_BPS,
        impact_coef_bps=IMPACT_COEF_BPS,
    )

    case_baseline = baseline_df[baseline_df["date"].dt.year == case2026.CASE_YEAR].copy()
    case_tc = tc_df[tc_df["date"].dt.year == case2026.CASE_YEAR].copy()
    case_execution = execution_detail[execution_detail["date"].dt.year == case2026.CASE_YEAR].copy()
    if case_baseline.empty or case_execution.empty:
        raise RuntimeError("No 2026 Alpha case rows were generated.")

    summary_rows = []
    raw_metrics = case2026.calculate_metrics(case_baseline, "return")
    raw_metrics.update({"scenario": "baseline_raw", "avg_turnover": case_baseline["turnover"].mean()})
    summary_rows.append(raw_metrics)
    turnover_by_scenario = {
        "baseline": case_baseline["turnover"].mean(),
        "tc50_buf2": case_tc["turnover"].mean(),
    }
    for scenario, group in case_execution.groupby("scenario", sort=False):
        metrics = case2026.calculate_metrics(group, "net_return")
        metrics.update(
            {
                "scenario": scenario,
                "avg_turnover": turnover_by_scenario.get(scenario, np.nan),
                "avg_cash_weight": group["cash_weight"].mean(),
                "avg_fill_ratio": group["fill_ratio"].mean(),
                "avg_period_cost": group["period_cost"].mean(),
            }
        )
        summary_rows.append(metrics)
    summary_df = pd.DataFrame(summary_rows)

    factor_returns.to_csv(DATA_DIR / f"case_2026_factor_returns_{BASE_SUFFIX}.csv", index=False, encoding="utf-8-sig")
    case_baseline.to_csv(
        DATA_DIR / f"case_2026_portfolio_returns_{BASE_SUFFIX}.csv", index=False, encoding="utf-8-sig"
    )
    case_tc.to_csv(
        DATA_DIR / f"case_2026_portfolio_returns_{BASE_SUFFIX}_tc50_buf2.csv", index=False, encoding="utf-8-sig"
    )
    case_execution.to_csv(
        DATA_DIR / f"case_2026_execution_detail_{BASE_SUFFIX}.csv", index=False, encoding="utf-8-sig"
    )
    summary_df.to_csv(DATA_DIR / f"case_2026_summary_{BASE_SUFFIX}.csv", index=False, encoding="utf-8-sig")

    build_2026_raw_figure(case_baseline)
    build_2026_cost_figure(case_execution)
    return {"summary": summary_df, "baseline": case_baseline, "tc": case_tc, "execution": case_execution}


def period_end_nav(df: pd.DataFrame, return_col: str) -> pd.DataFrame:
    df = df.sort_values("date").copy()
    nav = (1.0 + df[return_col]).cumprod()
    dates = [df["date"].iloc[0]] + df["next_date"].tolist()
    values = [1.0] + nav.tolist()
    return pd.DataFrame({"date": pd.to_datetime(dates), "nav": values})


def fmt_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def build_turnover_platform_figure(
    ranking_df: pd.DataFrame, reval_summary_df: pd.DataFrame, capacity_summary_df: pd.DataFrame
) -> None:
    configure_matplotlib()
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    combined = pd.concat([reval_summary_df, capacity_summary_df], ignore_index=True, sort=False)
    combined = combined.sort_values(["scenario", "capital", "participation_limit"]).drop_duplicates(
        ["scenario", "capital", "participation_limit"], keep="last"
    )
    scenarios = ["baseline", "tc60_buf1", "tc60_buf2", "tc60_buf3", "tc60_buf4"]
    colors = {
        "baseline": "#d62728",
        "tc60_buf1": "#7f8792",
        "tc60_buf2": "#1f5b9d",
        "tc60_buf3": "#2f8f5b",
        "tc60_buf4": "#c46f2d",
    }
    capital_order = [10_000_000, 30_000_000, 100_000_000, 300_000_000, 500_000_000]
    capital_labels = ["1000万", "3000万", "1亿", "3亿", "5亿"]
    plot_df = combined[
        combined["scenario"].isin(scenarios)
        & combined["capital"].isin(capital_order)
        & combined["participation_limit"].round(4).eq(0.10)
    ].copy()
    plot_df["capital_pos"] = plot_df["capital"].map({capital: i for i, capital in enumerate(capital_order)})

    fig = plt.figure(figsize=(11.2, 5.4))
    grid = fig.add_gridspec(2, 1, height_ratios=[3.1, 1.35], hspace=0.36)
    ax = fig.add_subplot(grid[0])
    for scenario in scenarios:
        group = plot_df[plot_df["scenario"].eq(scenario)].sort_values("capital_pos")
        ax.plot(
            group["capital_pos"],
            group["annual_return"] * 100,
            marker="o",
            linewidth=2.2,
            color=colors[scenario],
            label=scenario,
        )
    ax.set_title("Alpha精选版：10% ADV约束下的容量曲线", fontsize=14, fontweight="bold", pad=10)
    ax.set_xlabel("资金规模")
    ax.set_ylabel("净年化收益（%）")
    ax.set_xticks(range(len(capital_order)))
    ax.set_xticklabels(capital_labels)
    ax.grid(True, alpha=0.22)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(loc="best", ncol=5, frameon=False)

    ax_table = fig.add_subplot(grid[1])
    ax_table.axis("off")
    table_source = ranking_df.set_index("scenario").reindex(scenarios).reset_index()
    table_rows = [
        [
            row["scenario"],
            fmt_pct(row["mean_annual_return"]),
            fmt_pct(row["min_annual_return"]),
            fmt_pct(row["mean_max_drawdown"]),
            fmt_pct(row["mean_fill_ratio"]),
            fmt_pct(row["mean_target_overlap"]),
            fmt_pct(row["mean_cash_weight"]),
        ]
        for _, row in table_source.iterrows()
    ]
    table = ax_table.table(
        cellText=table_rows,
        colLabels=["候选", "平均净年化", "最低净年化", "平均回撤", "成交完成", "目标兑现", "平均现金"],
        loc="center",
        cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.35)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#cfd6e3")
        if row == 0:
            cell.set_facecolor("#2d3f57")
            cell.set_text_props(color="white", weight="bold")
        elif row % 2 == 0:
            cell.set_facecolor("#f3f6fa")
    fig.savefig(IMAGE_DIR / f"final_main_turnover_platform_{BASE_SUFFIX}.png", dpi=220, bbox_inches="tight")
    plt.close(fig)


def build_capacity_figure(summary_df: pd.DataFrame) -> None:
    configure_matplotlib()
    scenarios = ["baseline", "tc60_buf2"]
    colors = {"baseline": "#7f8792", "tc60_buf2": "#1f5b9d"}
    plot_df = summary_df[
        summary_df["scenario"].isin(scenarios)
        & summary_df["participation_limit"].round(4).eq(0.10)
        & summary_df["capital"].isin([10_000_000, 30_000_000, 100_000_000])
    ].copy()
    plot_df["capital_yi"] = plot_df["capital"] / 100_000_000

    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.3))
    for scenario in scenarios:
        group = plot_df[plot_df["scenario"].eq(scenario)].sort_values("capital_yi")
        axes[0].plot(group["capital_yi"], group["annual_return"] * 100, marker="o", linewidth=2.3, label=scenario, color=colors[scenario])
        axes[1].plot(group["capital_yi"], group["avg_target_overlap_weight"] * 100, marker="o", linewidth=2.3, label=scenario, color=colors[scenario])
    axes[0].set_title("Alpha精选版：小规模资金10% ADV下净年化", fontsize=13.5, fontweight="bold")
    axes[0].set_ylabel("净年化（%）")
    axes[1].set_title("Alpha精选版：小规模资金10% ADV下目标兑现", fontsize=13.5, fontweight="bold")
    axes[1].set_ylabel("目标兑现（%）")
    for ax in axes:
        ax.set_xlabel("资金规模（亿元）")
        ax.set_xticks([0.1, 0.3, 1.0])
        ax.set_xticklabels(["1000万", "3000万", "1亿"])
        ax.grid(True, alpha=0.22)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.legend(frameon=False, loc="best")
    fig.tight_layout()
    fig.savefig(IMAGE_DIR / f"final_main_capacity_tc60_buf2_{BASE_SUFFIX}.png", dpi=220, bbox_inches="tight")
    plt.close(fig)


def build_core_figure(ranking_df: pd.DataFrame, summary_df: pd.DataFrame) -> None:
    configure_matplotlib()
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.9), gridspec_kw={"width_ratios": [1.05, 1]})
    ax_scatter, ax_heat = axes
    scatter = ax_scatter.scatter(
        -ranking_df["mean_max_drawdown"] * 100,
        ranking_df["mean_annual_return"] * 100,
        c=ranking_df["mean_cash_weight"] * 100,
        s=48 + ranking_df["mean_fill_ratio"] * 45,
        cmap="viridis_r",
        alpha=0.78,
        edgecolors="white",
        linewidths=0.6,
    )
    current = ranking_df[ranking_df["scenario"].eq(BASE_SCENARIO)].iloc[0]
    ax_scatter.scatter(
        [-current["mean_max_drawdown"] * 100],
        [current["mean_annual_return"] * 100],
        s=150,
        facecolors="none",
        edgecolors="#d62728",
        linewidths=2.2,
        label="当前参数",
    )
    ax_scatter.annotate(
        "L20/S5/B2/X500/Y50",
        xy=(-current["mean_max_drawdown"] * 100, current["mean_annual_return"] * 100),
        xytext=(8, -12),
        textcoords="offset points",
        fontsize=9.5,
        color="#d62728",
    )
    ax_scatter.set_title("Alpha精选版：收益-回撤-现金权衡", fontsize=13.5, fontweight="bold", pad=9)
    ax_scatter.set_xlabel("平均最大回撤绝对值（%）")
    ax_scatter.set_ylabel("平均净年化（%）")
    ax_scatter.grid(True, alpha=0.22)
    ax_scatter.spines["top"].set_visible(False)
    ax_scatter.spines["right"].set_visible(False)
    ax_scatter.legend(frameon=False, loc="best")
    fig.colorbar(scatter, ax=ax_scatter, fraction=0.045, pad=0.02).set_label("平均现金（%）")

    meta_cols = ["scenario", "long_prd", "short_prd", "channel_bins"]
    heat_df = summary_df.merge(ranking_df[meta_cols], on="scenario", how="left")
    heat_df = heat_df[
        heat_df["capital"].eq(500_000_000)
        & heat_df["participation_limit"].round(4).eq(0.10)
        & heat_df["channel_bins"].eq(2)
    ].copy()
    pivot = heat_df.pivot(index="long_prd", columns="short_prd", values="annual_return").sort_index()
    image = ax_heat.imshow(pivot.values * 100, cmap="RdYlGn", aspect="auto")
    ax_heat.set_title("固定 B2/X500/Y50：5亿、10% ADV净年化", fontsize=13.5, fontweight="bold", pad=9)
    ax_heat.set_xticks(range(len(pivot.columns)))
    ax_heat.set_xticklabels(pivot.columns)
    ax_heat.set_yticks(range(len(pivot.index)))
    ax_heat.set_yticklabels(pivot.index)
    ax_heat.set_xlabel("short_prd")
    ax_heat.set_ylabel("long_prd")
    for i, long_prd in enumerate(pivot.index):
        for j, short_prd in enumerate(pivot.columns):
            ax_heat.text(j, i, f"{pivot.iloc[i, j] * 100:.1f}%", ha="center", va="center", fontsize=9)
            if long_prd == 20 and short_prd == 5:
                ax_heat.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False, edgecolor="#1f5b9d", linewidth=2.2))
    fig.colorbar(image, ax=ax_heat, fraction=0.045, pad=0.02).set_label("净年化（%）")
    fig.tight_layout()
    fig.savefig(IMAGE_DIR / f"final_main_core_parameter_stability_{BASE_SUFFIX}_baseline.png", dpi=220, bbox_inches="tight")
    plt.close(fig)


def build_2026_raw_figure(case_baseline_df: pd.DataFrame) -> None:
    configure_matplotlib()
    nav_df = period_end_nav(case_baseline_df, "return")
    fig, ax = plt.subplots(figsize=(12.5, 5.2))
    ax.plot(nav_df["date"], nav_df["nav"], color="#1F77B4", linewidth=2.2, label="baseline（不计成本）")
    ax.axhline(1.0, color="#6B7280", linewidth=1.0, linestyle="--", alpha=0.7)
    ax.set_title("2026年Alpha精选版原始收益曲线（不计成本、不加换手控制）", fontsize=15, pad=14)
    ax.set_ylabel("净值（2026年初=1）")
    ax.grid(True, alpha=0.25)
    ax.legend(frameon=False, loc="best")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(IMAGE_DIR / f"final_main_2026_raw_curve_{BASE_SUFFIX}.png", dpi=220)
    plt.close(fig)


def build_2026_cost_figure(case_execution_df: pd.DataFrame) -> None:
    configure_matplotlib()
    fig, ax = plt.subplots(figsize=(12.5, 5.2))
    colors = {"baseline": "#D62728", "tc50_buf2": "#2CA02C"}
    labels = {"baseline": "原始目标持仓", "tc50_buf2": "换手控制后（tc50_buf2）"}
    for scenario, group in case_execution_df.groupby("scenario", sort=False):
        nav_df = period_end_nav(group.sort_values("date"), "net_return")
        ax.plot(nav_df["date"], nav_df["nav"], linewidth=2.2, color=colors.get(scenario), label=labels.get(scenario, scenario))
    ax.axhline(1.0, color="#6B7280", linewidth=1.0, linestyle="--", alpha=0.7)
    ax.set_title("2026年Alpha精选版成本约束后收益曲线（1亿资金，10%ADV参与率）", fontsize=15, pad=14)
    ax.set_ylabel("净值（2026年初=1）")
    ax.grid(True, alpha=0.25)
    ax.legend(frameon=False, loc="best")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(IMAGE_DIR / f"final_main_2026_cost_curve_{BASE_SUFFIX}.png", dpi=220)
    plt.close(fig)


def main() -> None:
    retarget_base_suffix()
    build_turnover_and_capacity()
    build_core_parameter_stability()
    build_2026_case()
    print("Alpha selected chapter 6-8 artifacts finished.")


if __name__ == "__main__":
    main()
