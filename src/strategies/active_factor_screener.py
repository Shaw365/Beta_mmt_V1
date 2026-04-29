"""
主动因子筛选模块

功能：
1. 加载AI因子数据（F:\Data\AI\AI_FACTOR）
2. 使用2019-2020年IC方向确定各因子符号
3. 合成主动因子总分
4. 从Barra择时候选池中二次精选
"""

import pandas as pd
import numpy as np
import os
import glob
import warnings
warnings.filterwarnings('ignore')


class ActiveFactorScreener:
    """主动因子筛选器"""
    
    def __init__(self, factor_dir, ic_period=('2019-01-01', '2020-12-31')):
        """
        参数:
            factor_dir: 因子数据目录 (F:\Data\AI\AI_FACTOR)
            ic_period: IC计算区间，默认2019-2020年
        """
        self.factor_dir = factor_dir
        self.ic_start = ic_period[0]
        self.ic_end = ic_period[1]
        self.factor_signs = {}       # 因子名 -> 符号 (+1/-1)
        self.factor_data = None      # 合并后的全部因子数据
        self.factor_names = []       # 去重后的因子名列表
        
    def load_factor_data(self):
        """
        加载所有因子数据并合并
        
        去重策略：同名因子只保留第一个文件
        """
        print("\n加载主动因子数据...")
        
        files = glob.glob(os.path.join(self.factor_dir, '*.csv'))
        print(f"  发现 {len(files)} 个因子文件")
        
        loaded_factors = {}
        
        for f in files:
            # 提取因子名（文件名格式: factorname_timestamp.csv）
            basename = os.path.basename(f)
            factor_name = basename.split('_260')[0]
            
            # 去重
            if factor_name in loaded_factors:
                continue
            
            df = pd.read_csv(f)
            df['date'] = pd.to_datetime(df['date'])
            
            # 找到因子值列（非date/code的列）
            val_cols = [c for c in df.columns if c not in ['date', 'code']]
            if len(val_cols) == 0:
                continue
            
            # 统一列名为因子名
            val_col = val_cols[0]
            df = df.rename(columns={val_col: factor_name})
            df = df[['date', 'code', factor_name]]
            
            loaded_factors[factor_name] = df
            
        self.factor_names = list(loaded_factors.keys())
        print(f"  去重后 {len(self.factor_names)} 个因子: {self.factor_names}")
        
        # 合并所有因子到一张宽表
        print("  合并因子数据...")
        dfs = list(loaded_factors.values())
        merged = dfs[0]
        for df in dfs[1:]:
            merged = merged.merge(df, on=['date', 'code'], how='outer')
        
        self.factor_data = merged
        print(f"  合并后: {len(merged)} 行, {merged['code'].nunique()} 只股票, "
              f"{merged['date'].nunique()} 个交易日")
        
        return self.factor_data
    
    def calculate_ic_directions(self, price_df=None):
        """
        计算2019-2020年各因子的IC方向
        
        IC = 因子值与次日收益率的Spearman相关系数
        如果IC均值 > 0，符号为+1（同向）
        如果IC均值 < 0，符号为-1（反向）
        
        参数:
            price_df: 价格数据（用于计算次日收益率），如果为None则从因子数据推断
        
        返回:
            factor_signs: {因子名: 符号(+1/-1)}
        """
        print("\n计算IC方向...")
        print(f"  IC计算区间: {self.ic_start} ~ {self.ic_end}")
        
        if self.factor_data is None:
            self.load_factor_data()
        
        # 筛选IC计算区间
        ic_data = self.factor_data[
            (self.factor_data['date'] >= self.ic_start) & 
            (self.factor_data['date'] <= self.ic_end)
        ].copy()
        
        print(f"  IC区间数据: {len(ic_data)} 行")
        
        # 计算每个因子的截面IC（Rank IC）
        # 使用因子值与次日收益率的秩相关
        # 先计算次日收益率
        if price_df is not None:
            # 使用提供的价格数据计算次日收益率
            price_df = price_df.copy()
            price_df['date'] = pd.to_datetime(price_df['date'])
            price_df = price_df.sort_values(['code', 'date'])
            price_df['next_ret'] = price_df.groupby('code')['pct_chg'].shift(-1)
            price_df = price_df.dropna(subset=['next_ret'])
            
            # 与因子数据合并
            ic_data = ic_data.merge(
                price_df[['date', 'code', 'next_ret']], 
                on=['date', 'code'], how='inner'
            )
        else:
            # 无法计算，使用默认正方向
            print("  警告: 未提供价格数据，所有因子默认方向为+1")
            for name in self.factor_names:
                self.factor_signs[name] = 1
            return self.factor_signs
        
        # 按日期计算截面Rank IC
        print("  计算截面Rank IC...")
        ic_results = {}
        
        for factor_name in self.factor_names:
            if factor_name not in ic_data.columns:
                continue
            
            daily_ics = []
            for date, group in ic_data.groupby('date'):
                valid = group.dropna(subset=[factor_name, 'next_ret'])
                if len(valid) < 30:
                    continue
                
                # Spearman秩相关（用rank的pearson代替）
                rank_factor = valid[factor_name].rank()
                rank_ret = valid['next_ret'].rank()
                ic = rank_factor.corr(rank_ret)
                
                if np.isfinite(ic):
                    daily_ics.append(ic)
            
            if len(daily_ics) > 0:
                mean_ic = np.mean(daily_ics)
                ic_results[factor_name] = {
                    'mean_ic': mean_ic,
                    'std_ic': np.std(daily_ics),
                    'icir': mean_ic / np.std(daily_ics) if np.std(daily_ics) > 0 else 0,
                    'n_days': len(daily_ics),
                    'sign': 1 if mean_ic > 0 else -1
                }
                self.factor_signs[factor_name] = 1 if mean_ic > 0 else -1
        
        # 打印IC结果
        print(f"\n  {'因子名':45s} {'IC均值':>8s} {'IC标准差':>8s} {'ICIR':>8s} {'方向':>6s}")
        print("  " + "-" * 80)
        for name, info in sorted(ic_results.items(), key=lambda x: abs(x[1]['mean_ic']), reverse=True):
            direction = '+' if info['sign'] > 0 else '-'
            print(f"  {name:45s} {info['mean_ic']:>8.4f} {info['std_ic']:>8.4f} "
                  f"{info['icir']:>8.4f} {direction:>6s}")
        
        # 保存IC分析结果
        ic_df = pd.DataFrame([
            {
                'factor': name, 
                'mean_ic': info['mean_ic'], 
                'std_ic': info['std_ic'],
                'icir': info['icir'], 
                'sign': info['sign']
            }
            for name, info in ic_results.items()
        ])
        
        print(f"\n  正方向因子: {sum(1 for v in self.factor_signs.values() if v > 0)} 个")
        print(f"  反方向因子: {sum(1 for v in self.factor_signs.values() if v < 0)} 个")
        
        return self.factor_signs, ic_df
    
    def compute_composite_score(self, date, codes):
        """
        计算指定日期、指定股票池的主动因子合成得分
        
        参数:
            date: 日期
            codes: 股票代码列表
            
        返回:
            Series, index=code, values=合成得分（降序排列）
        """
        if self.factor_data is None or len(self.factor_signs) == 0:
            return pd.Series(dtype=float)
        
        # 获取该日期该股票池的因子数据
        mask = (self.factor_data['date'] == date) & (self.factor_data['code'].isin(codes))
        date_data = self.factor_data[mask].copy()
        
        if len(date_data) == 0:
            return pd.Series(dtype=float)
        
        # 对每个因子按截面z-score标准化
        composite = pd.Series(0.0, index=date_data['code'].values)
        n_factors = 0
        
        for factor_name, sign in self.factor_signs.items():
            if factor_name not in date_data.columns:
                continue
            
            values = date_data.set_index('code')[factor_name]
            
            # z-score标准化
            mean_val = values.mean()
            std_val = values.std()
            if std_val == 0 or np.isnan(std_val):
                continue
            
            z_score = (values - mean_val) / std_val
            
            # 乘以方向符号
            composite += sign * z_score.fillna(0)
            n_factors += 1
        
        if n_factors > 0:
            composite = composite / n_factors
        
        return composite.sort_values(ascending=False)
    
    def select_stocks(self, date, candidate_codes, top_n=100):
        """
        从候选池中选出主动因子得分最高的top_n只股票
        
        参数:
            date: 日期（使用该日期的因子数据）
            candidate_codes: 候选股票代码列表（来自Barra择时筛选）
            top_n: 选出的股票数量
            
        返回:
            选中的股票代码列表
        """
        scores = self.compute_composite_score(date, candidate_codes)
        
        if len(scores) == 0:
            return []
        
        selected = scores.head(top_n).index.tolist()
        return selected
    
    def save_ic_results(self, output_path):
        """保存IC分析结果"""
        if not hasattr(self, '_ic_df') or self._ic_df is None:
            return
        self._ic_df.to_csv(output_path, index=False, encoding='utf-8-sig')
        print(f"IC分析结果已保存: {output_path}")
