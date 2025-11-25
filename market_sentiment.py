import requests
import pandas as pd
from datetime import datetime
import time

class MarketSentimentMonitor:
    def __init__(self):
        self.fng_url = "https://api.alternative.me/fng/?limit=1"
        self.binance_fapi = "https://fapi.binance.com"
        self.bybit_api = "https://api.bybit.com"
        
        self.targets = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'DOGEUSDT', 'BNBUSDT']

        # ⚡️ 代理配置 (仅用于 Binance)
        # 你的端口是 7890 (Clash)
        # self.proxies = {
        #     'http': 'http://127.0.0.1:7890', 
        #     'https': 'http://127.0.0.1:7890'
        # }
        self.proxies = None

    def get_fear_and_greed(self):
        try:
            response = requests.get(self.fng_url, timeout=10)
            data = response.json()
            if data['data']:
                item = data['data'][0]
                return {
                    'value': int(item['value']),
                    'status': item['value_classification'],
                    'update_time': datetime.fromtimestamp(int(item['timestamp']))
                }
        except: return None

    # --- 1. 获取 Binance 数据 (走代理) ---
    def get_binance_data(self):
        data_map = {}
        try:
            # A. 资金费率
            r = requests.get(f"{self.binance_fapi}/fapi/v1/premiumIndex", proxies=self.proxies, timeout=10)
            all_premium = r.json()
            premium_map = {item['symbol']: item for item in all_premium}

            # B. 多空比
            for symbol in self.targets:
                item = premium_map.get(symbol)
                if not item: continue
                
                price = float(item['markPrice'])
                funding = float(item['lastFundingRate']) * 100 # 转百分比
                
                ls_ratio = 0
                try:
                    url = f"{self.binance_fapi}/futures/data/globalLongShortAccountRatio"
                    params = {'symbol': symbol, 'period': '4h', 'limit': 1}
                    res = requests.get(url, params=params, proxies=self.proxies, timeout=5)
                    if res.status_code == 200:
                        ls_data = res.json()
                        if ls_data: ls_ratio = float(ls_data[0]['longShortRatio'])
                except: pass

                data_map[symbol] = {
                    'Price': price,
                    'Binance_Funding': funding,
                    'Binance_LS': ls_ratio
                }
        except Exception as e:
            print(f"❌ Binance 获取失败: {e}")
        return data_map

    # --- 2. 获取 Bybit 数据 (直连/不强制代理) ---
    def get_bybit_data(self):
        data_map = {}
        headers = {'User-Agent': 'Mozilla/5.0'}
        try:
            for symbol in self.targets:
                # A. 费率
                url_ticker = f"{self.bybit_api}/v5/market/tickers"
                try:
                    r = requests.get(url_ticker, params={'category':'linear','symbol':symbol}, headers=headers, timeout=5).json()
                    funding = 0
                    if r['retCode'] == 0 and r['result']['list']:
                        funding = float(r['result']['list'][0].get('fundingRate', 0)) * 100
                except: funding = 0

                # B. 多空比
                ls_ratio = 0
                url_ratio = f"{self.bybit_api}/v5/market/account-ratio"
                try:
                    r = requests.get(url_ratio, params={'category':'linear','symbol':symbol,'period':'4h','limit':1}, headers=headers, timeout=5).json()
                    if r['retCode'] == 0 and r['result']['list']:
                        item = r['result']['list'][0]
                        buy = float(item.get('buyRatio', 0))
                        sell = float(item.get('sellRatio', 1))
                        if sell > 0: ls_ratio = round(buy/sell, 2)
                except: pass

                data_map[symbol] = {
                    'Bybit_Funding': funding,
                    'Bybit_LS': ls_ratio
                }
        except Exception as e:
            print(f"❌ Bybit 获取失败: {e}")
        return data_map

    # --- 3. 合并数据 ---
    def get_all_data(self):
        print("1. 正在抓取 Binance 数据...")
        binance_data = self.get_binance_data()
        print("2. 正在抓取 Bybit 数据...")
        bybit_data = self.get_bybit_data()
        
        combined_results = []
        for symbol in self.targets:
            b_data = binance_data.get(symbol, {})
            y_data = bybit_data.get(symbol, {})
            
            # 如果两边都没拿到，就跳过
            if not b_data and not y_data: continue

            # 优先用 Binance 价格，没有则用 0
            price = b_data.get('Price', 0)
            
            row = {
                'Symbol': symbol.replace('USDT', ''),
                'Price': price,
                # Binance
                'Binance Funding': b_data.get('Binance_Funding', 0),
                'Binance LS': b_data.get('Binance_LS', 0),
                # Bybit
                'Bybit Funding': y_data.get('Bybit_Funding', 0),
                'Bybit LS': y_data.get('Bybit_LS', 0),
            }
            # 清洗微小负数
            if abs(row['Binance Funding']) < 0.0001: row['Binance Funding'] = 0.0
            if abs(row['Bybit Funding']) < 0.0001: row['Bybit Funding'] = 0.0
            
            combined_results.append(row)
            
        return pd.DataFrame(combined_results)

if __name__ == "__main__":
    monitor = MarketSentimentMonitor()
    df = monitor.get_all_data()
    print(df.to_string())