import ccxt
import requests
import pandas as pd
from datetime import datetime
import time

class DerivativesRiskMonitor:
    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self.exchange = ccxt.binance({
            'enableRateLimit': True,
            'apiKey': api_key, # Optional for some endpoints
            'options': {'defaultType': 'future'} # 强制使用合约API
        })
        self.fapi_base = "https://fapi.binance.com"

    def get_basic_metrics(self, symbol: str = 'BTC/USDT'):
        """
        获取 Funding Rate 和 Open Interest
        """
        try:
            # Ensure symbol format for CCXT
            if '/' not in symbol:
                symbol = f"{symbol}/USDT"
            
            # 1. Fetch Funding Rate
            funding_info = self.exchange.fetch_funding_rate(symbol)
            
            # 2. Fetch Open Interest
            # Use ccxt method which handles the endpoint correctly
            oi_info = self.exchange.fetch_open_interest(symbol)
            oi_val = float(oi_info.get('openInterestAmount') or 0)
            oi_usd = float(oi_info.get('openInterestValue') or 0) # Notional Value
            
            # If value is 0, try to calculate
            if oi_usd == 0 and oi_val > 0:
                mark_price = float(funding_info.get('markPrice') or 0)
                if mark_price == 0:
                     ticker = self.exchange.fetch_ticker(symbol)
                     mark_price = float(ticker['last'])
                oi_usd = oi_val * mark_price

            return {
                "symbol": symbol,
                "price": float(funding_info.get('markPrice') or 0),
                "funding_rate_cur": funding_info['fundingRate'],
                "funding_rate_annualized": funding_info['fundingRate'] * 3 * 365 * 100,
                "open_interest_usd": oi_usd
            }
        except Exception as e:
            return {"error": f"Basic metrics failed for {symbol}: {str(e)}"}

    def get_long_short_ratio(self, symbol: str = 'BTC/USDT', period: str = '5m'):
        """
        获取多空持仓人数比 (Top Trader Long/Short Ratio)
        Primary: Binance (often blocked)
        Fallback: Bybit (Public API)
        """
        # 1. Try Binance (Top Traders)
        try:
            raw_symbol = symbol.replace('/', '')
            if '/' not in symbol:
                raw_symbol = f"{symbol}USDT"
            
            url = f"{self.fapi_base}/fapi/v1/topLongShortAccountRatio"
            params = {"symbol": raw_symbol, "period": period, "limit": 1}
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, params=params, headers=headers, timeout=2).json()
            
            if isinstance(resp, list) and len(resp) > 0:
                data = resp[0]
                return {
                    "ls_ratio": float(data['longShortRatio']),
                    "long_account_pct": float(data['longAccount']) * 100,
                    "short_account_pct": float(data['shortAccount']) * 100,
                    "source": "Binance"
                }
        except Exception:
            pass # Fallback to Bybit

        # 2. Try Bybit (Fallback)
        try:
            # Map symbol to Bybit format (BTC/USDT -> BTCUSDT)
            bybit_symbol = symbol.replace('/', '')
            # Only append USDT if not present and length is short (e.g. BTC)
            if not bybit_symbol.endswith('USDT'):
                bybit_symbol = f"{bybit_symbol}USDT"
                
            url = "https://api.bybit.com/v5/market/account-ratio"
            params = {
                "category": "linear",
                "symbol": bybit_symbol,
                "period": "5min",
                "limit": 1
            }
            resp = requests.get(url, params=params, timeout=5).json()
            
            if resp['retCode'] == 0 and resp['result']['list']:
                data = resp['result']['list'][0]
                buy_ratio = float(data['buyRatio'])
                sell_ratio = float(data['sellRatio'])
                return {
                    "ls_ratio": round(buy_ratio / sell_ratio, 4) if sell_ratio else 0,
                    "long_account_pct": buy_ratio * 100,
                    "short_account_pct": sell_ratio * 100,
                    "source": "Bybit"
                }
        except Exception:
            pass # Fallback failed
            
        return {"error": "No L/S data found"}

    def get_recent_liquidations(self, symbol: str = 'BTCUSDT'):
        """
        获取最近的强平订单 (Liquidation Orders)
        API: GET /fapi/v1/forceOrders (Public?)
        Note: This endpoint often requires an API key even for public data on Binance.
        If it fails, we return a specific error.
        """
        try:
            url = f"{self.fapi_base}/fapi/v1/forceOrders"
            params = {
                "symbol": symbol.replace('/', ''),
                "limit": 20
            }
            # Some public endpoints work without key but need User-Agent
            headers = {
                "User-Agent": "Mozilla/5.0",
            }
            if self.api_key:
                headers["X-MBX-APIKEY"] = self.api_key

            resp = requests.get(url, params=params, headers=headers).json()
            
            if isinstance(resp, dict) and 'code' in resp and resp['code'] == -2014:
                 return {"error": "Liquidation data requires API Key (Private Endpoint)"}

            if isinstance(resp, list):
                # 简单聚合计算
                total_qty = 0
                buy_qty = 0 # Shorts getting liquidated (Buy orders)
                sell_qty = 0 # Longs getting liquidated (Sell orders)
                
                for order in resp:
                    qty = float(order['originalQuantity'])
                    side = order['side'] # SELL means Long liquidation, BUY means Short liquidation
                    total_qty += qty
                    if side == 'SELL':
                        sell_qty += qty
                    else:
                        buy_qty += qty
                
                return {
                    "recent_liquidation_count": len(resp),
                    "total_liquidation_vol_base": total_qty,
                    "long_liquidations_vol": sell_qty, # 多头爆仓 (卖单)
                    "short_liquidations_vol": buy_qty  # 空头爆仓 (买单)
                }
            return {"error": f"Liquidation API error: {resp}"}
        except Exception as e:
            return {"error": f"Liquidation fetch failed: {str(e)}"}

    def execute_analysis(self):
        target_symbol_ccxt = 'BTC/USDT'
        target_symbol_raw = 'BTCUSDT'
        
        print(f"--- Derivatives Risk Report: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
        
        # 1. Basic Leverage Metrics
        basic = self.get_basic_metrics(target_symbol_ccxt)
        if "error" in basic:
            print(f"Error fetching basic metrics: {basic['error']}")
        else:
            print(f"\n[Leverage Status - {target_symbol_ccxt}]")
            print(f"Price: ${basic.get('price', 0):,.2f}")
            print(f"Funding Rate (8h): {basic.get('funding_rate_cur', 0)*100:.4f}%")
            print(f"Funding Rate (Ann.): {basic.get('funding_rate_annualized', 0):.2f}% (Positive = Bullish/Over-leveraged Longs)")
            print(f"Open Interest: ${basic.get('open_interest_usd', 0):,.0f}")

        # 2. Sentiment (L/S Ratio)
        ls_data = self.get_long_short_ratio(target_symbol_raw)
        if "error" in ls_data:
            print(f"Error fetching L/S Ratio: {ls_data['error']}")
        else:
            print(f"\n[Market Sentiment - Top Traders]")
            print(f"Long/Short Ratio: {ls_data.get('ls_ratio')} ( > 1 means more Long accounts)")
            print(f"Long Accounts: {ls_data.get('long_account_pct')}%")
            print(f"Short Accounts: {ls_data.get('short_account_pct')}%")

        # 3. Liquidation Pressure
        liq_data = self.get_recent_liquidations(target_symbol_raw)
        if "error" in liq_data:
            print(f"Error fetching liquidations: {liq_data['error']}")
        else:
            print(f"\n[Immediate Liquidation Pressure (Last ~1-5 min)]")
            print(f"Longs Liquidated (Vol): {liq_data.get('long_liquidations_vol')} BTC")
            print(f"Shorts Liquidated (Vol): {liq_data.get('short_liquidations_vol')} BTC")
        
        # Risk Signal Logic
        risk_score = 0
        if basic.get('funding_rate_annualized', 0) > 50: risk_score += 1 # High funding
        if ls_data.get('ls_ratio', 1) > 2.5: risk_score += 1 # Crowded Longs
        if liq_data.get('long_liquidations_vol', 0) > 50: risk_score += 1 # Heavy liquidations occurring
        
        print(f"\n[Summary]")
        print(f"Risk Level: {'HIGH' if risk_score >= 2 else 'MODERATE' if risk_score == 1 else 'LOW'}")

if __name__ == "__main__":
    monitor = DerivativesRiskMonitor()
    monitor.execute_analysis()
