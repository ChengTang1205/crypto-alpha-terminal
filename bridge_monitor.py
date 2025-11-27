import requests
import pandas as pd
from datetime import datetime
import time

class BridgeFlowMonitor:
    def __init__(self):
        self.api_url = "https://bridges.llama.fi/bridges?includeChains=true"

    def get_bridge_data(self):
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在获取跨链桥数据...")
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(self.api_url, headers=headers, timeout=20)
            response.raise_for_status()
            data = response.json()
            
            if 'bridges' in data: return data['bridges']
            if 'data' in data and 'bridges' in data['data']: return data['data']['bridges']
            return []
        except Exception as e:
            print(f"❌ API 请求失败: {e}")
            return []

    def analyze_bridges(self):
        bridges = self.get_bridge_data()
        if not bridges: return pd.DataFrame()

        results = []

        for b in bridges:
            name = b.get('displayName', 'Unknown')
            
            # 1. 获取交易量
            vol_24h = b.get('lastDailyVolume')
            if vol_24h is None:
                vol_24h = b.get('last24hVolume', 0)
            
            # 异常值过滤：如果单个桥日交易量 > 100亿美金，肯定是数据错误
            if vol_24h > 10_000_000_000: continue

            vol_prev = b.get('dayBeforeLastVolume', 0)
            if vol_prev is None: vol_prev = 0
            
            vol_7d = b.get('weeklyVolume', 0)
            
            # 2. 计算变化率 (优化版)
            vol_change_pct = 0
            
            # 仅当昨日交易量 > $50,000 时才计算百分比
            # 避免 "从 $100 变成 $10,000,000" 这种无意义的百万倍增长
            if vol_prev > 50000:
                vol_change_pct = ((vol_24h - vol_prev) / vol_prev) * 100
            elif vol_prev <= 50000 and vol_24h > 1000000:
                # 如果是新启动的桥 (昨日没量，今日爆发)，给一个固定的高分
                vol_change_pct = 999.0 
            
            # 数值封顶：为了图表好看，最大只显示 +2000%
            # 原始数据可以保留在 tooltip，但用于排序和画图的列我们要处理一下
            display_change_pct = min(vol_change_pct, 2000.0)

            chains = b.get('chains', [])
            if chains:
                short_chains = [c.replace('Ethereum', 'Eth').replace('Arbitrum', 'Arb').replace('Optimism', 'Op') for c in chains]
                if len(short_chains) > 3:
                    chains_str = f"{', '.join(short_chains[:3])} (+{len(short_chains)-3})"
                else:
                    chains_str = ", ".join(short_chains)
            else:
                chains_str = "-"

            results.append({
                'Bridge': name,
                'Chains': chains_str,
                'Volume (24h)': vol_24h,
                # 我们存入处理过的百分比，避免 UI 爆炸
                'Vol Change (24h)': display_change_pct, 
                'Volume (7d)': vol_7d,
                'Trend': self.get_trend_label(vol_24h, display_change_pct)
            })

        return pd.DataFrame(results)

    def get_trend_label(self, vol, change):
        if vol > 50_000_000: return "🐋 Whale Mov"
        if vol > 10_000_000 and change > 30: return "🚀 Hot Flow"
        if 1_000_000 < vol <= 10_000_000 and change > 100: return "👀 New Trend?" 
        if change < -50: return "❄️ Cooling"
        return "Stable"

if __name__ == "__main__":
    monitor = BridgeFlowMonitor()
    df = monitor.analyze_bridges()
    if not df.empty:
        print(df.sort_values('Volume (24h)', ascending=False).head(5).to_string())