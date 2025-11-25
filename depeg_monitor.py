import requests
import pandas as pd
from datetime import datetime
import time
import os

class DepegMonitor:
    def __init__(self):
        # 使用 CoinGecko API
        self.api_url = "https://api.coingecko.com/api/v3/simple/price"
        
        # --- 🔴 核心修复点: 阈值单位修正 ---
        # 现在的单位直接是百分比 (%)
        # 0.3 代表 0.3% (即 $0.997)
        # 1.0 代表 1.0% (即 $0.990)
        self.warning_threshold = 0.3   
        self.critical_threshold = 1.0  
        
        self.targets = {
            'tether':       {'symbol': 'USDT',  'peg': 1.0},
            'usd-coin':     {'symbol': 'USDC',  'peg': 1.0},
            'dai':          {'symbol': 'DAI',   'peg': 1.0},
            'ethena-usde':  {'symbol': 'USDe',  'peg': 1.0},
            'first-digital-usd': {'symbol': 'FDUSD', 'peg': 1.0},
            'paypal-usd':   {'symbol': 'PYUSD', 'peg': 1.0},
            'frax':         {'symbol': 'FRAX',  'peg': 1.0},
            'usdd':         {'symbol': 'USDD',  'peg': 1.0},
            'true-usd':     {'symbol': 'TUSD',  'peg': 1.0},
        }
        
        self.stablecoin_ids = [k for k, v in self.targets.items() if v['peg'] is not None]

    def get_market_data(self):
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在扫描全网稳定币价格 (Source: CoinGecko)...")
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/json'
            }
            params = {
                'ids': ",".join(self.stablecoin_ids),
                'vs_currencies': 'usd',
                'include_24hr_change': 'true',
                'precision': '4'
            }
            response = requests.get(self.api_url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"❌ 获取价格失败: {e}")
            return None

    def analyze_pegs(self):
        data = self.get_market_data()
        if not data: return pd.DataFrame()

        results = []
        
        for coin_id, info in self.targets.items():
            if coin_id not in data: continue
            
            market_data = data[coin_id]
            current_price = market_data.get('usd', 0)
            change_24h = market_data.get('usd_24h_change', 0)
            target_peg = info['peg']
            symbol = info['symbol']

            # 计算偏差
            deviation_abs = abs(current_price - target_peg)
            # 这里计算出来已经是百分比数值，例如 0.05
            deviation_pct = (deviation_abs / target_peg) * 100
            
            # 状态判定逻辑
            status = "✅ Stable"
            risk_level = 0
            
            if deviation_pct >= self.critical_threshold:
                status = "🚨 DEPEG CRITICAL"
                risk_level = 2
            elif deviation_pct >= self.warning_threshold:
                status = "⚠️ Warning"
                risk_level = 1
            
            results.append({
                'Asset': symbol,
                'Price': current_price,
                'Peg Target': target_peg,
                'Deviation %': deviation_pct,
                '24h Change %': change_24h,
                'Status': status,
                'risk_score': risk_level
            })

        return pd.DataFrame(results)

def format_price(x): return f"${x:.4f}"
def format_deviation(x): return f"{x:.3f}%"
def color_status(val):
    if "CRITICAL" in val: return f"🔴 {val}"
    if "Warning" in val: return f"🟡 {val}"
    return val

if __name__ == "__main__":
    monitor = DepegMonitor()
    df = monitor.analyze_pegs()

    if not df.empty:
        df = df.sort_values(by=['risk_score', 'Deviation %'], ascending=[False, False])
        
        filename = f"depeg_alert_fixed_{datetime.now().strftime('%Y%m%d')}.csv"
        df.drop(columns=['risk_score']).to_csv(filename, index=False)
        print(f"✅ 监控日志已保存: {filename}")

        print("\n" + "="*90)
        print("🚨 稳定币脱钩监控 (Depeg Alert System) [Fixed Version]")
        print(f"   [阈值说明] 🟡 警告: >{monitor.warning_threshold}% | 🔴 严重: >{monitor.critical_threshold}%")
        print("="*90)

        display_df = df.copy()
        display_df['Price'] = display_df['Price'].apply(format_price)
        display_df['Deviation %'] = display_df['Deviation %'].apply(format_deviation)
        display_df['24h Change %'] = display_df['24h Change %'].apply(lambda x: f"{x:+.2f}%")
        display_df['Status'] = display_df['Status'].apply(color_status)

        cols = ['Asset', 'Price', 'Peg Target', 'Deviation %', 'Status', '24h Change %']
        print(display_df[cols].to_string(index=False, col_space=12))
        
        # 警报摘要
        warnings = df[df['risk_score'] >= 1]
        if not warnings.empty:
            print("\n" + "!"*90)
            print(f"⚠️ 注意: 检测到 {len(warnings)} 个资产存在脱钩风险 (Warning/Critical)")
            print("!"*90)
    else:
        print("⚠️ 未获取到数据。")