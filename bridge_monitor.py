import requests
import pandas as pd
from datetime import datetime
import time
import os

class BridgeFlowMonitor:
    def __init__(self):
        self.api_url = "https://bridges.llama.fi/bridges?includeChains=true"
        self.min_volume_threshold = 0  # 保持 0 以确保显示所有数据

    def get_bridge_data(self):
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在从 DefiLlama 获取跨链桥数据...")
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/json'
            }
            response = requests.get(self.api_url, headers=headers, timeout=20)
            response.raise_for_status()
            data = response.json()
            
            # 处理返回结构
            if 'bridges' in data: return data['bridges']
            if 'data' in data and 'bridges' in data['data']: return data['data']['bridges']
            return []
        except Exception as e:
            print(f"❌ API 请求失败: {e}")
            return []

    def analyze_bridges(self):
        bridges = self.get_bridge_data()
        if not bridges: return pd.DataFrame()

        print(f"   -> API 返回了 {len(bridges)} 个桥的数据。开始处理...")
        results = []

        for b in bridges:
            name = b.get('displayName', 'Unknown')
            
            # --- 核心修复：使用新的字段名 ---
            # 1. 获取 24h 交易量
            # 优先用 lastDailyVolume，如果没有则尝试 last24hVolume
            vol_24h = b.get('lastDailyVolume')
            if vol_24h is None:
                vol_24h = b.get('last24hVolume', 0)
            
            # 2. 获取前一天的交易量 (用于计算变化)
            vol_prev = b.get('dayBeforeLastVolume', 0)
            if vol_prev is None: vol_prev = 0
            
            # 3. 获取其他周期数据
            vol_7d = b.get('weeklyVolume', 0)
            vol_30d = b.get('monthlyVolume', 0)

            # 计算变化率
            vol_change_pct = 0
            if vol_prev > 0:
                vol_change_pct = ((vol_24h - vol_prev) / vol_prev) * 100

            chains = b.get('chains', [])
            chains_str = ", ".join(chains[:3]) 

            results.append({
                'Bridge': name,
                'Chains': chains_str,
                'Volume (24h)': vol_24h,
                'Vol Change (24h)': vol_change_pct,
                'Volume (7d)': vol_7d,
                'Volume (30d)': vol_30d
            })

        return pd.DataFrame(results)

def format_currency(x):
    if x is None or x == 0 or pd.isna(x): return "-"
    if x >= 1_000_000_000: return f"${x/1_000_000_000:.2f}B"
    if x >= 1_000_000: return f"${x/1_000_000:.2f}M"
    if x >= 1_000: return f"${x/1_000:.0f}k"
    return f"${x:.0f}"

def format_pct(x):
    if pd.isna(x): return "-"
    color = "🔴" if x < 0 else "🟢"
    # 如果变化率超过 1000%，显示为爆量
    if x > 1000: return "🔥 SURGE"
    return f"{color} {x:+.1f}%"

def get_trend_label(row):
    # 简单的趋势判断
    vol = row['Volume (24h)']
    change = row['Vol Change (24h)']
    
    if vol > 10_000_000 and change > 50: return "🚀 Hot Flow"
    if vol > 50_000_000: return "🐋 High Vol"
    if change < -50: return "❄️ Cooling"
    return "Stable"

if __name__ == "__main__":
    monitor = BridgeFlowMonitor()
    df = monitor.analyze_bridges()

    if not df.empty:
        # 1. 按照 24小时交易量 排序
        df = df.sort_values('Volume (24h)', ascending=False).reset_index(drop=True)
        
        # 2. 保存
        filename = f"bridge_flows_v3_{datetime.now().strftime('%Y%m%d')}.csv"
        df.to_csv(filename, index=False)
        print(f"✅ 数据已保存: {filename}")

        # 3. 打印前 20 名
        print("\n" + "="*110)
        print(f"🌉 跨链桥资金流向监控 (Top 20 by Volume)")
        print("   [注意] API 已不再返回 TVL 数据，重点关注 Volume (流量)")
        print("="*110)
        
        top_df = df.head(20).copy()
        top_df['Trend'] = top_df.apply(get_trend_label, axis=1)
        
        # 格式化
        cols_to_fmt = ['Volume (24h)', 'Volume (7d)', 'Volume (30d)']
        for col in cols_to_fmt:
            top_df[col] = top_df[col].apply(format_currency)
            
        top_df['Vol Change (24h)'] = top_df['Vol Change (24h)'].apply(format_pct)

        # 调整显示顺序
        display_cols = ['Bridge', 'Trend', 'Volume (24h)', 'Vol Change (24h)', 'Volume (7d)', 'Chains']
        
        print(top_df[display_cols].to_string(index=False, col_space=12))
        print("="*110)
    else:
        print("\n⚠️ 依然没有数据。")