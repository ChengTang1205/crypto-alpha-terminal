import ccxt
import pandas as pd
import numpy as np
import talib
import yfinance as yf
from typing import Dict, List, Tuple

class BacktestEngine:
    def __init__(self):
        self.exchange = ccxt.binance({'enableRateLimit': True})

    def fetch_data(self, symbol: str = 'BTC/USDT', timeframe: str = '1h', limit: int = 1000) -> pd.DataFrame:
        """Fetch historical OHLCV data from Binance (supports >1000 candles via pagination)"""
        try:
            all_ohlcv = []
            remaining = limit
            since = None
            
            # Fetch most recent data first
            while remaining > 0:
                fetch_limit = min(remaining, 1000)
                
                # If we have data, we need to fetch data BEFORE the oldest timestamp we have
                params = {}
                if all_ohlcv:
                    # all_ohlcv[0] is the oldest candle, index 0 is timestamp
                    # We want data ending before this timestamp
                    params['endTime'] = all_ohlcv[0][0] - 1
                
                ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=fetch_limit, params=params)
                
                if not ohlcv:
                    break
                
                # Prepend new data (since we are fetching backwards)
                all_ohlcv = ohlcv + all_ohlcv
                remaining -= len(ohlcv)
                
                # Safety break if we got fewer than requested (reached beginning of history)
                if len(ohlcv) < fetch_limit:
                    break
                    
            df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            print(f"Error fetching data from Binance: {e}. Trying Yahoo Finance fallback...")
            return self.fetch_data_yfinance(symbol, timeframe, limit)

    def fetch_data_yfinance(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        """Fallback: Fetch data from Yahoo Finance"""
        try:
            # 1. Map Symbol (BTC/USDT -> BTC-USD)
            yf_symbol = symbol.replace('/', '-').replace('USDT', 'USD')
            
            # 2. Map Timeframe
            # ccxt: 1h, 4h, 1d
            # yf: 1h, 1d (YF doesn't support 4h well, maybe use 1h and resample? For now just try exact match)
            # YF valid intervals: 1m,2m,5m,15m,30m,60m,90m,1h,1d,5d,1wk,1mo,3mo
            
            period = "2y" # Max available for hourly data
            if timeframe == '4h':
                # YF doesn't support 4h directly. We could fetch 1h and resample, but for simplicity let's fallback to 1h or error
                # Ideally we fetch 1h and resample. Users selected 1h typically.
                # Let's just try to map 4h -> 1h for now as a fallback? No, that's misleading.
                # Let's stick to 1h default or supports 1d.
                pass
            
            print(f"Fetching {yf_symbol} from Yahoo Finance...")
            df = yf.download(yf_symbol, period=period, interval=timeframe, progress=False)
            
            if df.empty:
                return pd.DataFrame()
                
            # Flatten MultiIndex columns if present (YF v0.2+)
            if isinstance(df.columns, pd.MultiIndex):
                # Try to extract just the ticker level if it exists, or just drop level
                df.columns = df.columns.droplevel(1) 
            
            df = df.reset_index()
            
            # Rename columns
            # YF: Date (or Datetime), Open, High, Low, Close, Adj Close, Volume
            col_map = {
                'Date': 'timestamp',
                'Datetime': 'timestamp',
                'Open': 'open',
                'High': 'high',
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume'
            }
            df = df.rename(columns=col_map)
            
            # Standardize
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # Filter columns
            req_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            df = df[[c for c in req_cols if c in df.columns]]
            
            # Sort and Slice
            df = df.sort_values('timestamp')
            if len(df) > limit:
                df = df.iloc[-limit:]
                
            return df.reset_index(drop=True)
            
        except Exception as e:
            print(f"Error fetching from YFinance: {e}")
            return pd.DataFrame()

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate the 6 technical indicators"""
        # Ensure we have enough data
        if len(df) < 50:
            return df

        close = df['close'].values
        high = df['high'].values
        low = df['low'].values

        # 1. RSI (14)
        df['RSI'] = talib.RSI(close, timeperiod=14)

        # 2. MACD (12, 26, 9)
        macd, signal, hist = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
        df['MACD'] = macd
        df['MACD_Signal_Line'] = signal
        df['MACD_Hist'] = hist

        # 3. ROC (10)
        df['ROC'] = talib.ROC(close, timeperiod=10)

        # 4. Stochastic (14, 3, 3)
        slowk, slowd = talib.STOCH(high, low, close, fastk_period=14, slowk_period=3, slowd_period=3)
        df['Stoch_K'] = slowk
        df['Stoch_D'] = slowd

        # 5. Williams %R (14)
        df['WillR'] = talib.WILLR(high, low, close, timeperiod=14)
        # Smooth WillR with EMA(6) to reduce noise
        df['WillR_EMA'] = talib.EMA(df['WillR'], timeperiod=6)

        # 6. EMA 200 (Trend Filter)
        df['EMA_200'] = talib.EMA(close, timeperiod=200)

        # 7. ADX (14)
        df['ADX'] = talib.ADX(high, low, close, timeperiod=14)

        return df

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate -1 (Sell), 0 (Neutral), 1 (Buy) signals"""
        
        # Initialize signal columns
        for ind in ['RSI', 'MACD', 'ROC', 'Stoch', 'WillR']:
            df[f'{ind}_Signal'] = 0

        # 1. RSI Logic
        # Buy < 30, Sell > 70
        df.loc[df['RSI'] < 30, 'RSI_Signal'] = 1
        df.loc[df['RSI'] > 70, 'RSI_Signal'] = -1

        # 2. MACD Logic
        # Buy: MACD > Signal (Crossover) - Simplified to just being above
        # Better logic: Crossover. But for vectorization, let's use:
        # Buy if MACD > Signal AND MACD.shift(1) < Signal.shift(1) (Golden Cross)
        # Sell if MACD < Signal AND MACD.shift(1) > Signal.shift(1) (Death Cross)
        # For simplicity in this "state" check, let's use the user's likely interpretation or standard trend following
        # Let's use the standard crossover logic for signals
        
        # Golden Cross
        df.loc[(df['MACD'] > df['MACD_Signal_Line']) & (df['MACD'].shift(1) <= df['MACD_Signal_Line'].shift(1)), 'MACD_Signal'] = 1
        # Death Cross
        df.loc[(df['MACD'] < df['MACD_Signal_Line']) & (df['MACD'].shift(1) >= df['MACD_Signal_Line'].shift(1)), 'MACD_Signal'] = -1

        # 3. ROC Logic
        # Buy > 0, Sell < 0 (Simple Momentum)
        # Or crossing 0
        df.loc[(df['ROC'] > 0) & (df['ROC'].shift(1) <= 0), 'ROC_Signal'] = 1
        df.loc[(df['ROC'] < 0) & (df['ROC'].shift(1) >= 0), 'ROC_Signal'] = -1

        # 4. Stochastic Logic
        # Buy: %K crosses above %D (Golden Cross) AND %K < 20 (Oversold)
        # Sell: %K crosses below %D (Death Cross) AND %K > 80 (Overbought)
        
        # Golden Cross in Oversold Zone
        df.loc[(df['Stoch_K'] > df['Stoch_D']) & 
               (df['Stoch_K'].shift(1) <= df['Stoch_D'].shift(1)) & 
               (df['Stoch_K'] < 20), 'Stoch_Signal'] = 1
               
        # Death Cross in Overbought Zone
        df.loc[(df['Stoch_K'] < df['Stoch_D']) & 
               (df['Stoch_K'].shift(1) >= df['Stoch_D'].shift(1)) & 
               (df['Stoch_K'] > 80), 'Stoch_Signal'] = -1

        # 5. Williams %R Logic (Smoothed)
        # Buy: Smoothed WillR crosses above -80 (Exit Oversold)
        # Sell: Smoothed WillR crosses below -20 (Exit Overbought)
        
        # Cross above -80
        df.loc[(df['WillR_EMA'] > -80) & (df['WillR_EMA'].shift(1) <= -80), 'WillR_Signal'] = 1
        
        # Cross below -20
        df.loc[(df['WillR_EMA'] < -20) & (df['WillR_EMA'].shift(1) >= -20), 'WillR_Signal'] = -1

        # ADX is a filter, usually doesn't generate directional signals alone.
        # We can use it to filter other signals (e.g., only trade if ADX > 25)
        # For this backtest, we'll treat it as a filter strength metric, or maybe skip it for direct signal generation
        # The user asked to backtest "these 6 indicators". Let's treat ADX as a trend strength confirmation?
        # Or maybe just skip ADX for "Win Rate" calculation as it's non-directional.
        # I will calculate it but not generate a directional signal for it in this basic version.

        return df

    def run_backtest(self, symbol: str = 'BTC/USDT', timeframe: str = '1h', horizon: int = 3, stop_loss: float = 0.02, take_profit: float = 0.04, limit: int = 1000, use_trend_filter: bool = False, trailing_stop: float = 0.0, adx_threshold: int = 0) -> Dict:
        """
        Run backtest to calculate win rate for each indicator.
        Horizon: Number of candles to look ahead (e.g., 3 candles).
        Win: Price at T+Horizon > Price at T (for Buy)
        Trend Filter: If True, only Buy when Price > EMA200, only Sell when Price < EMA200.
        Trailing Stop: If > 0, activates trailing stop logic.
        ADX Filter: If > 0, only trade when ADX > Threshold.
        """
        # Fetch extra data for indicator warmup (e.g. EMA 200 needs 200 candles)
        warmup = 200
        df = self.fetch_data(symbol, timeframe, limit=limit + warmup)
        
        if df.empty:
            return {"error": "No data fetched"}

        df = self.calculate_indicators(df)
        
        # Slice back to the requested limit
        if len(df) > limit:
            df = df.iloc[-limit:].reset_index(drop=True)

        df = self.generate_signals(df)

        # Calculate Future Returns
        # (Close[T+H] - Close[T]) / Close[T]
        df['Future_Ret'] = df['close'].shift(-horizon) - df['close']
        
        results = {}
        
        indicators = ['RSI', 'MACD', 'ROC', 'Stoch', 'WillR']
        
        for ind in indicators:
            sig_col = f'{ind}_Signal'
            
            # Initialize counters
            buy_wins = 0
            sell_wins = 0
            
            # Apply Trend Filter if enabled
            if use_trend_filter:
                # Filter Buy Signals: Must be above EMA 200
                df.loc[(df['close'] < df['EMA_200']) & (df[sig_col] == 1), sig_col] = 0
                
                # Filter Sell Signals: Must be below EMA 200
                df.loc[(df['close'] > df['EMA_200']) & (df[sig_col] == -1), sig_col] = 0
            
            # Apply ADX Filter if enabled
            if adx_threshold > 0:
                df.loc[(df['ADX'] < adx_threshold) & (df[sig_col] != 0), sig_col] = 0
            
            # Buy Signals
            buy_signals = df[df[sig_col] == 1]
            if len(buy_signals) > 0:
                # Win if Future_Ret > 0
                buy_wins = len(buy_signals[buy_signals['Future_Ret'] > 0])
                buy_win_rate = buy_wins / len(buy_signals)
            else:
                buy_win_rate = 0.0

            # Sell Signals
            sell_signals = df[df[sig_col] == -1]
            if len(sell_signals) > 0:
                # Win if Future_Ret < 0
                sell_wins = len(sell_signals[sell_signals['Future_Ret'] < 0])
                sell_win_rate = sell_wins / len(sell_signals)
            else:
                sell_win_rate = 0.0

            # Combined Win Rate (Weighted by number of trades)
            total_trades = len(buy_signals) + len(sell_signals)
            if total_trades > 0:
                total_win_rate = (buy_wins + sell_wins) / total_trades
            else:
                total_win_rate = 0.0

            # Calculate PnL (Total Return & Max Drawdown)
            df_pnl = self.calculate_pnl_curve(df, ind, horizon=horizon, stop_loss=stop_loss, take_profit=take_profit, trailing_stop=trailing_stop)
            final_equity = df_pnl['Equity'].iloc[-1]
            total_return = (final_equity - 1000) / 1000 * 100
            
            peak = df_pnl['Equity'].cummax()
            drawdown = (df_pnl['Equity'] - peak) / peak
            max_dd = drawdown.min() * 100

            results[ind] = {
                "Win Rate": round(total_win_rate * 100, 2),
                "Buy Signals": len(buy_signals),
                "Sell Signals": len(sell_signals),
                "Buy Win Rate": round(buy_win_rate * 100, 2),
                "Sell Win Rate": round(sell_win_rate * 100, 2),
                "Total Return": round(total_return, 2),
                "Max Drawdown": round(max_dd, 2),
                "Total Signals": len(buy_signals) + len(sell_signals)
            }

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "horizon": horizon,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "trailing_stop": trailing_stop,
            "adx_threshold": adx_threshold,
            "limit": limit,
            "use_trend_filter": use_trend_filter,
            "data_points": len(df),
            "results": results,
            "df": df  # Return the dataframe for visualization
        }

    def calculate_pnl_curve(self, df: pd.DataFrame, indicator: str, horizon: int = 3, initial_capital: float = 1000.0, fee_rate: float = 0.001, stop_loss: float = 0.02, take_profit: float = 0.04, trailing_stop: float = 0.0) -> pd.DataFrame:
        """
        Simulate a trade strategy: Enter on Signal, Exit after 'horizon' candles OR Stop Loss / Take Profit / Trailing Stop.
        Returns a DataFrame with 'Equity' curve.
        Includes Trading Fees (default 0.1% per trade).
        """
        df = df.copy()
        df['Equity'] = initial_capital
        capital = initial_capital
        position = 0 # 0: None, 1: Long, -1: Short
        entry_price = 0
        exit_index = -1
        
        # For Trailing Stop
        highest_high = 0
        lowest_low = 0
        
        sig_col = f'{indicator}_Signal'
        equity_curve = []
        
        # Simple loop simulation
        for i in range(len(df)):
            # Check for exit first (SL/TP/TS or Time-based)
            if position != 0:
                current_low = df['low'].iloc[i]
                current_high = df['high'].iloc[i]
                current_close = df['close'].iloc[i]
                
                # Update High/Low for Trailing Stop
                if position == 1:
                    highest_high = max(highest_high, current_high)
                elif position == -1:
                    lowest_low = min(lowest_low, current_low)
                
                exit_price = 0
                exit_reason = "" # 'SL', 'TP', 'TS', 'Time'
                
                # Check SL/TP/TS
                if position == 1: # Long
                    sl_price = entry_price * (1 - stop_loss)
                    tp_price = entry_price * (1 + take_profit)
                    ts_price = highest_high * (1 - trailing_stop)
                    
                    if stop_loss > 0 and current_low <= sl_price:
                        exit_price = sl_price
                        exit_reason = "SL"
                    elif trailing_stop > 0 and current_low <= ts_price:
                        exit_price = ts_price
                        exit_reason = "TS"
                    elif take_profit > 0 and current_high >= tp_price:
                        exit_price = tp_price
                        exit_reason = "TP"
                    elif i == exit_index:
                        exit_price = current_close
                        exit_reason = "Time"
                        
                elif position == -1: # Short
                    sl_price = entry_price * (1 + stop_loss)
                    tp_price = entry_price * (1 - take_profit)
                    ts_price = lowest_low * (1 + trailing_stop)
                    
                    if stop_loss > 0 and current_high >= sl_price:
                        exit_price = sl_price
                        exit_reason = "SL"
                    elif trailing_stop > 0 and current_high >= ts_price:
                        exit_price = ts_price
                        exit_reason = "TS"
                    elif take_profit > 0 and current_low <= tp_price:
                        exit_price = tp_price
                        exit_reason = "TP"
                    elif i == exit_index:
                        exit_price = current_close
                        exit_reason = "Time"
                
                # Execute Exit if triggered
                if exit_reason != "":
                    # Calculate Gross PnL
                    if position == 1:
                        gross_pnl = (exit_price - entry_price) / entry_price
                    else:
                        gross_pnl = (entry_price - exit_price) / entry_price
                    
                    capital *= (1 + gross_pnl) * ((1 - fee_rate) ** 2)
                    position = 0
            
            # Check for entry (if no position)
            if position == 0 and i < len(df) - horizon:
                signal = df[sig_col].iloc[i]
                if signal == 1: # Buy
                    position = 1
                    entry_price = df['close'].iloc[i]
                    highest_high = entry_price # Init for TS
                    exit_index = i + horizon
                elif signal == -1: # Sell
                    position = -1
                    entry_price = df['close'].iloc[i]
                    lowest_low = entry_price # Init for TS
                    exit_index = i + horizon
            
            equity_curve.append(capital)
            
        df['Equity'] = equity_curve
        return df

if __name__ == "__main__":
    # Test run
    engine = BacktestEngine()
    res = engine.run_backtest(symbol='BTC/USDT', timeframe='1h', horizon=3)
    import json
    print(json.dumps(res, indent=2))
