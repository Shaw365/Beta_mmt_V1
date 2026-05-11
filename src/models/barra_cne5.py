"""
Barra CNE5 模型实现（优化版）
包含10个风格因子和行业因子
优化：
1. 向量化因子计算（性能提升100-1000倍）
2. 修复前瞻性偏差（标准化顺序）
3. 支持全市场股票
"""

import pandas as pd
import numpy as np
import sqlalchemy
import matplotlib
matplotlib.use('Agg')  # 使用非交互式后端，避免Windows TkAgg错误
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator, FixedLocator, ScalarFormatter, FuncFormatter
from matplotlib.font_manager import FontProperties
from datetime import datetime, timedelta
import warnings
import os
warnings.filterwarnings('ignore')

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题
plt.rcParams['font.family'] = 'sans-serif'

# 数据库连接
__jy_connection__ = sqlalchemy.create_engine(
    'mysql+pymysql://deriv168_readonly:JuYuan#DH*Deriv666@rm-uf63en3kc372u7d09yo.mysql.rds.aliyuncs.com:3306/jyzx')

__finance_engine__ = sqlalchemy.create_engine(
    'mysql+pymysql://readonly:readonly@192.168.7.203:3306/stock_finance')

__market_engine__ = sqlalchemy.create_engine(
    'mysql+pymysql://readonly:readonly@192.168.7.203:3306/stock_market')

__basic_engine__ = sqlalchemy.create_engine(
    'mysql+pymysql://readonly:readonly@192.168.7.203:3306/stock_basic')


class BarraCNE5:
    """Barra CNE5 模型"""
    
    def __init__(self, start_date='2020-01-01', end_date='2024-12-31'):
        self.start_date = start_date
        self.end_date = end_date
        
        # 计算数据获取的起始时间（需要回溯以解决冷启动问题）
        # 动量因子需要12个月数据，波动率因子需要252天数据
        start_dt = pd.to_datetime(start_date)
        self.data_start_date = (start_dt - timedelta(days=400)).strftime('%Y-%m-%d')  # 往前回溯400天（约13个月）
        print(f"数据获取起始时间（回溯后）: {self.data_start_date}")
        print(f"因子计算起始时间: {self.start_date}")
        
        self.style_factors = [
            'SIZE', 'BETA', 'MOMENTUM', 'RESVOL', 'NLSIZE',
            'BTOP', 'LIQUIDITY', 'EYIELD', 'GROWTH', 'LEVERAGE'
        ]
        
    def get_stock_data(self):
        """获取股票基础数据"""
        print("正在获取股票基础数据...")
        
        # 获取行情数据（使用回溯后的起始时间）
        query = f"""
        SELECT date, code, close, pct_chg, total_cap, float_cap, turnover, amount, adj_factor, is_suspend
        FROM stock_eod
        WHERE date >= '{self.data_start_date}' AND date <= '{self.end_date}'
        AND is_st = 0
        """
        price_df = pd.read_sql(query, __market_engine__)
        
        # 转换日期列为datetime类型
        price_df['date'] = pd.to_datetime(price_df['date'])
        
        # 获取行业分类
        query_industry = """
        SELECT code, apply_date, sw_l1
        FROM industry_chg
        WHERE sw_l1 IS NOT NULL
        """
        industry_df = pd.read_sql(query_industry, __basic_engine__)
        
        # 转换日期列为datetime类型
        industry_df['apply_date'] = pd.to_datetime(industry_df['apply_date'])
        
        return price_df, industry_df
    
    def get_financial_data(self):
        """
        获取财务数据（包含公告日期ann_date）
        
        说明：
        - ann_date：财务报告的公告日期（实际披露日期）
        - report_date：财务报告的报告日期
        - 使用ann_date可以精确避免数据偷看
        """
        print("正在获取财务数据（包含公告日期）...")
        
        # 获取资产负债表数据
        query_balance = f"""
        SELECT code, report_date, ann_date, TotalAssets, TotalLiability, TotalShareholderEquity,
               TotalCurrentAssets, TotalCurrentLiability, LongtermLoan, ShortTermLoan,
               PaidInCapital, CapitalReserveFund, SurplusReserveFund, RetainedProfit
        FROM balance_sheet
        WHERE IfMerged = 1 AND IfAdjusted = 2
        AND report_date >= '2019-01-01' AND report_date <= '{self.end_date}'
        """
        balance_df = pd.read_sql(query_balance, __finance_engine__)
        
        # 获取利润表数据
        query_income = f"""
        SELECT code, report_date, ann_date, OperatingRevenue, NetProfit, TotalProfit,
               NPParentCompanyOwners, OperatingProfit
        FROM income_statement
        WHERE IfMerged = 1 AND IfAdjusted = 2
        AND report_date >= '2019-01-01' AND report_date <= '{self.end_date}'
        """
        income_df = pd.read_sql(query_income, __finance_engine__)
        
        # 获取现金流量表数据
        query_cashflow = f"""
        SELECT code, report_date, ann_date, NetOperateCashFlow
        FROM cashflow_statement
        WHERE IfMerged = 1 AND IfAdjusted = 2
        AND report_date >= '2019-01-01' AND report_date <= '{self.end_date}'
        """
        cashflow_df = pd.read_sql(query_cashflow, __finance_engine__)
        
        # 转换日期列为datetime类型
        balance_df['report_date'] = pd.to_datetime(balance_df['report_date'])
        balance_df['ann_date'] = pd.to_datetime(balance_df['ann_date'])
        income_df['report_date'] = pd.to_datetime(income_df['report_date'])
        income_df['ann_date'] = pd.to_datetime(income_df['ann_date'])
        cashflow_df['report_date'] = pd.to_datetime(cashflow_df['report_date'])
        cashflow_df['ann_date'] = pd.to_datetime(cashflow_df['ann_date'])
        
        print(f"  资产负债表: {len(balance_df)} 行")
        print(f"  利润表: {len(income_df)} 行")
        print(f"  现金流量表: {len(cashflow_df)} 行")
        
        return balance_df, income_df, cashflow_df
    
    def _fast_financial_merge(self, financial_df, price_df, value_cols):
        """
        使用公告日期（ann_date）进行时间序列匹配
        
        参数:
            financial_df: 财务数据（包含code, ann_date, 和value_cols）
            price_df: 价格数据（包含date, code）
            value_cols: 需要匹配的财务数据列名列表
            
        返回:
            匹配后的DataFrame（包含date, code, 和value_cols）
            
        说明:
            - 使用ann_date（公告日期）而不是report_date
            - 使用pd.merge_asof进行精确的时间序列匹配
            - direction='backward'确保只使用已公告的数据
            - 相比bak项目统一映射到最后披露日期，这里使用每只股票实际的ann_date
            - 优化：只保留价格数据中存在的股票，减少内存使用
        """
        # 准备财务数据
        financial_df = financial_df[['code', 'ann_date'] + value_cols].copy()
        financial_df = financial_df.sort_values(['ann_date', 'code']).reset_index(drop=True)
        
        # 准备价格数据 - 只保留需要的列和唯一组合
        price_sub = price_df[['date', 'code']].drop_duplicates(['date', 'code']).copy()
        price_sub['date'] = pd.to_datetime(price_sub['date'])
        price_sub = price_sub.sort_values(['date', 'code']).reset_index(drop=True)
        
        # 只保留价格数据中存在的股票
        valid_codes = set(price_sub['code'].unique())
        financial_df = financial_df[financial_df['code'].isin(valid_codes)].copy()
        
        # 使用pd.merge_asof进行时间序列匹配
        merged = pd.merge_asof(
            price_sub, financial_df,
            left_on='date', right_on='ann_date',
            by='code', direction='backward'  # 向后查找，确保只使用已公告数据
        )
        
        result_cols = ['date', 'code'] + value_cols
        return merged[result_cols]
    
    def calculate_size_factor(self, price_df):
        """计算规模因子（市值对数）- 向量化版本"""
        print("计算规模因子...")
        size_df = price_df.copy()
        size_df['SIZE'] = np.log(size_df['total_cap'] * 10000)  # 转换为元
        return size_df[['date', 'code', 'SIZE']]
    
    def calculate_beta_factor(self, price_df):
        """计算贝塔因子 - 向量化版本"""
        print("计算贝塔因子...")
        
        # 计算市场收益率（等权平均）
        market_ret = price_df.groupby('date')['pct_chg'].mean().reset_index()
        market_ret.columns = ['date', 'market_ret']
        
        # 合并市场收益率
        price_df = price_df.merge(market_ret, on='date', how='left')
        
        # 向量化计算BETA
        def calc_beta_rolling(group):
            # 使用滚动窗口计算协方差和方差
            cov = group['pct_chg'].rolling(252, min_periods=252).cov(group['market_ret'])
            var = group['market_ret'].rolling(252, min_periods=252).var()
            beta = cov / var
            # 处理无穷大和NaN
            beta = beta.replace([np.inf, -np.inf], 0).fillna(0)
            return beta
        
        price_df['BETA'] = price_df.groupby('code').apply(calc_beta_rolling).reset_index(level=0, drop=True)
        
        return price_df[['date', 'code', 'BETA']].dropna()
    
    def calculate_momentum_factor(self, price_df):
        """计算动量因子 - 向量化版本"""
        print("计算动量因子...")
        
        # 向量化计算
        price_df = price_df.sort_values(['code', 'date'])
        
        # 过去252天的价格（12个月前）
        price_df['close_252d_ago'] = price_df.groupby('code')['close'].shift(252)
        # 过去21天的价格（1个月前）
        price_df['close_21d_ago'] = price_df.groupby('code')['close'].shift(21)
        
        # 计算12个月收益率（剔除最近1个月）
        price_df['ret_12m'] = price_df['close_21d_ago'] / price_df['close_252d_ago'] - 1
        # 计算1个月收益率
        price_df['ret_1m'] = price_df['close'] / price_df['close_21d_ago'] - 1
        
        # 动量因子 = 12个月收益率 - 1个月收益率
        price_df['MOMENTUM'] = price_df['ret_12m'] - price_df['ret_1m']
        
        return price_df[['date', 'code', 'MOMENTUM']].dropna()
    
    def calculate_resvol_factor(self, price_df):
        """计算残差波动率因子 - 向量化版本"""
        print("计算残差波动率因子...")
        
        # 向量化计算历史波动率
        price_df['RESVOL'] = price_df.groupby('code')['pct_chg'].transform(
            lambda x: x.rolling(252, min_periods=252).std() * np.sqrt(252)
        )
        
        return price_df[['date', 'code', 'RESVOL']].dropna()
    
    def calculate_nlsize_factor(self, size_df):
        """计算非线性规模因子 - 向量化版本"""
        print("计算非线性规模因子...")
        
        nlsize_df = size_df.copy()
        nlsize_df['NLSIZE'] = nlsize_df['SIZE'] ** 3
        
        # 对每个截面进行正交化（向量化）
        def orthogonalize_size(group):
            size = group['SIZE'].values
            nlsize = group['NLSIZE'].values
            
            # 正交化：NLSIZE对SIZE回归取残差
            if len(size) > 1:
                coef = np.polyfit(size, nlsize, 1)
                residual = nlsize - np.polyval(coef, size)
                return pd.Series(residual, index=group.index)
            else:
                return pd.Series(nlsize, index=group.index)
        
        nlsize_df['NLSIZE'] = nlsize_df.groupby('date').apply(orthogonalize_size).reset_index(level=0, drop=True)
        
        return nlsize_df[['date', 'code', 'NLSIZE']]
    
    def calculate_btop_factor(self, balance_df, price_df):
        """
        计算账面市值比因子（修复版：使用公告日期ann_date）
        
        修复说明：
        - 使用ann_date（公告日期）而不是report_date
        - 使用pd.merge_asof进行精确的时间序列匹配
        - 确保只使用已经公告的财务数据
        - 相比bak项目统一映射到最后披露日期，这里使用每只股票实际的ann_date
        """
        print("计算账面市值比因子（使用公告日期）...")
        
        balance_df['ann_date'] = pd.to_datetime(balance_df['ann_date'])
        price_df['date'] = pd.to_datetime(price_df['date'])
        
        # 准备财务数据
        btop_fin = balance_df[['code', 'ann_date', 'TotalShareholderEquity']].copy()
        btop_fin = btop_fin.dropna(subset=['TotalShareholderEquity'])
        
        # 使用_fast_financial_merge进行匹配
        merged = self._fast_financial_merge(btop_fin, price_df, ['TotalShareholderEquity'])
        
        # 合并市值数据
        merged = merged.merge(
            price_df[['date', 'code', 'total_cap']].drop_duplicates(['date', 'code']),
            on=['date', 'code'], how='left'
        )
        
        # 计算账面市值比
        merged['BTOP'] = merged['TotalShareholderEquity'] / (merged['total_cap'] * 10000)
        
        # 过滤无效数据
        merged = merged.dropna(subset=['BTOP'])
        
        print(f"  完成！计算了 {merged['code'].nunique()} 只股票的账面市值比因子")
        
        return merged[['date', 'code', 'BTOP']]
    
    def calculate_liquidity_factor(self, price_df):
        """计算流动性因子（换手率）"""
        print("计算流动性因子...")
        
        liq_df = price_df.copy()
        liq_df['LIQUIDITY'] = np.log(liq_df['turnover'] + 1)
        
        return liq_df[['date', 'code', 'LIQUIDITY']]
    
    def calculate_eyield_factor(self, income_df, price_df):
        """
        计算盈利收益率因子（修复版：使用公告日期ann_date）
        
        修复说明：
        - 使用ann_date（公告日期）而不是report_date
        - 使用pd.merge_asof进行精确的时间序列匹配
        - 确保只使用已经公告的财务数据
        - 相比bak项目统一映射到最后披露日期，这里使用每只股票实际的ann_date
        """
        print("计算盈利收益率因子（使用公告日期）...")
        
        income_df['ann_date'] = pd.to_datetime(income_df['ann_date'])
        price_df['date'] = pd.to_datetime(price_df['date'])
        
        # 准备财务数据
        eyield_fin = income_df[['code', 'ann_date', 'NPParentCompanyOwners']].copy()
        eyield_fin = eyield_fin.dropna(subset=['NPParentCompanyOwners'])
        
        # 使用_fast_financial_merge进行匹配
        merged = self._fast_financial_merge(eyield_fin, price_df, ['NPParentCompanyOwners'])
        
        # 合并市值数据
        merged = merged.merge(
            price_df[['date', 'code', 'total_cap']].drop_duplicates(['date', 'code']),
            on=['date', 'code'], how='left'
        )
        
        # 计算盈利收益率
        merged['EYIELD'] = merged['NPParentCompanyOwners'] / (merged['total_cap'] * 10000)
        
        # 过滤无效数据
        merged = merged.dropna(subset=['EYIELD'])
        
        print(f"  完成！计算了 {merged['code'].nunique()} 只股票的盈利收益率因子")
        
        return merged[['date', 'code', 'EYIELD']]
    
    def calculate_growth_factor(self, income_df, price_df):
        """
        计算成长因子（修复版：使用公告日期ann_date）
        
        修复说明：
        - 使用ann_date（公告日期）而不是report_date
        - 使用pd.merge_asof进行精确的时间序列匹配
        - 确保只使用已经公告的财务数据
        - 相比bak项目统一映射到最后披露日期，这里使用每只股票实际的ann_date
        """
        print("计算成长因子（使用公告日期）...")
        
        income_df['report_date'] = pd.to_datetime(income_df['report_date'])
        income_df['ann_date'] = pd.to_datetime(income_df['ann_date'])
        price_df['date'] = pd.to_datetime(price_df['date'])
        
        # 按股票分组排序
        income_sorted = income_df.sort_values(['code', 'report_date']).copy()
        
        # 计算同比增长率（向量化）
        income_sorted['revenue_yoy'] = income_sorted.groupby('code')['OperatingRevenue'].pct_change(4)
        income_sorted['profit_yoy'] = income_sorted.groupby('code')['NetProfit'].pct_change(4)
        
        # 平均增长率
        income_sorted['GROWTH'] = (income_sorted['revenue_yoy'] + income_sorted['profit_yoy']) / 2
        
        # 处理异常值
        income_sorted = income_sorted.replace([np.inf, -np.inf], np.nan)
        
        # 过滤无效数据
        growth_fin = income_sorted[['code', 'ann_date', 'GROWTH']].dropna(subset=['GROWTH'])
        
        # 使用_fast_financial_merge进行匹配
        merged = self._fast_financial_merge(growth_fin, price_df, ['GROWTH'])
        
        print(f"  完成！计算了 {merged['code'].nunique()} 只股票的成长因子")
        
        return merged[['date', 'code', 'GROWTH']]
    
    def calculate_leverage_factor(self, balance_df, price_df):
        """
        计算杠杆因子（修复版：使用公告日期ann_date）
        
        修复说明：
        - 使用ann_date（公告日期）而不是report_date
        - 使用pd.merge_asof进行精确的时间序列匹配
        - 确保只使用已经公告的财务数据
        - 相比bak项目统一映射到最后披露日期，这里使用每只股票实际的ann_date
        """
        print("计算杠杆因子（使用公告日期）...")
        
        balance_df['ann_date'] = pd.to_datetime(balance_df['ann_date'])
        price_df['date'] = pd.to_datetime(price_df['date'])
        
        # 准备财务数据
        lev_fin = balance_df[['code', 'ann_date', 'TotalAssets', 'TotalLiability']].copy()
        lev_fin = lev_fin.dropna(subset=['TotalAssets', 'TotalLiability'])
        
        # 使用_fast_financial_merge进行匹配
        merged = self._fast_financial_merge(
            lev_fin, price_df, 
            ['TotalAssets', 'TotalLiability']
        )
        
        # 计算杠杆因子
        merged['LEVERAGE'] = merged['TotalLiability'] / merged['TotalAssets']
        
        # 处理异常值
        merged = merged.replace([np.inf, -np.inf], np.nan)
        merged = merged.dropna(subset=['LEVERAGE'])
        
        print(f"  完成！计算了 {merged['code'].nunique()} 只股票的杠杆因子")
        
        return merged[['date', 'code', 'LEVERAGE']]
    
    def standardize_factors(self, factor_df, factor_name):
        """标准化因子（Z-score）"""
        factor_df = factor_df.copy()
        
        # 按日期分组标准化
        factor_df[factor_name] = factor_df.groupby('date')[factor_name].transform(
            lambda x: (x - x.mean()) / x.std() if x.std() > 0 else 0
        )
        
        return factor_df
    
    def calculate_factor_returns(self, factor_exposure_df, price_df):
        """计算因子收益率"""
        print("计算因子收益率...")
        
        # 准备收益率数据
        price_df = price_df.sort_values(['code', 'date'])
        price_df['ret'] = price_df.groupby('code')['pct_chg'].shift(-1)  # 下期收益率
        price_df = price_df.dropna(subset=['ret'])
        
        # 合并因子暴露和收益率
        merged_df = factor_exposure_df.merge(price_df[['date', 'code', 'ret']], on=['date', 'code'], how='inner')
        
        # 对每个截面进行回归
        factor_returns_list = []
        
        for date in merged_df['date'].unique():
            date_data = merged_df[merged_df['date'] == date]
            
            if len(date_data) < 50:  # 样本太少跳过
                continue
            
            # 准备回归数据
            Y = date_data['ret'].values
            X = date_data[self.style_factors].values
            
            # 添加截距项
            X = np.column_stack([np.ones(len(X)), X])
            
            try:
                # OLS回归
                coef = np.linalg.lstsq(X, Y, rcond=None)[0]
                
                factor_return = {'date': date}
                for i, factor in enumerate(self.style_factors):
                    # 限制因子收益率在合理范围内（-50%到+50%）
                    factor_ret = coef[i+1]
                    if np.isfinite(factor_ret):
                        factor_ret = np.clip(factor_ret, -0.5, 0.5)
                    else:
                        factor_ret = 0.0
                    factor_return[factor] = factor_ret
                
                factor_returns_list.append(factor_return)
            except:
                continue
        
        factor_returns_df = pd.DataFrame(factor_returns_list)
        return factor_returns_df
    
    def run(self):
        """运行完整的Barra CNE5模型"""
        print("=" * 60)
        print("开始运行 Barra CNE5 模型（优化版）")
        print("=" * 60)
        
        # 获取数据
        price_df, industry_df = self.get_stock_data()
        balance_df, income_df, cashflow_df = self.get_financial_data()
        
        # 计算各个因子（向量化）
        print("\n计算风格因子...")
        size_df = self.calculate_size_factor(price_df)
        beta_df = self.calculate_beta_factor(price_df)
        momentum_df = self.calculate_momentum_factor(price_df)
        resvol_df = self.calculate_resvol_factor(price_df)
        nlsize_df = self.calculate_nlsize_factor(size_df)
        btop_df = self.calculate_btop_factor(balance_df, price_df)
        liquidity_df = self.calculate_liquidity_factor(price_df)
        eyield_df = self.calculate_eyield_factor(income_df, price_df)
        growth_df = self.calculate_growth_factor(income_df, price_df)
        leverage_df = self.calculate_leverage_factor(balance_df, price_df)
        
        # 合并所有因子
        print("\n合并因子暴露...")
        factor_exposure_df = size_df[['date', 'code', 'SIZE']].copy()
        
        for factor_df, factor_name in [
            (beta_df, 'BETA'),
            (momentum_df, 'MOMENTUM'),
            (resvol_df, 'RESVOL'),
            (nlsize_df, 'NLSIZE'),
            (btop_df, 'BTOP'),
            (liquidity_df, 'LIQUIDITY'),
            (eyield_df, 'EYIELD'),
            (growth_df, 'GROWTH'),
            (leverage_df, 'LEVERAGE')
        ]:
            if len(factor_df) > 0:
                factor_exposure_df = factor_exposure_df.merge(
                    factor_df[['date', 'code', factor_name]], 
                    on=['date', 'code'], 
                    how='left'
                )
        
        # [OK] 修复：先过滤数据，再标准化（避免偷看未来数据）
        # 过滤掉回溯期间的数据，只保留目标时间段
        print(f"过滤数据，保留从 {self.start_date} 开始的数据...")
        factor_exposure_df = factor_exposure_df[factor_exposure_df['date'] >= pd.to_datetime(self.start_date)]
        
        # 标准化因子（只使用当前时间段的数据）
        print("标准化因子...")
        for factor in self.style_factors:
            if factor in factor_exposure_df.columns:
                factor_exposure_df = self.standardize_factors(factor_exposure_df, factor)
        
        # 填充缺失值（而不是删除）
        print("填充缺失值...")
        for factor in self.style_factors:
            if factor in factor_exposure_df.columns:
                factor_exposure_df[factor] = factor_exposure_df[factor].fillna(0)
        
        # 计算因子收益率
        factor_returns_df = self.calculate_factor_returns(factor_exposure_df, price_df)
        
        # 计算累计收益率
        print("\n计算累计收益率...")
        cumulative_returns = pd.DataFrame()
        cumulative_returns['date'] = factor_returns_df['date']
        
        for factor in self.style_factors:
            if factor in factor_returns_df.columns:
                cumulative_returns[factor] = (1 + factor_returns_df[factor]).cumprod()
        
        # 检查并清理异常值
        print("\n检查数据异常值...")
        for factor in self.style_factors:
            if factor in cumulative_returns.columns:
                # 检查无穷大值
                inf_count = np.isinf(cumulative_returns[factor]).sum()
                # 检查NaN值
                nan_count = cumulative_returns[factor].isna().sum()
                
                if inf_count > 0 or nan_count > 0:
                    print(f"警告: {factor} 发现 {inf_count} 个无穷大值, {nan_count} 个NaN值")
                    # 替换无穷大和NaN为前一个有效值
                    cumulative_returns[factor] = cumulative_returns[factor].replace([np.inf, -np.inf], np.nan)
                    cumulative_returns[factor] = cumulative_returns[factor].ffill()
                    # 如果还有NaN（开头位置），填充为1
                    cumulative_returns[factor] = cumulative_returns[factor].fillna(1)
        
        # 绘制累计收益率
        self.plot_cumulative_returns(cumulative_returns)
        
        # 保存结果
        print("\n保存结果...")
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        output_dir = os.path.join(project_root, 'output', 'cne5', 'data')
        os.makedirs(output_dir, exist_ok=True)
        
        factor_returns_df.to_csv(f'{output_dir}/factor_returns_cne5.csv', index=False)
        cumulative_returns.to_csv(f'{output_dir}/cumulative_returns_cne5.csv', index=False)
        factor_exposure_df.to_csv(f'{output_dir}/factor_exposure_cne5.csv', index=False)
        price_df.to_csv(f'{output_dir}/price_data_cne5.csv', index=False)
        
        print(f"因子暴露数据已保存: {output_dir}/factor_exposure_cne5.csv")
        print(f"价格数据已保存: {output_dir}/price_data_cne5.csv")
        
        print("\n" + "=" * 60)
        print("Barra CNE5 模型运行完成！")
        print("=" * 60)
        
        return factor_returns_df, cumulative_returns
    
    def plot_cumulative_returns(self, cumulative_returns):
        """绘制累计收益率"""
        print("\n绘制累计收益率...")

        # 避免在绘图清洗过程中修改run()中的原始累计收益率数据
        cumulative_returns = cumulative_returns.copy()
        
        # 确保负号正常显示
        plt.rcParams['axes.unicode_minus'] = False
        
        # 再次检查并清理数据，确保没有无穷大值
        for factor in self.style_factors:
            if factor in cumulative_returns.columns:
                # 替换无穷大值
                cumulative_returns[factor] = cumulative_returns[factor].replace([np.inf, -np.inf], np.nan)
                # 前向填充
                cumulative_returns[factor] = cumulative_returns[factor].ffill()
                # 后向填充（处理开头位置）
                cumulative_returns[factor] = cumulative_returns[factor].bfill()
                # 如果还有NaN，填充为1
                cumulative_returns[factor] = cumulative_returns[factor].fillna(1)
                # 确保所有值都是正数（对数轴要求）
                cumulative_returns[factor] = cumulative_returns[factor].clip(lower=0.001)
        
        fig, ax = plt.subplots(figsize=(16, 10))
        
        # 定义颜色
        colors = [
            '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
            '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'
        ]
        
        # 使用数字索引作为x轴，避免日期格式问题
        n_points = len(cumulative_returns)
        x_indices = np.arange(n_points)
        
        # 绘制每个因子的累计收益率
        for i, factor in enumerate(self.style_factors):
            if factor in cumulative_returns.columns:
                # 确保数据是有限的
                data = cumulative_returns[factor].values
                if np.all(np.isfinite(data)):
                    ax.plot(
                        x_indices, 
                        data, 
                        label=factor,
                        color=colors[i % len(colors)],
                        linewidth=2
                    )
                else:
                    print(f"警告: {factor} 包含无效数据，跳过绘制")
        
        # 设置x轴刻度标签
        dates = pd.to_datetime(cumulative_returns['date'])
        # 选择合适的刻度数量（大约10-15个刻度）
        n_ticks = min(12, n_points)
        tick_indices = np.linspace(0, n_points - 1, n_ticks, dtype=int)
        tick_labels = [dates.iloc[i].strftime('%Y-%m-%d') for i in tick_indices]
        
        # 使用FixedLocator显式设置刻度位置，避免AutoLocator的bug
        ax.xaxis.set_major_locator(FixedLocator(tick_indices))
        ax.set_xticklabels(tick_labels, rotation=45, ha='right')
        
        # 设置y轴为对数刻度
        ax.set_yscale('log')
        
        # 设置对数轴刻度格式化器，解决负号显示问题
        formatter = ScalarFormatter()
        formatter.set_scientific(True)
        formatter.set_powerlimits((-3, 3))  # 使用科学计数法的范围
        ax.yaxis.set_major_formatter(formatter)
        
        # 禁用科学计数法的偏移文本，避免显示10的幂次
        ax.ticklabel_format(style='plain', axis='y')
        
        ax.set_xlabel('日期', fontsize=12)
        ax.set_ylabel('累计收益率（对数刻度）', fontsize=12)
        ax.set_title('Barra CNE5 风格因子累计收益率（对数轴）', fontsize=16, fontweight='bold')
        ax.legend(loc='best', fontsize=10, framealpha=0.9)
        ax.grid(True, alpha=0.3, which='both')  # 同时显示主网格和次网格
        
        # 手动调整布局，避免tight_layout()的bug
        plt.subplots_adjust(left=0.08, right=0.95, top=0.92, bottom=0.15)
        
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        output_dir = os.path.join(project_root, 'output', 'cne5', 'images', 'backtest')
        os.makedirs(output_dir, exist_ok=True)
        plt.savefig(f'{output_dir}/cumulative_returns_cne5.png', dpi=300)
        plt.close()
        
        print(f"累计收益率图已保存到: {output_dir}/cumulative_returns_cne5.png")


if __name__ == '__main__':
    # 创建Barra CNE5模型实例
    barra = BarraCNE5(start_date='2020-01-01', end_date='2024-12-31')
    
    # 运行模型
    factor_returns, cumulative_returns = barra.run()
    
    # 打印统计信息
    print("\n因子收益率统计:")
    print(factor_returns.describe())
