"""
从头开始运行完整流程（优化版）

优化内容：
1. 支持缓存功能（默认使用缓存）
2. 可选择是否强制从头开始
3. 代码结构优化，参考run_factor_timing_v3.py
"""

import pandas as pd
import numpy as np
import os
import shutil
import sys
from datetime import datetime

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from src.strategies.factor_timing_strategy_v3 import FactorTimingStrategy

# 缓存文件路径
CACHE_DIR = os.path.join(project_root, 'output', 'cne6', 'data')
FACTOR_EXPOSURE_CACHE = f'{CACHE_DIR}/factor_exposure_cne6.csv'
PRICE_DATA_CACHE = f'{CACHE_DIR}/price_data_cne6.csv'
FACTOR_RETURNS_CACHE = f'{CACHE_DIR}/factor_returns_cne6.csv'
CUMULATIVE_RETURNS_CACHE = f'{CACHE_DIR}/cumulative_returns_cne6.csv'


def clear_all_cache():
    """清除所有缓存数据"""
    print("\n清除所有缓存数据...")
    
    if os.path.exists(CACHE_DIR):
        print(f"缓存目录: {CACHE_DIR}")
        
        # 列出要删除的文件
        files_to_delete = [
            'factor_exposure_cne6.csv',
            'price_data_cne6.csv',
            'factor_returns_cne6.csv',
            'cumulative_returns_cne6.csv',
            'portfolio_returns_v3.csv',
            'portfolio_returns_final.csv',
            'optimal_vectors_v3.csv',
            'optimal_vectors_final.csv',
            '交易记录.xlsx',
            '交易记录_完整.xlsx',
            '交易记录_测试.xlsx'
        ]
        
        deleted_count = 0
        for file in files_to_delete:
            file_path = os.path.join(CACHE_DIR, file)
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"  [删除] {file}")
                deleted_count += 1
        
        print(f"\n已删除 {deleted_count} 个缓存文件")
    else:
        print(f"缓存目录不存在: {CACHE_DIR}")


def load_or_generate_barra_data(use_cache=True, force_from_scratch=False):
    """
    加载或生成Barra数据
    
    参数:
        use_cache: 是否使用缓存
        force_from_scratch: 是否强制从头开始（清除所有缓存）
        
    返回:
        factor_returns_df, cumulative_returns_df, factor_exposure_df, price_df
    """
    
    # 如果强制从头开始，先清除所有缓存
    if force_from_scratch:
        clear_all_cache()
    
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
        print("\n缓存不存在或已清除，重新生成Barra数据...")
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


def main(force_from_scratch=False):
    """
    主函数
    
    参数:
        force_from_scratch: 是否强制从头开始（默认False，使用缓存）
    """
    
    print("=" * 100)
    print("从头开始运行完整流程（优化版）")
    print("=" * 100)
    print("\n优化内容:")
    print("  1. 支持缓存功能（默认使用缓存，< 1分钟）")
    print("  2. 可选择强制从头开始（清除所有缓存，12-18分钟）")
    print("  3. 代码结构优化，参考run_factor_timing_v3.py")
    print("=" * 100)
    
    if force_from_scratch:
        print("\n[模式] 强制从头开始（清除所有缓存）")
    else:
        print("\n[模式] 使用缓存数据（如果存在）")
    
    # 步骤1: 加载或生成Barra数据
    print("\n步骤1: 加载Barra数据...")
    factor_returns_df, cumulative_returns_df, factor_exposure_df, price_df = load_or_generate_barra_data(
        use_cache=True, 
        force_from_scratch=force_from_scratch
    )
    
    # 步骤2: 检查股票池大小
    print("\n步骤2: 检查股票池大小...")
    print(f"因子暴露数据股票数: {factor_exposure_df['code'].nunique()}")
    print(f"价格数据股票数: {price_df['code'].nunique()}")
    
    # 步骤3: 创建择时策略实例
    print("\n步骤3: 创建择时策略实例...")
    strategy = FactorTimingStrategy(
        long_prd=20,
        short_prd=5,
        extreme_value=3,
        top_n=100
    )
    
    # 步骤4: 执行周度换仓策略
    print("\n步骤4: 执行周度换仓策略...")
    portfolio_returns_df, optimal_vector_df = strategy.run_weekly_rebalance(
        factor_exposure_df, 
        cumulative_returns_df.set_index('date'),
        price_df
    )
    
    # 步骤5: 计算统计指标
    print("\n步骤5: 计算策略统计指标...")
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
    
    # 步骤6: 绘制策略表现
    print("\n步骤6: 绘制策略表现...")
    output_dir = os.path.join(project_root, 'output', 'cne6')
    os.makedirs(output_dir, exist_ok=True)
    
    strategy.plot_strategy_performance(portfolio_returns_df, output_dir,
                                       stats=stats, annual_returns=annual_returns,
                                       monthly_win_rate=monthly_win_rate)
    
    # 步骤7: 生成交易记录
    print("\n步骤7: 生成交易记录...")
    strategy.generate_trade_report(f'{output_dir}/data')
    
    # 步骤8: 保存结果
    print("\n步骤8: 保存结果...")
    suffix = strategy.get_param_suffix()
    portfolio_returns_df.to_csv(f'{output_dir}/data/portfolio_returns_{suffix}.csv', index=False)
    optimal_vector_df.to_csv(f'{output_dir}/data/optimal_vectors_{suffix}.csv')
    
    print("\n" + "=" * 100)
    print("完成！")
    print("=" * 100)
    print(f"\n结果文件:")
    print(f"  - 策略收益: {output_dir}/data/portfolio_returns_{suffix}.csv")
    print(f"  - 最优向量: {output_dir}/data/optimal_vectors_{suffix}.csv")
    print(f"  - 策略图表: {output_dir}/images/backtest/factor_timing_{suffix}.png")
    print(f"  - 交易记录: {output_dir}/data/交易记录_{suffix}.xlsx")
    
    return portfolio_returns_df, optimal_vector_df, stats


if __name__ == '__main__':
    import argparse
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='从头开始运行完整流程')
    parser.add_argument('--force', action='store_true', help='强制从头开始（清除所有缓存）')
    args = parser.parse_args()
    
    # 运行主函数
    portfolio_returns, optimal_vectors, stats = main(force_from_scratch=args.force)
