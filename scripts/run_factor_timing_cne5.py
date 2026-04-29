"""
运行CNE5风格因子择时策略
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
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.strategies.factor_timing_strategy_v3 import FactorTimingStrategy

# 缓存文件路径
CACHE_DIR = 'e:/code/python/ai_project/beta_mmt/output/cne5/data'
FACTOR_EXPOSURE_CACHE = f'{CACHE_DIR}/factor_exposure_cne5.csv'
PRICE_DATA_CACHE = f'{CACHE_DIR}/price_data_cne5.csv'
FACTOR_RETURNS_CACHE = f'{CACHE_DIR}/factor_returns_cne5.csv'
CUMULATIVE_RETURNS_CACHE = f'{CACHE_DIR}/cumulative_returns_cne5.csv'


def load_or_generate_barra_data(use_cache=True):
    """
    加载或生成Barra CNE5数据
    
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
        print("\n缓存不存在，重新生成Barra CNE5数据...")
        from src.models.barra_cne5 import BarraCNE5
        
        print("运行Barra CNE5模型...")
        barra = BarraCNE5(start_date='2020-01-01', end_date='2025-12-31')
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
    print("CNE5风格因子择时策略")
    print("=" * 100)
    print("\n优化内容:")
    print("  1. 预先计算周度收益率（性能优化）")
    print("  2. 使用前一天的因子暴露数据（避免偷看未来数据）")
    print("  3. 带缓存功能")
    print("=" * 100)
    
    # 步骤1: 加载或生成Barra数据（使用缓存）
    print("\n步骤1: 加载Barra CNE5数据...")
    factor_returns_df, cumulative_returns_df, factor_exposure_df, price_df = load_or_generate_barra_data(use_cache=True)
    
    # 步骤2: 创建择时策略实例
    print("\n步骤2: 创建择时策略实例...")
    strategy = FactorTimingStrategy(
        long_prd=20,
        short_prd=5,
        extreme_value=3,
        top_n=50
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
    print("=" * 100)
    
    # 步骤5: 绘制策略表现
    print("\n步骤5: 绘制策略表现...")
    output_dir = 'e:/code/python/ai_project/beta_mmt/output/cne5'
    os.makedirs(output_dir, exist_ok=True)
    
    strategy.plot_strategy_performance(portfolio_returns_df, output_dir,
                                       stats=stats, annual_returns=annual_returns,
                                       monthly_win_rate=monthly_win_rate)
    
    # 步骤6: 生成交易记录
    print("\n步骤6: 生成交易记录...")
    strategy.generate_trade_report(f'{output_dir}/data')
    
    # 步骤7: 保存结果
    print("\n步骤7: 保存结果...")
    suffix = strategy.get_param_suffix()
    portfolio_returns_df.to_csv(f'{output_dir}/data/portfolio_returns_{suffix}.csv', index=False)
    optimal_vector_df.to_csv(f'{output_dir}/data/optimal_vectors_{suffix}.csv')
    
    print("\n" + "=" * 100)
    print("CNE5风格因子择时策略运行完成！")
    print("=" * 100)
    print(f"\n结果文件:")
    print(f"  - 策略收益: {output_dir}/data/portfolio_returns_{suffix}.csv")
    print(f"  - 最优向量: {output_dir}/data/optimal_vectors_{suffix}.csv")
    print(f"  - 策略图表: {output_dir}/factor_timing_{suffix}.png")
    print(f"  - 交易记录: {output_dir}/data/交易记录_{suffix}.xlsx")
    
    return portfolio_returns_df, optimal_vector_df, stats


if __name__ == '__main__':
    portfolio_returns, optimal_vectors, stats = main()
