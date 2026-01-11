import requests
import pandas as pd
import time
from datetime import datetime
import os

class CEXReserveMonitor:
    def __init__(self):
        self.base_url = "https://api.llama.fi"
        
        # 1. 修正交易所列表，Huobi 改为 'htx'
        self.target_exchanges = [
            'binance-cex', 
            'okx', 
            'bybit', 
            'bitfinex',
            'kucoin',
            'deribit', 
            'gate',      # Verified: $6.7B
            'bitmex',    # Verified: $151M
            'htx' 
        ]
        
        self.name_mapping = {
            'binance-cex': 'Binance',
            'okx': 'OKX',
            'bybit': 'Bybit',
            'bitfinex': 'Bitfinex',
            'kucoin': 'KuCoin',
            'deribit': 'Deribit',
            'gate': 'Gate.io',
            'bitmex': 'BitMEX',
            'htx': 'HTX (Huobi)'
        }
        
        # 目标监控资产
        self.target_tokens = ['USDT', 'USDC', 'DAI', 'ETH', 'BTC']

    def get_exchange_details(self, slug):
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            url = f"{self.base_url}/protocol/{slug}"
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code >= 400:
                print(f"⚠️  [API Error] 无法找到: {slug} (Status: {response.status_code})")
                return None
            return response.json()
        except Exception as e:
            print(f"❌ [Net Error] 获取 {slug} 失败: {e}")
            return None

    def extract_latest_tokens(self, token_data):
        """智能解析字典或列表格式的数据"""
        if isinstance(token_data, dict):
            return token_data
        if isinstance(token_data, list):
            if not token_data: return {}
            latest = token_data[-1]
            return latest.get('tokens', latest)
        return {}

    def run_monitor(self):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始获取交易所储备数据 (DefiLlama CEX)...")
        all_reserves = []

        for slug in self.target_exchanges:
            name = self.name_mapping.get(slug, slug)
            print(f"正在读取: {name}...")
            
            data = self.get_exchange_details(slug)
            if not data: continue

            # 初始化余额 (这是数量，不是金额)
            token_counts = {t: 0.0 for t in self.target_tokens}
            found_data = False
            
            # 优先从 chainTvls 提取
            if 'chainTvls' in data:
                for chain, details in data['chainTvls'].items():
                    raw_tokens = details.get('tokens')
                    if raw_tokens:
                        tokens_dict = self.extract_latest_tokens(raw_tokens)
                        for t_name, amount in tokens_dict.items():
                            clean = t_name.upper()
                            # 常见别名映射
                            if clean in ['WETH', 'STETH', 'BETH']: clean = 'ETH'
                            if clean in ['WBTC', 'CBTC', 'BTCB']: clean = 'BTC'
                            
                            if clean in self.target_tokens:
                                token_counts[clean] += float(amount)
                                found_data = True
            
            # 备用：从根目录 tokens 提取
            if not found_data and 'tokens' in data:
                 tokens_dict = self.extract_latest_tokens(data['tokens'])
                 for t_name, amount in tokens_dict.items():
                    clean = t_name.upper()
                    if clean in ['WETH']: clean = 'ETH'
                    if clean in ['WBTC']: clean = 'BTC'
                    if clean in self.target_tokens:
                        token_counts[clean] += float(amount)

            # 获取总资产 USD 价值 (这是 DefiLlama 算好的)
            tvl_data = data.get('tvl', [])
            total_usd = 0
            if isinstance(tvl_data, list) and tvl_data:
                total_usd = tvl_data[-1].get('totalLiquidityUSD', 0)
            elif isinstance(tvl_data, (int, float)):
                total_usd = tvl_data

            row = {'Exchange': name, 'Total_Reserves_USD': total_usd}
            row.update(token_counts)
            all_reserves.append(row)
            time.sleep(1)

        return pd.DataFrame(all_reserves)

# --- 格式化显示函数 ---
def format_usd_large(x):
    """用于美元列 (Total Reserves, USDT, USDC)"""
    if pd.isna(x) or x == 0: return "-"
    if x > 1_000_000_000: return f"${x/1_000_000_000:.2f}B"
    if x > 1_000_000: return f"${x/1_000_000:.2f}M"
    return f"${x:,.0f}"

def format_quantity(x):
    """用于数量列 (ETH, BTC) - 不带 $ 符号"""
    if pd.isna(x) or x == 0: return "-"
    if x > 1_000_000: return f"{x/1_000_000:.2f}M" # M 代表 Million (百万枚)
    if x > 1_000: return f"{x/1_000:.0f}k"         # k 代表 Thousand (千枚)
    return f"{x:,.0f}"

if __name__ == "__main__":
    monitor = CEXReserveMonitor()
    df = monitor.run_monitor()

    if not df.empty:
        # 按总资产排序
        df = df.sort_values(by='Total_Reserves_USD', ascending=False)
        
        # 保存 CSV (原始数据，未格式化，方便后续分析)
        filename = f"cex_reserves_{datetime.now().strftime('%Y%m%d')}.csv"
        df.to_csv(filename, index=False)
        print(f"\n✅ 数据已保存至文件: {filename}")

        print("\n" + "="*85)
        print("📊 交易所链上储备概览 (Token Counts vs USD Value)")
        print("="*85)
        
        display_df = df.copy()
        
        # 1. 格式化美元列
        usd_cols = ['Total_Reserves_USD', 'USDT', 'USDC', 'DAI']
        for col in usd_cols:
            if col in display_df.columns:
                display_df[col] = display_df[col].apply(format_usd_large)
        
        # 2. 格式化数量列 (BTC, ETH)
        qty_cols = ['ETH', 'BTC']
        for col in qty_cols:
            if col in display_df.columns:
                display_df[col] = display_df[col].apply(format_quantity)
                # 重命名列头，增加 (Qty) 提示
                display_df.rename(columns={col: f"{col} (Qty)"}, inplace=True)
        
        print(display_df.to_string(index=False))
        print("\n[注] USDT/USDC/DAI 为美元价值; ETH/BTC 为代币数量 (Quantity)")
    else:
        print("\n⚠️ 未获取到数据。")