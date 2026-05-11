"""
风格因子择时策略（优化版）
优化：
1. 预先计算所有股票的周度收益率（性能优化）
2. 使用前一天的因子暴露数据选股（避免偷看未来数据）
3. 增加换手率统计
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator, ScalarFormatter
from datetime import datetime, timedelta
import warnings
import os
import sys

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.utils.trade_recorder import TradeRecorder

warnings.filterwarnings('ignore')

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['font.family'] = 'sans-serif'


class FactorTimingStrategy:
    """风格因子择时策略"""
    
    def __init__(self, long_prd=20, short_prd=5, channel_bins=3, extreme_value=1, top_n=100,
                 initial_capital=100000000, stock_capital=1000000,
                 turnover_control=False, max_turnover=None, turnover_buffer_multiplier=2.0):
        """
        参数:
            long_prd: 长周期（用于计算通道）
            short_prd: 短周期（用于过滤噪音）
            channel_bins: 通道内分档数（仅用于[0,1]区间，通道外仍为±1）
            extreme_value: 极端值（上涨=3, 震荡=0, 下跌=-3）
            top_n: 选股数量
            initial_capital: 初始资金（默认1亿）
            stock_capital: 单只股票市值（默认100万）
            turnover_control: 是否启用换手控制
            max_turnover: 单期最大单边换手率，如0.3表示最多卖出上一期30%的持仓
            turnover_buffer_multiplier: 换手缓冲候选池倍数，如2.0表示在Top 200里保留旧持仓
        """
        self.long_prd = long_prd
        self.short_prd = short_prd
        self.channel_bins = max(1, int(channel_bins))
        self.extreme_value = extreme_value
        self.top_n = top_n
        self.initial_capital = initial_capital
        self.stock_capital = stock_capital
        self.turnover_control = turnover_control
        self.max_turnover = max_turnover
        self.turnover_buffer_multiplier = max(1.0, float(turnover_buffer_multiplier))
        
        # 初始化交易记录器
        self.trade_recorder = TradeRecorder(initial_capital, stock_capital)
        
    def calc_pst(self, cumulative_returns_df):
        """
        计算择时信号（基于累计收益率）
        
        参数:
            cumulative_returns_df: 累计收益率数据 (index=日期, columns=因子名称)
            
        返回:
            择时信号DataFrame (index=日期, columns=因子名称,
            values: 通道外为±1，通道内按channel_bins等分并映射到(-1,1)的等距档位)
        """
        print("计算择时信号...")
        
        factors = cumulative_returns_df.columns.tolist()
        pst_df = pd.DataFrame(index=cumulative_returns_df.index, columns=factors, data=np.nan)

        # 通道内分档边界（[0, 1]）和对应信号值（去掉两端±1）
        bin_edges = np.linspace(0.0, 1.0, self.channel_bins + 1)
        inner_levels = np.linspace(-1.0, 1.0, self.channel_bins + 2)[1:-1]
        
        for factor in factors:
            # 计算通道上下轨
            bf_max = cumulative_returns_df[factor].shift(self.short_prd).rolling(self.long_prd).max()
            bf_min = cumulative_returns_df[factor].shift(self.short_prd).rolling(self.long_prd).min()

            channel_width = bf_max - bf_min
            valid_mask = bf_max.notna() & bf_min.notna()
            non_zero_width_mask = valid_mask & (channel_width != 0)

            # 计算当前位置在上下轨中的比例: 0=下轨, 1=上轨
            position = (cumulative_returns_df[factor] - bf_min) / channel_width

            # 通道宽度为0时无法分段，置为中性信号
            pst_df.loc[valid_mask & ~non_zero_width_mask, factor] = 0.0

            # 通道外单独赋值
            pst_df.loc[non_zero_width_mask & (position > 1.0), factor] = 1.0
            pst_df.loc[non_zero_width_mask & (position < 0.0), factor] = -1.0

            # 通道内[0,1]按channel_bins等比例分档
            in_channel = non_zero_width_mask & (position >= 0.0) & (position <= 1.0)
            for i in range(self.channel_bins):
                low = bin_edges[i]
                high = bin_edges[i + 1]
                level = inner_levels[i]

                if i == self.channel_bins - 1:
                    mask = in_channel & (position >= low) & (position <= high)
                else:
                    mask = in_channel & (position >= low) & (position < high)

                pst_df.loc[mask, factor] = level
            
        # 删除前面的NaN值（由于rolling和shift）
        pst_df = pst_df.dropna()
        
        return pst_df
    
    def generate_optimal_vector(self, pst_df):
        """
        生成最优向量
        
        参数:
            pst_df: 择时信号DataFrame (通道外为±1，通道内为按分档映射的离散值)
            
        返回:
            最优向量DataFrame (index=日期, columns=因子名称,
            通道外极端信号映射为±extreme_value，通道内信号保持原始分档强度)
        """
        print("生成最优向量...")
        
        # 余弦相似度对整体等比例缩放不敏感，因此只放大通道外的极端信号，
        # 保留通道内分档值，令extreme_value实际改变因子间的相对权重。
        optimal_vector_df = pst_df.copy()
        extreme_mask = np.isclose(optimal_vector_df.abs(), 1.0)
        optimal_vector_df = optimal_vector_df.mask(
            extreme_mask,
            np.sign(optimal_vector_df) * self.extreme_value
        )
        
        return optimal_vector_df
    
    def calculate_cosine_similarity(self, factor_vector, optimal_vector):
        """
        计算余弦相似度
        
        参数:
            factor_vector: 股票因子暴露向量 (标准化后的因子值)
            optimal_vector: 最优向量 (通道外极端信号已按extreme_value放大)
            
        返回:
            余弦相似度 (值越大越相似)
        """
        # 确保向量维度一致
        factor_vec = np.array(factor_vector).flatten()
        optimal_vec = np.array(optimal_vector).flatten()
        
        # 计算余弦相似度
        dot_product = np.dot(factor_vec, optimal_vec)
        norm_factor = np.linalg.norm(factor_vec)
        norm_optimal = np.linalg.norm(optimal_vec)
        
        if norm_factor == 0 or norm_optimal == 0:
            return 0
        
        similarity = dot_product / (norm_factor * norm_optimal)
        return similarity
    
    def precompute_weekly_returns(self, price_df, weekly_dates):
        """
        预先计算所有股票的周度收益率（性能优化）
        
        参数:
            price_df: 价格数据 (包含date, code, pct_chg)
            weekly_dates: 换仓日期列表
            
        返回:
            周度收益率DataFrame (index=股票代码, columns=换仓日期)
        """
        print("预计算所有股票的周度收益率...")
        
        # 确保日期格式一致
        price_df = price_df.copy()
        price_df['date'] = pd.to_datetime(price_df['date'])
        
        # 将价格数据转换为宽表格式（日期×股票）
        print("  转换数据格式...")
        price_pivot = price_df.pivot(index='date', columns='code', values='pct_chg')
        
        # 计算复权净值
        print("  计算复权净值...")
        nav_df = (1 + price_pivot).cumprod()
        
        # 计算每周收益率
        print("  计算周度收益率...")
        weekly_returns_dict = {}
        
        # 确保weekly_dates中的日期在nav_df的索引中
        available_dates = nav_df.index
        
        for i in range(len(weekly_dates) - 1):
            current_date = weekly_dates[i]
            next_date = weekly_dates[i + 1]
            
            # 找到最近的可用日期
            try:
                # 找到>= current_date的最近日期
                current_idx = available_dates.get_indexer([current_date], method='nearest')[0]
                # 找到<= next_date的最近日期
                next_idx = available_dates.get_indexer([next_date], method='nearest')[0]
                
                if current_idx >= 0 and next_idx >= 0 and next_idx > current_idx:
                    start_nav = nav_df.iloc[current_idx]
                    end_nav = nav_df.iloc[next_idx]
                    
                    # 周度收益率 = 期末净值 / 期初净值 - 1
                    weekly_return = end_nav / start_nav - 1
                    weekly_returns_dict[current_date] = weekly_return
            except Exception as e:
                # 如果日期不存在，跳过
                continue
        
        # 转换为DataFrame
        if len(weekly_returns_dict) > 0:
            weekly_returns_df = pd.DataFrame(weekly_returns_dict).T
            weekly_returns_df.index.name = 'date'
        else:
            # 如果没有数据，返回空DataFrame
            weekly_returns_df = pd.DataFrame()
        
        print(f"  完成！周度收益率矩阵: {weekly_returns_df.shape}")
        
        return weekly_returns_df
    
    def select_stocks(self, factor_exposure_df, optimal_vector, signal_date, trade_date,
                      suspended_codes=None, candidate_pool_size=None):
        """
        选择股票（使用信号日的因子暴露，交易日前一天的数据）
        
        参数:
            factor_exposure_df: 因子暴露数据 (包含date, code和因子列)
            optimal_vector: 最优向量 (Series, index=因子名称)
            signal_date: 信号生成日期（使用该日期的因子暴露）
            trade_date: 交易日期（用于日志）
            suspended_codes: 停牌股票代码集合（不参与选股）
            candidate_pool_size: 候选池大小。为空时直接返回top_n；启用换手控制时可扩大候选池
            
        返回:
            选中的股票代码列表
        """
        if suspended_codes is None:
            suspended_codes = set()
        # 确保日期格式一致
        factor_exposure_df = factor_exposure_df.copy()
        factor_exposure_df['date'] = pd.to_datetime(factor_exposure_df['date'])
        
        # 使用信号日期的因子暴露数据（避免偷看未来数据）
        current_data = factor_exposure_df[factor_exposure_df['date'] == signal_date].copy()
        
        if len(current_data) == 0:
            # 如果信号日期没有数据，使用之前最近的数据
            current_data = factor_exposure_df[factor_exposure_df['date'] <= signal_date].copy()
            if len(current_data) == 0:
                print(f"警告: {signal_date} 没有因子暴露数据")
                return []
            current_data = current_data.sort_values('date')
            current_data = current_data.groupby('code').last().reset_index()
        
        # 计算每只股票与最优向量的余弦相似度
        similarities = []
        factors = optimal_vector.index.tolist()
        
        for idx, row in current_data.iterrows():
            # 跳过停牌股票
            if row['code'] in suspended_codes:
                continue
            factor_vector = row[factors].values
            similarity = self.calculate_cosine_similarity(factor_vector, optimal_vector)
            similarities.append({
                'code': row['code'],
                'similarity': similarity
            })
        
        # 转换为DataFrame并排序
        similarity_df = pd.DataFrame(similarities)
        
        if len(similarity_df) == 0:
            print(f"警告: {signal_date} 所有候选股票均停牌")
            return []
        
        similarity_df = similarity_df.sort_values('similarity', ascending=False)
        
        # 选择相似度最高的股票。换手控制会先拿更宽的候选池，再从中保留旧持仓。
        pool_size = candidate_pool_size if candidate_pool_size is not None else self.top_n
        selected_codes = similarity_df.head(pool_size)['code'].tolist()
        
        if len(selected_codes) < min(pool_size, self.top_n):
            print(f"警告: {signal_date} 只选出了 {len(selected_codes)} 只股票（目标 {self.top_n}）")
        
        return selected_codes

    def get_turnover_candidate_pool_size(self):
        """根据换手缓冲倍数计算候选池大小。"""
        if not self.turnover_control:
            return self.top_n
        return max(self.top_n, int(np.ceil(self.top_n * self.turnover_buffer_multiplier)))

    def apply_turnover_control(self, prev_stocks, candidate_codes, target_n=None, blocked_codes=None):
        """
        在候选池中优先保留旧持仓，以降低单期换手。

        逻辑：
        1. 不启用换手控制时，直接取候选池前target_n只股票；
        2. 启用后，旧持仓如果仍落在缓冲候选池内，则优先保留；
        3. 如果设置了max_turnover，则至少保留对应数量的旧持仓；
        4. 最后按候选池排名补足到target_n。
        """
        target_n = target_n if target_n is not None else self.top_n
        blocked_codes = set(blocked_codes or [])
        candidate_codes = list(dict.fromkeys(candidate_codes))

        if (not self.turnover_control) or len(prev_stocks) == 0:
            return candidate_codes[:target_n]

        prev_set = set(prev_stocks)
        rank = {code: idx for idx, code in enumerate(candidate_codes)}

        # 已经在Top N里的旧持仓自然保留；缓冲池内的旧持仓作为降换手的备选保留对象。
        base_keep = [code for code in candidate_codes[:target_n] if code in prev_set]
        buffer_keep = [code for code in candidate_codes if code in prev_set and code not in base_keep]
        keep_codes = base_keep.copy()

        if self.max_turnover is not None:
            max_turnover = min(max(float(self.max_turnover), 0.0), 1.0)
            max_sells = int(np.floor(len(prev_stocks) * max_turnover))
            min_keep = max(0, min(len(prev_stocks), target_n) - max_sells)
            for code in buffer_keep:
                if len(keep_codes) >= min_keep:
                    break
                keep_codes.append(code)
            # 如果缓冲候选池里的旧持仓不足以满足换手上限，则继续保留未停牌的旧持仓。
            # 这一步会牺牲部分当期相似度排名，但能让max_turnover成为真正的交易约束。
            for code in prev_stocks:
                if len(keep_codes) >= min_keep:
                    break
                if code not in keep_codes and code not in blocked_codes:
                    keep_codes.append(code)
        else:
            keep_codes.extend(buffer_keep)

        keep_codes = sorted(dict.fromkeys(keep_codes), key=lambda code: rank.get(code, len(rank)))
        fill_codes = [code for code in candidate_codes if code not in set(keep_codes)]
        selected_codes = (keep_codes + fill_codes)[:target_n]

        return selected_codes
    
    def calculate_turnover(self, prev_stocks, current_stocks):
        """
        计算换手率（单边）
        
        参数:
            prev_stocks: 上一期持仓股票列表
            current_stocks: 本期持仓股票列表
            
        返回:
            换手率（单边，卖出数/上期持仓数，上限100%）
        """
        if len(prev_stocks) == 0 or len(current_stocks) == 0:
            return 0
        
        # 计算卖出的股票数
        sold = set(prev_stocks) - set(current_stocks)
        
        # 单边换手率 = 卖出数 / 上期持仓数
        turnover = len(sold) / len(prev_stocks)
        
        # 限制在 [0, 1]
        turnover = min(turnover, 1.0)
        
        return turnover
    
    def run_weekly_rebalance(self, factor_exposure_df, cumulative_returns_df, price_df,
                              active_screener=None, active_top_n=100):
        """
        执行周度换仓策略
        
        参数:
            factor_exposure_df: 因子暴露数据
            cumulative_returns_df: 累计收益率数据 (index=日期, columns=因子名称)
            price_df: 价格数据
            active_screener: 主动因子筛选器（可选），如果提供则从候选池中二次精选
            active_top_n: 主动因子筛选后保留的股票数量（默认100）
            
        返回:
            策略收益DataFrame
        """
        print("\n开始执行周度换仓策略...")
        if active_screener is not None:
            print(f"  启用主动因子筛选: Barra选{self.top_n}只 → 主动因子精选{active_top_n}只")
        
        # 计算择时信号（基于累计收益率）
        pst_df = self.calc_pst(cumulative_returns_df)
        
        # 生成最优向量
        optimal_vector_df = self.generate_optimal_vector(pst_df)
        
        # 获取交易日历（周度）
        all_dates = price_df['date'].unique()
        all_dates = pd.to_datetime(all_dates)
        all_dates = sorted(all_dates)
        
        # 选择每周最后一个交易日作为换仓日
        weekly_dates = []
        for i in range(len(all_dates)):
            current_date = all_dates[i]
            if i == 0:
                weekly_dates.append(current_date)
            else:
                prev_date = all_dates[i-1]
                if current_date.isocalendar().week != prev_date.isocalendar().week:
                    weekly_dates.append(current_date)
        
        print(f"总换仓次数: {len(weekly_dates)}")
        
        # 预计算所有股票的周度收益率（性能优化）
        weekly_returns_df = self.precompute_weekly_returns(price_df, weekly_dates)
        
        # 预构建停牌股票查找表（按日期索引，避免每次查询）
        print("构建停牌股票查找表...")
        price_df_with_date = price_df.copy()
        price_df_with_date['date'] = pd.to_datetime(price_df_with_date['date'])
        if 'is_suspend' in price_df_with_date.columns:
            suspend_lookup = price_df_with_date[price_df_with_date['is_suspend'] == 1].groupby('date')['code'].apply(set).to_dict()
        else:
            suspend_lookup = {}
        
        # 执行换仓
        portfolio_returns = []
        prev_stocks = []
        
        for i in range(len(weekly_dates) - 1):
            current_date = weekly_dates[i]
            next_date = weekly_dates[i + 1]
            
            # 获取信号日期（使用前一天的因子暴露，避免偷看未来数据）
            # 找到current_date前一个交易日
            current_idx = all_dates.index(current_date)
            if current_idx == 0:
                signal_date = current_date
            else:
                signal_date = all_dates[current_idx - 1]
            
            # 检查信号日期是否有择时信号
            if signal_date not in optimal_vector_df.index:
                continue
            
            # 获取最优向量
            optimal_vector = optimal_vector_df.loc[signal_date]
            
            # 获取当日停牌股票集合
            suspended_codes = suspend_lookup.get(current_date, set())
            
            # 第一步：Barra择时选股（使用信号日期的因子暴露，排除停牌股票）
            # 启用换手控制时，先取更宽的候选池，随后在候选池内优先保留旧持仓。
            candidate_pool_size = self.get_turnover_candidate_pool_size()
            selected_codes = self.select_stocks(factor_exposure_df, optimal_vector, signal_date, current_date, 
                                                suspended_codes=suspended_codes,
                                                candidate_pool_size=candidate_pool_size)
            
            if len(selected_codes) == 0:
                continue
            
            # 第二步：主动因子二次筛选（使用前一天的因子值，防止数据偷看）
            if active_screener is not None and len(selected_codes) > active_top_n:
                # 使用signal_date（前一个交易日）的因子数据
                active_selected = active_screener.select_stocks(
                    signal_date, selected_codes, top_n=active_top_n
                )
                if len(active_selected) > 0:
                    selected_codes = active_selected
                else:
                    # Active因子数据缺失时，沿用上一期持仓，避免持仓数从active_top_n暴增到Barra的top_n
                    if len(prev_stocks) > 0:
                        selected_codes = prev_stocks
                    # 如果是第一期且无Active数据，跳过本次换仓
                    else:
                        continue

            target_n = active_top_n if active_screener is not None else self.top_n
            selected_codes = self.apply_turnover_control(
                prev_stocks,
                selected_codes,
                target_n=target_n,
                blocked_codes=suspended_codes,
            )
            
            # 从预计算的周度收益率中获取组合收益率
            if current_date in weekly_returns_df.index:
                # 获取选中股票的周度收益率
                stock_returns = weekly_returns_df.loc[current_date, selected_codes]
                
                # 移除NaN值
                stock_returns = stock_returns.dropna()
                
                if len(stock_returns) == 0:
                    continue
                
                # 计算等权重组合收益率
                port_return = stock_returns.mean()
            else:
                continue
            
            # 计算换手率
            turnover = self.calculate_turnover(prev_stocks, selected_codes)
            
            # 记录交易
            self.trade_recorder.process_rebalance(current_date, selected_codes, price_df)
            
            portfolio_returns.append({
                'date': current_date,
                'signal_date': signal_date,
                'next_date': next_date,
                'return': port_return,
                'num_stocks': len(selected_codes),
                'turnover': turnover,
                'selected_codes': selected_codes
            })
            
            prev_stocks = selected_codes
        
        # 转换为DataFrame
        portfolio_returns_df = pd.DataFrame(portfolio_returns)
        
        print(f"有效换仓次数: {len(portfolio_returns_df)}")
        
        # 统计持仓数量
        if len(portfolio_returns_df) > 0:
            print(f"\n持仓数量统计:")
            print(f"  平均持仓: {portfolio_returns_df['num_stocks'].mean():.1f}")
            print(f"  最小持仓: {portfolio_returns_df['num_stocks'].min()}")
            print(f"  最大持仓: {portfolio_returns_df['num_stocks'].max()}")
            print(f"  持仓不足100的次数: {(portfolio_returns_df['num_stocks'] < 100).sum()}")
            
            print(f"\n换手率统计:")
            print(f"  平均换手率: {portfolio_returns_df['turnover'].mean()*100:.2f}%")
            print(f"  最小换手率: {portfolio_returns_df['turnover'].min()*100:.2f}%")
            print(f"  最大换手率: {portfolio_returns_df['turnover'].max()*100:.2f}%")
        
        return portfolio_returns_df, optimal_vector_df
    
    def get_param_suffix(self):
        """生成参数后缀，用于区分不同参数组合的输出文件"""
        suffix = f'l{self.long_prd}_s{self.short_prd}_b{self.channel_bins}_e{self.extreme_value}_n{self.top_n}'
        if self.turnover_control:
            if self.max_turnover is not None:
                turnover_pct = int(round(float(self.max_turnover) * 100))
                suffix += f'_tc{turnover_pct}'
            else:
                suffix += '_tcbuf'
            buffer_label = f'{self.turnover_buffer_multiplier:g}'.replace('.', 'p')
            suffix += f'_buf{buffer_label}'
        return suffix
    
    def generate_trade_report(self, output_dir, file_suffix=None):
        """
        生成交易记录报告（文件名包含参数信息）
        
        参数:
            output_dir: 输出目录
            file_suffix: 自定义文件名后缀（如不提供则使用参数后缀）
        """
        print("\n生成交易记录报告...")
        
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)
        
        # 生成Excel文件（文件名包含参数）
        suffix = file_suffix if file_suffix else self.get_param_suffix()
        output_path = f'{output_dir}/交易记录_{suffix}.xlsx'
        self.trade_recorder.generate_excel_report(output_path)
    
    def plot_strategy_performance(self, portfolio_returns_df, output_dir, stats=None,
                                  annual_returns=None, monthly_win_rate=None,
                                  file_suffix=None, strategy_title=None,
                                  benchmark_data=None):
        """
        绘制策略表现（含统计指标叠加、基准对比、超额收益和回撤）
        
        参数:
            portfolio_returns_df: 策略收益数据
            output_dir: 输出目录
            stats: 基本统计指标字典
            annual_returns: 年度收益率DataFrame
            monthly_win_rate: 月度胜率DataFrame
            file_suffix: 自定义文件名后缀
            strategy_title: 自定义策略标题
            benchmark_data: 基准数据 DataFrame (index=date, columns=[csi500_nav, csi1000_nav, excess_csi500, excess_csi1000])
        """
        print("\n绘制策略表现...")
        
        df = portfolio_returns_df.copy()
        df['date'] = pd.to_datetime(df['date'])
        df['cumulative_return'] = (1 + df['return']).cumprod()
        
        # 计算回撤
        running_max = df['cumulative_return'].expanding().max()
        df['drawdown'] = (df['cumulative_return'] - running_max) / running_max
        
        # 确定后缀和标题
        suffix = file_suffix if file_suffix else self.get_param_suffix()
        title = strategy_title if strategy_title else f'风格因子择时策略 (L={self.long_prd}, S={self.short_prd}, E={self.extreme_value}, N={self.top_n})'
        
        has_benchmark = benchmark_data is not None and len(benchmark_data) > 0
        
        # 根据是否有基准数据调整布局
        if has_benchmark:
            # 8行: 累计收益+基准, 超额收益, 回撤, 周度收益, 年度收益, 持仓, 换手率
            fig = plt.figure(figsize=(16, 32))
            gs = fig.add_gridspec(8, 1, height_ratios=[1.2, 0.8, 0.6, 0.5, 0.6, 0.5, 0.5, 0.5], hspace=0.4)
        else:
            # 6行: 累计收益, 回撤, 周度收益, 年度收益, 持仓, 换手率
            fig = plt.figure(figsize=(16, 26))
            gs = fig.add_gridspec(6, 1, height_ratios=[1.2, 0.6, 0.7, 0.6, 0.5, 0.5], hspace=0.4)
        
        ax_idx = 0
        
        # ===== 1. 累计收益曲线 + 基准 =====
        ax1 = fig.add_subplot(gs[ax_idx]); ax_idx += 1
        ax1.plot(df['date'], df['cumulative_return'], 
                linewidth=2, color='#2E86AB', label='策略累计收益')
        
        if has_benchmark:
            bench_aligned = benchmark_data.reindex(df['date'], method='nearest')
            if 'csi500_nav' in bench_aligned.columns:
                ax1.plot(df['date'], bench_aligned['csi500_nav'], 
                        linewidth=1.5, color='#FF9800', alpha=0.8, linestyle='--', label='中证500')
            if 'csi1000_nav' in bench_aligned.columns:
                ax1.plot(df['date'], bench_aligned['csi1000_nav'], 
                        linewidth=1.5, color='#4CAF50', alpha=0.8, linestyle='--', label='中证1000')
        
        ax1.axhline(y=1, color='gray', linestyle='--', alpha=0.5)
        
        if stats:
            stats_text = (
                f"累计收益率: {stats['累计收益率']}    "
                f"年化收益率: {stats['年化收益率']}    "
                f"夏普比率: {stats['夏普比率']}    "
                f"最大回撤: {stats['最大回撤']}    "
                f"胜率: {stats['胜率']}    "
                f"盈亏比: {stats['盈亏比']}\n"
                f"交易次数: {stats['交易次数']}    "
                f"平均持仓: {stats['平均持仓数量']}    "
                f"平均换手率: {stats['平均换手率']}    "
                f"年化波动率: {stats['年化波动率']}"
            )
            ax1.set_title(f'{title}\n{stats_text}',
                         fontsize=11, fontweight='bold', loc='left')
        else:
            ax1.set_title(f'{title} - 累计收益', fontsize=14, fontweight='bold')
        
        ax1.set_ylabel('累计净值', fontsize=11)
        ax1.legend(loc='upper left', fontsize=10)
        ax1.grid(True, alpha=0.3)
        formatter = ScalarFormatter()
        formatter.set_scientific(False)
        ax1.yaxis.set_major_formatter(formatter)
        
        # ===== 2. 超额累计收益 (仅在有基准时) =====
        if has_benchmark:
            ax2 = fig.add_subplot(gs[ax_idx]); ax_idx += 1
            bench_aligned = benchmark_data.reindex(df['date'], method='nearest')
            has_excess = False
            if 'excess_csi500' in bench_aligned.columns:
                ax2.plot(df['date'], bench_aligned['excess_csi500'] * 100, 
                        linewidth=1.5, color='#FF9800', label='超额(中证500)')
                has_excess = True
            if 'excess_csi1000' in bench_aligned.columns:
                ax2.plot(df['date'], bench_aligned['excess_csi1000'] * 100, 
                        linewidth=1.5, color='#4CAF50', label='超额(中证1000)')
                has_excess = True
            if has_excess:
                ax2.axhline(y=0, color='black', linewidth=0.8)
                ax2.set_title('累计超额收益 (策略 - 基准)', fontsize=13, fontweight='bold')
                ax2.set_ylabel('超额收益 (%)', fontsize=11)
                ax2.legend(loc='upper left', fontsize=10)
                ax2.grid(True, alpha=0.3)
                # 标注最终超额收益
                if 'excess_csi1000' in bench_aligned.columns:
                    final_excess = bench_aligned['excess_csi1000'].iloc[-1] * 100
                    ax2.text(0.98, 0.95, f'超额(中证1000): {final_excess:.1f}%', 
                            transform=ax2.transAxes, ha='right', va='top', fontsize=10,
                            bbox=dict(boxstyle='round', facecolor='#4CAF50', alpha=0.3))
                if 'excess_csi500' in bench_aligned.columns:
                    final_excess = bench_aligned['excess_csi500'].iloc[-1] * 100
                    ax2.text(0.98, 0.82, f'超额(中证500): {final_excess:.1f}%', 
                            transform=ax2.transAxes, ha='right', va='top', fontsize=10,
                            bbox=dict(boxstyle='round', facecolor='#FF9800', alpha=0.3))
        
        # ===== 3. 回撤 =====
        ax_dd = fig.add_subplot(gs[ax_idx]); ax_idx += 1
        ax_dd.fill_between(df['date'], df['drawdown'] * 100, 0, 
                          color='#F44336', alpha=0.4)
        ax_dd.plot(df['date'], df['drawdown'] * 100, 
                  linewidth=1, color='#F44336')
        ax_dd.set_title('回撤', fontsize=13, fontweight='bold')
        ax_dd.set_ylabel('回撤 (%)', fontsize=11)
        ax_dd.grid(True, alpha=0.3)
        # 标注最大回撤
        min_dd_idx = df['drawdown'].idxmin()
        min_dd_val = df['drawdown'].min() * 100
        ax_dd.annotate(f'{min_dd_val:.1f}%', 
                       xy=(df.loc[min_dd_idx, 'date'], min_dd_val),
                       xytext=(10, 10), textcoords='offset points',
                       fontsize=9, color='red', fontweight='bold')
        
        # ===== 4. 周度收益率 =====
        ax_wr = fig.add_subplot(gs[ax_idx]); ax_idx += 1
        ax_wr.bar(df['date'], df['return'] * 100, 
               color=np.where(df['return'] >= 0, '#4CAF50', '#F44336'),
               alpha=0.7, width=5)
        ax_wr.axhline(y=0, color='black', linewidth=0.8)
        ax_wr.set_title('周度收益率', fontsize=13, fontweight='bold')
        ax_wr.set_ylabel('收益率 (%)', fontsize=11)
        ax_wr.grid(True, alpha=0.3, axis='y')
        
        # ===== 5. 年度收益率柱状图 =====
        ax_ar = fig.add_subplot(gs[ax_idx]); ax_idx += 1
        if annual_returns is not None and len(annual_returns) > 0:
            years = annual_returns['年份'].astype(str).tolist()
            ret_values = [float(r.replace('%', '')) for r in annual_returns['年度收益率']]
            colors = ['#4CAF50' if v >= 0 else '#F44336' for v in ret_values]
            bars = ax_ar.bar(years, ret_values, color=colors, alpha=0.8, width=0.6)
            for bar, val in zip(bars, ret_values):
                ax_ar.text(bar.get_x() + bar.get_width()/2., 
                        bar.get_height() + (0.5 if val >= 0 else -1.5),
                        f'{val:.1f}%', ha='center', va='bottom' if val >= 0 else 'top',
                        fontsize=9, fontweight='bold')
            ax_ar.axhline(y=0, color='black', linewidth=0.8)
        ax_ar.set_title('年度收益率', fontsize=13, fontweight='bold')
        ax_ar.set_ylabel('收益率 (%)', fontsize=11)
        ax_ar.grid(True, alpha=0.3, axis='y')
        
        # ===== 6. 持仓股票数量 =====
        ax_h = fig.add_subplot(gs[ax_idx]); ax_idx += 1
        ax_h.plot(df['date'], df['num_stocks'], 
                linewidth=2, color='#FF9800', marker='o', markersize=3)
        ax_h.axhline(y=self.top_n, color='red', linestyle='--', alpha=0.5, label=f'目标数量: {self.top_n}')
        ax_h.set_title('持仓股票数量', fontsize=13, fontweight='bold')
        ax_h.set_ylabel('股票数量', fontsize=11)
        ax_h.legend(loc='best', fontsize=10)
        ax_h.grid(True, alpha=0.3)
        
        # ===== 7. 换手率 =====
        ax_to = fig.add_subplot(gs[ax_idx]); ax_idx += 1
        ax_to.plot(df['date'], df['turnover'] * 100, 
                linewidth=2, color='#9C27B0', marker='o', markersize=3)
        ax_to.set_title('换手率', fontsize=13, fontweight='bold')
        ax_to.set_ylabel('换手率 (%)', fontsize=11)
        ax_to.grid(True, alpha=0.3)
        
        # 保存图表
        fig_dir = os.path.join(output_dir, 'images', 'backtest')
        os.makedirs(fig_dir, exist_ok=True)
        fig_path = os.path.join(fig_dir, f'factor_timing_{suffix}.png')
        plt.savefig(fig_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"策略表现图表已保存: {fig_path}")
        
        # 额外保存年度收益率和月度胜率到CSV
        data_dir = os.path.join(output_dir, 'data')
        os.makedirs(data_dir, exist_ok=True)
        
        if annual_returns is not None and len(annual_returns) > 0:
            annual_path = f'{data_dir}/annual_returns_{suffix}.csv'
            annual_returns.to_csv(annual_path, index=False, encoding='utf-8-sig')
            print(f"年度收益率已保存: {annual_path}")
        
        if monthly_win_rate is not None and len(monthly_win_rate) > 0:
            monthly_path = f'{data_dir}/monthly_win_rate_{suffix}.csv'
            monthly_win_rate.to_csv(monthly_path, index=False, encoding='utf-8-sig')
            print(f"月度胜率已保存: {monthly_path}")
    
    def calculate_statistics(self, portfolio_returns_df):
        """
        计算策略统计指标（含详细分解）
        
        参数:
            portfolio_returns_df: 策略收益数据
            
        返回:
            stats: 基本统计指标字典
            annual_returns: 年度收益率DataFrame
            monthly_win_rate: 月度胜率DataFrame
        """
        print("\n计算策略统计指标...")
        
        df = portfolio_returns_df.copy()
        df['date'] = pd.to_datetime(df['date'])
        df['cumulative_return'] = (1 + df['return']).cumprod()
        
        # ============ 基本统计指标 ============
        cumulative_return = (1 + df['return']).prod() - 1
        
        days = (df['date'].max() - df['date'].min()).days
        years = days / 365.25
        annual_return = (1 + cumulative_return) ** (1 / years) - 1 if years > 0 else 0
        
        weekly_vol = df['return'].std()
        annual_vol = weekly_vol * np.sqrt(52)
        
        risk_free_rate = 0.03
        sharpe_ratio = (annual_return - risk_free_rate) / annual_vol if annual_vol != 0 else 0
        
        running_max = df['cumulative_return'].expanding().max()
        drawdown = (df['cumulative_return'] - running_max) / running_max
        max_drawdown = drawdown.min()
        
        win_rate = (df['return'] > 0).sum() / len(df) * 100
        
        avg_win = df[df['return'] > 0]['return'].mean()
        avg_loss = abs(df[df['return'] < 0]['return'].mean())
        profit_loss_ratio = avg_win / avg_loss if avg_loss != 0 else 0
        
        avg_turnover = df['turnover'].mean() * 100
        
        stats = {
            '累计收益率': f'{cumulative_return * 100:.2f}%',
            '年化收益率': f'{annual_return * 100:.2f}%',
            '年化波动率': f'{annual_vol * 100:.2f}%',
            '夏普比率': f'{sharpe_ratio:.2f}',
            '最大回撤': f'{max_drawdown * 100:.2f}%',
            '胜率': f'{win_rate:.2f}%',
            '盈亏比': f'{profit_loss_ratio:.2f}',
            '交易次数': len(df),
            '平均持仓数量': f'{df["num_stocks"].mean():.0f}',
            '平均换手率': f'{avg_turnover:.2f}%'
        }
        
        # ============ 年度收益率 ============
        df['year'] = df['date'].dt.year
        annual_returns_list = []
        for year, grp in df.groupby('year'):
            ann_ret = (1 + grp['return']).prod() - 1
            ann_vol = grp['return'].std() * np.sqrt(52) if len(grp) > 1 else 0
            ann_sharpe = (ann_ret - risk_free_rate / 52 * len(grp)) / ann_vol if ann_vol != 0 else 0
            ann_win = (grp['return'] > 0).sum() / len(grp) * 100
            ann_mdd = ((1 + grp['return']).cumprod().expanding().max() - (1 + grp['return']).cumprod()) / (1 + grp['return']).cumprod().expanding().max()
            ann_max_dd = ann_mdd.max() * 100 if len(ann_mdd) > 0 else 0
            annual_returns_list.append({
                '年份': year,
                '交易次数': len(grp),
                '年度收益率': f'{ann_ret * 100:.2f}%',
                '年化波动率': f'{ann_vol * 100:.2f}%',
                '夏普比率': f'{ann_sharpe:.2f}',
                '胜率': f'{ann_win:.2f}%',
                '最大回撤': f'{ann_max_dd:.2f}%'
            })
        annual_returns = pd.DataFrame(annual_returns_list)
        
        # ============ 月度胜率 ============
        df['month'] = df['date'].dt.to_period('M')
        monthly_stats_list = []
        for month, grp in df.groupby('month'):
            m_ret = (1 + grp['return']).prod() - 1
            m_win = (grp['return'] > 0).sum() / len(grp) * 100
            monthly_stats_list.append({
                '月份': str(month),
                '交易次数': len(grp),
                '月度收益率': f'{m_ret * 100:.2f}%',
                '月度胜率': f'{m_win:.2f}%'
            })
        monthly_win_rate = pd.DataFrame(monthly_stats_list)
        
        print(f"  年度数: {len(annual_returns)}, 月度数: {len(monthly_win_rate)}")
        
        return stats, annual_returns, monthly_win_rate
