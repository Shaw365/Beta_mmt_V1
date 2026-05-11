"""
运行风格因子择时策略（优化版）
优化：
1. 预先计算周度收益率（性能优化）
2. 使用前一天的因子暴露数据（避免偷看未来数据）
3. 带缓存功能
"""

import pandas as pd
import numpy as np
import sys
import os
from datetime import datetime

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from src.strategies.factor_timing_strategy_v3 import FactorTimingStrategy
from src.utils.benchmark import load_index_data, compute_weekly_benchmark_returns, compute_relative_returns

# 缓存文件路径
OUTPUT_DIR = os.path.join(project_root, 'output', 'cne6')
CACHE_DIR = os.path.join(OUTPUT_DIR, 'data')
FACTOR_EXPOSURE_CACHE = os.path.join(CACHE_DIR, 'factor_exposure_cne6.csv')
PRICE_DATA_CACHE = os.path.join(CACHE_DIR, 'price_data_cne6.csv')
FACTOR_RETURNS_CACHE = os.path.join(CACHE_DIR, 'factor_returns_cne6.csv')
CUMULATIVE_RETURNS_CACHE = os.path.join(CACHE_DIR, 'cumulative_returns_cne6.csv')


def load_or_generate_barra_data(use_cache=True):
    """
    加载或生成Barra数据
    
    参数:
        use_cache: 是否使用缓存
        
    返回:
        factor_returns_df, cumulative_returns_df, factor_exposure_df, price_df
    """
    
    # 检查缓存文件是否存在
    cache_exists = (
        os.path.exists(FACTOR_EXPOSURE_CACHE) and
        os.path.exists(PRICE_DATA_CACHE) and
        os.path.exists(FACTOR_RETURNS_CACHE) and
        os.path.exists(CUMULATIVE_RETURNS_CACHE)
    )
    
    if use_cache and cache_exists:
        print("\n使用缓存数据...")
        print("加载因子暴露数据...")
        factor_exposure_df = pd.read_csv(FACTOR_EXPOSURE_CACHE)
        factor_exposure_df['date'] = pd.to_datetime(factor_exposure_df['date'])
        
        print("加载价格数据...")
        price_df = pd.read_csv(PRICE_DATA_CACHE)
        price_df['date'] = pd.to_datetime(price_df['date'])
        
        print("加载因子收益率数据...")
        factor_returns_df = pd.read_csv(FACTOR_RETURNS_CACHE)
        factor_returns_df['date'] = pd.to_datetime(factor_returns_df['date'])
        
        print("加载累计收益率数据...")
        cumulative_returns_df = pd.read_csv(CUMULATIVE_RETURNS_CACHE)
        cumulative_returns_df['date'] = pd.to_datetime(cumulative_returns_df['date'])
        
        print(f"因子暴露数据: {len(factor_exposure_df)} 行")
        print(f"价格数据: {len(price_df)} 行")
        print(f"因子收益率数据: {len(factor_returns_df)} 行")
        print(f"累计收益率数据: {len(cumulative_returns_df)} 行")
        
    else:
        print("\n缓存不存在，重新生成Barra数据...")
        from src.models.barra_cne6 import BarraCNE6
        
        print("运行Barra CNE6模型...")
        barra = BarraCNE6(start_date='2020-01-01', end_date='2025-12-31')
        factor_returns_df, cumulative_returns_df = barra.run()
        
        # 重新加载数据
        print("\n加载生成的数据...")
        factor_exposure_df = pd.read_csv(FACTOR_EXPOSURE_CACHE)
        factor_exposure_df['date'] = pd.to_datetime(factor_exposure_df['date'])
        
        price_df = pd.read_csv(PRICE_DATA_CACHE)
        price_df['date'] = pd.to_datetime(price_df['date'])
        
        factor_returns_df = pd.read_csv(FACTOR_RETURNS_CACHE)
        factor_returns_df['date'] = pd.to_datetime(factor_returns_df['date'])
        
        cumulative_returns_df = pd.read_csv(CUMULATIVE_RETURNS_CACHE)
        cumulative_returns_df['date'] = pd.to_datetime(cumulative_returns_df['date'])
    
    return factor_returns_df, cumulative_returns_df, factor_exposure_df, price_df


def main():
    """主函数"""
    
    print("=" * 100)
    print("风格因子择时策略（优化版）")
    print("=" * 100)
    print("\n优化内容:")
    print("  1. 预先计算周度收益率（性能优化）")
    print("  2. 使用前一天的因子暴露数据（避免偷看未来数据）")
    print("  3. 带缓存功能")
    print("=" * 100)
    
    # 步骤1: 加载或生成Barra数据（使用缓存）
    print("\n步骤1: 加载Barra数据...")
    factor_returns_df, cumulative_returns_df, factor_exposure_df, price_df = load_or_generate_barra_data(use_cache=True)
    
    # 步骤2: 创建择时策略实例
    print("\n步骤2: 创建择时策略实例...")
    strategy = FactorTimingStrategy(
        long_prd=20,
        short_prd=5,
        channel_bins=2,
        extreme_value=1,
        top_n=100
    )
    
    # 步骤3: 执行周度换仓策略
    print("\n步骤3: 执行周度换仓策略...")
    portfolio_returns_df, optimal_vector_df = strategy.run_weekly_rebalance(
        factor_exposure_df, 
        cumulative_returns_df.set_index('date'),
        price_df
    )
    
    # 步骤4: 计算统计指标
    print("\n步骤4: 计算策略统计指标...")
    stats, annual_returns, monthly_win_rate = strategy.calculate_statistics(portfolio_returns_df)
    
    print("\n" + "=" * 100)
    print("策略统计指标:")
    print("=" * 100)
    for key, value in stats.items():
        print(f"{key:15s}: {value}")
    
    print("\n" + "-" * 100)
    print("年度收益率:")
    print("-" * 100)
    if len(annual_returns) > 0:
        print(annual_returns.to_string(index=False))
    
    print("\n" + "-" * 100)
    print("月度胜率 (最近12个月):")
    print("-" * 100)
    if len(monthly_win_rate) > 0:
        print(monthly_win_rate.tail(12).to_string(index=False))
    print("=" * 100)
    
    # 步骤5: 加载基准数据
    print("\n步骤5: 加载基准指数数据...")
    index_cache = f'{CACHE_DIR}/index_eod.csv'
    index_data = load_index_data(cache_path=index_cache)
    
    # 获取策略换仓日期
    weekly_dates = sorted(portfolio_returns_df['date'].unique())
    weekly_dates = [pd.Timestamp(d) for d in weekly_dates]
    
    # 计算周度基准收益率和超额收益
    benchmark_weekly = compute_weekly_benchmark_returns(index_data, weekly_dates)
    benchmark_relative = compute_relative_returns(portfolio_returns_df, benchmark_weekly)
    
    # 打印超额收益
    print("\n" + "-" * 100)
    print("超额收益:")
    print("-" * 100)
    for col in benchmark_relative.columns:
        if col.startswith('excess_'):
            name = '中证500' if 'csi500' in col else '中证1000'
            final = benchmark_relative[col].iloc[-1] * 100
            print(f"  累计超额({name}): {final:.2f}%")
    
    # 步骤6: 绘制策略表现
    print("\n步骤6: 绘制策略表现...")
    output_dir = OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)
    
    strategy.plot_strategy_performance(portfolio_returns_df, output_dir,
                                       stats=stats, annual_returns=annual_returns,
                                       monthly_win_rate=monthly_win_rate,
                                       benchmark_data=benchmark_relative)
    
    # 步骤7: 生成交易记录
    print("\n步骤7: 生成交易记录...")
    strategy.generate_trade_report(f'{output_dir}/data')
    
    # 步骤8: 保存结果
    print("\n步骤8: 保存结果...")
    suffix = strategy.get_param_suffix()
    portfolio_returns_df.to_csv(f'{output_dir}/data/portfolio_returns_{suffix}.csv', index=False)
    optimal_vector_df.to_csv(f'{output_dir}/data/optimal_vectors_{suffix}.csv')
    benchmark_relative.to_csv(f'{output_dir}/data/benchmark_relative_{suffix}.csv', encoding='utf-8-sig')
    
    print("\n" + "=" * 100)
    print("风格因子择时策略运行完成！")
    print("=" * 100)
    print(f"\n结果文件:")
    print(f"  - 策略收益: {output_dir}/data/portfolio_returns_{suffix}.csv")
    print(f"  - 最优向量: {output_dir}/data/optimal_vectors_{suffix}.csv")
    print(f"  - 策略图表: {output_dir}/images/backtest/factor_timing_{suffix}.png")
    print(f"  - 交易记录: {output_dir}/data/交易记录_{suffix}.xlsx")
    print(f"  - 年度收益率: {output_dir}/data/annual_returns_{suffix}.csv")
    print(f"  - 月度胜率: {output_dir}/data/monthly_win_rate_{suffix}.csv")
    print(f"  - 基准对比: {output_dir}/data/benchmark_relative_{suffix}.csv")
    
    return portfolio_returns_df, optimal_vector_df, stats


if __name__ == '__main__':
    portfolio_returns, optimal_vectors, stats = main()
