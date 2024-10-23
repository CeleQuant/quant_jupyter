import ccxt
import pandas as pd
apiKey = ''
secretKey = ''
#
exchange = ccxt.binance({
    'apiKey': apiKey,
    'secret': secretKey,
    'timeout': 30000,
    'options': {'defaultType': 'spot'},
    'proxies': {
        'http': 'http://127.0.0.1:7890',
        'https': 'http://127.0.0.1:7890',
    },
})

#exchange.load_markets()



