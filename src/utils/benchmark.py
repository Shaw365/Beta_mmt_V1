"""
基准指数工具模块

功能：
1. 从数据库加载中证500、中证1000指数行情
2. 计算与策略对齐的周度基准收益率
3. 计算超额收益
"""

import pandas as pd
import numpy as np
import sqlalchemy
import os

# 数据库连接
__index_engine__ = sqlalchemy.create_engine(
    'mysql+pymysql://readonly:readonly@192.168.7.203:3306/index_market')

# 指数代码
INDEX_CODES = {
    'csi500': '000905.SH',   # 中证500
    'csi1000': '000852.SH',  # 中证1000
}


def load_index_data(start_date='2020-01-01', end_date='2025-12-31', cache_path=None):
    """
    加载指数行情数据

    参数:
        start_date: 开始日期
        end_date: 结束日期
        cache_path: 缓存路径，如提供则优先使用缓存

    返回:
        DataFrame: columns=[date, code, pct_chg, close]
    """
    if cache_path and os.path.exists(cache_path):
        print(f"使用缓存指数数据: {cache_path}")
        df = pd.read_csv(cache_path)
        df['date'] = pd.to_datetime(df['date'])
        return df

    print("从数据库加载指数行情数据...")

    codes = list(INDEX_CODES.values())
    code_list = "','".join(codes)

    query = f"""
    SELECT date, code, pct_chg, close
    FROM index_eod
    WHERE code IN ('{code_list}')
      AND date >= '{start_date}'
      AND date <= '{end_date}'
    ORDER BY date, code
    """

    df = pd.read_sql(query, __index_engine__)
    df['date'] = pd.to_datetime(df['date'])

    print(f"  指数数据: {len(df)} 行, {df['code'].unique()} 代码")
    print(f"  日期范围: {df['date'].min().date()} ~ {df['date'].max().date()}")

    # 缓存
    if cache_path:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        df.to_csv(cache_path, index=False)
        print(f"  已缓存到: {cache_path}")

    return df


def compute_weekly_benchmark_returns(index_data, weekly_dates):
    """
    计算与策略换仓日期对齐的周度基准收益率

    参数:
        index_data: load_index_data() 返回的 DataFrame
        weekly_dates: 策略换仓日期列表

    返回:
        DataFrame: index=date, columns=[csi500_return, csi1000_return]
    """
    print("计算周度基准收益率...")

    index_data = index_data.copy()
    index_data['date'] = pd.to_datetime(index_data['date'])

    results = {}

    for name, code in INDEX_CODES.items():
        idx_df = index_data[index_data['code'] == code].set_index('date')['close'].sort_index()
        idx_nav = (1 + idx_df.pct_change().fillna(0)).cumprod()

        weekly_rets = {}
        for i in range(len(weekly_dates) - 1):
            d1 = weekly_dates[i]
            d2 = weekly_dates[i + 1]

            try:
                i1 = idx_nav.index.get_indexer([d1], method='nearest')[0]
                i2 = idx_nav.index.get_indexer([d2], method='nearest')[0]
                if i1 >= 0 and i2 >= 0 and i2 > i1:
                    ret = idx_nav.iloc[i2] / idx_nav.iloc[i1] - 1
                    weekly_rets[d1] = ret
            except Exception:
                continue

        results[f'{name}_return'] = pd.Series(weekly_rets)

    benchmark_df = pd.DataFrame(results)
    benchmark_df.index.name = 'date'

    print(f"  基准周度收益率: {len(benchmark_df)} 行")

    return benchmark_df


def compute_benchmark_cumulative(index_data, date_range):
    """
    计算指数在指定日期范围内的累计净值（日频）

    参数:
        index_data: load_index_data() 返回的 DataFrame
        date_range: 日期列表 (DatetimeIndex)

    返回:
        DataFrame: index=date, columns=[csi500_nav, csi1000_nav]
    """
    results = {}

    for name, code in INDEX_CODES.items():
        idx_df = index_data[index_data['code'] == code].copy()
        idx_df = idx_df.set_index('date')['close'].sort_index()
        # 转为净值
        idx_nav = idx_df / idx_df.iloc[0]
        # 只保留 date_range 中的日期
        idx_nav = idx_nav.reindex(date_range, method='nearest')
        results[name + '_nav'] = idx_nav

    return pd.DataFrame(results)


def compute_relative_returns(portfolio_returns_df, benchmark_df):
    """
    计算策略相对于基准的超额累计收益

    参数:
        portfolio_returns_df: 策略收益 DataFrame (需含 date, return 列)
        benchmark_df: compute_weekly_benchmark_returns() 返回的 DataFrame

    返回:
        DataFrame: index=date, columns=[excess_csi500, excess_csi1000, strategy_nav, csi500_nav, csi1000_nav]
    """
    df = portfolio_returns_df.copy()
    df['date'] = pd.to_datetime(df['date'])

    merged = df[['date', 'return']].copy()
    merged = merged.merge(
        benchmark_df, left_on='date', right_index=True, how='left'
    )

    # 策略累计净值
    merged['strategy_nav'] = (1 + merged['return']).cumprod()

    result = pd.DataFrame()
    result['date'] = merged['date'].values
    result['strategy_nav'] = merged['strategy_nav'].values

    for name in ['csi500', 'csi1000']:
        col = f'{name}_return'
        if col in merged.columns:
            bench_nav = (1 + merged[col].fillna(0)).cumprod()
            result[f'{name}_nav'] = bench_nav.values
            result[f'excess_{name}'] = result['strategy_nav'] / bench_nav.values - 1

    result = result.set_index('date')
    return result
