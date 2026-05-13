import os
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models.barra_cne6 import BarraCNE6, __market_engine__
from src.strategies.factor_timing_strategy_v3 import FactorTimingStrategy
from src.optimize import execution_capacity_experiment as execution_core


OUTPUT_DIR = PROJECT_ROOT / "output" / "cne6"
DATA_DIR = OUTPUT_DIR / "data"
IMAGE_DIR = OUTPUT_DIR / "images" / "report"

SUFFIX = "l20_s5_b2_e1_n100"
HISTORICAL_FACTOR_RETURNS_PATH = DATA_DIR / "factor_returns_cne6.csv"
HISTORICAL_CUMULATIVE_RETURNS_PATH = DATA_DIR / "cumulative_returns_cne6.csv"
HISTORICAL_FACTOR_EXPOSURE_PATH = DATA_DIR / "factor_exposure_cne6.csv"
HISTORICAL_PRICE_PATH = DATA_DIR / "price_data_cne6.csv"

CASE_FACTOR_RETURNS_PATH = DATA_DIR / f"case_2026_factor_returns_{SUFFIX}.csv"
CASE_PORTFOLIO_BASELINE_PATH = DATA_DIR / f"case_2026_portfolio_returns_{SUFFIX}.csv"
CASE_PORTFOLIO_TC_PATH = DATA_DIR / f"case_2026_portfolio_returns_{SUFFIX}_tc50_buf2.csv"
CASE_EXECUTION_DETAIL_PATH = DATA_DIR / f"case_2026_execution_detail_{SUFFIX}.csv"
CASE_SUMMARY_PATH = DATA_DIR / f"case_2026_summary_{SUFFIX}.csv"

RAW_FIGURE_PATH = IMAGE_DIR / f"final_main_2026_raw_curve_{SUFFIX}.png"
COST_FIGURE_PATH = IMAGE_DIR / f"final_main_2026_cost_curve_{SUFFIX}.png"

CASE_YEAR = 2026
INCREMENTAL_START_DATE = "2025-10-01"
CAPITAL = 100_000_000
PARTICIPATION_LIMIT = 0.10
FIXED_COST_BPS = 10
IMPACT_COEF_BPS = 25


class NullTradeRecorder:
    def process_rebalance(self, trade_date, selected_codes, price_df):
        return None


class FastFactorTimingStrategy(FactorTimingStrategy):
    def __init__(self, *args, exposure_df=None, weekly_returns_df=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.trade_recorder = NullTradeRecorder()
        self._weekly_returns_df = weekly_returns_df
        self._exposure_by_date = {}
        self._available_exposure_dates = []
        if exposure_df is not None:
            self.set_exposure_lookup(exposure_df)

    def set_exposure_lookup(self, exposure_df):
        exposure_df = exposure_df.copy()
        exposure_df["date"] = pd.to_datetime(exposure_df["date"])
        self._exposure_by_date = {
            pd.Timestamp(date): group.reset_index(drop=True)
            for date, group in exposure_df.groupby("date", sort=True)
        }
        self._available_exposure_dates = sorted(self._exposure_by_date)

    def precompute_weekly_returns(self, price_df, weekly_dates):
        if self._weekly_returns_df is not None:
            return self._weekly_returns_df
        self._weekly_returns_df = super().precompute_weekly_returns(price_df, weekly_dates)
        return self._weekly_returns_df

    def _get_signal_exposure(self, signal_date):
        signal_date = pd.Timestamp(signal_date)
        if signal_date in self._exposure_by_date:
            return self._exposure_by_date[signal_date]
        previous = [date for date in self._available_exposure_dates if date <= signal_date]
        if not previous:
            return None
        return self._exposure_by_date[previous[-1]]

    def select_stocks(
        self,
        factor_exposure_df,
        optimal_vector,
        signal_date,
        trade_date,
        suspended_codes=None,
        candidate_pool_size=None,
    ):
        suspended_codes = set(suspended_codes or [])
        current_data = self._get_signal_exposure(signal_date)
        if current_data is None or current_data.empty:
            print(f"Warning: no factor exposure for signal date {signal_date}")
            return []

        if suspended_codes:
            current_data = current_data[~current_data["code"].isin(suspended_codes)]
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
            .sort_values("similarity", ascending=False)
            .head(pool_size)
        )
        return ranked["code"].tolist()


def get_latest_case_end_date():
    query = """
    SELECT MAX(date) AS max_date
    FROM stock_eod
    WHERE date >= '2026-01-01'
    """
    max_date = pd.read_sql(query, __market_engine__)["max_date"].iloc[0]
    if pd.isna(max_date):
        raise RuntimeError("stock_eod has no 2026 data.")
    return pd.Timestamp(max_date).strftime("%Y-%m-%d")


def build_incremental_barra_data(start_date, end_date):
    barra = BarraCNE6(start_date=start_date, end_date=end_date)
    price_df, _industry_df = barra.get_stock_data()
    balance_df, income_df, cashflow_df = barra.get_financial_data()

    print("\nCalculating incremental Barra CNE6 exposures...")
    size_df = barra.calculate_size_factors(price_df)
    vol_df = barra.calculate_volatility_factors(price_df)
    mom_df = barra.calculate_momentum_factors(price_df)
    value_df = barra.calculate_value_factors(balance_df, income_df, cashflow_df, price_df)
    growth_df = barra.calculate_growth_factors(income_df, price_df)
    lev_df = barra.calculate_leverage_factors(balance_df, price_df)
    liq_df = barra.calculate_liquidity_factors(price_df)
    prof_df = barra.calculate_profitability_factors(income_df, balance_df, price_df)
    inv_df = barra.calculate_investment_factors(balance_df, cashflow_df, price_df)
    other_df = barra.calculate_other_factors(price_df)

    factor_exposure_df = size_df.copy()
    factor_dfs = [
        (vol_df, ["BETA", "RESVOL", "HISTVOL"]),
        (mom_df, ["MOMENTUM", "RESMOM"]),
        (value_df, ["BTOP", "EYIELD", "CFP", "SP", "LP"]),
        (growth_df, ["EGRO", "SGRO"]),
        (lev_df, ["MLEV", "BLEV"]),
        (liq_df, ["LIQUIDITY", "STOM", "STOQ"]),
        (prof_df, ["ROE", "ROA"]),
        (inv_df, ["CAPX", "AGRO"]),
        (other_df, ["TOPSI", "SEASON"]),
    ]
    for factor_df, factor_names in factor_dfs:
        if not factor_df.empty:
            factor_exposure_df = factor_exposure_df.merge(
                factor_df[["date", "code"] + factor_names],
                on=["date", "code"],
                how="left",
            )

    factor_exposure_df = factor_exposure_df[factor_exposure_df["date"] >= start_date].copy()
    for factor in barra.style_factors:
        if factor in factor_exposure_df.columns:
            factor_exposure_df = barra.standardize_factors(factor_exposure_df, factor)
            factor_exposure_df[factor] = factor_exposure_df.groupby("date")[factor].transform(
                lambda x: x.fillna(x.mean())
            )
            factor_exposure_df[factor] = factor_exposure_df[factor].fillna(0)

    factor_returns_df = barra.calculate_factor_returns(factor_exposure_df, price_df)
    return factor_returns_df, factor_exposure_df, price_df, barra.style_factors


def build_weekly_dates(price_df):
    all_dates = sorted(pd.to_datetime(price_df["date"].unique()))
    weekly_dates = []
    for index, current_date in enumerate(all_dates):
        if index == 0:
            weekly_dates.append(current_date)
        else:
            previous_date = all_dates[index - 1]
            if current_date.isocalendar().week != previous_date.isocalendar().week:
                weekly_dates.append(current_date)
    return weekly_dates, all_dates


def get_signal_dates(weekly_dates, all_dates):
    date_pos = {date: index for index, date in enumerate(all_dates)}
    signal_dates = []
    for current_date in weekly_dates[:-1]:
        pos = date_pos[current_date]
        signal_dates.append(current_date if pos == 0 else all_dates[pos - 1])
    return signal_dates


def load_historical_signal_exposures(signal_dates, factor_cols):
    wanted_dates = {
        pd.Timestamp(date).strftime("%Y-%m-%d")
        for date in signal_dates
        if pd.Timestamp(date).year < CASE_YEAR
    }
    if not wanted_dates:
        return pd.DataFrame(columns=["date", "code"] + factor_cols)

    records = []
    usecols = ["date", "code"] + factor_cols
    for chunk in pd.read_csv(HISTORICAL_FACTOR_EXPOSURE_PATH, usecols=usecols, chunksize=500_000):
        chunk = chunk[chunk["date"].isin(wanted_dates)]
        if not chunk.empty:
            records.append(chunk)
    if not records:
        return pd.DataFrame(columns=usecols)
    exposure_df = pd.concat(records, ignore_index=True)
    exposure_df["date"] = pd.to_datetime(exposure_df["date"])
    return exposure_df


def combine_factor_returns(incremental_factor_returns):
    historical = pd.read_csv(HISTORICAL_FACTOR_RETURNS_PATH, parse_dates=["date"])
    incremental = incremental_factor_returns.copy()
    incremental["date"] = pd.to_datetime(incremental["date"])
    last_historical_date = historical["date"].max()
    combined = pd.concat(
        [historical, incremental[incremental["date"] > last_historical_date]],
        ignore_index=True,
    )
    combined = combined.drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)
    return combined


def build_cumulative_returns(factor_returns_df, factor_cols):
    cumulative = pd.DataFrame({"date": factor_returns_df["date"]})
    for factor in factor_cols:
        cumulative[factor] = (1.0 + factor_returns_df[factor]).cumprod()
    return cumulative


def combine_price_data(incremental_price):
    historical = pd.read_csv(HISTORICAL_PRICE_PATH, parse_dates=["date"])
    incremental = incremental_price.copy()
    incremental["date"] = pd.to_datetime(incremental["date"])
    last_historical_date = historical["date"].max()
    combined = pd.concat(
        [historical, incremental[incremental["date"] > last_historical_date]],
        ignore_index=True,
    )
    combined = (
        combined.drop_duplicates(["date", "code"], keep="last")
        .sort_values(["date", "code"])
        .reset_index(drop=True)
    )
    return combined


def build_price_features(price_df, target_df):
    wanted_dates = set(pd.to_datetime(target_df["date"].unique()))
    wanted_codes = set()
    for codes in target_df["selected_codes"]:
        wanted_codes.update(codes)

    usecols = ["date", "code", "pct_chg", "amount", "is_suspend"]
    feature_df = price_df[usecols].copy()
    feature_df = feature_df.sort_values(["code", "date"]).reset_index(drop=True)
    shifted_amount = feature_df.groupby("code")["amount"].shift(1)
    feature_df["adv_amount"] = (
        shifted_amount.groupby(feature_df["code"])
        .rolling(20, min_periods=5)
        .mean()
        .reset_index(level=0, drop=True)
    )
    feature_df = feature_df[feature_df["date"].isin(wanted_dates)]
    feature_df = feature_df[feature_df["code"].isin(wanted_codes)]
    return feature_df[["date", "code", "pct_chg", "is_suspend", "adv_amount"]]


def calculate_metrics(df, return_col, risk_free_rate=0.03):
    df = df.sort_values("date")
    returns = df[return_col]
    nav = (1.0 + returns).cumprod()
    running_max = nav.cummax()
    drawdown = nav / running_max - 1.0
    years = (df["date"].max() - df["date"].min()).days / 365.25
    cumulative_return = nav.iloc[-1] - 1.0
    annual_return = (
        (1.0 + cumulative_return) ** (1.0 / years) - 1.0
        if years > 0
        else np.nan
    )
    annual_volatility = returns.std() * np.sqrt(52.0)
    sharpe_ratio = (
        (annual_return - risk_free_rate) / annual_volatility
        if annual_volatility and annual_volatility != 0
        else np.nan
    )
    return {
        "period_count": len(df),
        "start_date": df["date"].min().strftime("%Y-%m-%d"),
        "end_date": df["date"].max().strftime("%Y-%m-%d"),
        "cumulative_return": cumulative_return,
        "annual_return": annual_return,
        "annual_volatility": annual_volatility,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown": drawdown.min(),
    }


def format_pct(value):
    return f"{value * 100:.1f}%"


def build_period_end_nav(df, return_col):
    df = df.sort_values("date").copy()
    nav = (1.0 + df[return_col]).cumprod()
    dates = [df["date"].iloc[0]] + df["next_date"].tolist()
    values = [1.0] + nav.tolist()
    return pd.DataFrame({"date": pd.to_datetime(dates), "nav": values})


def plot_raw_curve(case_baseline_df):
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    nav_df = build_period_end_nav(case_baseline_df, "return")

    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    fig, ax = plt.subplots(figsize=(12.5, 5.2))
    ax.plot(nav_df["date"], nav_df["nav"], color="#1F77B4", linewidth=2.2, label="baseline（不计成本）")
    ax.axhline(1.0, color="#6B7280", linewidth=1.0, linestyle="--", alpha=0.7)
    ax.set_title("2026年原始策略收益曲线（不计成本、不加换手控制）", fontsize=15, pad=14)
    ax.set_ylabel("净值（2026年初=1）")
    ax.grid(True, alpha=0.25)
    ax.legend(frameon=False, loc="best")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(RAW_FIGURE_PATH, dpi=220)
    plt.close(fig)


def plot_cost_curve(case_execution_df):
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    df = case_execution_df.sort_values(["scenario", "date"]).copy()

    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    fig, ax = plt.subplots(figsize=(12.5, 5.2))
    colors = {"baseline": "#D62728", "tc50_buf2": "#2CA02C"}
    labels = {"baseline": "原始策略", "tc50_buf2": "换手控制后（tc50_buf2）"}
    for scenario, group in df.groupby("scenario", sort=False):
        group = group.sort_values("date")
        nav_df = build_period_end_nav(group, "net_return")
        ax.plot(
            nav_df["date"],
            nav_df["nav"],
            linewidth=2.2,
            color=colors.get(scenario),
            label=labels.get(scenario, scenario),
        )
    ax.axhline(1.0, color="#6B7280", linewidth=1.0, linestyle="--", alpha=0.7)
    ax.set_title("2026年成本约束后收益曲线（1亿资金，10%ADV参与率）", fontsize=15, pad=14)
    ax.set_ylabel("净值（2026年初=1）")
    ax.grid(True, alpha=0.25)
    ax.legend(frameon=False, loc="best")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(COST_FIGURE_PATH, dpi=220)
    plt.close(fig)


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    end_date = get_latest_case_end_date()
    print(f"Latest 2026 market date: {end_date}")

    incremental_factor_returns, incremental_exposure, incremental_price, factor_cols = (
        build_incremental_barra_data(INCREMENTAL_START_DATE, end_date)
    )

    factor_returns = combine_factor_returns(incremental_factor_returns)
    cumulative_returns = build_cumulative_returns(factor_returns, factor_cols)
    price_df = combine_price_data(incremental_price)

    weekly_dates, all_dates = build_weekly_dates(price_df)
    signal_dates = get_signal_dates(weekly_dates, all_dates)
    historical_exposure = load_historical_signal_exposures(signal_dates, factor_cols)
    incremental_signal_exposure = incremental_exposure[
        incremental_exposure["date"].isin(pd.to_datetime(signal_dates))
    ][["date", "code"] + factor_cols].copy()
    signal_exposure = pd.concat(
        [historical_exposure, incremental_signal_exposure],
        ignore_index=True,
    ).drop_duplicates(["date", "code"], keep="last")

    weekly_returns_strategy = FastFactorTimingStrategy(
        long_prd=20,
        short_prd=5,
        channel_bins=2,
        extreme_value=1,
        top_n=100,
    )
    weekly_returns_df = weekly_returns_strategy.precompute_weekly_returns(price_df, weekly_dates)

    baseline_strategy = FastFactorTimingStrategy(
        long_prd=20,
        short_prd=5,
        channel_bins=2,
        extreme_value=1,
        top_n=100,
        exposure_df=signal_exposure,
        weekly_returns_df=weekly_returns_df,
    )
    baseline_df, _baseline_optimal = baseline_strategy.run_weekly_rebalance(
        signal_exposure,
        cumulative_returns.set_index("date"),
        price_df,
    )

    tc_strategy = FastFactorTimingStrategy(
        long_prd=20,
        short_prd=5,
        channel_bins=2,
        extreme_value=1,
        top_n=100,
        turnover_control=True,
        max_turnover=0.50,
        turnover_buffer_multiplier=2.0,
        exposure_df=signal_exposure,
        weekly_returns_df=weekly_returns_df,
    )
    tc_df, _tc_optimal = tc_strategy.run_weekly_rebalance(
        signal_exposure,
        cumulative_returns.set_index("date"),
        price_df,
    )

    target_df = pd.concat(
        [
            baseline_df.assign(scenario="baseline"),
            tc_df.assign(scenario="tc50_buf2"),
        ],
        ignore_index=True,
    )
    price_feature_df = build_price_features(price_df, target_df)
    execution_detail, _trade_detail = execution_core.simulate_execution_capacity(
        target_df=target_df,
        weekly_returns_df=weekly_returns_df,
        price_feature_df=price_feature_df,
        capital=CAPITAL,
        participation_limit=PARTICIPATION_LIMIT,
        fixed_cost_bps=FIXED_COST_BPS,
        impact_coef_bps=IMPACT_COEF_BPS,
    )

    case_baseline = baseline_df[baseline_df["date"].dt.year == CASE_YEAR].copy()
    case_tc = tc_df[tc_df["date"].dt.year == CASE_YEAR].copy()
    case_execution = execution_detail[execution_detail["date"].dt.year == CASE_YEAR].copy()

    if case_baseline.empty or case_execution.empty:
        raise RuntimeError("No 2026 case rows were generated.")

    factor_returns.to_csv(CASE_FACTOR_RETURNS_PATH, index=False, encoding="utf-8-sig")
    case_baseline.to_csv(CASE_PORTFOLIO_BASELINE_PATH, index=False, encoding="utf-8-sig")
    case_tc.to_csv(CASE_PORTFOLIO_TC_PATH, index=False, encoding="utf-8-sig")
    case_execution.to_csv(CASE_EXECUTION_DETAIL_PATH, index=False, encoding="utf-8-sig")

    summary_rows = []
    raw_metrics = calculate_metrics(case_baseline, "return")
    raw_metrics.update(
        {
            "scenario": "baseline_raw",
            "avg_turnover": case_baseline["turnover"].mean(),
        }
    )
    summary_rows.append(raw_metrics)
    turnover_by_scenario = {
        "baseline": case_baseline["turnover"].mean(),
        "tc50_buf2": case_tc["turnover"].mean(),
    }
    for scenario, group in case_execution.groupby("scenario", sort=False):
        metrics = calculate_metrics(group, "net_return")
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
    summary_df.to_csv(CASE_SUMMARY_PATH, index=False, encoding="utf-8-sig")

    plot_raw_curve(case_baseline)
    plot_cost_curve(case_execution)

    print("Saved:")
    for path in [
        CASE_FACTOR_RETURNS_PATH,
        CASE_PORTFOLIO_BASELINE_PATH,
        CASE_PORTFOLIO_TC_PATH,
        CASE_EXECUTION_DETAIL_PATH,
        CASE_SUMMARY_PATH,
        RAW_FIGURE_PATH,
        COST_FIGURE_PATH,
    ]:
        print(f"  {path}")
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
