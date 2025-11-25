import requests
import pandas as pd
from datetime import datetime
import os

class MarketSentimentMonitor:
    def __init__(self):
        self.fng_url = "https://api.alternative.me/fng/?limit=1"
        self.binance_fapi = "https://fapi.binance.com"
        self.bybit_api = "https://api.bybit.com"
        self.coingecko_api = "https://api.coingecko.com/api/v3"
        
        self.targets = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'DOGEUSDT', 'BNBUSDT']
        
        # CoinGecko 的 ID 映射
        self.cg_mapping = {
            'BTCUSDT': 'bitcoin',
            'ETHUSDT': 'ethereum',
            'SOLUSDT': 'solana',
            'DOGEUSDT': 'dogecoin',
            'BNBUSDT': 'binancecoin'
        }

        # 部署上线时设为 None
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

    # --- 1. 获取 Binance 数据 ---
    def get_binance_data(self):
        data_map = {}
        try:
            r = requests.get(f"{self.binance_fapi}/fapi/v1/premiumIndex", proxies=self.proxies, timeout=5)
            if r.status_code != 200: return {} # 被墙了直接返回
            all_premium = r.json()
            premium_map = {item['symbol']: item for item in all_premium}

            for symbol in self.targets:
                item = premium_map.get(symbol)
                if not item: continue
                
                price = float(item['markPrice'])
                funding = float(item['lastFundingRate']) * 100
                ls_ratio = 0
                try:
                    url = f"{self.binance_fapi}/futures/data/globalLongShortAccountRatio"
                    params = {'symbol': symbol, 'period': '4h', 'limit': 1}
                    res = requests.get(url, params=params, proxies=self.proxies, timeout=3)
                    if res.status_code == 200:
                        ls_data = res.json()
                        if ls_data: ls_ratio = float(ls_data[0]['longShortRatio'])
                except: pass

                data_map[symbol] = {'Price': price, 'Binance_Funding': funding, 'Binance_LS': ls_ratio}
        except: pass
        return data_map

    # --- 2. 获取 Bybit 数据 ---
    def get_bybit_data(self):
        data_map = {}
        headers = {'User-Agent': 'Mozilla/5.0'}
        try:
            # 简单测试连接，如果连 tickers 都拿不到，说明也被墙了
            url_ticker = f"{self.bybit_api}/v5/market/tickers"
            test = requests.get(url_ticker, params={'category':'linear','symbol':'BTCUSDT'}, headers=headers, timeout=5)
            if test.status_code != 200: return {} 

            for symbol in self.targets:
                # A. 费率 & 价格
                funding = 0
                try:
                    r = requests.get(url_ticker, params={'category':'linear','symbol':symbol}, headers=headers, timeout=3).json()
                    if r['retCode'] == 0 and r['result']['list']:
                        funding = float(r['result']['list'][0].get('fundingRate', 0)) * 100
                except: pass

                # B. 多空比
                ls_ratio = 0
                url_ratio = f"{self.bybit_api}/v5/market/account-ratio"
                try:
                    r = requests.get(url_ratio, params={'category':'linear','symbol':symbol,'period':'4h','limit':1}, headers=headers, timeout=3).json()
                    if r['retCode'] == 0 and r['result']['list']:
                        item = r['result']['list'][0]
                        buy = float(item.get('buyRatio', 0))
                        sell = float(item.get('sellRatio', 1))
                        if sell > 0: ls_ratio = round(buy/sell, 2)
                except: pass

                data_map[symbol] = {'Bybit_Funding': funding, 'Bybit_LS': ls_ratio}
        except: pass
        return data_map

    # --- 3. [新] CoinGecko 兜底数据 ---
    def get_fallback_data(self):
        print("⚠️ 触发熔断：切换至 CoinGecko 基础数据源")
        ids = ",".join(self.cg_mapping.values())
        url = f"{self.coingecko_api}/simple/price"
        params = {
            'ids': ids,
            'vs_currencies': 'usd',
            'include_24hr_change': 'true'
        }
        data_map = {}
        try:
            r = requests.get(url, params=params, timeout=10)
            data = r.json()
            for symbol, cg_id in self.cg_mapping.items():
                if cg_id in data:
                    item = data[cg_id]
                    # 用 "涨跌幅" 伪装成 "费率" 列显示，但会标记清楚
                    data_map[symbol] = {
                        'Price': item.get('usd', 0),
                        'Binance_Funding': 0, # 无法获取
                        'Binance_LS': 0,
                        'Bybit_Funding': 0,
                        'Bybit_LS': 0,
                        '24h_Change': item.get('usd_24h_change', 0) # 新增字段
                    }
        except: pass
        return data_map

    # --- 4. 主逻辑 ---
    def get_all_data(self):
        # 尝试获取 CEX 数据
        binance_data = self.get_binance_data()
        bybit_data = self.get_bybit_data()
        
        # 判断是否被墙：如果两家数据都是空的，或者获取不到任何有效内容
        is_blocked = (not binance_data) and (not bybit_data)
        
        if is_blocked:
            # 启动兜底方案
            fallback_map = self.get_fallback_data()
            combined_results = []
            for symbol in self.targets:
                item = fallback_map.get(symbol, {})
                combined_results.append({
                    'Symbol': symbol.replace('USDT', ''),
                    'Price': item.get('Price', 0),
                    'Binance Funding': 0,
                    'Binance LS': 0,
                    'Bybit Funding': 0,
                    'Bybit LS': 0,
                    'Note': f"24h涨跌: {item.get('24h_Change', 0):.2f}%" # 备注
                })
            return pd.DataFrame(combined_results), True # True 代表是降级模式
            
        # 如果没被墙，正常合并
        combined_results = []
        for symbol in self.targets:
            b_data = binance_data.get(symbol, {})
            y_data = bybit_data.get(symbol, {})
            
            price = b_data.get('Price', 0) or y_data.get('Price', 0) # 优先用有价格的
            
            row = {
                'Symbol': symbol.replace('USDT', ''),
                'Price': price,
                'Binance Funding': b_data.get('Binance_Funding', 0),
                'Binance LS': b_data.get('Binance_LS', 0),
                'Bybit Funding': y_data.get('Bybit_Funding', 0),
                'Bybit LS': y_data.get('Bybit_LS', 0),
                'Note': "Live Data"
            }
            # 清洗
            if abs(row['Binance Funding']) < 0.0001: row['Binance Funding'] = 0.0
            if abs(row['Bybit Funding']) < 0.0001: row['Bybit Funding'] = 0.0
            
            combined_results.append(row)
            
        return pd.DataFrame(combined_results), False # False 代表是正常模式

if __name__ == "__main__":
    monitor = MarketSentimentMonitor()
    df, is_fallback = monitor.get_all_data()
    print(f"模式: {'降级模式' if is_fallback else '实时合约模式'}")
    print(df.to_string())