import requests
import pandas as pd
import numpy as np
from datetime import datetime
from collections import deque
import time
import json
try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None

class WhaleAlertMonitor:
    def __init__(self, window_size=30):
        self.base_url = "https://api.bybit.com/v5/market/tickers"
        self.window_size = window_size
        # Data buffer: list of dicts {'timestamp': ..., 'oi': ..., 'price': ...}
        self.history = deque(maxlen=window_size + 5) 
        self.last_analysis = None

    def fetch_market_data(self, symbol="BTC"):
        """
        Fetch real-time data from Bybit V5 Public API (No Key Needed)
        """
        # Ensure symbol format
        if not symbol.endswith("USDT"):
            symbol = f"{symbol}USDT"
            
        params = {
            "category": "linear",
            "symbol": symbol
        }
        
        try:
            resp = requests.get(self.base_url, params=params, timeout=5)
            data = resp.json()
            
            if data['retCode'] == 0 and data['result']['list']:
                item = data['result']['list'][0]
                return {
                    "symbol": symbol,
                    "price": float(item['lastPrice']),
                    "open_interest": float(item['openInterestValue']), # OI in USDT
                    "funding_rate": float(item['fundingRate']),
                    "volume_24h": float(item['turnover24h']),
                    "timestamp": datetime.now()
                }
            return None
        except Exception as e:
            print(f"Error fetching Bybit data: {e}")
            return None

    def _prefill_history(self, symbol):
        """
        Fetch historical k-line data to pre-fill buffer
        """
        try:
            # Bybit V5 K-line endpoint
            url = "https://api.bybit.com/v5/market/kline"
            params = {
                "category": "linear",
                "symbol": symbol,
                "interval": "5", # 5 minute interval
                "limit": self.window_size + 5
            }
            
            resp = requests.get(url, params=params, timeout=5)
            data = resp.json()
            
            if data['retCode'] == 0 and data['result']['list']:
                # Bybit returns [startTime, openPrice, highPrice, lowPrice, closePrice, volume, turnover]
                # Note: Standard kline doesn't have OI. We need premium index or just use price for now?
                # Wait, Bybit V5 has 'openInterest' in market/tickers but not in standard kline.
                # Actually, for OI history we need /v5/market/open-interest
                
                # Let's fetch OI history instead
                oi_url = "https://api.bybit.com/v5/market/open-interest"
                oi_params = {
                    "category": "linear",
                    "symbol": symbol,
                    "intervalTime": "5min",
                    "limit": self.window_size + 5
                }
                
                oi_resp = requests.get(oi_url, params=oi_params, timeout=5)
                oi_data = oi_resp.json()
                
                if oi_data['retCode'] == 0 and oi_data['result']['list']:
                    # Combine Price (from kline) and OI (from oi history) if possible, 
                    # but simpler to just use OI history and maybe fetch price separately or approximate.
                    # Actually, let's just use the OI history endpoint which gives us OI.
                    # We also need price for the signal logic.
                    
                    # Let's just fill what we can. The most important is OI for Z-Score.
                    # OI Data: [symbol, category, openInterest, timestamp]
                    
                    # We need to align timestamps. This is getting complex for a quick fix.
                    # Alternative: Just fill with OI data and assume price is relatively stable or fetch price history too.
                    
                    # Let's fetch Price History (Kline)
                    kline_resp = requests.get(url, params=params, timeout=5).json()
                    kline_list = kline_resp['result']['list'] # [time, open, high, low, close, ...]
                    
                    # Create a dict map for price: time -> close
                    price_map = {int(k[0]): float(k[4]) for k in kline_list}
                    
                    # Process OI Data
                    # OI List is usually descending by time
                    for item in reversed(oi_data['result']['list']):
                        ts = int(item['timestamp'])
                        # Find closest price (simple matching)
                        # Timestamps might not match exactly due to different recording times, but 5min interval should be close.
                        # Let's just take the price with closest timestamp or just current price if not found.
                        
                        # Approximate matching (truncate to minutes)
                        price = 0
                        for t, p in price_map.items():
                            if abs(t - ts) < 300000: # within 5 mins
                                price = p
                                break
                        
                        if price > 0:
                            self.history.append({
                                "symbol": symbol,
                                "price": price,
                                "open_interest": float(item['openInterestValue']),
                                "funding_rate": 0, # Historical funding not critical for Z-score warmup
                                "volume_24h": 0,
                                "timestamp": datetime.fromtimestamp(ts/1000)
                            })
                            
                    print(f"Prefilled {len(self.history)} data points for {symbol}")
                    
        except Exception as e:
            print(f"Error prefilling history: {e}")

    def process_data(self, symbol="BTC"):
        """
        Main loop step: Fetch -> Update Buffer -> Calculate Z-Score
        """
        # Auto-prefill if empty
        if len(self.history) == 0:
            self._prefill_history(symbol)
            
        current_data = self.fetch_market_data(symbol)
        if not current_data:
            return {"error": "Failed to fetch data"}

        # Add to history
        self.history.append(current_data)
        
        # Need enough data to calculate Z-Score
        if len(self.history) < 5:
            return {
                "status": "WARMUP", 
                "message": f"Collecting data... ({len(self.history)}/{self.window_size})",
                "description": "Initializing...", # Ensure description key exists
                "data": current_data
            }

        # Calculate Z-Score for Open Interest Change
        df = pd.DataFrame(self.history)
        df['oi_change_pct'] = df['open_interest'].pct_change() * 100
        
        # Drop NaNs
        changes = df['oi_change_pct'].dropna()
        
        if len(changes) < 2:
            return {"status": "WARMUP", "data": current_data, "description": "Initializing..."}

        # Calculate Statistics
        # We use the last N periods for mean/std
        recent_changes = changes.tail(self.window_size)
        mu = recent_changes.mean()
        sigma = recent_changes.std()
        
        if sigma == 0: sigma = 1e-9 # Avoid division by zero
        
        current_change = changes.iloc[-1]
        z_score = (current_change - mu) / sigma
        
        # Determine Signal
        signal = "NEUTRAL"
        signal_desc = "Normal Activity"
        severity = "LOW"
        
        # Thresholds
        Z_THRESHOLD = 2.5
        
        price_change = df['price'].pct_change().iloc[-1] * 100
        
        if abs(z_score) > Z_THRESHOLD:
            severity = "HIGH"
            if z_score > 0:
                # OI Spike (Large Position Entry)
                if price_change > 0:
                    signal = "LONG_BUILDUP"
                    signal_desc = "🐋 Whale Long Build-up (OI Spike + Price Up)"
                else:
                    signal = "SHORT_BUILDUP"
                    signal_desc = "🐋 Whale Short Build-up (OI Spike + Price Down)"
            else:
                # OI Drop (Large Liquidation/Exit)
                if price_change > 0:
                    signal = "SHORT_COVER"
                    signal_desc = "⚠️ Short Covering/Liquidation (OI Drop + Price Up)"
                else:
                    signal = "LONG_FLUSH"
                    signal_desc = "⚠️ Long Liquidation/Flush (OI Drop + Price Down)"
        
        result = {
            "status": "ACTIVE",
            "timestamp": current_data['timestamp'],
            "symbol": current_data['symbol'],
            "price": current_data['price'],
            "oi": current_data['open_interest'],
            "funding_rate": current_data['funding_rate'],
            "oi_change_pct": current_change,
            "z_score": z_score,
            "signal": signal,
            "description": signal_desc,
            "severity": severity
        }
        
        self.last_analysis = result
        return result

    def analyze_signal(self, signal_data, api_key, base_url="https://api.deepseek.com", model="deepseek-chat"):
        """
        Analyze the signal using an LLM (DeepSeek/OpenAI)
        """
        if not ChatOpenAI:
            return {"error": "LangChain OpenAI not installed"}
            
        try:
            llm = ChatOpenAI(
                api_key=api_key,
                base_url=base_url,
                model=model,
                temperature=0.3
            )
            
            prompt = f"""
            You are a crypto market analyst. Analyze this whale alert:
            
            Symbol: {signal_data.get('symbol', 'Unknown')}
            Signal: {signal_data.get('signal', 'Unknown')} ({signal_data.get('description', '')})
            Price: ${signal_data.get('price', 0)}
            OI Change: {signal_data.get('oi_change_pct', 0):.2f}%
            Z-Score: {signal_data.get('z_score', 0):.2f}
            Funding Rate: {signal_data.get('funding_rate', 0) * 100:.4f}%
            
            Task: Analyze the intent. Is this FOMO, manipulation, or sustainable?
            Output JSON: {{ "sentiment": "bullish/bearish", "confidence": 0.0-1.0, "reason": "..." }}
            """
            
            response = llm.invoke(prompt)
            content = response.content.strip()
            
            # Clean json block if needed
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
                
            return json.loads(content)
            
        except Exception as e:
            return {"error": str(e)}

if __name__ == "__main__":
    monitor = WhaleAlertMonitor(window_size=10)
    print("Starting Whale Monitor (Bybit)...")
    
    # Simulate a loop
    for i in range(5):
        res = monitor.process_data("BTC")
        print(f"[{i}] {res.get('description', res.get('message'))} | Z: {res.get('z_score', 0):.2f}")
        time.sleep(1)
