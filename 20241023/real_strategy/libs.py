import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import vectorbt as vbt
import ccxt
import asyncio

class StrategyFrame():
    df = pd.DataFrame()
    orders = pd.DataFrame()

    def __init__(self, data: pd.DataFrame):
        self.df = data

    def resample_data(self, rule='15min'):
        data = self.df
        res_data = data.set_index('datetime')
        res_df = pd.DataFrame()
        res_df['open'] = res_data['open'].resample(rule).first()
        res_df['high'] = res_data['high'].resample(rule).max()
        res_df['low'] = res_data['low'].resample(rule).min()
        res_df['close'] = res_data['close'].resample(rule).last()
        res_df['volume'] = res_data['volume'].resample(rule).sum()
        res_df['amount'] = res_data['amount'].resample(rule).sum()
        res_df['buy_amount'] = res_data['buy_amount'].resample(rule).sum()
        res_df['amount'] = res_data['amount'].resample(rule).sum()
        self.df = res_df
        return self

    def signal_ma(self, N1=5, N2=20):
        entry_list = {}
        exit_list = {}
        res_df = pd.DataFrame()
        res_df['o'] = self.df['open']
        res_df['h'] = self.df['high']
        res_df['l'] = self.df['low']
        res_df['c'] = self.df['close']
        res_df['v'] = self.df['volume']
        res_df['date'] = self.df.index
        res_df['ma_s'] = res_df['c'].rolling(N1, min_periods=1).mean()
        res_df['ma_l'] = res_df['c'].rolling(N2, min_periods=1).mean()
        last_ma_s = 0
        last_ma_l = 0
        # 默认等交易数据N2天以后再交易
        for i, (index, row) in enumerate(res_df.iterrows()):
            entry_list[index] = False
            exit_list[index] = False
            if i == N1:
                last_ma_s = row['ma_s']
            if i == N2:
                last_ma_l = row['ma_l']
            if i > N2:
                if (row['ma_s'] >= row['ma_l']) and (last_ma_s < last_ma_l):
                    entry_list[index] = True
                if (row['ma_s'] <= row['ma_l']) and (last_ma_s > last_ma_l):
                    exit_list[index] = True
                last_ma_s = row['ma_s']
                last_ma_l = row['ma_l']
        #
        res_df['entry'] = entry_list.values()
        res_df['exit'] = exit_list.values()
        self.df = res_df
        return self

    def backtest(self ,init_cash=100 ,fees=0.001):
        pf = vbt.Portfolio.from_signals(
            self.df['c'],
            entries=self.df['entry'],
            exits=self.df['exit'],
            price=self.df['c'],
            init_cash=init_cash,
            fees=fees
        )
        return pf

