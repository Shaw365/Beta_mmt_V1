"""
重新生成Barra数据并运行择时策略

说明：
- 该脚本会重新生成所有Barra数据（不使用缓存）
- 适用于数据更新、模型修改后的重新计算
- 运行时间约12-18分钟
"""

import pandas as pd
import sys
import os

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


def regenerate_barra_data():
    """
    重新生成Barra数据（不使用缓存）
    
    返回:
        factor_returns_df, cumulative_returns_df, factor_exposure_df, price_df
    """
    
    print("\n重新生成Barra数据...")
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
    """
    主函数
    """
    
    print("=" * 100)
    print("重新生成Barra数据并运行择时策略")
    print("=" * 100)
    print("\n说明:")
    print("  - 该脚本会重新生成所有Barra数据（不使用缓存）")
    print("  - 适用于数据更新、模型修改后的重新计算")
    print("  - 运行时间约12-18分钟")
    print("=" * 100)
    
    # 步骤1: 重新生成Barra数据
    print("\n步骤1: 重新生成Barra数据...")
    factor_returns_df, cumulative_returns_df, factor_exposure_df, price_df = regenerate_barra_data()
    
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
    # 运行主函数
    portfolio_returns, optimal_vectors, stats = main()
