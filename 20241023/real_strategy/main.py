import pandas as pd
import libs
import warnings

warnings.filterwarnings('ignore')

def backtest():
    data = pd.read_csv('../../20241020/BTCUSDT.csv', parse_dates=['datetime'])
    SF = libs.StrategyFrame(data).resample_data('3h').signal_ma(6,26)
    pf = SF.backtest()
    print(pf.stats())

backtest()