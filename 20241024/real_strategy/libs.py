import time
import pandas as pd
import vectorbt as vbt
import ccxt

import config

pd.set_option('display.max_columns', None)
pd.set_option('display.width', 2000)


class StrategyFrame():
    df = pd.DataFrame()
    orders = pd.DataFrame()
    exchange = ccxt.binance({
        'apiKey': config.api_key,
        'secret': config.api_secret,
        'timeout': 30000,
        'options': {'defaultType': 'spot'},
        'proxies': {
            'http': 'http://127.0.0.1:7890',
            'https': 'http://127.0.0.1:7890',
        },
    })
    # 当前balance只需要btc和usdt这2个值，可根据实际需求调整
    btc_balance = 0
    usdt_balance = 0

    # 初始化
    def __init__(self, data: pd.DataFrame):
        self.df = data
        self.exchange_balances()

    # 数据按时间聚合
    def resample_data(self, rule='15min'):
        res_df = self.df.resample(rule).last()
        res_df['t'] = self.df['t'].resample(rule).last()
        res_df['o'] = self.df['o'].resample(rule).first()
        res_df['h'] = self.df['h'].resample(rule).max()
        res_df['l'] = self.df['l'].resample(rule).min()
        res_df['c'] = self.df['c'].resample(rule).last()
        res_df['v'] = self.df['v'].resample(rule).sum()
        self.df = res_df
        return self

    # 获取最近的数据，要求在1000分钟之内
    def get_last_diff_data(self, symbol='BTC/USDT'):
        since = self.df['t'].tail(1).values[0]
        print(f'since: {since}', pd.to_datetime(since, unit='ms', origin='1970-01-01 08:00:00'))
        res_df = pd.DataFrame(self.exchange.fetch_ohlcv(symbol, timeframe='1m', since=since))
        res_df.columns = ['t', 'o', 'h', 'l', 'c', 'v']
        res_df['datetime'] = pd.to_datetime(res_df['t'], unit='ms', origin='1970-01-01 08:00:00')
        res_df.set_index('datetime', inplace=True)
        res_df = pd.concat([self.df[:-1], res_df])
        if self.check_data(res_df):
            res_df.to_csv('./BTCUSDT.csv')
            self.df = res_df
        else:
            print('check data error,no update')
        return self

    # 获取最近几K条数据更新数据并存入csv
    def get_last_data(self, count=1, symbol='BTC/USDT'):
        df = pd.DataFrame(self.exchange.fetch_ohlcv(symbol, timeframe='1m', limit=1000))
        for i in range(count - 1):
            since = df[0][0] - 1000 * 60 * 1000
            res_df = pd.DataFrame(self.exchange.fetch_ohlcv(symbol, timeframe='1m', since=since, limit=1000))
            df = pd.concat([res_df, df], ignore_index=True)
            time.sleep(0.2)
        df.columns = ['t', 'o', 'h', 'l', 'c', 'v']
        df['datetime'] = pd.to_datetime(df['t'], unit='ms', origin='1970-01-01 08:00:00')
        df.set_index('datetime', inplace=True)
        #
        if self.check_data(df):
            df.to_csv('./BTCUSDT.csv')
            self.df = df
        else:
            print('check data error,no update')
        return self

    # 检查数据完整性 True完整 False不完整
    @staticmethod
    def check_data(data: pd.DataFrame):
        duplicated_ok = data[data.index.duplicated()].empty
        diff = data['t'].diff()[1:]
        diff_ok = len(diff[diff == diff.iloc[0]]) == len(diff)
        if not duplicated_ok:
            print('数据有重复')
        if not diff_ok:
            print('数据不连续')
        return duplicated_ok and diff_ok

    # 生成交易信号, 交易信号的返回内容有 index date o h l c v entry exit
    # 假设模拟最简单的低买高卖， 低于等于低价 即买入，高于高价即卖出
    def signal(self, min_price, max_price):
        entry_list = {}
        exit_list = {}
        res_df = pd.DataFrame()
        res_df['t'] = self.df['t']
        res_df['o'] = self.df['o']
        res_df['h'] = self.df['h']
        res_df['l'] = self.df['l']
        res_df['c'] = self.df['c']
        res_df['v'] = self.df['v']
        res_df['date'] = self.df.index
        for i, (index, row) in enumerate(res_df.iterrows()):
            entry_list[index] = False
            exit_list[index] = False
            # 入场
            if row['c'] <= min_price:
                entry_list[index] = True
            if row['c'] >= max_price:
                exit_list[index] = True
        #
        res_df['entry'] = entry_list.values()
        res_df['exit'] = exit_list.values()
        self.df = res_df
        return self

    def signal_ma(self, N1=5, N2=20):
        entry_list = {}
        exit_list = {}
        res_df = pd.DataFrame()
        res_df['t'] = self.df['t']
        res_df['o'] = self.df['o']
        res_df['h'] = self.df['h']
        res_df['l'] = self.df['l']
        res_df['c'] = self.df['c']
        res_df['v'] = self.df['v']

        res_df['date'] = self.df.index
        res_df['ma_s'] = res_df['c'].rolling(N1, min_periods=1).mean()
        res_df['ma_l'] = res_df['c'].rolling(N2, min_periods=1).mean()
        last_ma_s = 0
        last_ma_l = 0
        # 默认等交易数据N2根bar以后再交易
        for i, (index, row) in enumerate(res_df.iterrows()):
            entry_list[index] = False
            exit_list[index] = False
            # 入场
            if i == N1:
                last_ma_s = row['ma_s']
            if i == N2:
                last_ma_l = row['ma_l']
            if i > N2:
                if (row['ma_s'] >= row['ma_l']) and (last_ma_s < last_ma_l):
                    limit_price = res_df.loc[res_df.index[i - 1], 'c']
                    if row['c'] < limit_price:
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

    # vectorbt快速回测
    def backtest(self, init_cash=100, fees=0.001):
        pf = vbt.Portfolio.from_signals(
            self.df['c'],
            entries=self.df['entry'],
            exits=self.df['exit'],
            price=self.df['c'],
            init_cash=init_cash,
            fees=fees
        )
        return pf

    ## exchange.fetch_balance() 返回值,获取账户余额，每个交易所可能有不同
    # {
    #   'info':
    #       {
    #           'makerCommission': '10',
    #           'takerCommission': '10',
    #           'buyerCommission': '0',
    #           'sellerCommission': '0',
    #           'commissionRates': {'maker': '0.00100000', 'taker': '0.00100000', 'buyer': '0.00000000', 'seller': '0.00000000'},
    #           'canTrade': True,
    #           'canWithdraw': True,
    #           'canDeposit': True,
    #           'brokered': False,
    #           'requireSelfTradePrevention': False,
    #           'preventSor': False,
    #           'updateTime': '1729528789467',
    #           'accountType': 'SPOT',
    #           'balances': [{'asset': 'BTC', 'free': '0.00000835', 'locked': '0.00000000'},]
    #       }
    # }
    ## 获取币对可用余额
    def exchange_balances(self):
        balance_list = self.exchange.fetch_balance()['info']['balances']
        for v in balance_list:
            if v['asset'] == 'BTC':
                self.btc_balance = float(v['free'])
            if v['asset'] == 'USDT':
                self.usdt_balance = float(v['free'])

    ##{'symbol': 'BTC/USDT', 'bids': [[67204.58, 0.42166],'asks': [[67204.58, 0.42166],],}
    ## bids 按价格降序排列。最佳（最高）买价是第一个元素，最差（最低）买价是最后一个元素
    ## asks 按价格升序排列。最佳（最低）卖价是第一个元素，最差（最高）卖价是最后一个元素
    ##最新订单成交价
    def exchange_order_price(self, symbol='BTC/USDT'):
        orderbook = self.exchange.fetch_order_book(symbol)
        return orderbook['asks'][0][0]

    ##市价单 买入amount单位 使用最新价格买
    def exchange_market_buy_order(self, amount: float, symbol='BTC/USDT'):
        try:
            res = self.exchange.create_market_buy_order(symbol, amount)
            print(res)
        except Exception as e:
            print(e)

    ##市价单 卖出amount单位 使用最新价格卖
    def exchange_market_sell_order(self, amount: float, symbol='BTC/USDT'):
        try:
            res = self.exchange.create_market_sell_order(symbol, amount)
            print(res)
        except Exception as e:
            print(e)

    ##限价单 需要按照价格和下单时间来排单  买
    def exchange_limit_buy_order(self, amount: float, order_price, symbol='BTC/USDT'):
        try:
            res = self.exchange.create_limit_buy_order(symbol, amount, order_price)
            print(res)
        except Exception as e:
            print(e)

    ##限价单 卖
    def exchange_limit_sell_order(self, amount: float, order_price, symbol='BTC/USDT'):
        try:
            res = self.exchange.create_limit_sell_order(symbol, amount, order_price)
            print(res)
        except Exception as e:
            print(e)

    ## 设置止损订单止损 binance不支持,一般策略可以根据价格触发市价单即可
    ## 正常来说，市价单 和 限价单 满足我们的绝大部分需求

    ## 撤销订单
    def exchange_cancel_orders(self, order_ids: list[str],symbol='BTC/USDT'):
        try:
            res = self.exchange.cancel_orders(order_ids, symbol)
            print(res)
        except Exception as e:
            print(e)

    ## 获取订单列表
    ## [{'info':[
    # {'symbol': 'BTCUSDT', 'orderId': '31174686371', 'orderListId': '-1', 'clientOrderId': 'x-MGFCMH4Us40525057101', 'price': '60800.00000000', 'origQty': '0.00032000', 'executedQty': '0.00000000', 'cummulativeQuoteQty': '0.00000000', 'status': 'CANCELED', 'timeInForce': 'GTC', 'type': 'LIMIT', 'side': 'BUY', 'stopPrice': '0.00000000', 'icebergQty': '0.00000000', 'time': '1728540525216', 'updateTime': '1728540811029', 'isWorking': True, 'workingTime': '1728540525216', 'origQuoteOrderQty': '0.00000000', 'selfTradePreventionMode': 'EXPIRE_MAKER'}
    # ]}]
    ## 默认屏蔽了已取消的订单
    def exchange_get_orders(self, symbol='BTC/USDT'):
        try:
            res = self.exchange.fetch_orders(symbol)
            res_orders = []
            for order in res:
                if order['info']['status'] != 'CANCELED':
                    res_orders.append(order['info'])
            return pd.DataFrame(res_orders)
        except Exception as e:
            print(e)
    ##


SF = StrategyFrame(pd.DataFrame())
print(f'btc:{SF.btc_balance:8f}, usdt:{SF.usdt_balance}')
last_price = SF.exchange_order_price()
print(last_price)
# # SF.exchange_limit_sell_order(1,last_price)
order_df = SF.exchange_get_orders('BTC/USDT')
print(order_df)
