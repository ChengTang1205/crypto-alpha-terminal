import requests
import pandas as pd
from datetime import datetime
import time

class DepegMonitor:
    def __init__(self):
        # 使用 DefiLlama Price API (无限制，最稳定)
        self.api_url = "https://coins.llama.fi/prices/current"
        
        self.warning_threshold = 0.3   
        self.critical_threshold = 1.0  
        
        # 映射表
        self.targets = {
            'USDT':  {'id': 'coingecko:tether',            'peg': 1.0},
            'USDC':  {'id': 'coingecko:usd-coin',          'peg': 1.0},
            'DAI':   {'id': 'coingecko:dai',               'peg': 1.0},
            'USDe':  {'id': 'coingecko:ethena-usde',       'peg': 1.0},
            'FDUSD': {'id': 'coingecko:first-digital-usd', 'peg': 1.0},
            'PYUSD': {'id': 'coingecko:paypal-usd',        'peg': 1.0},
            'FRAX':  {'id': 'coingecko:frax',              'peg': 1.0},
            'USDD':  {'id': 'coingecko:usdd',              'peg': 1.0},
            'TUSD':  {'id': 'coingecko:true-usd',          'peg': 1.0},
            'crvUSD':{'id': 'coingecko:crvusd',            'peg': 1.0},
        }

    def get_market_data(self):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在获取稳定币价格 (Source: DefiLlama)...")
        
        query_ids = ",".join([info['id'] for info in self.targets.values()])
        url = f"{self.api_url}/{query_ids}"
        
        try:
            # searchWidth=4h 确保数据连贯性
            response = requests.get(url, params={'searchWidth': '4h'}, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get('coins', {})
        except Exception as e:
            print(f"❌ 获取价格失败: {e}")
            return {}

    def analyze_pegs(self):
        coins_data = self.get_market_data()
        if not coins_data: return pd.DataFrame()

        results = []
        
        for symbol, info in self.targets.items():
            query_id = info['id']
            
            if query_id not in coins_data:
                continue
                
            item = coins_data[query_id]
            current_price = item.get('price', 0)
            target_peg = info['peg']

            # 计算偏差
            diff = current_price - target_peg
            deviation_pct = (abs(diff) / target_peg) * 100
            
            # 状态判定
            status = "✅ Stable"
            risk_val = 0
            
            if deviation_pct >= self.critical_threshold:
                if diff < 0:
                    status = "🚨 CRITICAL DIP"
                    risk_val = 3
                else:
                    status = "📈 HIGH PREMIUM"
                    risk_val = 1
            elif deviation_pct >= self.warning_threshold:
                if diff < 0:
                    status = "⚠️ Discount"
                    risk_val = 2
                else:
                    status = "🔵 Premium"
                    risk_val = 0
            
            results.append({
                'Asset': symbol,
                'Price': current_price,
                'Peg Target': target_peg,
                'Dev %': deviation_pct,
                'Diff': diff,
                '24h Chg': 0.0, # DefiLlama 无此数据，置 0 占位
                'Status': status,
                # 🔥 关键修复：键名改回 'risk_score' 以匹配 app.py
                'risk_score': risk_val 
            })

        return pd.DataFrame(results)

if __name__ == "__main__":
    monitor = DepegMonitor()
    df = monitor.analyze_pegs()
    if not df.empty:
        print(df.to_string())
    else:
        print("⚠️ 未获取到数据")