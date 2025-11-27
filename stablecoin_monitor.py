import requests
import pandas as pd
from datetime import datetime, timedelta
import time

class StablecoinSupplyMonitor:
    def __init__(self):
        self.llama_base = "https://stablecoins.llama.fi"
        self.protocol_base = "https://api.llama.fi/protocol"
        self.cg_base = "https://api.coingecko.com/api/v3"
        self.tvl_base = "https://api.llama.fi/tvl"
        
        self.coins = {
            'USDT': {'llama': '1',   'cg': 'tether'},
            'USDC': {'llama': '2',   'cg': 'usd-coin'},
            'DAI':  {'llama': '5',   'cg': 'dai'},
            'USDe': {'llama': '162', 'cg': 'ethena-usde', 'slug': 'ethena'}, # 重点
            'FDUSD':{'llama': '127', 'cg': 'first-digital-usd'},
            'PYUSD':{'llama': '136', 'cg': 'paypal-usd'},
            'FRAX': {'llama': '6',   'cg': 'frax'}
        }

    # ==========================================
    # Part 1: 获取当前市值 (各种手段)
    # ==========================================
    
    # 1. DefiLlama 列表快照
    def get_llama_list(self):
        try:
            url = f"{self.llama_base}/stablecoins?includePrices=true"
            data = requests.get(url, timeout=10).json()
            caps = {}
            if 'peggedAssets' in data:
                for coin in data['peggedAssets']:
                    cid = str(coin.get('id'))
                    circ = coin.get('circulating')
                    val = 0
                    if isinstance(circ, dict): val = circ.get('peggedUSD', 0)
                    else: val = float(circ) if circ else 0
                    if val > 0: caps[cid] = val
            return caps
        except: return {}

    # 2. CoinGecko 兜底
    def get_gecko_cap(self, cg_id):
        try:
            url = f"{self.cg_base}/simple/price"
            params = {'ids': cg_id, 'vs_currencies': 'usd', 'include_market_cap': 'true'}
            data = requests.get(url, params=params, timeout=5).json()
            if cg_id in data:
                return data[cg_id].get('usd_market_cap', 0)
        except: pass
        return 0

    # 3. [协议级 TVL] (USDe 救星)
    def get_protocol_tvl_robust(self, slug):
        """同时检查 currentChainTvls 和 tvl 数组"""
        try:
            url = f"{self.protocol_base}/{slug}"
            data = requests.get(url, timeout=10).json()
            
            val_a = 0
            # 策略 A: 累加各链 TVL (最准)
            if 'currentChainTvls' in data:
                for chain, val in data['currentChainTvls'].items():
                    if chain not in ['Borrowed']:
                        val_a += float(val)
            
            val_b = 0
            # 策略 B: 读取历史数组最后一位
            if 'tvl' in data and isinstance(data['tvl'], list) and data['tvl']:
                val_b = data['tvl'][-1]['totalLiquidityUSD']
            
            return max(val_a, val_b)
        except: pass
        return 0

    # ==========================================
    # Part 2: 获取历史数据 (修复 FDUSD)
    # ==========================================

    # 1. CoinGecko 历史
    def get_gecko_history(self, cg_id):
        try:
            url = f"{self.cg_base}/coins/{cg_id}/market_chart"
            params = {'vs_currency': 'usd', 'days': '180', 'interval': 'daily'}
            data = requests.get(url, params=params, timeout=10).json()
            market_caps = data.get('market_caps', [])
            
            parsed = []
            for item in market_caps:
                ts = item[0] / 1000
                val = item[1]
                if val > 0: parsed.append({'date': ts, 'supply': float(val)})
            
            df = pd.DataFrame(parsed)
            if not df.empty:
                df['date'] = pd.to_datetime(df['date'], unit='s')
                df = df.sort_values('date')
            return df
        except: return pd.DataFrame()

    # 2. DefiLlama 历史
    def get_llama_history(self, asset_id):
        url = f"{self.llama_base}/stablecoin/{asset_id}"
        try:
            data = requests.get(url, timeout=10).json()
            df = pd.DataFrame()
            
            # 优先 ChainBalances
            if 'chainBalances' in data:
                daily_totals = {}
                for chain, details in data['chainBalances'].items():
                    if chain in ['Borrowed']: continue
                    tokens = details.get('tokens') or []
                    if not isinstance(tokens, list): continue
                    for entry in tokens:
                        ts = entry.get('date')
                        val = entry.get('circulating', {}).get('peggedUSD', 0)
                        if ts and val > 0: daily_totals[ts] = daily_totals.get(ts, 0) + val
                if daily_totals:
                    df = pd.DataFrame(list(daily_totals.items()), columns=['date', 'supply'])

            # 兜底
            if df.empty:
                raw = data.get('pegHistory') or data.get('totalCirculatingUSD') or []
                parsed = []
                for entry in raw:
                    ts = entry.get('date')
                    val = entry.get('circulating') or entry.get('totalCirculatingUSD') or entry.get('peggedUSD') or 0
                    if isinstance(val, dict): val = val.get('peggedUSD', 0)
                    if ts and val > 0: parsed.append({'date': ts, 'supply': float(val)})
                if parsed: df = pd.DataFrame(parsed)

            if not df.empty:
                df['date'] = pd.to_datetime(df['date'], unit='s')
                df = df.sort_values('date')
            return df
        except: return pd.DataFrame()

    # 3. 统一历史获取 (Router)
    def get_combined_history(self, symbol):
        info = self.coins.get(symbol)
        if not info: return pd.DataFrame()
        
        # A. 优先 Llama
        df = self.get_llama_history(info['llama'])
        
        # B. 失败则切换 Gecko (修复 FDUSD)
        if df.empty:
            df = self.get_gecko_history(info['cg'])
            
        return df

    # --- 辅助 ---
    def get_val_at_date(self, df, target_date):
        if df.empty: return 0
        df = df.set_index('date')
        try:
            idx = df.index.get_indexer([target_date], method='nearest')[0]
            if abs((df.index[idx] - target_date).days) > 2: return 0
            return df.iloc[idx]['supply']
        except: return 0

    # --- 外部接口 ---
    def get_asset_history(self, symbol):
        df = self.get_combined_history(symbol)
        if not df.empty:
            cutoff = datetime.now() - timedelta(days=180)
            df = df[df['date'] > cutoff]
            df = df[['date', 'supply']].rename(columns={'date': 'Date', 'supply': 'Supply'})
        return df

    # --- 主逻辑 ---
    def analyze_shifts(self):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在同步稳定币数据 (V7.1 竞价版)...")
        
        list_caps = self.get_llama_list()
        results = []
        now = datetime.now()

        for symbol, info in self.coins.items():
            llama_id = info['llama']
            cg_id = info['cg']
            
            # --- 核心改动：USDe 采用“竞价机制” (回归 V5.0 逻辑) ---
            if symbol == 'USDe':
                print("   🔍 [Debug] USDe 多源竞价中...")
                val_1 = list_caps.get(llama_id, 0)
                val_2 = 0
                if 'slug' in info:
                    val_2 = self.get_protocol_tvl_robust(info['slug'])
                val_3 = self.get_gecko_cap(cg_id)
                
                # 哪个大用哪个，彻底杜绝 0 值
                supply_now = max(val_1, val_2, val_3)
                print(f"      List:{val_1} | Proto:{val_2} | Gecko:{val_3} -> Final: {supply_now}")
            else:
                # 其他币种：优先 List，0则Gecko
                supply_now = list_caps.get(llama_id, 0)
                if supply_now == 0:
                    supply_now = self.get_gecko_cap(cg_id)

            # 2. 获取历史 (Priority: Llama -> Gecko)
            df_hist = self.get_combined_history(symbol)
            
            # 历史数据最后一条兜底当前值 (防止历史数据比当前还新)
            if supply_now == 0 and not df_hist.empty:
                supply_now = df_hist.iloc[-1]['supply']

            # 3. 计算资金流
            s24h, s7d, s30d = 0, 0, 0
            if not df_hist.empty and supply_now > 0:
                v24h = self.get_val_at_date(df_hist, now - timedelta(days=1))
                v7d  = self.get_val_at_date(df_hist, now - timedelta(days=7))
                v30d = self.get_val_at_date(df_hist, now - timedelta(days=30))
                
                if v24h > 0: s24h = supply_now - v24h
                if v7d > 0:  s7d  = supply_now - v7d
                if v30d > 0: s30d = supply_now - v30d

            results.append({
                'Asset': symbol,
                'Total Supply': supply_now,
                'Net Flow (24h)': s24h,
                'Net Flow (7d)': s7d,
                'Net Flow (30d)': s30d
            })
            time.sleep(0.1)
            
        return pd.DataFrame(results)

if __name__ == "__main__":
    monitor = StablecoinSupplyMonitor()
    df = monitor.analyze_shifts()
    print(df.to_string())