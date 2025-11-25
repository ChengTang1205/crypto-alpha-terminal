import requests
import pandas as pd
from datetime import datetime, timedelta
import time
import os

class StablecoinSupplyMonitor:
    def __init__(self):
        self.base_url = "https://stablecoins.llama.fi"
        
        # 目标稳定币 ID
        self.targets = {
            'USDT': '1',
            'USDC': '2',
            'DAI': '5',
            'USDe': '162',   # Ethena
            'FDUSD': '127',  # First Digital USD
            'PYUSD': '136',  # PayPal USD
            'FRAX': '6'      # 顺便加上 FRAX，凑个整
        }

    def get_historical_supply(self, asset_id):
        """混合策略获取数据：优先尝试多链聚合，失败则尝试全局字段"""
        url = f"{self.base_url}/stablecoin/{asset_id}"
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            df_chain = pd.DataFrame()
            
            # --- 策略 A: 尝试聚合多链数据 (Chain Balances) ---
            # 适用于 USDT, USDC, DAI 这种在多条链发行的资产
            if isinstance(data.get('chainBalances'), dict):
                daily_totals = {}
                chains = data['chainBalances']
                
                for chain_name, chain_data in chains.items():
                    if not isinstance(chain_data, dict):
                        continue
                    # 修复点 1: 增加 `or []` 防止 tokens 为 None 导致崩溃
                    tokens_history = chain_data.get('tokens') or []
                    
                    if not isinstance(tokens_history, list): continue

                    for entry in tokens_history:
                        date_ts = entry.get('date')
                        circ = entry.get('circulating', {})
                        # 兼容直接数字或字典结构
                        amount = circ.get('peggedUSD', 0) if isinstance(circ, dict) else (circ if isinstance(circ, (int, float)) else 0)
                        
                        if date_ts and amount > 0:
                            daily_totals[date_ts] = daily_totals.get(date_ts, 0) + amount
                
                if daily_totals:
                    df_chain = pd.DataFrame(list(daily_totals.items()), columns=['date', 'totalCirculatingUSD'])
                    df_chain['date'] = pd.to_datetime(df_chain['date'], unit='s')
                    df_chain = df_chain.sort_values('date')

            # --- 策略 B: 兜底检查 (Fallback) ---
            # 如果策略 A 没拿到数据，或者数据明显过小 (例如 USDe 可能只抓到了某个测试网数据)
            # 则尝试直接读取根目录下的 'totalCirculatingUSD'
            
            use_fallback = False
            if df_chain.empty:
                use_fallback = True
            else:
                # 如果最新供应量小于 100万 (对于主流币来说明显不对)，说明 Chain 数据不全
                latest_supply = df_chain.iloc[-1]['totalCirculatingUSD']
                if latest_supply < 1_000_000: 
                    use_fallback = True
            
            if use_fallback:
                # print(f"   [Debug] ID {asset_id} 多链数据不足，切换至全局数据源...")
                target_key = None
                # 常见全局 Key
                possible_keys = ['totalCirculatingUSD', 'circulating', 'pegHistory']
                for key in possible_keys:
                    if key in data and isinstance(data[key], list) and len(data[key]) > 0:
                        target_key = key
                        break
                
                if target_key:
                    df_fallback = pd.DataFrame(data[target_key])
                    # 标准化列名
                    cols = [c for c in df_fallback.columns if c != 'date']
                    if cols:
                        df_fallback.rename(columns={cols[0]: 'totalCirculatingUSD'}, inplace=True)
                    
                    if 'date' in df_fallback.columns and 'totalCirculatingUSD' in df_fallback.columns:
                        df_fallback['date'] = pd.to_datetime(df_fallback['date'], unit='s')
                        df_chain = df_fallback.sort_values('date') # 覆盖 df_chain

            # --- 最终数据清洗 ---
            if df_chain.empty:
                return pd.DataFrame()

            cutoff_date = datetime.now() - timedelta(days=90)
            df_chain = df_chain[df_chain['date'] > cutoff_date]
            
            return df_chain
            
        except Exception as e:
            print(f"❌ 获取 ID {asset_id} 数据失败: {e}")
            return pd.DataFrame()

    def get_supply_at_timestamp(self, df, target_date):
        if df.empty or 'totalCirculatingUSD' not in df.columns: return 0
        df_indexed = df.set_index('date')
        try:
            idx = df_indexed.index.get_indexer([target_date], method='nearest')[0]
            if idx == -1: return 0
            return df_indexed.iloc[idx]['totalCirculatingUSD']
        except: return 0

    # --- 请将此方法添加到 StablecoinSupplyMonitor 类中 ---
    def get_asset_history(self, symbol):
        """获取指定币种 (如 USDT) 的完整历史 DataFrame"""
        asset_id = self.targets.get(symbol)
        if not asset_id: return pd.DataFrame()
        
        # 复用已有的获取逻辑
        df = self.get_historical_supply(asset_id)
        
        if not df.empty:
            df = df.sort_values('date')
            # 简化列名，方便前端绘图
            df = df[['date', 'totalCirculatingUSD']].rename(
                columns={'date': 'Date', 'totalCirculatingUSD': 'Supply'}
            )
        return df

    def analyze_shifts(self):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始全量分析 (混合策略版)...")
        results = []
        
        # 这一行保留，用于 UI 显示时间，但不用来做计算锚点
        now_sys = datetime.now() 

        for symbol, asset_id in self.targets.items():
            # print(f"正在提取: {symbol} (ID: {asset_id})...") # 可注释掉以减少刷屏
            df = self.get_historical_supply(asset_id)
            
            if df.empty:
                continue

            # --- 核心修复：基于数据自身的时间戳计算，防止 24h Flow 为 0 ---
            # 1. 获取数据里最新的时间点
            last_date = df.iloc[-1]['date']
            supply_now = df.iloc[-1]['totalCirculatingUSD']
            
            # 2. 基于由于数据的时间点，向前回溯
            # 这样能确保我们对比的是 "最新数据" vs "最新数据的1天前/7天前"
            # 避免因为 API 还没更新导致 Now 和 24h_Ago 撞到同一个点
            supply_24h = self.get_supply_at_timestamp(df, last_date - timedelta(days=1))
            supply_7d  = self.get_supply_at_timestamp(df, last_date - timedelta(days=7))
            
            # 注意：30d 还是建议保留一定的 buffer，也可以用 last_date
            supply_30d = self.get_supply_at_timestamp(df, last_date - timedelta(days=30))

            results.append({
                'Asset': symbol,
                'Total Supply': supply_now,
                # 只有当历史数据有效时才计算
                'Net Flow (24h)': (supply_now - supply_24h) if supply_24h > 0 else 0,
                'Net Flow (7d)': (supply_now - supply_7d) if supply_7d > 0 else 0,
                'Net Flow (30d)': (supply_now - supply_30d) if supply_30d > 0 else 0
            })
            time.sleep(0.1)

        return pd.DataFrame(results)

# --- 格式化 ---
def format_currency(x):
    if pd.isna(x): return "-"
    abs_x = abs(x)
    prefix = "-" if x < 0 else "+" if x > 0 else ""
    if abs_x >= 1_000_000_000: return f"{prefix}${abs_x/1_000_000_000:.2f}B"
    if abs_x >= 1_000_000: return f"{prefix}${abs_x/1_000_000:.2f}M"
    return f"{prefix}${abs_x:,.0f}"

def get_trend_emoji(val):
    if val > 5_000_000: return "🟢 Mint"
    if val < -5_000_000: return "🔴 Burn"
    return "⚪ Flat"

if __name__ == "__main__":
    monitor = StablecoinSupplyMonitor()
    df = monitor.analyze_shifts()

    if not df.empty:
        df = df.sort_values('Total Supply', ascending=False).reset_index(drop=True)
        total_market_cap = df['Total Supply'].sum()
        df['Share'] = (df['Total Supply'] / total_market_cap) * 100
        
        # 保存 CSV
        filename = f"stablecoin_report_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        csv_cols = ['Asset', 'Total Supply', 'Share', 'Net Flow (24h)', 'Net Flow (7d)', 'Net Flow (30d)']
        df[csv_cols].to_csv(filename, index=False)
        print(f"\n✅ 文件已保存: {os.getcwd()}/{filename}")
        
        # 打印显示
        print("\n" + "="*105)
        print("📊 全球主流稳定币流动性监控 (Top Stablecoins Liquidity Monitor)")
        print("="*105)
        
        display_df = df.copy()
        display_df['Total Supply'] = display_df['Total Supply'].apply(format_currency)
        display_df['Share'] = display_df['Share'].apply(lambda x: f"{x:.1f}%")
        for col in ['Net Flow (24h)', 'Net Flow (7d)', 'Net Flow (30d)']:
            display_df[col] = display_df[col].apply(format_currency)
        display_df['7d Trend'] = df['Net Flow (7d)'].apply(get_trend_emoji)
        
        final_cols = ['Asset', 'Total Supply', 'Share', 'Net Flow (24h)', 'Net Flow (7d)', '7d Trend', 'Net Flow (30d)']
        print(display_df[final_cols].to_string(index=False, col_space=13))
        print("="*105)
        print(f"[Stat] 监控池总市值: ${total_market_cap/1_000_000_000:.2f}B")
    else:
        print("\n⚠️ 未获取到有效数据。")