import asyncio
import time
import pandas as pd
import vectorbt as vbt
import ccxt
import ccxt.pro as ccxtpro
import sys
sys.path.append("..")
import config.fdusd_config as config

pd.set_option('display.max_columns', None)
pd.set_option('display.width', 2000)


class StrategyFrame():
    df = pd.DataFrame()
    order_df = pd.DataFrame()
    # 当前balance只需要FDUSD和usdt这2个值，可根据实际需求调整
    fdusd_balance = 0
    usdt_balance = 0
    is_first_buy = True
    exchange = ccxt.binance({
        'apiKey': config.api_key,
        'secret': config.secret,
        'timeout': 30000,
        'options': {'defaultType': 'spot'},
        'proxies': {
            'http': 'http://127.0.0.1:7890',
            'https': 'http://127.0.0.1:7890',
        },
    })
    exchange_pro = ccxtpro.binance({
        'apiKey': config.api_key,
        'secret': config.secret,
        'timeout': 30000,
        'options': {'defaultType': 'spot'},
        'proxies': {
            'http': 'http://127.0.0.1:7890',
            'https': 'http://127.0.0.1:7890',
        },
    })
    # 初始化
    def __init__(self, data: pd.DataFrame):
        self.df = data
        self.exchange_balances()

    # 获取最近几K条数据更新数据并存入csv
    def get_last_data(self, count=1, symbol='FDUSD/USDT'):
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
            df.to_csv('./data.csv')
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


    ## 使用网格策略
    # 假设grid有10个区间,具体操作如下
    # 1 第一次头寸，分析当前价格是否小于中线，小于直接买入50%
    # 2 价格基于每下降一格，继续买入10%
    # 3 价格每上升一格，卖出10%
    # 4 若卖出100%，结束交易退出策略
    def signal(self, mid_price: float, grid_height: float):
        df = self.df
        entrys, exits, positions,prices = {}, {}, {},{}
        res_df = pd.DataFrame()
        res_df[['t', 'o', 'h', 'l', 'c', 'v']] = df[['t', 'o', 'h', 'l', 'c', 'v']]
        res_df['date'] = df.index
        last_position = 0
        # is_first_buy = false
        last_grid_price = 0
        for i, (index, row) in enumerate(res_df.iterrows()):
            entrys[index], exits[index] = False, False
            positions[index] = last_position
            prices[index] = row['c']
            # 第一次买入，直接买50%仓位
            # if is_first_buy and row['c'] < mid_price:
            #     # 判断所属档位
            #     n = (mid_price - row['c']) // grid_height
            #     is_first_buy = False
            #     entrys[index] = True
            #     positions[index] = 0.5
            #     last_position = positions[index]
            #     last_grid_price = mid_price - grid_height * n
            # 非第一次买，当价格下降n格时买入0.1*n个仓位,上升n格卖出0.1*n个仓位
            if i ==0:
                entrys[index] = True
                positions[index] = 0.5
                prices[index] = 0.9998
                last_position = positions[index]
                last_grid_price = 0.9998
            if i>0:
                # n = abs(row['c'] - last_grid_price)//grid_height
                # 买
                if row['c'] <= last_grid_price - grid_height and last_position <= 0.9:
                    entrys[index] = True
                    positions[index] = last_position + 0.1
                    last_grid_price = last_grid_price - grid_height
                # 卖
                if row['c'] >= last_grid_price + grid_height and last_position >= 0.1:
                    exits[index] = True
                    positions[index] = last_position - 0.1
                    last_grid_price = last_grid_price + grid_height
                # 仓位归零,退出交易
                if last_position == 0:
                    break
                ###
                last_position = positions[index]

        res_df['pos'] = positions.values()
        res_df['entry'] = entrys.values()
        res_df['exit'] = exits.values()
        self.df = res_df
        return self

    # vectorbt快速回测
    def backtest(self, init_cash=100, fees=0.0):
        pf = vbt.Portfolio.from_signals(
            self.df['c'],
            entries=self.df['entry'],
            exits=self.df['exit'],
            price=self.df['c'],
            size=self.df['pos'].apply(lambda x: x*100),
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
    #           'balances': [{'asset': 'FDUSD', 'free': '0.00000835', 'locked': '0.00000000'},]
    #       }
    # }
    ## 获取币对可用余额
    def exchange_balances(self):
        balance_list = self.exchange.fetch_balance()['info']['balances']
        for v in balance_list:
            if v['asset'] == 'FDUSD':
                self.fdusd_balance = float(v['free'])
            if v['asset'] == 'USDT':
                self.usdt_balance = float(v['free'])

    ##{'symbol': 'FDUSD/USDT', 'bids': [[67204.58, 0.42166],'asks': [[67204.58, 0.42166],],}
    ## bids 按价格降序排列。最佳（最高）买价是第一个元素，最差（最低）买价是最后一个元素
    ## asks 按价格升序排列。最佳（最低）卖价是第一个元素，最差（最高）卖价是最后一个元素
    ##最新订单成交价
    def exchange_order_price(self, symbol='FDUSD/USDT'):
        orderbook = self.exchange.fetch_order_book(symbol)
        return orderbook['asks'][0][0]

    ##市价单 买入amount单位 使用最新价格买
    def exchange_market_buy_order(self, amount: float, symbol='FDUSD/USDT'):
        try:
            res = self.exchange.create_market_buy_order(symbol, amount)
            print(res)
        except Exception as e:
            print(e)

    ##市价单 卖出amount单位 使用最新价格卖
    def exchange_market_sell_order(self, amount: float, symbol='FDUSD/USDT'):
        try:
            res = self.exchange.create_market_sell_order(symbol, amount)
            print(res)
        except Exception as e:
            print(e)

    ##限价单 需要按照价格和下单时间来排单  买
    def exchange_limit_buy_order(self, amount: float, order_price, symbol='FDUSD/USDT'):
        try:
            res = self.exchange.create_limit_buy_order(symbol, amount, order_price)
            print(res)
        except Exception as e:
            print(e)

    ##限价单 卖
    def exchange_limit_sell_order(self, amount: float, order_price, symbol='FDUSD/USDT'):
        try:
            res = self.exchange.create_limit_sell_order(symbol, amount, order_price)
            print(res)
        except Exception as e:
            print(e)

    ## 设置止损订单止损 binance不支持,一般策略可以根据价格触发市价单即可
    ## 正常来说，市价单 和 限价单 满足我们的绝大部分需求

    ## 撤销订单
    def exchange_cancel_orders(self, order_ids: list[str],symbol='FDUSD/USDT'):
        try:
            res = self.exchange.cancel_orders(order_ids, symbol)
            print(res)
        except Exception as e:
            print(e)

    ## 获取订单列表
    ## [{'info':[
    # {'symbol': 'FDUSDUSDT', 'orderId': '31174686371', 'orderListId': '-1', 'clientOrderId': 'x-MGFCMH4Us40525057101', 'price': '60800.00000000', 'origQty': '0.00032000', 'executedQty': '0.00000000', 'cummulativeQuoteQty': '0.00000000', 'status': 'CANCELED', 'timeInForce': 'GTC', 'type': 'LIMIT', 'side': 'BUY', 'stopPrice': '0.00000000', 'icebergQty': '0.00000000', 'time': '1728540525216', 'updateTime': '1728540811029', 'isWorking': True, 'workingTime': '1728540525216', 'origQuoteOrderQty': '0.00000000', 'selfTradePreventionMode': 'EXPIRE_MAKER'}
    # ]}]
    ## 默认屏蔽了已取消的订单
    def exchange_get_orders(self, symbol='FDUSD/USDT'):
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

async def loop():
    SF = StrategyFrame(pd.DataFrame())
    print(f'usdt:{SF.usdt_balance}, fdusd:{SF.fdusd_balance}')
    exchange_pro = SF.exchange_pro
    symbol = 'FDUSD/USDT'
    timeframe = '1m'
    last_deal_t = 0
    count_num = 0
    while True:
        ohlcv = await exchange_pro.watch_ohlcv(symbol, timeframe)
        t = ohlcv[0][0]
        # print(t)
        df = pd.DataFrame(ohlcv)
        df.columns = ['t', 'o', 'h', 'l', 'c', 'v']
        df['datetime'] = pd.to_datetime(df['t'], unit='ms', origin='1970-01-01 08:00:00')
        df.set_index('datetime', inplace=True)
        res_df = pd.concat([SF.df, df])
        res_df.drop_duplicates(subset=['t'], inplace=True, keep='last')
        SF.df = res_df
        if last_deal_t<t:
            time_s = pd.to_datetime(t/1000, unit='s', origin='1970-01-01 08:00:00')
            print(t/1000,time_s)
            # print(SF.df)
            SF = SF.signal(0.9998,0.0002)
            pf = SF.backtest(init_cash=100, fees=0.0)
            orders = pf.orders.records_readable
            # print(orders.tail(5))
            last_order = orders.tail(1).values[0]
            order_t =  pd.to_datetime(last_order[2]).value/ 10**9 - 3600*8
            order_price = last_order[4]
            order_side = last_order[6]
            if order_t==t/1000:
                if count_num > 0:
                    SF.exchange_balances()
                    print(f'usdt:{SF.usdt_balance}, fdusd:{SF.fdusd_balance}')
                    print(orders.tail(3))
                    # trade_price = ohlcv[0][4]
                    trade_price = float(order_price)
                    trade_num = 10.0
                    print(order_t,time_s, order_side,trade_num,trade_price)

                    if order_side == 'Buy':
                        try:
                            res = await exchange_pro.create_limit_buy_order_ws('FDUSD/USDT',amount=trade_num,price=trade_price)
                            print(res)
                        except Exception as e:
                            print(e)
                    if order_side == 'Sell':
                        try:
                            res = await exchange_pro.create_limit_sell_order_ws('FDUSD/USDT',amount=trade_num,price=trade_price)
                            print(res)
                        except Exception as e:
                            print(e)
                count_num += 1
            last_deal_t = t
        else:
            last_deal_t = t
    await exchange.close()



asyncio.run(loop())


asyncio.run(loop())