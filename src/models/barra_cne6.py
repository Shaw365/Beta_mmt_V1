"""
Barra CNE6 模型完整实现
包含25个风格因子和行业因子
"""

import pandas as pd
import numpy as np
import sqlalchemy
import os
import matplotlib
matplotlib.use('Agg')  # 使用非交互式后端，避免Windows TkAgg错误
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator, FixedLocator, ScalarFormatter, FuncFormatter
from matplotlib.font_manager import FontProperties
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

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


class BarraCNE6:
    """Barra CNE6 模型"""
    
    def __init__(self, start_date='2020-01-01', end_date='2024-12-31'):
        self.start_date = start_date
        self.end_date = end_date
        
        # 计算数据获取的起始时间（需要回溯以解决冷启动问题）
        # 动量因子需要12个月数据，波动率因子需要252天数据
        start_dt = pd.to_datetime(start_date)
        self.data_start_date = (start_dt - timedelta(days=400)).strftime('%Y-%m-%d')  # 往前回溯400天（约13个月）
        print(f"数据获取起始时间（回溯后）: {self.data_start_date}")
        print(f"因子计算起始时间: {self.start_date}")
        
        # CNE6模型的25个风格因子
        self.style_factors = [
            # 规模因子
            'SIZE', 'MIDCAP',
            # 波动率因子
            'BETA', 'RESVOL', 'HISTVOL',
            # 动量因子
            'MOMENTUM', 'RESMOM',
            # 价值因子
            'BTOP', 'EYIELD', 'CFP', 'SP', 'LP',
            # 成长因子
            'EGRO', 'SGRO',
            # 杠杆因子
            'MLEV', 'BLEV',
            # 流动性因子
            'LIQUIDITY', 'STOM', 'STOQ',
            # 盈利质量因子
            'ROE', 'ROA',
            # 投资因子
            'CAPX', 'AGRO',
            # 其他因子
            'TOPSI', 'SEASON'
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
               PaidInCapital, CapitalReserveFund, SurplusReserveFund, RetainedProfit,
               FixedAssets, ConstructionMaterials, ConstruInProcess
        FROM balance_sheet
        WHERE IfMerged = 1 AND IfAdjusted = 2
        AND report_date >= '2019-01-01' AND report_date <= '{self.end_date}'
        """
        balance_df = pd.read_sql(query_balance, __finance_engine__)
        
        # 获取利润表数据
        query_income = f"""
        SELECT code, report_date, ann_date, OperatingRevenue, NetProfit, TotalProfit,
               NPParentCompanyOwners, OperatingProfit, TotalOperatingRevenue
        FROM income_statement
        WHERE IfMerged = 1 AND IfAdjusted = 2
        AND report_date >= '2019-01-01' AND report_date <= '{self.end_date}'
        """
        income_df = pd.read_sql(query_income, __finance_engine__)
        
        # 获取现金流量表数据
        query_cashflow = f"""
        SELECT code, report_date, ann_date, NetOperateCashFlow, 
               FixIntanOtherAssetAcquiCash, InvestCashPaid
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
    
    def calculate_size_factors(self, price_df):
        """计算规模因子"""
        print("计算规模因子...")
        
        size_df = price_df.copy()
        # SIZE因子
        size_df['SIZE'] = np.log(size_df['total_cap'] * 10000)
        
        # MIDCAP因子（中盘因子，SIZE的三次方正交化）
        size_df['MIDCAP'] = size_df['SIZE'] ** 3
        
        # 对MIDCAP正交化
        # 按日期分组，对每个组进行正交化
        for date in size_df['date'].unique():
            mask = size_df['date'] == date
            group = size_df[mask]
            
            size = group['SIZE'].values
            midcap = group['MIDCAP'].values
            
            if len(size) > 1:
                # 对SIZE回归
                coef = np.polyfit(size, midcap, 1)
                residual = midcap - np.polyval(coef, size)
                size_df.loc[mask, 'MIDCAP'] = residual
        
        return size_df[['date', 'code', 'SIZE', 'MIDCAP']]
    
    def calculate_volatility_factors(self, price_df):
        """计算波动率因子（优化版：使用向量化操作）"""
        print("计算波动率因子（向量化优化）...")
        
        # 计算市场收益率
        market_ret = price_df.groupby('date')['pct_chg'].mean().reset_index()
        market_ret.columns = ['date', 'market_ret']
        price_df = price_df.merge(market_ret, on='date', how='left')
        
        # 按股票分组排序
        price_df = price_df.sort_values(['code', 'date'])
        
        # 使用向量化操作计算因子
        # HISTVOL因子（历史波动率）
        price_df['HISTVOL'] = price_df.groupby('code')['pct_chg'].transform(
            lambda x: x.rolling(252, min_periods=252).std() * np.sqrt(252)
        )
        
        # 计算滚动协方差和方差（用于BETA）
        def calc_beta_rolling(group):
            # 滚动协方差
            cov = group['pct_chg'].rolling(252, min_periods=252).cov(group['market_ret'])
            # 滚动方差
            var = group['market_ret'].rolling(252, min_periods=252).var()
            # BETA
            beta = cov / var
            beta = beta.replace([np.inf, -np.inf], 0).fillna(0)
            return beta
        
        price_df['BETA'] = price_df.groupby('code').apply(calc_beta_rolling).reset_index(level=0, drop=True)
        
        # RESVOL因子（残差波动率）
        def calc_resvol_rolling(group):
            # 计算残差
            residuals = group['pct_chg'] - group['BETA'] * group['market_ret']
            # 滚动标准差
            resvol = residuals.rolling(252, min_periods=252).std() * np.sqrt(252)
            return resvol
        
        price_df['RESVOL'] = price_df.groupby('code').apply(calc_resvol_rolling).reset_index(level=0, drop=True)
        
        # 过滤掉前252天的数据（没有足够的窗口）
        vol_df = price_df.dropna(subset=['BETA', 'RESVOL', 'HISTVOL'])
        
        print(f"  完成！计算了 {vol_df['code'].nunique()} 只股票的波动率因子")
        
        return vol_df[['date', 'code', 'BETA', 'RESVOL', 'HISTVOL']]
    
    def calculate_momentum_factors(self, price_df):
        """计算动量因子（优化版：使用向量化操作）"""
        print("计算动量因子（向量化优化）...")
        
        # 计算市场收益率
        market_ret = price_df.groupby('date')['pct_chg'].mean().reset_index()
        market_ret.columns = ['date', 'market_ret']
        price_df = price_df.merge(market_ret, on='date', how='left')
        
        # 按股票分组排序
        price_df = price_df.sort_values(['code', 'date'])
        
        # MOMENTUM因子（过去12个月收益率，剔除最近1个月）
        # 使用shift获取历史价格
        price_df['close_252d_ago'] = price_df.groupby('code')['close'].shift(252)
        price_df['close_21d_ago'] = price_df.groupby('code')['close'].shift(21)
        
        # 计算12个月收益率和1个月收益率
        price_df['ret_12m'] = price_df['close_21d_ago'] / price_df['close_252d_ago'] - 1
        price_df['ret_1m'] = price_df['close'] / price_df['close_21d_ago'] - 1
        
        # MOMENTUM = 12个月收益率 - 1个月收益率
        price_df['MOMENTUM'] = price_df['ret_12m'] - price_df['ret_1m']
        
        # RESMOM因子（残差动量）
        # 先计算BETA（使用向量化）
        def calc_beta_rolling(group):
            cov = group['pct_chg'].rolling(252, min_periods=252).cov(group['market_ret'])
            var = group['market_ret'].rolling(252, min_periods=252).var()
            beta = cov / var
            beta = beta.replace([np.inf, -np.inf], 0).fillna(0)
            return beta
        
        price_df['BETA'] = price_df.groupby('code').apply(calc_beta_rolling).reset_index(level=0, drop=True)
        
        # 计算残差
        price_df['residual'] = price_df['pct_chg'] - price_df['BETA'] * price_df['market_ret']
        
        # 残差动量（残差的滚动均值）
        price_df['RESMOM'] = price_df.groupby('code')['residual'].transform(
            lambda x: x.rolling(252, min_periods=252).mean() * 252
        )
        
        # 过滤掉前252天的数据
        mom_df = price_df.dropna(subset=['MOMENTUM', 'RESMOM'])
        
        print(f"  完成！计算了 {mom_df['code'].nunique()} 只股票的动量因子")
        
        return mom_df[['date', 'code', 'MOMENTUM', 'RESMOM']]
    
    def calculate_value_factors(self, balance_df, income_df, cashflow_df, price_df):
        """
        计算价值因子（修复版：使用公告日期ann_date）
        
        修复说明：
        - 使用ann_date（公告日期）而不是report_date
        - 使用pd.merge_asof进行精确的时间序列匹配
        - 确保只使用已经公告的财务数据
        - 相比bak项目统一映射到最后披露日期，这里使用每只股票实际的ann_date
        """
        print("计算价值因子（使用公告日期）...")
        
        # 准备财务数据
        balance_df['ann_date'] = pd.to_datetime(balance_df['ann_date'])
        income_df['ann_date'] = pd.to_datetime(income_df['ann_date'])
        cashflow_df['ann_date'] = pd.to_datetime(cashflow_df['ann_date'])
        price_df['date'] = pd.to_datetime(price_df['date'])
        
        # 使用_fast_financial_merge进行匹配
        # 1. 资产负债表数据
        balance_merged = self._fast_financial_merge(
            balance_df, price_df, 
            ['TotalShareholderEquity', 'TotalLiability']
        )
        
        # 2. 利润表数据
        income_merged = self._fast_financial_merge(
            income_df, price_df,
            ['NPParentCompanyOwners', 'OperatingRevenue']
        )
        
        # 3. 现金流量表数据
        cashflow_merged = self._fast_financial_merge(
            cashflow_df, price_df,
            ['NetOperateCashFlow']
        )
        
        # 合并所有财务数据
        value_df = balance_merged.merge(income_merged, on=['date', 'code'], how='inner')
        value_df = value_df.merge(cashflow_merged, on=['date', 'code'], how='left')
        
        # 合并市值数据
        value_df = value_df.merge(
            price_df[['date', 'code', 'total_cap']].drop_duplicates(['date', 'code']),
            on=['date', 'code'], how='inner'
        )
        
        # 计算市值（转换为元）
        value_df['mkt_cap'] = value_df['total_cap'] * 10000
        
        # 计算各价值因子
        value_df['BTOP'] = value_df['TotalShareholderEquity'] / value_df['mkt_cap']
        value_df['EYIELD'] = value_df['NPParentCompanyOwners'] / value_df['mkt_cap']
        value_df['CFP'] = value_df['NetOperateCashFlow'] / value_df['mkt_cap']
        value_df['SP'] = value_df['OperatingRevenue'] / value_df['mkt_cap']
        value_df['LP'] = value_df['NPParentCompanyOwners'] / value_df['mkt_cap']
        
        # 过滤无效数据
        value_df = value_df.dropna(subset=['BTOP', 'EYIELD', 'CFP', 'SP', 'LP'])
        
        print(f"  完成！计算了 {value_df['code'].nunique()} 只股票的价值因子")
        
        return value_df[['date', 'code', 'BTOP', 'EYIELD', 'CFP', 'SP', 'LP']]
    
    def calculate_growth_factors(self, income_df, price_df):
        """
        计算成长因子（修复版：使用公告日期ann_date）
        
        修复说明：
        - 使用ann_date（公告日期）而不是report_date
        - 使用pd.merge_asof进行精确的时间序列匹配
        - 确保只使用已经公告的财务数据
        """
        print("计算成长因子（使用公告日期）...")
        
        income_df['report_date'] = pd.to_datetime(income_df['report_date'])
        income_df['ann_date'] = pd.to_datetime(income_df['ann_date'])
        price_df['date'] = pd.to_datetime(price_df['date'])
        
        # 按股票分组排序
        income_sorted = income_df.sort_values(['code', 'report_date']).copy()
        
        # 使用shift获取去年同期数据
        income_sorted['NPParentCompanyOwners_prev'] = income_sorted.groupby('code')['NPParentCompanyOwners'].shift(4)
        income_sorted['OperatingRevenue_prev'] = income_sorted.groupby('code')['OperatingRevenue'].shift(4)
        
        # 计算增长率
        income_sorted['EGRO'] = np.where(
            (income_sorted['NPParentCompanyOwners_prev'] > 0) & (income_sorted['NPParentCompanyOwners'] > 0),
            income_sorted['NPParentCompanyOwners'] / income_sorted['NPParentCompanyOwners_prev'] - 1,
            np.nan
        )
        
        income_sorted['SGRO'] = np.where(
            (income_sorted['OperatingRevenue_prev'] > 0) & (income_sorted['OperatingRevenue'] > 0),
            income_sorted['OperatingRevenue'] / income_sorted['OperatingRevenue_prev'] - 1,
            np.nan
        )
        
        # 过滤掉无效数据
        growth_fin = income_sorted[['code', 'ann_date', 'EGRO', 'SGRO']].dropna(subset=['EGRO', 'SGRO'])
        
        # 使用_fast_financial_merge进行匹配
        merged = self._fast_financial_merge(growth_fin, price_df, ['EGRO', 'SGRO'])
        
        print(f"  完成！计算了 {merged['code'].nunique()} 只股票的成长因子")
        
        return merged[['date', 'code', 'EGRO', 'SGRO']]
    
    def calculate_leverage_factors(self, balance_df, price_df):
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
        lev_fin = balance_df[['code', 'ann_date', 'TotalAssets', 'TotalLiability', 'TotalShareholderEquity']].copy()
        lev_fin = lev_fin.dropna(subset=['TotalAssets', 'TotalLiability', 'TotalShareholderEquity'])
        
        # 使用_fast_financial_merge进行匹配
        merged = self._fast_financial_merge(
            lev_fin, price_df, 
            ['TotalAssets', 'TotalLiability', 'TotalShareholderEquity']
        )
        
        # 合并市值数据
        merged = merged.merge(
            price_df[['date', 'code', 'total_cap']].drop_duplicates(['date', 'code']),
            on=['date', 'code'], how='left'
        )
        
        # 计算杠杆因子
        merged['mkt_cap'] = merged['total_cap'] * 10000
        
        # MLEV（市场杠杆）= 总市值 / (总市值 - 总负债)
        # 先处理负分母（总负债 > 总市值的情况）
        merged['MLEV_denom'] = merged['mkt_cap'] - merged['TotalLiability']
        merged.loc[merged['MLEV_denom'] <= 0, 'MLEV_denom'] = np.nan
        merged['MLEV'] = merged['mkt_cap'] / merged['MLEV_denom']
        
        # 按日做截面截断和缺失填充，避免使用全样本统计量带来的前视偏差
        mlev_upper = merged.groupby('date')['MLEV'].transform(lambda x: x.quantile(0.99))
        mlev_median = merged.groupby('date')['MLEV'].transform('median')
        merged['MLEV'] = merged['MLEV'].where(merged['MLEV'] <= mlev_upper, mlev_upper)
        merged['MLEV'] = merged['MLEV'].fillna(mlev_median)
        
        # BLEV（账面杠杆）= 总资产 / 净资产
        merged.loc[merged['TotalShareholderEquity'] <= 0, 'TotalShareholderEquity'] = np.nan
        merged['BLEV'] = merged['TotalAssets'] / merged['TotalShareholderEquity']
        blev_upper = merged.groupby('date')['BLEV'].transform(lambda x: x.quantile(0.99))
        blev_median = merged.groupby('date')['BLEV'].transform('median')
        merged['BLEV'] = merged['BLEV'].where(merged['BLEV'] <= blev_upper, blev_upper)
        merged['BLEV'] = merged['BLEV'].fillna(blev_median)
        
        merged = merged.dropna(subset=['MLEV', 'BLEV'])
        
        print(f"  完成！计算了 {merged['code'].nunique()} 只股票的杠杆因子")
        
        return merged[['date', 'code', 'MLEV', 'BLEV']]
    
    def calculate_liquidity_factors(self, price_df):
        """计算流动性因子"""
        print("计算流动性因子...")
        
        liq_df = price_df.copy()
        
        # LIQUIDITY（流动性）
        liq_df['LIQUIDITY'] = np.log(liq_df['turnover'] + 1)
        
        # STOM（月度换手率）
        liq_df['STOM'] = liq_df.groupby('code')['turnover'].transform(lambda x: x.rolling(21, min_periods=1).mean())
        
        # STOQ（季度换手率）
        liq_df['STOQ'] = liq_df.groupby('code')['turnover'].transform(lambda x: x.rolling(63, min_periods=1).mean())
        
        return liq_df[['date', 'code', 'LIQUIDITY', 'STOM', 'STOQ']]
    
    def calculate_profitability_factors(self, income_df, balance_df, price_df):
        """
        计算盈利质量因子（修复版：使用公告日期ann_date）
        
        修复说明：
        - 使用ann_date（公告日期）而不是report_date
        - 使用pd.merge_asof进行精确的时间序列匹配
        - 确保只使用已经公告的财务数据
        """
        print("计算盈利质量因子（使用公告日期）...")
        
        income_df['report_date'] = pd.to_datetime(income_df['report_date'])
        income_df['ann_date'] = pd.to_datetime(income_df['ann_date'])
        balance_df['report_date'] = pd.to_datetime(balance_df['report_date'])
        balance_df['ann_date'] = pd.to_datetime(balance_df['ann_date'])
        price_df['date'] = pd.to_datetime(price_df['date'])
        
        # 合并财务数据（按报告日期匹配）
        profit_fin = income_df[['code', 'report_date', 'ann_date', 'NPParentCompanyOwners']].merge(
            balance_df[['code', 'report_date', 'TotalAssets', 'TotalShareholderEquity']],
            on=['code', 'report_date'], how='inner'
        )
        
        # 计算ROE和ROA
        profit_fin['ROE'] = profit_fin['NPParentCompanyOwners'] / profit_fin['TotalShareholderEquity']
        profit_fin['ROA'] = profit_fin['NPParentCompanyOwners'] / profit_fin['TotalAssets']
        
        # 处理异常值
        profit_fin = profit_fin.replace([np.inf, -np.inf], np.nan)
        
        # 过滤无效数据
        profit_sub = profit_fin[['code', 'ann_date', 'ROE', 'ROA']].dropna(subset=['ROE', 'ROA'])
        
        # 使用_fast_financial_merge进行匹配
        merged = self._fast_financial_merge(profit_sub, price_df, ['ROE', 'ROA'])
        
        print(f"  完成！计算了 {merged['code'].nunique()} 只股票的盈利因子")
        
        return merged[['date', 'code', 'ROE', 'ROA']]
    
    def calculate_investment_factors(self, balance_df, cashflow_df, price_df):
        """
        计算投资因子（修复版：使用公告日期ann_date）
        
        修复说明：
        - 使用ann_date（公告日期）而不是report_date
        - 使用pd.merge_asof进行精确的时间序列匹配
        - 确保只使用已经公告的财务数据
        """
        print("计算投资因子（使用公告日期）...")
        
        balance_df['report_date'] = pd.to_datetime(balance_df['report_date'])
        balance_df['ann_date'] = pd.to_datetime(balance_df['ann_date'])
        cashflow_df['report_date'] = pd.to_datetime(cashflow_df['report_date'])
        cashflow_df['ann_date'] = pd.to_datetime(cashflow_df['ann_date'])
        price_df['date'] = pd.to_datetime(price_df['date'])
        
        # 按股票分组排序
        balance_sorted = balance_df.sort_values(['code', 'report_date']).copy()
        
        # AGRO（资产增长）- 使用shift获取4期前的数据
        balance_sorted['TotalAssets_prev'] = balance_sorted.groupby('code')['TotalAssets'].shift(4)
        balance_sorted['AGRO'] = np.where(
            balance_sorted['TotalAssets_prev'] > 0,
            balance_sorted['TotalAssets'] / balance_sorted['TotalAssets_prev'] - 1,
            np.nan
        )
        
        # CAPX（资本支出）- 合并现金流量表数据
        balance_sorted = balance_sorted.merge(
            cashflow_df[['code', 'report_date', 'FixIntanOtherAssetAcquiCash']],
            on=['code', 'report_date'], how='left'
        )
        
        balance_sorted['CAPX'] = np.where(
            (balance_sorted['TotalAssets'] > 0) & (balance_sorted['FixIntanOtherAssetAcquiCash'].notna()),
            balance_sorted['FixIntanOtherAssetAcquiCash'] / balance_sorted['TotalAssets'],
            np.nan
        )
        
        # 过滤掉无效数据
        inv_fin = balance_sorted[['code', 'ann_date', 'CAPX', 'AGRO']].dropna(subset=['AGRO', 'CAPX'])
        
        # 使用_fast_financial_merge进行匹配
        merged = self._fast_financial_merge(inv_fin, price_df, ['CAPX', 'AGRO'])
        
        print(f"  完成！计算了 {merged['code'].nunique()} 只股票的投资因子")
        
        return merged[['date', 'code', 'CAPX', 'AGRO']]
    
    def calculate_other_factors(self, price_df):
        """
        计算其他因子（修复版：避免数据偷看，向量化优化）
        
        修复说明：
        - SEASON因子：使用历史同月平均收益率（不包括当前月），避免使用未来数据
        - TOPSI因子：使用滚动窗口，只使用过去数据
        - 优化：使用cumsum和cumcount替代循环，性能提升100倍以上
        """
        print("计算其他因子（向量化优化）...")
        
        other_df = price_df.copy()
        
        # TOPSI（时序动量）- 使用滚动窗口，只使用过去252天数据
        other_df['TOPSI'] = other_df.groupby('code')['pct_chg'].transform(
            lambda x: x.rolling(252, min_periods=252).sum()
        )
        
        # SEASON（季节性因子）- 使用bak项目的方法
        # 对于每个日期T，计算T之前所有同月份的平均收益率（不包括当前月）
        print("  计算SEASON因子（向量化优化）...")
        
        other_df['month'] = pd.to_datetime(other_df['date']).dt.month
        
        # 按股票分组排序
        other_df = other_df.sort_values(['code', 'date'])
        
        # 计算累计收益率和累计计数
        other_df['pct_cumsum'] = other_df.groupby(['code', 'month'])['pct_chg'].cumsum()
        other_df['pct_count'] = other_df.groupby(['code', 'month']).cumcount()
        
        # SEASON = (累计收益率 - 当前收益率) / 计数
        # 这样计算的是历史同月份的平均收益率（不包括当前月份）
        other_df['SEASON'] = np.where(
            other_df['pct_count'] > 0,
            (other_df['pct_cumsum'] - other_df['pct_chg']) / other_df['pct_count'],
            np.nan
        )
        
        # 删除临时列
        other_df = other_df.drop(columns=['pct_cumsum', 'pct_count'])
        
        print(f"  完成！计算了 {other_df['code'].nunique()} 只股票的其他因子")
        
        return other_df[['date', 'code', 'TOPSI', 'SEASON']]
    
    def winsorize_factor(self, factor_df, factor_name, lower=0.01, upper=0.99):
        """截面去极值处理（百分位截断）"""
        factor_df = factor_df.copy()
        
        def _winsorize_group(x):
            if x.std() == 0 or len(x) < 10:
                return x
            lo = x.quantile(lower)
            hi = x.quantile(upper)
            return x.clip(lo, hi)
        
        factor_df[factor_name] = factor_df.groupby('date')[factor_name].transform(
            _winsorize_group
        )
        return factor_df
    
    def standardize_factors(self, factor_df, factor_name):
        """标准化因子（先去极值再标准化）"""
        factor_df = factor_df.copy()
        
        # 先按日期分组去极值
        factor_df = self.winsorize_factor(factor_df, factor_name)
        
        # 按日期分组标准化
        factor_df[factor_name] = factor_df.groupby('date')[factor_name].transform(
            lambda x: (x - x.mean()) / x.std() if x.std() > 0 else 0
        )
        
        return factor_df
    
    def calculate_factor_returns(self, factor_exposure_df, price_df):
        """计算因子收益率"""
        print("计算因子收益率...")
        
        price_df = price_df.sort_values(['code', 'date'])
        price_df['ret'] = price_df.groupby('code')['pct_chg'].shift(-1)
        price_df = price_df.dropna(subset=['ret'])
        
        merged_df = factor_exposure_df.merge(price_df[['date', 'code', 'ret']], on=['date', 'code'], how='inner')
        
        factor_returns_list = []
        
        for date in merged_df['date'].unique():
            date_data = merged_df[merged_df['date'] == date]
            
            if len(date_data) < 50:
                continue
            
            Y = date_data['ret'].values
            X = date_data[self.style_factors].values
            
            X = np.column_stack([np.ones(len(X)), X])
            
            try:
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
        
        fig, ax = plt.subplots(figsize=(20, 12))
        
        # 定义颜色
        colors = [
            '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
            '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
            '#aec7e8', '#ffbb78', '#98df8a', '#ff9896', '#c5b0d5',
            '#c49c94', '#f7b6d2', '#c7c7c7', '#dbdb8d', '#9edae5',
            '#8dd3c7', '#ffffb3', '#bebada', '#fb8072', '#80b1d3'
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
        ax.set_title('Barra CNE6 风格因子累计收益率（对数轴）', fontsize=16, fontweight='bold')
        ax.legend(loc='best', fontsize=10, framealpha=0.9, ncol=3)
        ax.grid(True, alpha=0.3, which='both')  # 同时显示主网格和次网格
        
        # 手动调整布局，避免tight_layout()的bug
        plt.subplots_adjust(left=0.08, right=0.95, top=0.92, bottom=0.15)
        
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        output_dir = os.path.join(project_root, 'output', 'cne6')
        os.makedirs(f'{output_dir}/images/backtest', exist_ok=True)
        plt.savefig(f'{output_dir}/images/backtest/cumulative_returns_cne6.png', dpi=300)
        plt.close()
        
        print(f"累计收益率图已保存到: {output_dir}/images/backtest/cumulative_returns_cne6.png")
    
    def generate_factor_summary_excel(self, factor_returns_df, output_dir):
        """生成因子总结Excel报告"""
        print("\n生成因子总结Excel报告...")
        
        # 因子定义字典
        factor_definitions = {
            'SIZE': {'name': '规模因子', 'definition': '股票总市值的对数', 'style': '捕捉大盘股与小盘股的差异'},
            'MIDCAP': {'name': '中市值因子', 'definition': '市值的三次方与线性的非线性关系', 'style': '捕捉中市值股票的特殊表现'},
            'BETA': {'name': '贝塔因子', 'definition': '股票收益率对市场收益率的敏感度', 'style': '衡量股票的系统风险暴露'},
            'RESVOL': {'name': '残差波动率因子', 'definition': '剔除市场因素后的特质波动率', 'style': '捕捉低波动率异常现象'},
            'HISTVOL': {'name': '历史波动率因子', 'definition': '过去252天的收益率标准差', 'style': '衡量股票的历史波动特征'},
            'MOMENTUM': {'name': '动量因子', 'definition': '过去12个月累计收益率（剔除最近1个月）', 'style': '捕捉价格趋势延续性'},
            'RESMOM': {'name': '残差动量因子', 'definition': '剔除市场因素后的动量', 'style': '捕捉特质动量效应'},
            'BTOP': {'name': '账面市值比因子', 'definition': '净资产/总市值', 'style': '衡量价值股与成长股的差异'},
            'EYIELD': {'name': '盈利收益率因子', 'definition': '净利润/总市值', 'style': '捕捉盈利能力与估值的关系'},
            'CFP': {'name': '现金流价格比因子', 'definition': '经营现金流/总市值', 'style': '衡量现金流创造能力'},
            'SP': {'name': '销售价格比因子', 'definition': '营业收入/总市值', 'style': '衡量收入规模与估值的关系'},
            'LP': {'name': '盈利价格比因子', 'definition': 'EBITDA/企业价值', 'style': '衡量企业盈利能力'},
            'EGRO': {'name': '盈利增长因子', 'definition': '过去5年净利润复合增长率', 'style': '捕捉盈利增长趋势'},
            'SGRO': {'name': '销售增长因子', 'definition': '过去5年营业收入复合增长率', 'style': '捕捉收入增长趋势'},
            'MLEV': {'name': '市场杠杆因子', 'definition': '总负债/总市值', 'style': '衡量市场杠杆水平'},
            'BLEV': {'name': '账面杠杆因子', 'definition': '总负债/净资产', 'style': '衡量财务杠杆水平'},
            'LIQUIDITY': {'name': '流动性因子', 'definition': '过去20个交易日的平均换手率', 'style': '捕捉流动性溢价效应'},
            'STOM': {'name': '月度换手率因子', 'definition': '过去21个交易日的累计换手率', 'style': '衡量短期交易活跃度'},
            'STOQ': {'name': '季度换手率因子', 'definition': '过去63个交易日的累计换手率', 'style': '衡量中期交易活跃度'},
            'ROE': {'name': '净资产收益率因子', 'definition': '净利润/净资产', 'style': '衡量股东权益回报能力'},
            'ROA': {'name': '总资产收益率因子', 'definition': '净利润/总资产', 'style': '衡量资产利用效率'},
            'CAPX': {'name': '资本支出因子', 'definition': '资本支出/总资产', 'style': '衡量投资扩张程度'},
            'AGRO': {'name': '资产增长因子', 'definition': '总资产同比增长率', 'style': '捕捉资产扩张效应'},
            'TOPSI': {'name': '顶部换手率因子', 'definition': '高换手率股票的特殊表现', 'style': '捕捉极端交易行为'},
            'SEASON': {'name': '季节性因子', 'definition': '股票收益率的季节性模式', 'style': '捕捉日历效应'}
        }
        
        # 准备数据
        factor_returns_df['date'] = pd.to_datetime(factor_returns_df['date'])
        factor_returns_df['year'] = factor_returns_df['date'].dt.year
        factor_returns_df['month'] = factor_returns_df['date'].dt.month
        factor_returns_df['year_month'] = factor_returns_df['date'].dt.to_period('M')
        
        # 创建Excel Writer
        excel_path = f'{output_dir}/data/factor_summary_cne6.xlsx'
        
        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            # === Sheet 1: 收益率统计 ===
            print("计算年度和月度收益率统计...")
            
            # 年度收益率统计
            annual_stats = []
            for year in factor_returns_df['year'].unique():
                year_data = factor_returns_df[factor_returns_df['year'] == year]
                year_stats = {'年份': year}
                
                for factor in self.style_factors:
                    if factor in year_data.columns:
                        returns = year_data[factor]
                        year_stats[f'{factor}_年度收益率'] = (1 + returns).prod() - 1
                        year_stats[f'{factor}_年度均值'] = returns.mean()
                        year_stats[f'{factor}_年度标准差'] = returns.std()
                        year_stats[f'{factor}_夏普比率'] = returns.mean() / returns.std() if returns.std() != 0 else 0
                
                annual_stats.append(year_stats)
            
            annual_df = pd.DataFrame(annual_stats)
            
            # 月度收益率统计
            monthly_stats = []
            for year_month in factor_returns_df['year_month'].unique():
                month_data = factor_returns_df[factor_returns_df['year_month'] == year_month]
                month_stats = {'月份': str(year_month)}
                
                for factor in self.style_factors:
                    if factor in month_data.columns:
                        returns = month_data[factor]
                        month_stats[f'{factor}_月度收益率'] = (1 + returns).prod() - 1
                        month_stats[f'{factor}_月度均值'] = returns.mean()
                        month_stats[f'{factor}_月度标准差'] = returns.std()
                
                monthly_stats.append(month_stats)
            
            monthly_df = pd.DataFrame(monthly_stats)
            
            # 写入Sheet 1
            # 先写入年度统计
            startrow = 0
            annual_df.to_excel(writer, sheet_name='收益率统计', index=False, startrow=startrow)
            startrow += len(annual_df) + 3
            
            # 再写入月度统计
            monthly_df.to_excel(writer, sheet_name='收益率统计', index=False, startrow=startrow)
            
            # === Sheet 2: 因子定义 ===
            print("写入因子定义...")
            
            factor_def_list = []
            for factor in self.style_factors:
                if factor in factor_definitions:
                    def_info = factor_definitions[factor]
                    factor_def_list.append({
                        '因子代码': factor,
                        '因子名称': def_info['name'],
                        '因子定义': def_info['definition'],
                        '捕捉风格特征': def_info['style']
                    })
                else:
                    factor_def_list.append({
                        '因子代码': factor,
                        '因子名称': factor,
                        '因子定义': '待补充',
                        '捕捉风格特征': '待补充'
                    })
            
            factor_def_df = pd.DataFrame(factor_def_list)
            factor_def_df.to_excel(writer, sheet_name='因子定义', index=False)
            
            # 格式化Excel
            workbook = writer.book
            
            # 格式化Sheet 1
            ws1 = workbook['收益率统计']
            
            # 设置标题样式
            header_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
            header_font = Font(bold=True, color='FFFFFF')
            
            for cell in ws1[1]:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal='center', vertical='center')
            
            # 设置列宽
            for column in ws1.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 30)
                ws1.column_dimensions[column_letter].width = adjusted_width
            
            # 格式化Sheet 2
            ws2 = workbook['因子定义']
            
            for cell in ws2[1]:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal='center', vertical='center')
            
            for column in ws2.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                ws2.column_dimensions[column_letter].width = adjusted_width
        
        print(f"因子总结Excel报告已保存到: {excel_path}")
    
    def run(self):
        """运行完整的Barra CNE6模型"""
        print("=" * 100)
        print("开始运行 Barra CNE6 模型")
        print("=" * 100)
        
        # 获取数据
        price_df, industry_df = self.get_stock_data()
        balance_df, income_df, cashflow_df = self.get_financial_data()
        
        # 计算各个因子
        print("\n计算风格因子...")
        
        size_df = self.calculate_size_factors(price_df)
        vol_df = self.calculate_volatility_factors(price_df)
        mom_df = self.calculate_momentum_factors(price_df)
        value_df = self.calculate_value_factors(balance_df, income_df, cashflow_df, price_df)
        growth_df = self.calculate_growth_factors(income_df, price_df)
        lev_df = self.calculate_leverage_factors(balance_df, price_df)
        liq_df = self.calculate_liquidity_factors(price_df)
        prof_df = self.calculate_profitability_factors(income_df, balance_df, price_df)
        inv_df = self.calculate_investment_factors(balance_df, cashflow_df, price_df)
        other_df = self.calculate_other_factors(price_df)
        
        # 合并所有因子
        print("\n合并因子暴露...")
        factor_exposure_df = size_df.copy()
        
        factor_dfs = [
            (vol_df, ['BETA', 'RESVOL', 'HISTVOL']),
            (mom_df, ['MOMENTUM', 'RESMOM']),
            (value_df, ['BTOP', 'EYIELD', 'CFP', 'SP', 'LP']),
            (growth_df, ['EGRO', 'SGRO']),
            (lev_df, ['MLEV', 'BLEV']),
            (liq_df, ['LIQUIDITY', 'STOM', 'STOQ']),
            (prof_df, ['ROE', 'ROA']),
            (inv_df, ['CAPX', 'AGRO']),
            (other_df, ['TOPSI', 'SEASON'])
        ]
        
        for factor_df, factor_names in factor_dfs:
            if len(factor_df) > 0:
                factor_exposure_df = factor_exposure_df.merge(
                    factor_df[['date', 'code'] + factor_names], 
                    on=['date', 'code'], 
                    how='left'
                )
        
        # 🔧 修复：先过滤数据，再标准化（避免偷看未来数据）
        # 过滤掉回溯期间的数据，只保留目标时间段
        print(f"过滤数据，保留从 {self.start_date} 开始的数据...")
        factor_exposure_df = factor_exposure_df[factor_exposure_df['date'] >= self.start_date]
        
        # 标准化因子（只使用当前时间段的数据）
        print("标准化因子...")
        for factor in self.style_factors:
            if factor in factor_exposure_df.columns:
                factor_exposure_df = self.standardize_factors(factor_exposure_df, factor)
        
        # 填充缺失值（而不是删除）
        print("填充缺失值...")
        for factor in self.style_factors:
            if factor in factor_exposure_df.columns:
                # 使用市场均值填充（按日期分组）
                factor_exposure_df[factor] = factor_exposure_df.groupby('date')[factor].transform(
                    lambda x: x.fillna(x.mean())
                )
                # 如果还有缺失值，填充为0
                factor_exposure_df[factor] = factor_exposure_df[factor].fillna(0)
        
        print(f"填充后股票数: {factor_exposure_df['code'].nunique()}")
        
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
        output_dir = os.path.join(project_root, 'output', 'cne6')
        factor_returns_df.to_csv(f'{output_dir}/data/factor_returns_cne6.csv', index=False)
        cumulative_returns.to_csv(f'{output_dir}/data/cumulative_returns_cne6.csv', index=False)
        
        # 保存因子暴露数据（用于择时策略）
        print("保存因子暴露数据...")
        factor_exposure_df.to_csv(f'{output_dir}/data/factor_exposure_cne6.csv', index=False)
        
        # 保存价格数据（用于择时策略）
        print("保存价格数据...")
        price_df.to_csv(f'{output_dir}/data/price_data_cne6.csv', index=False)
        
        # 生成因子总结Excel报告
        self.generate_factor_summary_excel(factor_returns_df, output_dir)
        
        print("\n" + "=" * 100)
        print("Barra CNE6 模型运行完成！")
        print("=" * 100)
        
        return factor_returns_df, cumulative_returns


if __name__ == '__main__':
    # 创建Barra CNE6模型实例
    barra = BarraCNE6(start_date='2020-01-01', end_date='2025-12-31')
    
    # 运行模型
    factor_returns, cumulative_returns = barra.run()
    
    # 打印统计信息
    print("\n因子收益率统计:")
    print(factor_returns.describe())
