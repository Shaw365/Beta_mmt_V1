"""
交易记录模块
用于记录每次换仓的交易详情，并生成Excel文件
"""

import pandas as pd
import numpy as np
from datetime import datetime
import os


class TradeRecorder:
    """交易记录器"""
    
    def __init__(self, initial_capital=100000000, stock_capital=1000000):
        """
        参数:
            initial_capital: 初始资金（默认1亿）
            stock_capital: 单只股票市值（默认100万）
        """
        self.initial_capital = initial_capital
        self.stock_capital = stock_capital
        self.trades = []
        self.holdings = {}  # 当前持仓
        
    def record_trade(self, trade_date, stock_code, trade_direction, trade_price, trade_quantity, trade_amount):
        """
        记录单笔交易
        
        参数:
            trade_date: 交易日期
            stock_code: 股票代码
            trade_direction: 交易方向（'买入' 或 '卖出'）
            trade_price: 成交价格
            trade_quantity: 交易数量（股数）
            trade_amount: 交易金额
        """
        self.trades.append({
            '交易日期': trade_date,
            '股票代码': stock_code,
            '交易方向': trade_direction,
            '成交价格': round(trade_price, 2),
            '交易数量': int(trade_quantity),
            '交易金额': round(trade_amount, 2)
        })
    
    def process_rebalance(self, trade_date, selected_codes, price_df):
        """
        处理换仓
        
        参数:
            trade_date: 换仓日期
            selected_codes: 选中的股票代码列表
            price_df: 价格数据（包含date, code, open, high, low, close）
        """
        # 获取当天的价格数据
        trade_date_price = price_df[price_df['date'] == trade_date].copy()
        
        if len(trade_date_price) == 0:
            print(f"警告: {trade_date} 没有价格数据，跳过交易记录")
            return
        
        # 计算当天均价（如果有的话，否则使用收盘价）
        if 'vwap' in trade_date_price.columns:
            # 使用成交量加权平均价格
            trade_date_price['avg_price'] = trade_date_price['vwap']
        elif all(col in trade_date_price.columns for col in ['open', 'high', 'low', 'close']):
            # 使用OHLC平均价
            trade_date_price['avg_price'] = (trade_date_price['open'] + 
                                              trade_date_price['high'] + 
                                              trade_date_price['low'] + 
                                              trade_date_price['close']) / 4
        else:
            # 使用收盘价
            trade_date_price['avg_price'] = trade_date_price['close']
        
        # 计算需要卖出的股票（不在新持仓中的股票）
        stocks_to_sell = set(self.holdings.keys()) - set(selected_codes)
        
        # 记录卖出交易
        for stock_code in stocks_to_sell:
            stock_price_data = trade_date_price[trade_date_price['code'] == stock_code]
            
            if len(stock_price_data) == 0:
                # 如果当天没有价格数据，使用前一天的收盘价
                prev_date_data = price_df[price_df['date'] < trade_date].copy()
                prev_date_data = prev_date_data[prev_date_data['code'] == stock_code]
                if len(prev_date_data) > 0:
                    prev_date_data = prev_date_data.sort_values('date')
                    trade_price = prev_date_data.iloc[-1]['close']
                else:
                    print(f"警告: {trade_date} 无法找到股票 {stock_code} 的价格，跳过")
                    continue
            else:
                trade_price = stock_price_data.iloc[0]['avg_price']
            
            # 卖出数量
            trade_quantity = self.holdings[stock_code]
            trade_amount = trade_quantity * trade_price
            
            # 记录卖出
            self.record_trade(trade_date, stock_code, '卖出', trade_price, trade_quantity, trade_amount)
            
            # 从持仓中移除
            del self.holdings[stock_code]
        
        # 计算需要买入的股票（不在旧持仓中的股票）
        stocks_to_buy = set(selected_codes) - set(self.holdings.keys())
        
        # 记录买入交易
        for stock_code in stocks_to_buy:
            stock_price_data = trade_date_price[trade_date_price['code'] == stock_code]
            
            if len(stock_price_data) == 0:
                print(f"警告: {trade_date} 无法找到股票 {stock_code} 的价格，跳过买入")
                continue
            
            trade_price = stock_price_data.iloc[0]['avg_price']
            
            # 计算买入数量（按100万市值）
            trade_quantity = int(self.stock_capital / trade_price)
            trade_amount = trade_quantity * trade_price
            
            # 记录买入
            self.record_trade(trade_date, stock_code, '买入', trade_price, trade_quantity, trade_amount)
            
            # 添加到持仓
            self.holdings[stock_code] = trade_quantity
    
    def generate_excel_report(self, output_path):
        """
        生成交易记录Excel文件
        
        参数:
            output_path: 输出文件路径
        """
        if len(self.trades) == 0:
            print("警告: 没有交易记录")
            return
        
        # 转换为DataFrame
        trades_df = pd.DataFrame(self.trades)
        
        # 按日期排序
        trades_df = trades_df.sort_values(['交易日期', '交易方向', '股票代码'])
        
        # 添加序号
        trades_df.insert(0, '序号', range(1, len(trades_df) + 1))
        
        # 创建Excel写入器
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # 写入交易记录
            trades_df.to_excel(writer, sheet_name='交易记录', index=False)
            
            # 统计信息
            summary_data = {
                '指标': [
                    '总交易次数',
                    '买入次数',
                    '卖出次数',
                    '总交易金额',
                    '平均单笔交易金额',
                    '初始资金',
                    '单只股票市值'
                ],
                '数值': [
                    len(trades_df),
                    len(trades_df[trades_df['交易方向'] == '买入']),
                    len(trades_df[trades_df['交易方向'] == '卖出']),
                    f"{trades_df['交易金额'].sum():,.2f}",
                    f"{trades_df['交易金额'].mean():,.2f}",
                    f"{self.initial_capital:,.2f}",
                    f"{self.stock_capital:,.2f}"
                ]
            }
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='统计信息', index=False)
            
            # 按日期统计
            daily_stats = trades_df.groupby('交易日期').agg({
                '交易金额': 'sum',
                '股票代码': 'count'
            }).reset_index()
            daily_stats.columns = ['交易日期', '交易金额', '交易股票数']
            daily_stats.to_excel(writer, sheet_name='每日交易统计', index=False)
        
        print(f"\n交易记录已保存: {output_path}")
        print(f"总交易次数: {len(trades_df)}")
        print(f"买入次数: {len(trades_df[trades_df['交易方向'] == '买入'])}")
        print(f"卖出次数: {len(trades_df[trades_df['交易方向'] == '卖出'])}")
        print(f"总交易金额: {trades_df['交易金额'].sum():,.2f} 元")
    
    def get_trade_summary(self):
        """
        获取交易摘要
        
        返回:
            交易摘要DataFrame
        """
        if len(self.trades) == 0:
            return pd.DataFrame()
        
        trades_df = pd.DataFrame(self.trades)
        
        summary = {
            '总交易次数': len(trades_df),
            '买入次数': len(trades_df[trades_df['交易方向'] == '买入']),
            '卖出次数': len(trades_df[trades_df['交易方向'] == '卖出']),
            '总交易金额': trades_df['交易金额'].sum(),
            '平均单笔交易金额': trades_df['交易金额'].mean()
        }
        
        return pd.DataFrame([summary])
