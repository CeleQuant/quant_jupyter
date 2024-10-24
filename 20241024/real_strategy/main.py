import time

import pandas as pd
import libs
import warnings

pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)
warnings.filterwarnings('ignore')


def backtest():
    data = pd.read_csv('BTCUSDT.csv', parse_dates=['datetime'])
    data.set_index('datetime', inplace=True)
    SF = libs.StrategyFrame(data).resample_data('3h').signal(60000, 66000)
    print(SF.df)
    pf = SF.backtest()
    print(pf.stats())


def loop_real():
    data = pd.read_csv('BTCUSDT.csv', parse_dates=['datetime'])
    data.set_index('datetime', inplace=True)
    SF = libs.StrategyFrame(data)
    # SF = libs.StrategyFrame(pd.DataFrame()).get_last_data(100)
    while True:
        SF = SF.get_last_diff_data().signal(60000, 66000)
        print(SF.df.tail())
        pf = SF.backtest(init_cash=100, fees=0.001)
        orders = pf.orders.records_readable
        print(orders.tail())
        side = orders.tail(1).Side.values[0]
        size_num = orders.tail(1).Size.values[0]
        price = orders.tail(1).Price.values[0]
        print(side, price,size_num)
        # 执行交易逻辑
        # 一个固定cash的帐户，例如100USDT
        # 当USDT>=0 并且 side = Buy时 全买入
        # 当 side = Sell 且 BTC>0.00001 时 卖出
        SF.exchange_balances()
        if SF.usdt_balance > 0 and side == 'Buy':
            SF.exchange_limit_buy_order(float(size_num),price)
        elif SF.btc_balance > 0.0001 and side == 'Sell':
            SF.exchange_limit_sell_order(float(size_num), price)
        else:
            print(f'last signal:{side},usdt {SF.usdt_balance},btc {SF.btc_balance:6f},can not trade')
        time.sleep(61)


loop_real()
