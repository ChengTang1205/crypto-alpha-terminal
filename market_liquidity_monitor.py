import ccxt
import pandas as pd
import numpy as np
import requests
import time
from datetime import datetime, timedelta

class CryptoRiskMonitor:
    def __init__(self):
        self.binance = ccxt.binance({'enableRateLimit': True})
        self.deribit_url = "https://www.deribit.com/api/v2/public"
        self.defillama_url = "https://api.llama.fi"

    def get_market_volatility_and_volume(self, symbol: str = 'BTC/USDT', lookback_days: int = 30):
        """
        来源: Binance
        指标: 
        1. Realized Volatility (已实现波动率, 年化)
        2. Volume Spike (今日交易量 vs 过去 N 天均值)
        """
        try:
            # 获取日线数据
            ohlcv = self.binance.fetch_ohlcv(symbol, timeframe='1d', limit=lookback_days + 1)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # 计算 Log Returns
            df['log_ret'] = np.log(df['close'] / df['close'].shift(1))
            
            # 1. Realized Volatility (Annualized)
            # 标准差 * sqrt(365)
            realized_vol = df['log_ret'].std() * np.sqrt(365) * 100
            
            # 2. Volume Anomaly
            current_vol = df['volume'].iloc[-1]
            avg_vol = df['volume'].iloc[:-1].mean()
            vol_ratio = current_vol / avg_vol if avg_vol > 0 else 0
            
            return {
                "realized_vol_30d_annualized": round(realized_vol, 2),
                "volume_24h": current_vol,
                "avg_volume_30d": round(avg_vol, 2),
                "volume_spike_ratio": round(vol_ratio, 2)
            }
        except Exception as e:
            return {"error": f"Binance OHLCV failed: {str(e)}"}

    def get_order_book_depth(self, symbol: str = 'BTC/USDT', depth_pct: float = 0.02):
        """
        来源: Binance
        指标: +/- 2% 深度 (流动性枯竭监测)
        """
        try:
            # 获取 Order Book
            book = self.binance.fetch_order_book(symbol, limit=500)
            mid_price = (book['bids'][0][0] + book['asks'][0][0]) / 2
            
            # 计算深度
            bids_depth = sum([x[1] for x in book['bids'] if x[0] >= mid_price * (1 - depth_pct)])
            asks_depth = sum([x[1] for x in book['asks'] if x[0] <= mid_price * (1 + depth_pct)])
            
            # 计算滑点模拟 (假设买入 1M USDT)
            # 简易计算：查看消耗 1M USDT 后的价格偏离度
            target_amount = 1000000  # 100k -> 1M
            cost = 0
            filled_qty = 0
            slippage = 0
            
            # 简单滑点估算逻辑 (Ask side)
            current_p = 0
            for price, qty in book['asks']:
                if cost + (price * qty) >= target_amount:
                    needed = (target_amount - cost) / price
                    filled_qty += needed
                    cost += needed * price
                    current_p = price
                    break
                else:
                    cost += price * qty
                    filled_qty += qty
            
            if cost > 0:
                avg_price = cost / filled_qty
                slippage = (avg_price - mid_price) / mid_price * 100

            return {
                "bid_depth_2pct": round(bids_depth, 4),
                "ask_depth_2pct": round(asks_depth, 4),
                "total_depth_2pct": round(bids_depth + asks_depth, 4),
                "slippage_sim_100k_usdt": round(slippage, 6)  # 保留更多小数位
            }
        except Exception as e:
            return {"error": f"Orderbook failed: {str(e)}"}

    def get_implied_volatility(self, currency: str = 'BTC'):
        """
        来源: Deribit Public API
        指标: DVOL (Deribit Volatility Index)
        """
        try:
            # 使用 get_index_price 获取 DVOL
            url = f"{self.deribit_url}/get_index_price"
            # index_name: btcdvol_usdc
            params = {"index_name": f"{currency.lower()}dvol_usdc"}
            resp = requests.get(url, params=params).json()
            
            if 'result' in resp:
                dvol_value = resp['result'].get('index_price')
                return {"implied_volatility_index": dvol_value}
            return {"error": "No data"}
        except Exception as e:
            return {"error": f"Deribit API failed: {str(e)}"}

    def get_defi_tvl_risk(self, protocol_slug: str = 'uniswap-v3'):
        """
        来源: DefiLlama
        指标: TVL Change (监测流动性撤出)
        """
        try:
            # Try DefiLlama first
            url = f"{self.defillama_url}/protocol/{protocol_slug}"
            # Increase timeout to 30s as the response is large (40MB+)
            resp = requests.get(url, proxies={"http": None, "https": None}, timeout=30).json()
            
            tvl_data = resp.get('tvl', [])
            if len(tvl_data) < 2:
                return {"error": "Insufficient TVL data"}
            
            current_tvl = tvl_data[-1]['totalLiquidityUSD']
            prev_tvl_24h = tvl_data[-2]['totalLiquidityUSD']
            # 获取7天前数据
            prev_tvl_7d = tvl_data[-8]['totalLiquidityUSD'] if len(tvl_data) >= 8 else tvl_data[0]['totalLiquidityUSD']
            
            change_24h = (current_tvl - prev_tvl_24h) / prev_tvl_24h * 100
            change_7d = (current_tvl - prev_tvl_7d) / prev_tvl_7d * 100
            
            return {
                "current_tvl": f"${current_tvl:,.0f}",
                "tvl_change_24h_pct": round(change_24h, 2),
                "risk_alert": "HIGH" if change_24h < -10 else "NORMAL",
                "source": "DefiLlama"
            }
        except Exception as e:
            # Fallback to Binance UNI/USDT
            try:
                ticker = self.binance.fetch_ticker('UNI/USDT')
                change_24h = ticker['percentage']
                return {
                    "current_tvl": f"${ticker['last']:.2f} (UNI Price)",
                    "tvl_change_24h_pct": round(change_24h, 2),
                    "tvl_change_7d_pct": 0,
                    "risk_alert": "HIGH" if change_24h < -10 else "NORMAL",
                    "source": "Binance (Fallback)"
                }
            except Exception as binance_error:
                return {"error": f"DefiLlama & Binance failed: {str(e)}"}

    def execute_dashboard(self):
        print(f"--- Risk Report: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
        
        # 1. Market Data (BTC/USDT)
        print("\n[Market & Liquidity - BTC/USDT]")
        mkt_data = self.get_market_volatility_and_volume()
        depth_data = self.get_order_book_depth()
        print(f"Realized Vol (30d): {mkt_data.get('realized_vol_30d_annualized')}%")
        print(f"Volume Ratio (vs 30d avg): {mkt_data.get('volume_spike_ratio')}x")
        print(f"Orderbook Depth (+/-2%): {depth_data.get('total_depth_2pct')} BTC")
        print(f"Est. Slippage (100k Buy): {depth_data.get('slippage_sim_100k_usdt')}%")
        
        # 2. Implied Volatility
        print("\n[Derivatives Risk]")
        iv_data = self.get_implied_volatility('BTC')
        print(f"Deribit DVOL Index: {iv_data.get('implied_volatility_index')}")

        # 3. DeFi Risk
        print("\n[DeFi Liquidity Flight - Uniswap V3]")
        defi_data = self.get_defi_tvl_risk('uniswap-v3')
        print(f"TVL Change (24h): {defi_data.get('tvl_change_24h_pct')}%")
        print(f"Risk Status: {defi_data.get('risk_alert')}")

if __name__ == "__main__":
    monitor = CryptoRiskMonitor()
    monitor.execute_dashboard()
